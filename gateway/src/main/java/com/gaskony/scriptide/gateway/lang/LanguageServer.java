package com.gaskony.scriptide.gateway.lang;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.inductiveautomation.ignition.common.script.ScriptManager;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Consumer;
import java.util.function.Supplier;

/**
 * A Language Server Protocol server, spoken over one WebSocket channel.
 *
 * <h2>Why real LSP rather than a bespoke API</h2>
 *
 * <p>Because everything downstream of the protocol then comes for free from a
 * maintained client: the completion popup and its filtering, the documentation
 * window, signature-help parameter highlighting, diagnostic rendering, and
 * go-to-definition navigation. A bespoke JSON API means reimplementing all of that
 * in the frontend and maintaining it forever.</p>
 *
 * <p>It also forces the details that are otherwise discovered late — UTF-16
 * positions, document versioning, and incremental sync — to be correct from the
 * start rather than retrofitted.</p>
 *
 * <h2>Transport</h2>
 *
 * <p>There is no {@code Content-Length} framing here. The client
 * ({@code @codemirror/lsp-client}) is transport-agnostic and exchanges whole
 * JSON-RPC messages, so each WebSocket text frame is exactly one message. The
 * framing that a stdio server needs is the transport's job, and the transport is
 * a WebSocket.</p>
 *
 * <p>P3 answers from the platform hint tree only. Project-library intelligence —
 * go-to-definition, references, symbols — arrives in P4 from the AST index, which
 * is also where library completions must come from: spike S1 measured that the
 * per-project hint tree does NOT contain them.</p>
 */
public final class LanguageServer {

    private static final Logger logger = LoggerFactory.getLogger(LanguageServer.class);

    /** Rebuild the hint index at most this often. */
    private static final long HINT_TTL_MILLIS = 60_000;

    private final Supplier<ScriptManager> scriptManagerSupplier;
    private final Map<String, TextDocument> documents = new ConcurrentHashMap<>();

    /** Project-library navigation. Null when the server has no project context. */
    private final ProjectIndex projectIndex;
    private final String project;

    /** Where server-initiated notifications (diagnostics) go. */
    private volatile Consumer<JsonObject> notifier = m -> { };

    private volatile HintIndex hintIndex;

    /**
     * The last outline that PARSED, per document.
     *
     * <p>A buffer is unparseable for most of the time someone is typing — an
     * unclosed bracket, a half-written def. Returning an empty outline for those
     * moments makes the outline panel flicker and empty on nearly every keystroke,
     * which is worse than slightly stale. Every real IDE keeps the last good one,
     * so this does too.</p>
     */
    private final Map<String, ModuleSymbols> lastGoodSymbols = new ConcurrentHashMap<>();

    public LanguageServer(Supplier<ScriptManager> scriptManagerSupplier) {
        this(scriptManagerSupplier, null, null);
    }

    public LanguageServer(Supplier<ScriptManager> scriptManagerSupplier,
                          ProjectIndex projectIndex, String project) {
        this.scriptManagerSupplier = scriptManagerSupplier;
        this.projectIndex = projectIndex;
        this.project = project;
    }

    /** Install the sink for server-initiated notifications. */
    public void setNotifier(Consumer<JsonObject> notifier) {
        this.notifier = notifier == null ? m -> { } : notifier;
    }

    /**
     * Handle one JSON-RPC message.
     *
     * @return the response to send back, or {@code null} for a notification
     *         (which by definition has no reply)
     */
    public JsonObject handle(JsonObject message) {
        String method = message.has("method") ? message.get("method").getAsString() : null;
        if (method == null) {
            return null;
        }
        boolean isRequest = message.has("id");
        JsonObject params = message.has("params") && message.get("params").isJsonObject()
            ? message.getAsJsonObject("params")
            : new JsonObject();

        try {
            JsonElement result = dispatch(method, params);
            if (!isRequest) {
                return null;
            }
            JsonObject response = new JsonObject();
            response.addProperty("jsonrpc", "2.0");
            response.add("id", message.get("id"));
            response.add("result", result == null ? com.google.gson.JsonNull.INSTANCE : result);
            return response;
        } catch (RuntimeException e) {
            logger.debug("LSP method {} failed: {}", method, e.toString());
            if (!isRequest) {
                return null;
            }
            JsonObject error = new JsonObject();
            // -32603 is the JSON-RPC "internal error" code.
            error.addProperty("code", -32603);
            error.addProperty("message", String.valueOf(e.getMessage()));
            JsonObject response = new JsonObject();
            response.addProperty("jsonrpc", "2.0");
            response.add("id", message.get("id"));
            response.add("error", error);
            return response;
        }
    }

    private JsonElement dispatch(String method, JsonObject params) {
        switch (method) {
            case "initialize":
                return initialize();
            case "initialized":
            case "shutdown":
            case "exit":
                return null;
            case "textDocument/didOpen":
                didOpen(params);
                publishDiagnostics(uriOf(params));
                return null;
            case "textDocument/didChange":
                didChange(params);
                publishDiagnostics(uriOf(params));
                return null;
            case "textDocument/didClose":
                documents.remove(uriOf(params));
                lastGoodSymbols.remove(uriOf(params));
                return null;
            case "textDocument/didSave":
                return null;
            case "textDocument/completion":
                return completion(params);
            case "completionItem/resolve":
                return resolveCompletion(params);
            case "textDocument/hover":
                return hover(params);
            case "textDocument/signatureHelp":
                return signatureHelp(params);
            case "textDocument/definition":
                return definition(params);
            case "textDocument/documentSymbol":
                return documentSymbol(params);
            case "workspace/symbol":
                return workspaceSymbol(params);
            case "scriptide/searchText":
                return searchText(params);
            default:
                // Unknown methods answer null rather than erroring: an LSP client
                // probes for optional capabilities, and a hard error on each one
                // fills the console with noise that looks like a fault.
                logger.debug("Unhandled LSP method: {}", method);
                return null;
        }
    }

    // ==================== lifecycle ====================

    private JsonElement initialize() {
        JsonObject completionProvider = new JsonObject();
        JsonArray triggers = new JsonArray();
        triggers.add(".");
        completionProvider.add("triggerCharacters", triggers);
        completionProvider.addProperty("resolveProvider", true);

        JsonObject signatureProvider = new JsonObject();
        JsonArray sigTriggers = new JsonArray();
        sigTriggers.add("(");
        sigTriggers.add(",");
        signatureProvider.add("triggerCharacters", sigTriggers);

        JsonObject capabilities = new JsonObject();
        // 2 = Incremental. Full sync would be simpler but re-sends the whole
        // document on every keystroke, which on a 5,000-line script is a lot of
        // JSON per character typed.
        capabilities.addProperty("textDocumentSync", 2);
        capabilities.add("completionProvider", completionProvider);
        capabilities.add("signatureHelpProvider", signatureProvider);
        capabilities.addProperty("hoverProvider", true);
        capabilities.addProperty("definitionProvider", true);
        capabilities.addProperty("documentSymbolProvider", true);
        capabilities.addProperty("workspaceSymbolProvider", true);

        JsonObject serverInfo = new JsonObject();
        serverInfo.addProperty("name", "Script IDE");

        JsonObject result = new JsonObject();
        result.add("capabilities", capabilities);
        result.add("serverInfo", serverInfo);
        return result;
    }

    private void didOpen(JsonObject params) {
        JsonObject doc = params.getAsJsonObject("textDocument");
        String uri = doc.get("uri").getAsString();
        String text = doc.has("text") ? doc.get("text").getAsString() : "";
        int version = doc.has("version") ? doc.get("version").getAsInt() : 0;
        TextDocument document = new TextDocument(uri, text, version);
        documents.put(uri, document);
        // Seed the outline cache, so the first request after opening a file that is
        // momentarily unparseable still has something to show.
        symbolsFor(uri, document);
    }

    private void didChange(JsonObject params) {
        String uri = uriOf(params);
        TextDocument document = documents.get(uri);
        if (document == null) {
            return;
        }
        JsonObject doc = params.getAsJsonObject("textDocument");
        if (doc.has("version")) {
            document.setVersion(doc.get("version").getAsInt());
        }
        for (JsonElement element : params.getAsJsonArray("contentChanges")) {
            JsonObject change = element.getAsJsonObject();
            String text = change.get("text").getAsString();
            if (!change.has("range")) {
                document.setText(text);   // the client chose full replacement
                continue;
            }
            JsonObject range = change.getAsJsonObject("range");
            JsonObject start = range.getAsJsonObject("start");
            JsonObject end = range.getAsJsonObject("end");
            document.applyChange(
                start.get("line").getAsInt(), start.get("character").getAsInt(),
                end.get("line").getAsInt(), end.get("character").getAsInt(), text);
        }
    }

    // ==================== features ====================

    private JsonElement completion(JsonObject params) {
        TextDocument document = documents.get(uriOf(params));
        if (document == null) {
            return emptyCompletionList();
        }
        JsonObject position = params.getAsJsonObject("position");
        int line = position.get("line").getAsInt();
        int character = position.get("character").getAsInt();

        String prefix = document.dottedPrefixAt(line, character);
        // A prefix that STARTS with a dot means the thing before it is an expression
        // we cannot resolve statically - a string literal, a call result, a
        // subscript. Offering root-level names there would suggest `system` as a
        // member of `'abc'.`, which is worse than offering nothing.
        if (prefix.startsWith(".")) {
            return emptyCompletionList();
        }
        int lastDot = prefix.lastIndexOf('.');
        String base = lastDot < 0 ? "" : prefix.substring(0, lastDot);
        String partial = lastDot < 0 ? prefix : prefix.substring(lastDot + 1);

        List<HintIndex.Entry> candidates = index().childrenOf(base);
        JsonArray items = new JsonArray();
        for (HintIndex.Entry entry : candidates) {
            if (!partial.isEmpty()
                && !entry.name().regionMatches(true, 0, partial, 0, partial.length())) {
                continue;
            }
            items.add(completionItem(entry));
        }

        JsonObject list = new JsonObject();
        // isIncomplete=false: the whole candidate set for this prefix is here, so the
        // client may filter locally as the user keeps typing instead of round-tripping.
        list.addProperty("isIncomplete", false);
        list.add("items", items);
        return list;
    }

    private JsonObject completionItem(HintIndex.Entry entry) {
        JsonObject item = new JsonObject();
        item.addProperty("label", entry.name());
        item.addProperty("kind", lspKind(entry.kind()));
        if (entry.detail() != null) {
            item.addProperty("detail", entry.detail());
        }
        if (entry.deprecated()) {
            JsonArray tags = new JsonArray();
            tags.add(1);   // CompletionItemTag.Deprecated
            item.add("tags", tags);
        }
        // The dotted path round-trips through resolve, so the doc window can be
        // filled in on demand rather than sending every docstring up front.
        JsonObject data = new JsonObject();
        data.addProperty("dottedPath", entry.dottedPath());
        item.add("data", data);
        return item;
    }

    private JsonElement resolveCompletion(JsonObject params) {
        JsonObject item = params.deepCopy();
        if (!item.has("data") || !item.get("data").isJsonObject()) {
            return item;
        }
        String dotted = item.getAsJsonObject("data").get("dottedPath").getAsString();
        index().resolve(dotted).ifPresent(entry -> {
            String docs = markdownFor(entry);
            if (!docs.isEmpty()) {
                JsonObject documentation = new JsonObject();
                documentation.addProperty("kind", "markdown");
                documentation.addProperty("value", docs);
                item.add("documentation", documentation);
            }
        });
        return item;
    }

    private JsonElement hover(JsonObject params) {
        TextDocument document = documents.get(uriOf(params));
        if (document == null) {
            return null;
        }
        JsonObject position = params.getAsJsonObject("position");
        String dotted = fullDottedNameAt(document,
            position.get("line").getAsInt(), position.get("character").getAsInt());
        if (dotted.isEmpty()) {
            return null;
        }
        return index().resolve(dotted).map(entry -> {
            String markdown = markdownFor(entry);
            if (markdown.isEmpty()) {
                return null;
            }
            JsonObject contents = new JsonObject();
            contents.addProperty("kind", "markdown");
            contents.addProperty("value", markdown);
            JsonObject result = new JsonObject();
            result.add("contents", contents);
            return (JsonElement) result;
        }).orElse(null);
    }

    private JsonElement signatureHelp(JsonObject params) {
        TextDocument document = documents.get(uriOf(params));
        if (document == null) {
            return null;
        }
        JsonObject position = params.getAsJsonObject("position");
        int line = position.get("line").getAsInt();
        int character = position.get("character").getAsInt();
        String lineText = document.lineText(line);
        int cursor = Math.min(Math.max(0, character), lineText.length());

        int open = openCallParen(lineText, cursor);
        if (open < 0) {
            return null;
        }
        String callee = document.dottedPrefixAt(line, open);
        if (callee.isEmpty()) {
            return null;
        }
        return index().resolve(callee).map(entry -> {
            if (entry.kind() != HintIndex.Kind.FUNCTION) {
                return null;
            }
            JsonArray parameters = new JsonArray();
            for (HintIndex.Param p : entry.params()) {
                JsonObject param = new JsonObject();
                param.addProperty("label", p.optional() ? "[" + p.name() + "]" : p.name());
                if (p.documentation() != null) {
                    param.addProperty("documentation", p.documentation());
                }
                parameters.add(param);
            }
            JsonObject signature = new JsonObject();
            signature.addProperty("label", entry.detail() == null
                ? HintIndex.signature(entry.name(), entry.params())
                : entry.detail());
            if (entry.documentation() != null) {
                signature.addProperty("documentation", entry.documentation());
            }
            signature.add("parameters", parameters);

            JsonArray signatures = new JsonArray();
            signatures.add(signature);
            JsonObject result = new JsonObject();
            result.add("signatures", signatures);
            result.addProperty("activeSignature", 0);
            result.addProperty("activeParameter",
                Math.min(countArgumentsBefore(lineText, open, cursor),
                    Math.max(0, entry.params().size() - 1)));
            return (JsonElement) result;
        }).orElse(null);
    }


    /**
     * Go to the definition of the dotted name under the cursor.
     *
     * <p>Only project-library symbols resolve: a platform function like
     * {@code system.tag.readBlocking} has no source file on this gateway to jump
     * to, so it answers null and hover carries the documentation instead.</p>
     */
    private JsonElement definition(JsonObject params) {
        if (projectIndex == null || project == null) {
            return null;
        }
        TextDocument document = documents.get(uriOf(params));
        if (document == null) {
            return null;
        }
        JsonObject position = params.getAsJsonObject("position");
        String dotted = fullDottedNameAt(document,
            position.get("line").getAsInt(), position.get("character").getAsInt());
        if (dotted.isEmpty()) {
            return null;
        }
        // An unqualified name may be a local import alias; resolve it through the
        // module's own import bindings before giving up.
        String resolved = resolveThroughImports(document, dotted);
        return projectIndex.resolve(project, resolved)
            .map(def -> (JsonElement) locationOf(def))
            .orElse(null);
    }

    /**
     * Rewrite a name through the current module's imports.
     *
     * <p>{@code from util import helper} then {@code helper(...)} must resolve to
     * {@code util.helper}, and {@code import x.y as z} then {@code z.f} to
     * {@code x.y.f}. Without this, go-to-definition only works for names already
     * written in full, which is almost never how anyone writes code.</p>
     */
    private String resolveThroughImports(TextDocument document, String dotted) {
        ModuleSymbols symbols = ModuleSymbols.parse("<buffer>", document.text());
        int dot = dotted.indexOf('.');
        String head = dot < 0 ? dotted : dotted.substring(0, dot);
        String tail = dot < 0 ? "" : dotted.substring(dot);
        for (ModuleSymbols.ImportBinding binding : symbols.imports()) {
            if (!binding.boundName().equals(head)) {
                continue;
            }
            if (binding.targetMember() != null) {
                return binding.targetModule() + "." + binding.targetMember() + tail;
            }
            return binding.targetModule() + tail;
        }
        return dotted;
    }

    private JsonObject locationOf(ProjectIndex.Definition def) {
        JsonObject start = new JsonObject();
        start.addProperty("line", def.line());
        start.addProperty("character", def.column());
        JsonObject range = new JsonObject();
        range.add("start", start);
        range.add("end", start.deepCopy());
        JsonObject location = new JsonObject();
        location.addProperty("uri", "ignition://" + project + "/ignition/script-python/"
            + def.moduleName().replace('.', '/'));
        location.add("range", range);
        return location;
    }

    /** Outline of the OPEN buffer — not the saved resource, which may be stale. */
    private JsonElement documentSymbol(JsonObject params) {
        String uri = uriOf(params);
        TextDocument document = documents.get(uri);
        if (document == null) {
            return new JsonArray();
        }
        ModuleSymbols symbols = symbolsFor(uri, document);
        JsonArray out = new JsonArray();
        for (ModuleSymbols.Symbol symbol : symbols.symbols()) {
            JsonObject item = new JsonObject();
            item.addProperty("name", symbol.name());
            item.addProperty("kind", lspSymbolKind(symbol.kind()));
            if (symbol.container() != null) {
                item.addProperty("containerName", symbol.container());
            }
            JsonObject start = new JsonObject();
            start.addProperty("line", symbol.line());
            start.addProperty("character", symbol.column());
            JsonObject range = new JsonObject();
            range.add("start", start);
            range.add("end", start.deepCopy());
            JsonObject location = new JsonObject();
            location.addProperty("uri", document.uri());
            location.add("range", range);
            item.add("location", location);
            out.add(item);
        }
        return out;
    }

    /** Project-wide symbol search, for quick-open. */
    private JsonElement workspaceSymbol(JsonObject params) {
        JsonArray out = new JsonArray();
        if (projectIndex == null || project == null) {
            return out;
        }
        String query = params.has("query") ? params.get("query").getAsString() : "";
        for (ProjectIndex.SymbolHit hit : projectIndex.search(project, query, 200)) {
            JsonObject item = new JsonObject();
            item.addProperty("name", hit.symbol().name());
            item.addProperty("kind", lspSymbolKind(hit.symbol().kind()));
            item.addProperty("containerName", hit.moduleName());
            JsonObject start = new JsonObject();
            start.addProperty("line", hit.symbol().line());
            start.addProperty("character", hit.symbol().column());
            JsonObject range = new JsonObject();
            range.add("start", start);
            range.add("end", start.deepCopy());
            JsonObject location = new JsonObject();
            location.addProperty("uri", "ignition://" + project + "/ignition/script-python/"
                + hit.moduleName().replace('.', '/'));
            location.add("range", range);
            item.add("location", location);
            out.add(item);
        }
        return out;
    }

    /**
     * Publish diagnostics for one document.
     *
     * <p>P5 ships ONE check: the syntax error from the real Jython 2.7 parser.
     * That is deliberate. A false positive costs more trust than ten missed
     * problems, and the client-side grammar is Python 3 — so nothing but the real
     * parser is allowed to say a line is wrong. Jython reports only the first error
     * per parse, which matches the Designer's single squiggle.</p>
     */
    private void publishDiagnostics(String uri) {
        TextDocument document = documents.get(uri);
        if (document == null) {
            return;
        }
        JsonArray diagnostics = new JsonArray();
        ModuleSymbols symbols = ModuleSymbols.parse("<buffer>", document.text());
        symbols.syntaxError().ifPresent(message -> {
            JsonObject start = new JsonObject();
            start.addProperty("line", symbols.errorLine());
            start.addProperty("character", symbols.errorColumn());
            JsonObject end = new JsonObject();
            end.addProperty("line", symbols.errorLine());
            // Extend to the end of the line: a zero-width squiggle is invisible.
            end.addProperty("character",
                Math.max(symbols.errorColumn() + 1,
                    document.lineText(symbols.errorLine()).length()));
            JsonObject range = new JsonObject();
            range.add("start", start);
            range.add("end", end);
            JsonObject diagnostic = new JsonObject();
            diagnostic.add("range", range);
            diagnostic.addProperty("severity", 1);   // Error
            diagnostic.addProperty("source", "jython");
            diagnostic.addProperty("message", message);
            diagnostics.add(diagnostic);
        });

        JsonObject params = new JsonObject();
        params.addProperty("uri", uri);
        // Version-tagged so a client can drop a payload older than its buffer.
        params.addProperty("version", document.version());
        params.add("diagnostics", diagnostics);
        JsonObject notification = new JsonObject();
        notification.addProperty("jsonrpc", "2.0");
        notification.addProperty("method", "textDocument/publishDiagnostics");
        notification.add("params", params);
        notifier.accept(notification);
    }

    /**
     * Cross-file text search — a custom method, namespaced as LSP requires.
     *
     * <p>Custom rather than shoehorned into {@code workspace/symbol}: that method
     * searches SYMBOL names, and a user looking for a string literal or a comment
     * would get nothing back with no indication why.</p>
     */
    private JsonElement searchText(JsonObject params) {
        JsonArray out = new JsonArray();
        if (projectIndex == null || project == null) {
            return out;
        }
        String query = params.has("query") ? params.get("query").getAsString() : "";
        boolean caseSensitive = params.has("caseSensitive")
            && params.get("caseSensitive").getAsBoolean();
        for (ProjectIndex.TextHit hit
            : projectIndex.searchText(project, query, caseSensitive, 500)) {
            JsonObject item = new JsonObject();
            item.addProperty("module", hit.moduleName());
            item.addProperty("line", hit.line());
            item.addProperty("character", hit.column());
            item.addProperty("text", hit.lineText());
            item.addProperty("uri", "ignition://" + project + "/ignition/script-python/"
                + hit.moduleName().replace('.', '/'));
            out.add(item);
        }
        return out;
    }

    /**
     * Parse a buffer, falling back to the last outline that parsed.
     *
     * <p>Only the OUTLINE falls back. Diagnostics deliberately do not: a stale
     * "no errors" would hide the error the user just introduced, which is the exact
     * moment they need to see it.</p>
     */
    private ModuleSymbols symbolsFor(String uri, TextDocument document) {
        ModuleSymbols parsed = ModuleSymbols.parse("<buffer>", document.text());
        if (parsed.syntaxError().isEmpty()) {
            lastGoodSymbols.put(uri, parsed);
            return parsed;
        }
        return lastGoodSymbols.getOrDefault(uri, parsed);
    }

    private static int lspSymbolKind(ModuleSymbols.SymbolKind kind) {
        // LSP SymbolKind: Class=5, Method=6, Function=12, Variable=13.
        return switch (kind) {
            case CLASS -> 5;
            case METHOD -> 6;
            case FUNCTION -> 12;
            case VARIABLE -> 13;
        };
    }

    // ==================== helpers ====================

    /**
     * The whole dotted name under the cursor, not just the part before it.
     *
     * <p>Hover needs the complete name — a cursor in the middle of
     * {@code readBlocking} must resolve the whole function, not {@code readBlo}.</p>
     */
    static String fullDottedNameAt(TextDocument document, int line, int character) {
        String lineText = document.lineText(line);
        int end = Math.min(Math.max(0, character), lineText.length());
        while (end < lineText.length()) {
            char c = lineText.charAt(end);
            if (Character.isLetterOrDigit(c) || c == '_') {
                end++;
            } else {
                break;
            }
        }
        return document.dottedPrefixAt(line, end);
    }

    /**
     * Index of the '(' of the call the cursor sits inside, or -1.
     *
     * <p>Scans backwards tracking nesting depth, so an argument that is itself a
     * call — {@code foo(bar(1), |} — reports {@code foo}, not {@code bar}.</p>
     */
    static int openCallParen(String lineText, int cursor) {
        int depth = 0;
        for (int i = Math.min(cursor, lineText.length()) - 1; i >= 0; i--) {
            char c = lineText.charAt(i);
            if (c == ')') {
                depth++;
            } else if (c == '(') {
                if (depth == 0) {
                    return i;
                }
                depth--;
            }
        }
        return -1;
    }

    /** How many commas separate the open paren from the cursor, at depth zero. */
    static int countArgumentsBefore(String lineText, int openParen, int cursor) {
        int count = 0;
        int depth = 0;
        for (int i = openParen + 1; i < Math.min(cursor, lineText.length()); i++) {
            char c = lineText.charAt(i);
            if (c == '(' || c == '[' || c == '{') {
                depth++;
            } else if (c == ')' || c == ']' || c == '}') {
                depth--;
            } else if (c == ',' && depth == 0) {
                count++;
            }
        }
        return count;
    }

    static String markdownFor(HintIndex.Entry entry) {
        StringBuilder sb = new StringBuilder();
        if (entry.detail() != null) {
            sb.append("```python\n").append(entry.detail()).append("\n```\n\n");
        }
        if (entry.deprecated()) {
            sb.append("**Deprecated.**\n\n");
        }
        if (entry.documentation() != null && !entry.documentation().isBlank()) {
            sb.append(entry.documentation()).append("\n\n");
        }
        if (!entry.params().isEmpty()) {
            sb.append("**Parameters**\n\n");
            for (HintIndex.Param p : entry.params()) {
                sb.append("- `").append(p.name()).append('`');
                if (p.optional()) {
                    sb.append(" *(optional")
                        .append(p.defaultValue() == null ? "" : ", default `" + p.defaultValue() + "`")
                        .append(")*");
                }
                if (p.documentation() != null && !p.documentation().isBlank()) {
                    sb.append(" — ").append(p.documentation());
                }
                sb.append('\n');
            }
            sb.append('\n');
        }
        if (entry.returnType() != null && !entry.returnType().isBlank()) {
            sb.append("**Returns** ").append(entry.returnType()).append('\n');
        }
        return sb.toString().trim();
    }

    private static int lspKind(HintIndex.Kind kind) {
        // LSP CompletionItemKind: Method=2, Function=3, Module=9, Property=10.
        return switch (kind) {
            case MODULE -> 9;
            case FUNCTION -> 3;
            case PROPERTY -> 10;
        };
    }

    private static String uriOf(JsonObject params) {
        return params.getAsJsonObject("textDocument").get("uri").getAsString();
    }

    private static JsonObject emptyCompletionList() {
        JsonObject list = new JsonObject();
        list.addProperty("isIncomplete", false);
        list.add("items", new JsonArray());
        return list;
    }

    /**
     * The hint index, rebuilt on a TTL.
     *
     * <p>A TTL rather than an event subscription because the SDK exposes no
     * listener for module install or removal — so there is nothing to subscribe to
     * for the case that actually changes this tree. Rebuilding a few-hundred-node
     * tree once a minute is cheap, and the alternative is a stale API list after
     * someone installs a module. Do not "improve" this into an event listener
     * without first finding an event that exists.</p>
     */
    private HintIndex index() {
        HintIndex current = hintIndex;
        if (current != null
            && System.currentTimeMillis() - current.builtAtMillis() < HINT_TTL_MILLIS) {
            return current;
        }
        HintIndex rebuilt = HintIndex.build(scriptManagerSupplier);
        hintIndex = rebuilt;
        return rebuilt;
    }

    /** Number of open documents — for diagnostics and tests. */
    public int openDocumentCount() {
        return documents.size();
    }
}
