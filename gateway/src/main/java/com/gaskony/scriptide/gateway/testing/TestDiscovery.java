package com.gaskony.scriptide.gateway.testing;

import com.gaskony.scriptide.gateway.lang.ModuleSymbols;
import com.gaskony.scriptide.gateway.lang.ProjectIndex;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;

/**
 * Which functions in a project are tests.
 *
 * <h2>The convention, and why it is narrow</h2>
 *
 * <p>A test is a top-level {@code def test_*}, or a {@code def test_*} method on
 * a class whose name begins {@code Test}, in a module the convention below calls
 * a test module. Nothing else is a test, however it is named.</p>
 *
 * <p><b>The module rule is doing the important work.</b> Discovering
 * {@code def test_*} anywhere in a project would find
 * {@code plc.diagnostics.test_connection} and put it under a Run All button — a
 * function whose whole job is to open a socket to a PLC. Every wrong answer in
 * that direction is a production side effect fired by someone exploring a new
 * panel, and a discovery rule that has to be right is worth more than one that
 * has to be generous. So a module qualifies when its own name says it is for
 * tests:</p>
 *
 * <ul>
 *   <li>the last dotted segment starts with {@code test} ({@code orders.test_totals}), or</li>
 *   <li>any segment is exactly {@code tests} ({@code orders.tests.totals}).</li>
 * </ul>
 *
 * <p>Both are the layouts people already use, and neither can be reached by
 * accident. The cost is that a test in an ordinary module is invisible; the panel
 * says the rule out loud so that reads as a rule rather than as a bug.</p>
 *
 * <h2>Only Project Library modules</h2>
 *
 * <p>{@link ProjectIndex#modules} is library-only, which is exactly right here
 * for the reason it is right for go-to-definition: running a test means IMPORTING
 * the module that holds it, and a timer script is not importable. A gateway event
 * script cannot hold a test because there is no way to call one.</p>
 *
 * <h2>Setup and teardown</h2>
 *
 * <p>A module may define {@code setUp} and {@code tearDown} at the top level;
 * they run around EACH test in that module, which is the {@code unittest}
 * meaning of those names and therefore the one a reader already has. They are
 * discovered here so the runner does not have to guess whether calling them
 * would raise {@code NameError}.</p>
 */
public final class TestDiscovery {

    private TestDiscovery() { /* static discovery */ }

    /** The names a module may define to bracket each of its tests. */
    public static final String SETUP_NAME = "setUp";

    /** @see #SETUP_NAME */
    public static final String TEARDOWN_NAME = "tearDown";

    /** The convention, in one sentence, for the panel to show. */
    public static final String CONVENTION =
        "A test is a top-level def test_* (or a test_* method on a class named Test*) "
        + "in a module whose last name starts with 'test' or that sits under a 'tests' package.";

    /**
     * One discovered test.
     *
     * @param module   the dotted module name, which is also what gets imported
     * @param className the class holding it, or null for a top-level function
     * @param function the function name
     * @param line     0-based, for click-to-open
     */
    public record TestCase(String module, String className, String function, int line) {

        /** How the runner and the UI both name it: {@code module.Class.function}. */
        public String id() {
            return className == null
                ? module + "." + function
                : module + "." + className + "." + function;
        }
    }

    /** A module holding tests, with what brackets them. */
    public record TestModule(String module, boolean hasSetUp, boolean hasTearDown,
                             List<TestCase> tests) {

        /** Defensive copy: a record's list component is otherwise shared with its caller. */
        public TestModule {
            tests = List.copyOf(tests);
        }
    }

    /** Every test module in a project, in name order. */
    public static List<TestModule> discover(ProjectIndex index, String project) {
        return discover(index.modules(project));
    }

    /**
     * The same rule, over an already-parsed module set.
     *
     * <p>The seam the tests use. Discovery is a convention over symbol names and
     * has nothing to do with where the symbols came from, so proving it through
     * a {@code ProjectManager} would mean mocking the platform to assert a
     * string comparison.</p>
     */
    public static List<TestModule> discover(Map<String, ModuleSymbols> byName) {
        Map<String, ModuleSymbols> modules = new TreeMap<>(byName);
        List<TestModule> out = new ArrayList<>();
        for (Map.Entry<String, ModuleSymbols> entry : modules.entrySet()) {
            String moduleName = entry.getKey();
            if (!isTestModule(moduleName)) {
                continue;
            }
            ModuleSymbols symbols = entry.getValue();
            // A module that does not parse has no reliable symbol list, so it
            // contributes no tests. It is not silently dropped: the Problems
            // panel already reports the syntax error, which is the actionable
            // form of the same fact.
            if (symbols.syntaxError().isPresent()) {
                continue;
            }
            List<String> testClasses = new ArrayList<>();
            for (ModuleSymbols.Symbol symbol : symbols.symbols()) {
                if (symbol.kind() == ModuleSymbols.SymbolKind.CLASS
                    && symbol.container() == null
                    && symbol.name().startsWith("Test")) {
                    testClasses.add(symbol.name());
                }
            }
            List<TestCase> tests = new ArrayList<>();
            boolean setUp = false;
            boolean tearDown = false;
            for (ModuleSymbols.Symbol symbol : symbols.symbols()) {
                if (symbol.container() == null
                    && symbol.kind() == ModuleSymbols.SymbolKind.FUNCTION) {
                    if (SETUP_NAME.equals(symbol.name())) {
                        setUp = true;
                    } else if (TEARDOWN_NAME.equals(symbol.name())) {
                        tearDown = true;
                    } else if (isTestName(symbol.name())) {
                        tests.add(new TestCase(moduleName, null, symbol.name(), symbol.line()));
                    }
                } else if (symbol.kind() == ModuleSymbols.SymbolKind.METHOD
                    && testClasses.contains(symbol.container())
                    && isTestName(symbol.name())) {
                    tests.add(new TestCase(moduleName, symbol.container(), symbol.name(),
                        symbol.line()));
                }
            }
            if (!tests.isEmpty()) {
                out.add(new TestModule(moduleName, setUp, tearDown, List.copyOf(tests)));
            }
        }
        return List.copyOf(out);
    }

    /**
     * Whether a dotted module name is a test module.
     *
     * <p>Case-insensitive on the prefix, because {@code Test_Orders} is a name
     * people write and refusing it would look like the feature is broken rather
     * than like the file is misnamed. The {@code tests} package segment is
     * matched exactly: {@code testing.utils} is a utility module about testing,
     * not a package of tests, and treating it as one runs its helpers.</p>
     */
    public static boolean isTestModule(String moduleName) {
        if (moduleName == null || moduleName.isBlank()) {
            return false;
        }
        String[] segments = moduleName.split("\\.");
        for (String segment : segments) {
            if ("tests".equals(segment)) {
                return true;
            }
        }
        String last = segments[segments.length - 1].toLowerCase(Locale.ROOT);
        return last.startsWith("test");
    }

    /** Whether a function name is a test. {@code test_} or bare {@code test}. */
    public static boolean isTestName(String name) {
        return name != null && (name.startsWith("test_") || "test".equals(name));
    }
}
