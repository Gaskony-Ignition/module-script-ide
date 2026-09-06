package com.gaskony.scriptide.gateway.testing;

/**
 * The Jython that actually runs the tests. A CONSTANT.
 *
 * <h2>Nothing the user typed is concatenated into it</h2>
 *
 * <p>Same rule as {@code NamedQueryTestRouteHandler}, and for the same reason:
 * the selected tests arrive as a LIST seeded into the execution's namespace, not
 * as generated Python. A module called {@code x'); import os; os.system('} is a
 * name Ignition will accept, and the only defence that keeps working when
 * somebody adds a feature later is that there is no string formatting in this
 * path at all.</p>
 *
 * <h2>Why it is written flat</h2>
 *
 * <p>No {@code def}, anywhere. This module executes a script with ONE namespace
 * serving as both locals and globals — see the two-dict trap recorded in
 * {@code PrivateStateRunner} — and a function body defined here would not see
 * the module-level names it needs. Everything is therefore a module-level
 * statement, including the loop over the tests.</p>
 *
 * <h2>Three outcomes, and the difference between two of them matters</h2>
 *
 * <ul>
 *   <li>{@code pass} — the function returned.</li>
 *   <li>{@code fail} — it raised {@code AssertionError}. The test ran and the
 *       thing it asserts is not true.</li>
 *   <li>{@code error} — it raised anything else. The test did not get far enough
 *       to have an opinion, and the first one of these usually explains the rest.
 *       A runner that reported both as "failed" would send you to read an
 *       assertion that never executed.</li>
 * </ul>
 *
 * <h2>A Stop is not caught</h2>
 *
 * <p>The handlers are {@code except AssertionError} and {@code except Exception},
 * never a bare {@code except:}. A Stop, and the execution timeout that uses the
 * same mechanism, arrive as a Java {@code Error} — which is a {@code Throwable}
 * and not an {@code Exception}, so it passes straight through this loop and ends
 * the run, exactly as it does in the console. A bare {@code except:} would swallow
 * it and calmly carry on to the next test, which is how a Stop button comes to do
 * nothing while appearing to work.</p>
 *
 * <h2>Each test's output is its own — and NOT by swapping {@code sys.stdout}</h2>
 *
 * <p>The obvious implementation is to point {@code sys.stdout} at a
 * {@code StringIO} around each call. <b>It does not work, it fails silently, and
 * that was measured on 8.3.8 rather than reasoned about.</b> A {@code print}
 * inside a PROJECT LIBRARY function does not consult the {@code sys.stdout} the
 * calling script can see: with the swap in place the text reached neither the
 * buffer nor the execution's stream — it vanished — and with no swap at all the
 * same print streamed perfectly. Two probes against the running gateway,
 * reporting through an exception message because the thing under test was the
 * output path itself.</p>
 *
 * <p>So nothing is redirected. The harness writes a MARKER around each test on
 * the ordinary stream, and the Java side splits the streamed output on those
 * markers to attribute it. The marker carries a per-run nonce generated in Java,
 * so a test that prints something marker-shaped cannot forge a boundary.</p>
 *
 * <h2>Two passes, a re-assert and a flush — all three measured, all three needed</h2>
 *
 * <p>Getting a test's own output back took three separate findings on 8.3.8, and
 * each of them fails SILENTLY: the run reports success and the output is simply
 * gone. They are listed with what proves them, because the obvious edit to any
 * one of them puts the bug straight back.</p>
 *
 * <ol>
 *   <li><b>Every import happens in pass one, before any output.</b> Writing to
 *       {@code sys.stdout} and then importing a project library module loses the
 *       whole execution's output — not just the buffered write, everything after
 *       it too. Import first and the identical sequence works. So pass one
 *       imports and resolves and prints nothing; pass two writes markers and
 *       runs.</li>
 *   <li><b>The private state is re-asserted after the imports.</b> An import of a
 *       project library module leaves the THREAD's {@code PySystemState}
 *       pointing at the platform's, so {@code print} — which resolves stdout
 *       through {@code Py.getSystemState()} — goes to the gateway's own console
 *       from then on. Explicit {@code sys.stdout.write} kept working the whole
 *       time, and that asymmetry is what made it visible: a captured write
 *       beside a missing print means the two are resolving different objects.
 *       {@code Py.setSystemState(sys)} from Jython puts it back.</li>
 *   <li><b>The harness flushes its own streams at the end.</b> Jython buffers
 *       {@code sys.stdout}; on this path the runner's tail-flush does not reach
 *       that buffer, and without an explicit flush the capture came back
 *       completely empty. The script console never showed any of this, because a
 *       socket run has a periodic pump and a batch run does not.</li>
 * </ol>
 *
 * <p>One visible consequence of (1): a module's import-time output belongs to no
 * test and is dropped. That is the right answer anyway — it is not something a
 * test wrote.</p>
 *
 * <p>The cost, stated because it is real: attribution is positional, so anything
 * a BACKGROUND thread a test started prints after that test ends is attributed to
 * whichever test is running then. A test that leaves threads behind has a bigger
 * problem than its output labelling.</p>
 */
public final class TestHarness {

    private TestHarness() { /* constant holder */ }

    /** The list of {@code [module, class, function, id]} entries to run. */
    public static final String VAR_TESTS = "_scriptide_test_specs";


    /** Where the JSON result is left for the handler to read. */
    public static final String VAR_RESULT = "_scriptide_test_result";

    /**
     * The per-run boundary marker, generated in Java and seeded as data.
     *
     * <p>A nonce rather than a constant: a test that printed a fixed marker
     * could otherwise split its own output across two other tests' records, and
     * the result would look like a bug in whichever test it landed in.</p>
     */
    public static final String VAR_MARKER = "_scriptide_test_marker";


    /** The harness, as one flat script. */
    public static final String SOURCE = String.join("\n",
        "import json as _si_json",
        "import sys as _si_sys",
        "import time as _si_time",
        "import traceback as _si_tb",
        "",
        "_si_results = []",
        "_si_modules = {}",
        "_si_prepared = []",
        "",
        // ---- PASS ONE: import and resolve. NOTHING is printed in this loop.
        // See the class Javadoc: a write to stdout before an import loses the
        // whole execution's output, silently.
        "for _si_spec in " + VAR_TESTS + ":",
        "    _si_entry = {'spec': _si_spec, 'call': None, 'setup': None,",
        "                 'teardown': None, 'status': 'pass', 'message': '', 'trace': ''}",
        "    try:",
        "        _si_module = _si_spec[0]",
        "        if _si_module in _si_modules:",
        "            _si_target_module = _si_modules[_si_module]",
        "        else:",
        "            _si_target_module = __import__(_si_module, {}, {}, ['*'])",
        "            _si_modules[_si_module] = _si_target_module",
        "        _si_entry['setup'] = getattr(_si_target_module, '"
            + TestDiscovery.SETUP_NAME + "', None)",
        "        _si_entry['teardown'] = getattr(_si_target_module, '"
            + TestDiscovery.TEARDOWN_NAME + "', None)",
        "        if _si_spec[1]:",
        "            _si_owner = getattr(_si_target_module, _si_spec[1])()",
        "            _si_entry['call'] = getattr(_si_owner, _si_spec[2])",
        "        else:",
        "            _si_entry['call'] = getattr(_si_target_module, _si_spec[2])",
        "    except Exception, _si_error:",
        // A module that will not import is an ERROR for every test in it, and it
        // is reported per test rather than as one failure of the run: the
        // panel's row is where a reader looks.
        "        _si_entry['status'] = 'error'",
        "        _si_entry['message'] = _si_error.__class__.__name__ + ': ' + str(_si_error)",
        "        _si_entry['trace'] = _si_tb.format_exc()",
        "    _si_prepared.append(_si_entry)",
        "",
        // RE-ASSERT THE PRIVATE STATE. Importing a project library module
        // leaves the thread's PySystemState pointing at the PLATFORM's, so from
        // here on `print` — which resolves stdout through Py.getSystemState()
        // rather than through the `sys` this script can see — writes to the
        // gateway's own console and not to this execution's capture. Explicit
        // sys.stdout.write kept working throughout, which is what made the
        // difference visible: with the write captured and the print missing,
        // the two must be resolving different objects. Guarded, because a
        // gateway that will not hand out org.python.core should lose output
        // rather than lose the run.
        "try:",
        "    from org.python.core import Py as _si_Py",
        "    _si_Py.setSystemState(_si_sys)",
        "except Exception:",
        "    pass",
        "",
        // ---- PASS TWO: markers, and the actual runs.
        "for _si_entry in _si_prepared:",
        "    _si_spec = _si_entry['spec']",
        "    _si_id = _si_spec[3]",
        "    _si_status = _si_entry['status']",
        "    _si_message = _si_entry['message']",
        "    _si_trace = _si_entry['trace']",
        "    _si_started = _si_time.time()",
        "    _si_sys.stdout.write(" + VAR_MARKER + " + '>' + _si_id + chr(10))",
        "    if _si_entry['call'] is not None:",
        "        try:",
        "            if _si_entry['setup'] is not None:",
        "                _si_entry['setup']()",
        // tearDown runs even when the test raises, which is the whole reason
        // anyone writes one. It is NOT inside the except clauses below: a
        // teardown that runs only on success leaks exactly when it matters.
        "            try:",
        "                _si_entry['call']()",
        "            finally:",
        "                if _si_entry['teardown'] is not None:",
        "                    _si_entry['teardown']()",
        "        except AssertionError, _si_error:",
        "            _si_status = 'fail'",
        "            _si_message = str(_si_error)",
        "            if not _si_message:",
        "                _si_message = 'assertion failed'",
        "            _si_trace = _si_tb.format_exc()",
        "        except Exception, _si_error:",
        "            _si_status = 'error'",
        "            _si_message = _si_error.__class__.__name__ + ': ' + str(_si_error)",
        "            _si_trace = _si_tb.format_exc()",
        "    _si_sys.stdout.write(" + VAR_MARKER + " + '<' + chr(10))",
        "    _si_elapsed = int((_si_time.time() - _si_started) * 1000)",
        "    _si_results.append({",
        "        'id': _si_id,",
        "        'module': _si_spec[0],",
        "        'function': _si_spec[2],",
        "        'status': _si_status,",
        "        'message': _si_message,",
        "        'traceback': _si_trace,",
        "        'elapsedMs': _si_elapsed})",
        "",
        VAR_RESULT + " = _si_json.dumps({'results': _si_results})",
        // FLUSH FROM INSIDE. Jython buffers sys.stdout, and the runner's own
        // tail-flush does not reach this buffer on this path: without these two
        // lines the capture came back completely empty while the run reported
        // success. The console never showed the problem, because a socket run
        // has a periodic pump and this one does not.
        "_si_sys.stdout.flush()",
        "_si_sys.stderr.flush()",
        "");

    /**
     * Split streamed output into what each test produced.
     *
     * <p>Text before the first marker, or between an end marker and the next
     * begin, belongs to no test and is dropped: it is the harness's own
     * bookkeeping or a module's import-time output, and attributing either to a
     * test would put a line in a record the test did not write.</p>
     *
     * @param streamed everything the execution wrote, in arrival order
     * @param marker   the nonce handed to the harness for this run
     */
    public static java.util.Map<String, String> attribute(String streamed, String marker) {
        java.util.Map<String, String> out = new java.util.LinkedHashMap<>();
        if (streamed == null || streamed.isEmpty() || marker == null || marker.isEmpty()) {
            return out;
        }
        String[] parts = streamed.split(java.util.regex.Pattern.quote(marker), -1);
        // parts[0] is whatever preceded the first marker.
        for (int i = 1; i < parts.length; i++) {
            String chunk = parts[i];
            if (chunk.isEmpty() || chunk.charAt(0) != '>') {
                continue;       // an end marker, or a fragment we cannot place
            }
            int newline = chunk.indexOf('\n');
            String id = newline < 0 ? chunk.substring(1) : chunk.substring(1, newline);
            String body = newline < 0 ? "" : chunk.substring(newline + 1);
            // merge, not put: an id can legitimately appear twice, and losing
            // the first occurrence's output would be a silent hole.
            out.merge(id, body, String::concat);
        }
        return out;
    }
}
