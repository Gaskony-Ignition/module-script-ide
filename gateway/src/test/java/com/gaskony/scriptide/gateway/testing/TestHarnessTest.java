package com.gaskony.scriptide.gateway.testing;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.python.core.CompilerFlags;
import org.python.core.ParserFacade;

import java.io.StringReader;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * The harness is a constant, so what can be asserted about it is its SHAPE —
 * and every property here has cost this estate a release when it was absent.
 */
class TestHarnessTest {

    @Test
    @DisplayName("it parses as Jython 2.7")
    void parses() {
        // The one thing a constant can get catastrophically wrong. A syntax
        // error here fails every test run on the gateway with a traceback about
        // our own source, which reads as the user's script being at fault.
        ParserFacade.parseExpressionOrModule(
            new StringReader(TestHarness.SOURCE), "<harness>", new CompilerFlags());
    }

    @Test
    @DisplayName("it defines no functions, because there is one namespace")
    void isFlat() {
        // A `def` here would not see the module-level names it needs: this
        // module executes with the locals map serving as globals too. See
        // PrivateStateRunner's two-dict note.
        assertThat(TestHarness.SOURCE).doesNotContain("\ndef ");
        assertThat(TestHarness.SOURCE).doesNotContain("\nclass ");
    }

    @Test
    @DisplayName("it never catches bare, so a Stop is not swallowed")
    void doesNotCatchBare() {
        // A Stop and the execution timeout arrive as a Java Error, which is a
        // Throwable and not an Exception. A bare `except:` would catch it and
        // calmly continue to the next test — a Stop button that appears to work
        // and does nothing.
        assertThat(TestHarness.SOURCE).doesNotContain("except:");
        assertThat(TestHarness.SOURCE).contains("except AssertionError");
        assertThat(TestHarness.SOURCE).contains("except Exception");
    }

    @Test
    @DisplayName("tearDown runs in a finally, not only on success")
    void tearDownAlwaysRuns() {
        // A teardown that runs only when the test passed leaks exactly when it
        // matters, and the next test then fails for the previous one's reason.
        int call = TestHarness.SOURCE.indexOf("_si_entry['call']()");
        int finallyAfter = TestHarness.SOURCE.indexOf("finally:", call);
        int teardown = TestHarness.SOURCE.indexOf("_si_entry['teardown']()", call);
        assertThat(call).isGreaterThan(-1);
        assertThat(finallyAfter).isGreaterThan(call);
        assertThat(teardown).isGreaterThan(finallyAfter);
    }

    @Test
    @DisplayName("it never redirects sys.stdout")
    void neverRedirectsStdout() {
        // Measured on 8.3.8, twice: with sys.stdout pointed at a StringIO, a
        // print inside a project library function reached neither the buffer nor
        // the execution's stream — it vanished. With no redirect at all the same
        // print streamed perfectly. The obvious implementation is the wrong one
        // and it fails silently, so the absence is asserted.
        assertThat(TestHarness.SOURCE).doesNotContain("_si_sys.stdout =");
        assertThat(TestHarness.SOURCE).doesNotContain("StringIO");
    }

    @Test
    @DisplayName("every import happens before the first write to stdout")
    void importsBeforeAnyOutput() {
        // Measured on 8.3.8: a write to sys.stdout followed by an import of a
        // project library module loses the WHOLE execution's output — the write,
        // everything after it, and the run still reports success. Two passes is
        // the fix, and it is invisible in the source unless something asserts it.
        int lastImport = TestHarness.SOURCE.lastIndexOf("__import__");
        int firstWrite = TestHarness.SOURCE.indexOf("_si_sys.stdout.write");
        assertThat(lastImport).isGreaterThan(-1);
        assertThat(firstWrite).isGreaterThan(lastImport);
    }

    @Test
    @DisplayName("a module that will not import is an error on every test in it")
    void importFailureIsPerTest() {
        // Reported per test rather than as one failure of the whole run: the
        // panel's row is where a reader looks for why a test did not pass.
        assertThat(TestHarness.SOURCE).contains("_si_entry['status'] = 'error'");
        assertThat(TestHarness.SOURCE).contains("_si_entry['call'] is not None");
    }

    @Test
    @DisplayName("it re-asserts the private system state after the imports")
    void reassertsSystemState() {
        // Without this, `print` writes to the gateway's own console from the
        // first project import onward and the test's output comes back empty —
        // silently, with the run reporting success. Explicit sys.stdout.write
        // keeps working throughout, which is exactly why the bug is invisible.
        int lastImport = TestHarness.SOURCE.lastIndexOf("__import__");
        int reassert = TestHarness.SOURCE.indexOf("_si_Py.setSystemState(_si_sys)");
        assertThat(reassert).isGreaterThan(lastImport);
    }

    @Test
    @DisplayName("it flushes its own streams before it ends")
    void flushesItself() {
        // Jython buffers sys.stdout and the runner's tail-flush does not reach
        // that buffer on a batch run. Without these the capture is empty.
        assertThat(TestHarness.SOURCE).contains("_si_sys.stdout.flush()");
        assertThat(TestHarness.SOURCE).contains("_si_sys.stderr.flush()");
        assertThat(TestHarness.SOURCE.indexOf("_si_sys.stdout.flush()"))
            .isGreaterThan(TestHarness.SOURCE.indexOf(TestHarness.VAR_RESULT + " = "));
    }

    @Test
    @DisplayName("it writes a begin and an end marker around every test")
    void writesMarkers() {
        assertThat(TestHarness.SOURCE)
            .contains("_si_sys.stdout.write(" + TestHarness.VAR_MARKER + " + '>'");
        assertThat(TestHarness.SOURCE)
            .contains("_si_sys.stdout.write(" + TestHarness.VAR_MARKER + " + '<");
    }

    @Test
    @DisplayName("the end marker is written after the except clauses, so a failure still closes")
    void endMarkerFollowsTheHandlers() {
        int handler = TestHarness.SOURCE.indexOf("except Exception");
        int end = TestHarness.SOURCE.indexOf("+ '<", handler);
        assertThat(handler).isGreaterThan(-1);
        assertThat(end).isGreaterThan(handler);
    }

    @Test
    @DisplayName("it reads the tests from a seeded variable, never from formatted source")
    void nothingIsConcatenated() {
        // A module called `x'); import os; os.system('` is a name Ignition
        // accepts. The only defence that survives a later edit is that there is
        // no string formatting in this path at all.
        assertThat(TestHarness.SOURCE).contains("for _si_spec in " + TestHarness.VAR_TESTS);
        assertThat(TestHarness.SOURCE).doesNotContain("%s");
        assertThat(TestHarness.SOURCE).doesNotContain(".format(");
    }

    @Test
    @DisplayName("it leaves its result under the name the handler reads")
    void publishesTheResult() {
        assertThat(TestHarness.SOURCE).contains(TestHarness.VAR_RESULT + " = ");
        assertThat(TestHarness.SOURCE).contains("'results'");
    }

    @Test
    @DisplayName("attribute() gives each test the text between its own markers")
    void attributesOutput() {
        String m = "\u0001nonce\u0001";
        String streamed = "preamble\n"
            + m + ">a.test_one\n" + "first line\nsecond line\n" + m + "<\n"
            + m + ">a.test_two\n" + "only mine\n" + m + "<\n";

        var byId = TestHarness.attribute(streamed, m);
        assertThat(byId).containsEntry("a.test_one", "first line\nsecond line\n");
        assertThat(byId).containsEntry("a.test_two", "only mine\n");
    }

    @Test
    @DisplayName("text outside any test's markers belongs to nobody")
    void dropsUnattributedText() {
        // The harness's own bookkeeping, and a module's import-time output.
        // Attributing either would put a line in a record the test did not write.
        String m = "\u0001nonce\u0001";
        var byId = TestHarness.attribute(
            "loose text\n" + m + ">a.test_one\n" + "mine\n" + m + "<\nafterwards\n", m);
        assertThat(byId).hasSize(1);
        assertThat(byId.get("a.test_one")).isEqualTo("mine\n");
    }

    @Test
    @DisplayName("attribute() is safe on nothing at all")
    void attributeHandlesEmpty() {
        assertThat(TestHarness.attribute(null, "m")).isEmpty();
        assertThat(TestHarness.attribute("", "m")).isEmpty();
        assertThat(TestHarness.attribute("text", null)).isEmpty();
        assertThat(TestHarness.attribute("text with no markers", "\u0001m\u0001")).isEmpty();
    }

    @Test
    @DisplayName("a test that runs twice keeps both lots of output")
    void mergesRepeatedIds() {
        String m = "\u0001nonce\u0001";
        var byId = TestHarness.attribute(
            m + ">a.t\n" + "one\n" + m + "<\n" + m + ">a.t\n" + "two\n" + m + "<\n", m);
        assertThat(byId.get("a.t")).isEqualTo("one\ntwo\n");
    }

    @Test
    @DisplayName("every status the panel renders is one this harness can emit")
    void emitsTheThreeStatuses() {
        assertThat(TestHarness.SOURCE).contains("'pass'");
        assertThat(TestHarness.SOURCE).contains("'fail'");
        assertThat(TestHarness.SOURCE).contains("'error'");
    }
}
