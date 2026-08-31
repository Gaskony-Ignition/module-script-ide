package com.gaskony.scriptide.gateway.ws;

import com.gaskony.scriptide.gateway.exec.ExecAudit;
import com.gaskony.scriptide.gateway.exec.ExecPolicy;
import com.gaskony.scriptide.gateway.exec.ExecutionService;
import com.gaskony.scriptide.gateway.exec.PrivateStateRunner;
import com.gaskony.scriptide.gateway.exec.TracebackFormatter;
import com.gaskony.scriptide.gateway.lang.LanguageServer;
import com.gaskony.scriptide.gateway.lang.ProjectIndex;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.python.core.PyObject;
import org.eclipse.jetty.websocket.api.Callback;
import org.eclipse.jetty.websocket.api.Session;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * One authenticated browser connection.
 *
 * <p>At P0 this carries a single {@code ping}/{@code pong} exchange, which exists
 * for one reason: to prove that {@code addServlet(SOCKET_SERVLET_PATH, ...)}
 * actually resolves to {@code /system/scriptide} for a NEW module alias. Spike S1
 * answered every other question about this design but could not answer that one
 * without a built module, so it is the last unverified assumption and the deploy
 * gate checks it on every deploy.</p>
 *
 * <p>From P3 this becomes the LSP + execution transport, with a
 * {@code {"ch":"lsp"|"exec","msg":…}} envelope: one authentication handshake, and
 * per-message authorisation — {@code lsp} for any authenticated user,
 * {@code exec} for Administrators only. The channel shape is already honoured
 * here so the wire format does not change under the client later.</p>
 */
public class ScriptIdeSocket implements Session.Listener.AutoDemanding {

    private static final Logger logger = LoggerFactory.getLogger(ScriptIdeSocket.class);

    private final String username;
    private final boolean administrator;
    private final String csrfToken;
    private final String remoteHost;

    /** Stable id for this connection — the per-session execution limit keys on it. */
    private final String sessionId = java.util.UUID.randomUUID().toString();

    private volatile Session session;

    /**
     * Console REPL state, per project.
     *
     * <p>Kept so the console behaves like a REPL: a name bound in one submission is
     * still there in the next. Scoped to THIS socket and never shared — two people
     * at two browsers must not see each other's variables. Dropped on close.</p>
     */
    private final java.util.Map<String, PyObject> consoleLocals =
        new java.util.concurrent.ConcurrentHashMap<>();

    /** Whether this connection has presented its CSRF token on the exec channel. */
    private volatile boolean execUnlocked;

    /**
     * One language server per connection.
     *
     * <p>Per-connection, not shared: the server owns the open-document set, and two
     * browsers editing different files must not see each other's buffers. The
     * expensive part — the hint index — is rebuilt from the gateway and is cheap
     * enough to hold per socket.</p>
     */
    private volatile LanguageServer languageServer;
    private volatile String lspProject;

    public ScriptIdeSocket(String username, boolean administrator,
                           String csrfToken, String remoteHost) {
        this.username = username;
        this.administrator = administrator;
        this.csrfToken = csrfToken;
        this.remoteHost = remoteHost;
    }

    /** The authenticated user behind this socket. Never trusted from the client. */
    public String getUsername() {
        return username;
    }

    /** Whether this connection may use the {@code exec} channel (P2 onward). */
    public boolean isAdministrator() {
        return administrator;
    }

    @Override
    public void onWebSocketOpen(Session session) {
        this.session = session;
        ScriptIdeSocketRegistry.register(this);
        logger.debug("Script IDE socket opened for user '{}' (admin={})", username, administrator);
    }

    @Override
    public void onWebSocketText(String message) {
        JsonObject envelope;
        String channel;
        try {
            envelope = JsonParser.parseString(message).getAsJsonObject();
            channel = envelope.has("ch") ? envelope.get("ch").getAsString() : "";
        } catch (RuntimeException e) {
            // Malformed input from a client is expected traffic, not an incident.
            send("{\"ch\":\"error\",\"msg\":{\"error\":\"malformed envelope\"}}");
            return;
        }

        if ("ping".equals(channel)) {
            // P0 liveness probe. Echoes the authenticated identity so the deploy
            // gate proves the whole path — upgrade, auth, and round trip.
            JsonObject msg = new JsonObject();
            msg.addProperty("pong", true);
            msg.addProperty("username", username);
            msg.addProperty("administrator", administrator);
            JsonObject reply = new JsonObject();
            reply.addProperty("ch", "ping");
            reply.add("msg", msg);
            send(reply.toString());
            return;
        }

        if ("lsp".equals(channel)) {
            try {
                handleLsp(envelope.getAsJsonObject("msg"),
                    envelope.has("project") ? envelope.get("project").getAsString() : null);
            } catch (RuntimeException e) {
                logger.debug("lsp frame failed for '{}': {}", username, e.toString());
            }
            return;
        }

        if ("exec".equals(channel)) {
            try {
                handleExec(envelope.getAsJsonObject("msg"));
            } catch (RuntimeException e) {
                logger.debug("exec frame failed for '{}': {}", username, e.toString());
                sendError("exec", "Execution request failed: " + e.getMessage());
            }
            return;
        }

        // "lsp" arrives in P3.
        sendError("error", "unknown channel: " + channel);
    }

    /**
     * Handle one JSON-RPC frame on the language channel.
     *
     * <p>Requires authentication (guaranteed by the handshake) but NOT the
     * Administrator role: a read-only user should still get completions, hover and
     * signature help. Only running code is privileged.</p>
     */
    private void handleLsp(JsonObject msg, String project) {
        if (msg == null) {
            return;
        }
        LanguageServer server = languageServerFor(project);
        if (server == null) {
            sendError("lsp", "The module is shutting down.");
            return;
        }
        JsonObject response = server.handle(msg);
        if (response != null) {
            sendOn("lsp", response);
        }
    }

    /** The server for a project, rebuilt if the client switches projects. */
    private LanguageServer languageServerFor(String project) {
        if (ScriptIdeSocketRegistry.getContext() == null) {
            return null;
        }
        String target = (project == null || project.isBlank()) ? "" : project;
        LanguageServer existing = languageServer;
        if (existing != null && target.equals(lspProject)) {
            return existing;
        }
        synchronized (this) {
            if (languageServer == null || !target.equals(lspProject)) {
                // A supplier, not a resolved manager: the project's ScriptManager is
                // replaced when its library is rebuilt, and a captured one would
                // serve a stale API list for the life of the connection.
                var context = ScriptIdeSocketRegistry.getContext();
                ProjectIndex index = target.isEmpty()
                    ? null : new ProjectIndex(context.getProjectManager());
                LanguageServer server = new LanguageServer(() -> {
                    var ctx = ScriptIdeSocketRegistry.getContext();
                    if (ctx == null) {
                        return null;
                    }
                    return target.isEmpty()
                        ? ctx.getScriptManager()
                        : ctx.getProjectManager().getProjectScriptManager(target);
                }, index, target.isEmpty() ? null : target);
                // Diagnostics are server-initiated, so the server needs a way to
                // push a frame rather than only answering requests.
                server.setNotifier(notification -> sendOn("lsp", notification));
                languageServer = server;
                lspProject = target;
            }
            return languageServer;
        }
    }

    /**
     * Handle one frame on the execution channel.
     *
     * <p>Every gate is re-checked HERE, per frame, not once at connect: the policy
     * properties are read live so an operator can disable execution on a running
     * gateway, and a socket opened while execution was enabled must not keep the
     * privilege afterwards.</p>
     */
    private void handleExec(JsonObject msg) {
        if (msg == null) {
            sendError("exec", "Missing message body");
            return;
        }
        String action = msg.has("action") ? msg.get("action").getAsString() : "run";

        if (!ExecPolicy.executionEnabled()) {
            sendError("exec", "Script execution is disabled on this gateway ("
                + ExecPolicy.PROP_ENABLED + "=false).");
            return;
        }
        if (ExecPolicy.requireAdmin() && !administrator) {
            sendError("exec", "Running scripts requires the Administrator role.");
            return;
        }

        // WebSockets get no CORS preflight, so the same-origin check at handshake is
        // belt; this token is braces. Required once per connection, before anything
        // is executed.
        if (!execUnlocked) {
            String presented = msg.has("csrfToken") ? msg.get("csrfToken").getAsString() : null;
            if (csrfToken == null || presented == null || !csrfToken.equals(presented)) {
                sendError("exec", "CSRF token missing or invalid.");
                return;
            }
            execUnlocked = true;
        }

        ExecutionService service = ScriptIdeSocketRegistry.getExecutionService();
        if (service == null) {
            sendError("exec", "The module is shutting down.");
            return;
        }

        if ("stop".equals(action)) {
            String id = msg.has("executionId") ? msg.get("executionId").getAsString() : null;
            if (id == null) {
                sendError("exec", "stop requires an executionId");
                return;
            }
            JsonObject out = new JsonObject();
            out.addProperty("event", "stopping");
            out.addProperty("executionId", id);
            out.addProperty("detail", service.requestStop(id));
            sendOn("exec", out);
            return;
        }

        if (!"run".equals(action)) {
            sendError("exec", "unknown exec action: " + action);
            return;
        }

        String project = msg.has("project") ? msg.get("project").getAsString() : null;
        String source = msg.has("source") ? msg.get("source").getAsString() : null;
        if (project == null || project.isBlank() || source == null) {
            sendError("exec", "run requires 'project' and 'source'");
            return;
        }
        // A selection run prepends blank lines so traceback line numbers still match
        // the editor. The client says how many it added; we subtract them back off.
        int lineOffset = msg.has("lineOffset") ? msg.get("lineOffset").getAsInt() : 0;
        String target = msg.has("target") ? msg.get("target").getAsString() : "console";
        boolean isConsole = !msg.has("target");
        String executionId = java.util.UUID.randomUUID().toString();

        ExecAudit audit = ScriptIdeSocketRegistry.getExecAudit();
        if (audit != null) {
            // Before the run, so a script that hangs is still recorded.
            audit.record(username, remoteHost, project, target, source);
        }

        String fileName = "<script-ide:" + project + ":" + target + ">";
        JsonObject started = new JsonObject();
        started.addProperty("event", "started");
        started.addProperty("executionId", executionId);
        sendOn("exec", started);

        // A console keeps its locals so it behaves like a REPL; a file does not —
        // a file is not a REPL, and carrying state between runs of one would make
        // results depend on invisible history.
        PyObject locals = isConsole
            ? consoleLocals.computeIfAbsent(project, service::newLocals)
            : service.newLocals(project);

        PrivateStateRunner.Outcome outcome;
        try {
            outcome = service.execute(executionId, project, source, fileName, locals,
                username, sessionId);
        } catch (ExecutionService.RejectedException e) {
            sendError("exec", e.getMessage());
            return;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            sendError("exec", "Execution was interrupted.");
            return;
        }

        JsonObject result = new JsonObject();
        result.addProperty("event", "finished");
        result.addProperty("executionId", executionId);
        result.addProperty("stdout", outcome.stdout());
        result.addProperty("stderr", outcome.stderr());
        result.addProperty("truncated", outcome.truncated());
        result.addProperty("cancelled", outcome.cancelled());
        result.addProperty("ok", outcome.succeeded());
        if (outcome.failure() != null && !outcome.cancelled()) {
            result.add("error", TracebackFormatter.describe(
                outcome.failure(), fileName, lineOffset));
        }
        sendOn("exec", result);
    }

    /** Send one message on a channel. */
    private void sendOn(String channel, JsonObject msg) {
        JsonObject envelope = new JsonObject();
        envelope.addProperty("ch", channel);
        envelope.add("msg", msg);
        send(envelope.toString());
    }

    private void sendError(String channel, String message) {
        JsonObject msg = new JsonObject();
        msg.addProperty("error", message);
        sendOn(channel, msg);
    }

    @Override
    public void onWebSocketClose(int statusCode, String reason) {
        // Drop the REPL state with the connection — it is per-user and must not
        // outlive the socket that owns it.
        consoleLocals.clear();
        ScriptIdeSocketRegistry.unregister(this);
        logger.debug("Script IDE socket closed for '{}' ({}: {})", username, statusCode, reason);
    }

    @Override
    public void onWebSocketError(Throwable cause) {
        // Debug, not error: a browser tab closing mid-frame is routine.
        logger.debug("Script IDE socket error for '{}': {}", username, cause.toString());
        ScriptIdeSocketRegistry.unregister(this);
    }

    /** Send a text frame, swallowing send failures on a dead connection. */
    protected void send(String text) {
        Session current = this.session;
        if (current == null || !current.isOpen()) {
            return;
        }
        try {
            current.sendText(text, Callback.NOOP);
        } catch (RuntimeException e) {
            logger.debug("Failed to send on Script IDE socket for '{}': {}", username, e.getMessage());
        }
    }

    /** Close this socket because the module is shutting down. */
    void closeForShutdown() {
        Session current = this.session;
        if (current != null && current.isOpen()) {
            current.close(1001 /* going away */, "Script IDE module shutting down", Callback.NOOP);
        }
    }
}
