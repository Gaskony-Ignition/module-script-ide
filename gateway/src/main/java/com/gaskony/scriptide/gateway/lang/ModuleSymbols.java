package com.gaskony.scriptide.gateway.lang;

import org.python.antlr.ParseException;
import org.python.antlr.ast.Assign;
import org.python.antlr.ast.ClassDef;
import org.python.antlr.ast.FunctionDef;
import org.python.antlr.ast.Import;
import org.python.antlr.ast.ImportFrom;
import org.python.antlr.ast.Module;
import org.python.antlr.ast.Name;
import org.python.antlr.ast.Str;
import org.python.antlr.ast.alias;
import org.python.antlr.base.expr;
import org.python.antlr.base.mod;
import org.python.antlr.base.stmt;
import org.python.core.CompilerFlags;
import org.python.core.ParserFacade;
import org.python.core.PyException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * The symbols one project-library module defines, extracted from a real Jython
 * 2.7 parse.
 *
 * <h2>Why the platform's own parser</h2>
 *
 * <p>Spike S1 measured that {@code ParserFacade} accepts every Python-2-only form
 * that appears in real Ignition code — {@code print "x"}, {@code except E, e:},
 * {@code 10L}, backticks, {@code exec}, {@code 0777}, {@code <>},
 * {@code raise E, "msg"} — because it IS the interpreter's parser. No third-party
 * Python parser still handles those: jedi dropped Python 2 in 2020 and nothing
 * maintained replaced it. Using Jython's own parser is not a compromise, it is the
 * only correct option, and it costs nothing because Jython is already loaded.</p>
 *
 * <h2>Positions</h2>
 *
 * <p>The AST reports 1-based lines and 0-based columns. LSP wants both 0-based, so
 * lines are converted on the way out. Getting this wrong shifts every
 * go-to-definition by one line, which looks like an off-by-one in the editor
 * rather than in the indexer.</p>
 */
public final class ModuleSymbols {

    private static final Logger logger = LoggerFactory.getLogger(ModuleSymbols.class);

    /** What kind of thing a symbol is, mapped to LSP SymbolKind on the way out. */
    public enum SymbolKind { FUNCTION, CLASS, METHOD, VARIABLE }

    /** One definition in a module. */
    public record Symbol(String name, SymbolKind kind, int line, int column,
                         String container, String signature, String documentation) {
    }

    /** One name brought into the module by an import. */
    public record ImportBinding(String boundName, String targetModule, String targetMember,
                                boolean star, int line) {
    }

    private final String moduleName;
    private final List<Symbol> symbols;
    private final List<ImportBinding> imports;
    private final String syntaxError;
    private final int errorLine;
    private final int errorColumn;

    private ModuleSymbols(String moduleName, List<Symbol> symbols, List<ImportBinding> imports,
                          String syntaxError, int errorLine, int errorColumn) {
        this.moduleName = moduleName;
        this.symbols = List.copyOf(symbols);
        this.imports = List.copyOf(imports);
        this.syntaxError = syntaxError;
        this.errorLine = errorLine;
        this.errorColumn = errorColumn;
    }

    public String moduleName() {
        return moduleName;
    }

    public List<Symbol> symbols() {
        return symbols;
    }

    public List<ImportBinding> imports() {
        return imports;
    }

    /** The single syntax error, if the module does not parse. */
    public Optional<String> syntaxError() {
        return Optional.ofNullable(syntaxError);
    }

    /** 0-based line of the syntax error. */
    public int errorLine() {
        return errorLine;
    }

    /** 0-based column of the syntax error. */
    public int errorColumn() {
        return errorColumn;
    }

    /** Find a top-level symbol by name. */
    public Optional<Symbol> find(String name) {
        return symbols.stream()
            .filter(s -> s.name().equals(name) && s.container() == null)
            .findFirst();
    }

    /**
     * Parse one module.
     *
     * <p>Never throws: a module that does not parse yields a {@link ModuleSymbols}
     * carrying the error instead. An indexer that throws on one bad file loses the
     * whole project, and a project with one broken script is the normal case while
     * someone is typing.</p>
     */
    public static ModuleSymbols parse(String moduleName, String source) {
        List<Symbol> symbols = new ArrayList<>();
        List<ImportBinding> imports = new ArrayList<>();
        try {
            mod parsed = ParserFacade.parseExpressionOrModule(
                new StringReader(source == null ? "" : source), moduleName, new CompilerFlags());
            if (parsed instanceof Module module) {
                collect(module.getInternalBody(), null, symbols, imports);
            }
            return new ModuleSymbols(moduleName, symbols, imports, null, 0, 0);
        } catch (ParseException e) {
            // ANTLR-level failure. Positions live on the exception itself.
            return new ModuleSymbols(moduleName, symbols, imports,
                message(e), Math.max(0, e.line - 1), Math.max(0, e.charPositionInLine));
        } catch (PyException e) {
            // Jython surfaces most syntax errors as a Python SyntaxError whose value
            // carries (msg, (file, lineno, offset, text)). Measured in S1: lineno and
            // offset are readable directly, and the reported line is correct even for
            // an error several lines into the file.
            return fromPySyntaxError(moduleName, symbols, imports, e);
        } catch (RuntimeException e) {
            logger.debug("Unexpected parse failure for {}: {}", moduleName, e.toString());
            return new ModuleSymbols(moduleName, symbols, imports,
                "Could not parse: " + e.getMessage(), 0, 0);
        }
    }

    /**
     * Pull the message and position out of a Jython syntax error.
     *
     * <p>MEASURED, not assumed: Jython raises {@code PyIndentationError} (a
     * {@code PyException}) whose {@code value} is a <b>PyTuple</b> shaped
     * {@code (msg, (filename, lineno, offset, text))} — 1-based lineno. It is NOT a
     * {@code SyntaxError} instance with {@code .lineno}/{@code .offset} attributes,
     * which is what the equivalent Python-level code sees and what the obvious Java
     * translation reaches for; those accessors all return null here and the error
     * silently lands on line 1.</p>
     *
     * <p>The attribute form is still tried as a fallback, since other Jython entry
     * points do produce it.</p>
     */
    private static ModuleSymbols fromPySyntaxError(String moduleName, List<Symbol> symbols,
                                                   List<ImportBinding> imports, PyException e) {
        String text = String.valueOf(e.value);
        int line = 0;
        int column = 0;

        try {
            if (e.value instanceof org.python.core.PyTuple tuple && tuple.size() >= 2) {
                text = String.valueOf(tuple.pyget(0));
                if (tuple.pyget(1) instanceof org.python.core.PyTuple where
                    && where.size() >= 3) {
                    line = Math.max(0, ((org.python.core.PyObject) where.pyget(1)).asInt() - 1);
                    column = Math.max(0, ((org.python.core.PyObject) where.pyget(2)).asInt());
                }
                return new ModuleSymbols(moduleName, symbols, imports, text, line, column);
            }
        } catch (RuntimeException ignored) {
            // Fall through to the attribute form below.
        }

        try {
            org.python.core.PyObject lineno = e.value.__findattr__("lineno");
            if (lineno != null) {
                line = Math.max(0, lineno.asInt() - 1);
            }
            org.python.core.PyObject offset = e.value.__findattr__("offset");
            if (offset != null) {
                column = Math.max(0, offset.asInt());
            }
            org.python.core.PyObject msg = e.value.__findattr__("msg");
            if (msg != null) {
                text = msg.toString();
            }
        } catch (RuntimeException ignored) {
            // Position unavailable — still report the error, just at the top.
        }
        return new ModuleSymbols(moduleName, symbols, imports, text, line, column);
    }

    private static String message(ParseException e) {
        String m = e.getMessage();
        return m == null || m.isBlank() ? "Syntax error" : m;
    }

    /**
     * Walk a statement list, collecting definitions and imports.
     *
     * <p>Only ONE level is descended into a class, to pick up its methods. Deeper
     * nesting is deliberately not indexed: a function defined inside a function is
     * not reachable by an importer, so listing it in an outline or a workspace
     * symbol search would offer a jump target that cannot actually be called.</p>
     */
    private static void collect(List<stmt> body, String container,
                                List<Symbol> symbols, List<ImportBinding> imports) {
        if (body == null) {
            return;
        }
        for (stmt statement : body) {
            if (statement instanceof FunctionDef function) {
                symbols.add(new Symbol(
                    function.getInternalName(),
                    container == null ? SymbolKind.FUNCTION : SymbolKind.METHOD,
                    Math.max(0, function.getLineno() - 1), function.getCol_offset(),
                    container,
                    signatureOf(function),
                    docstringOf(function.getInternalBody())));
            } else if (statement instanceof ClassDef klass) {
                symbols.add(new Symbol(
                    klass.getInternalName(), SymbolKind.CLASS,
                    Math.max(0, klass.getLineno() - 1), klass.getCol_offset(),
                    container, null, docstringOf(klass.getInternalBody())));
                if (container == null) {
                    collect(klass.getInternalBody(), klass.getInternalName(), symbols, imports);
                }
            } else if (statement instanceof Assign assign && container == null) {
                for (expr target : assign.getInternalTargets()) {
                    if (target instanceof Name name) {
                        symbols.add(new Symbol(name.getInternalId(), SymbolKind.VARIABLE,
                            Math.max(0, name.getLineno() - 1), name.getCol_offset(),
                            null, null, null));
                    }
                }
            } else if (statement instanceof Import importStatement) {
                for (alias a : importStatement.getInternalNames()) {
                    String bound = a.getInternalAsname() != null
                        ? a.getInternalAsname()
                        // `import a.b.c` binds `a`, not `a.b.c` — a detail that
                        // quietly breaks resolution if treated as the full path.
                        : a.getInternalName().split("\\.")[0];
                    imports.add(new ImportBinding(bound, a.getInternalName(), null, false,
                        Math.max(0, importStatement.getLineno() - 1)));
                }
            } else if (statement instanceof ImportFrom from) {
                String module = from.getInternalModule();
                for (alias a : from.getInternalNames()) {
                    if ("*".equals(a.getInternalName())) {
                        // A star import makes the module's namespace unknowable
                        // statically. Recorded so undefined-name checks can switch
                        // themselves off for this module rather than emit nonsense.
                        imports.add(new ImportBinding("*", module, null, true,
                            Math.max(0, from.getLineno() - 1)));
                        continue;
                    }
                    String bound = a.getInternalAsname() != null
                        ? a.getInternalAsname() : a.getInternalName();
                    imports.add(new ImportBinding(bound, module, a.getInternalName(), false,
                        Math.max(0, from.getLineno() - 1)));
                }
            }
        }
    }

    /** {@code name(a, b=..., *args, **kwargs)} reconstructed from the AST. */
    static String signatureOf(FunctionDef function) {
        StringBuilder sb = new StringBuilder(function.getInternalName()).append('(');
        var args = function.getInternalArgs();
        List<String> parts = new ArrayList<>();
        if (args != null) {
            List<expr> positional = args.getInternalArgs();
            int defaults = args.getInternalDefaults() == null ? 0 : args.getInternalDefaults().size();
            int firstDefaulted = positional.size() - defaults;
            for (int i = 0; i < positional.size(); i++) {
                String name = (positional.get(i) instanceof Name n) ? n.getInternalId() : "?";
                parts.add(i >= firstDefaulted ? name + "=..." : name);
            }
            if (args.getInternalVararg() != null) {
                parts.add("*" + args.getInternalVararg());
            }
            if (args.getInternalKwarg() != null) {
                parts.add("**" + args.getInternalKwarg());
            }
        }
        return sb.append(String.join(", ", parts)).append(')').toString();
    }

    /** The leading string literal of a body, if it has one. */
    static String docstringOf(List<stmt> body) {
        if (body == null || body.isEmpty()) {
            return null;
        }
        if (body.get(0) instanceof org.python.antlr.ast.Expr first
            && first.getInternalValue() instanceof Str str) {
            Object value = str.getInternalS();
            return value == null ? null : value.toString();
        }
        return null;
    }
}
