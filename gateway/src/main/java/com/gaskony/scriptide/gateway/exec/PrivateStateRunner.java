package com.gaskony.scriptide.gateway.exec;

import com.inductiveautomation.ignition.common.script.ScriptManager;
import org.python.core.CompileMode;
import org.python.core.CompilerFlags;
import org.python.core.Py;
import org.python.core.PyCode;
import org.python.core.PyException;
import org.python.core.PyObject;
import org.python.core.PyStringMap;
import org.python.core.PySystemState;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.function.Supplier;

/**
 * Runs one script with its own private {@code stdout} and {@code stderr}.
 *
 * <h2>Why this does not use {@code ScriptManager.runCode}</h2>
 *
 * <p>Because that leaks one user's output into another's. Measured on Ignition
 * 8.3.8 / Jython 2.7.4 (spike S1): two concurrent {@code runCode} executions, each
 * printing 500 tagged lines through one {@code addStdOutStream} substream that
 * routed by thread id, produced <b>22–25 lines of cross-talk each way</b> and lost
 * ~45 more. Routing by thread is not enough because Jython's {@code sys.stdout} is
 * a single shared buffer: the thread that performs the write is not necessarily
 * the thread that produced the bytes.</p>
 *
 * <p>The approach below measured 0 cross-talk and 0 loss on the same test, and it
 * is the whole reason this class exists. Do not "simplify" it back.</p>
 *
 * <h2>The two refinements, both load-bearing</h2>
 * <ol>
 *   <li>A <b>fresh</b> {@link PySystemState} has an empty module registry, so
 *       {@code import system} and every project-library import raise
 *       {@code ImportError}. The manager's modules must be brought across.</li>
 *   <li><b>Sharing</b> the manager's module map is still not enough. In Jython
 *       {@code sys.modules['sys']} <i>is</i> the {@code PySystemState}, so a shared
 *       map leaves a script's {@code sys.stdout}/{@code sys.stderr} pointing at the
 *       MANAGER's streams. {@code print} would be isolated (it reads the
 *       thread-local state) while an explicit {@code sys.stderr.write(...)} would
 *       not. So the map is COPIED and the copy's {@code sys} is repointed at our
 *       own state.</li>
 * </ol>
 *
 * <p>Both were found the hard way, one spike iteration each. Removing either
 * breaks isolation silently — and one of the two failure modes is cross-user data
 * leakage, not merely lost output.</p>
 */
public final class PrivateStateRunner {

    private static final Logger logger = LoggerFactory.getLogger(PrivateStateRunner.class);

    /** Per-execution output cap. Beyond this, output is dropped, not the script. */
    static final int MAX_CAPTURED_BYTES = 2 * 1024 * 1024;

    /**
     * Resolves the project's CURRENT ScriptManager.
     *
     * <p>A supplier, not a stored manager, and that distinction is load-bearing.
     * The platform builds a project's script library into its ScriptManager, and
     * rebuilds it — into a NEW manager — when project resources change. Holding one
     * meant every execution ran against the library as it was when this runner was
     * first constructed: a script the user had just saved was invisible, failing
     * with a bare {@code ImportError: No module named X} while the resource plainly
     * existed on disk. That reads exactly like a broken save and is not.
     *
     * <p>Measured 01/09/2026: a freshly written library module was unimportable in
     * two different projects until the manager was resolved per execution. A
     * pre-existing module imported fine throughout, which is what made the cache
     * the obvious suspect.</p>
     */
    private final Supplier<ScriptManager> scriptManagerSupplier;

    /**
     * Cached manager state, valid only for {@link #managerStateOwner}.
     *
     * <p>Obtained without reflection: {@code ScriptManager.runCode} calls
     * {@code setState()} → {@code Py.setSystemState(manager.sys)} on the CALLING
     * thread and does not restore it, so running a trivial snippet and then reading
     * {@code Py.getSystemState()} yields the manager's state. Verified in S1.</p>
     */
    private volatile PySystemState managerState;

    /** The manager {@link #managerState} was probed from; a new one invalidates it. */
    private volatile ScriptManager managerStateOwner;

    public PrivateStateRunner(Supplier<ScriptManager> scriptManagerSupplier) {
        this.scriptManagerSupplier = scriptManagerSupplier;
    }

    /** What one execution produced. */
    public record Outcome(String stdout, String stderr, boolean truncated,
                          Throwable failure, boolean cancelled) {

        public boolean succeeded() {
            return failure == null && !cancelled;
        }
    }

    /**
     * Execute {@code source}, capturing its output privately.
     *
     * @param source   the code to run
     * @param fileName appears in every traceback frame — use a reversible token so
     *                 frames can be mapped back to an editor tab
     * @param locals   the locals map; pass the SAME one across calls for a console
     *                 session to behave like a REPL
     */
    public Outcome run(String source, String fileName, PyObject locals) {
        BoundedOutputStream out = new BoundedOutputStream(MAX_CAPTURED_BYTES);
        BoundedOutputStream err = new BoundedOutputStream(MAX_CAPTURED_BYTES);

        ScriptManager scriptManager = scriptManagerSupplier.get();
        PySystemState mgr = managerState(scriptManager);
        PySystemState state = ScriptManager.createUtf8PySystemState(out, err);
        applyModuleRegistry(state, mgr);

        PySystemState previous = Py.getSystemState();
        Throwable failure = null;
        boolean cancelled = false;
        try {
            // Thread-local: this is what makes the streams private.
            Py.setSystemState(state);
            PyCode code = Py.compile_flags(source, fileName, CompileMode.exec, new CompilerFlags());
            Py.runCode(code, locals, scriptManager.getGlobals());
        } catch (PyException e) {
            failure = e;
        } catch (Throwable t) {
            // MUST be Throwable, not Exception. A Stop raises a Java Error from a
            // Jython trace function that escapes Python's exception machinery
            // entirely — S1 confirmed neither a bare `except:` nor
            // `except java.lang.Throwable` in Jython catches it, and the worker
            // thread simply died. Catching it here is the only place it can be
            // turned into a clean "cancelled" result.
            failure = t;
            cancelled = isCancellation(t);
        } finally {
            flushQuietly(scriptManager, locals);
            try {
                Py.setSystemState(previous);
            } catch (RuntimeException e) {
                logger.debug("Could not restore the previous PySystemState: {}", e.getMessage());
            }
        }

        boolean truncated = out.truncated() || err.truncated();
        return new Outcome(
            out.toString(StandardCharsets.UTF_8),
            err.toString(StandardCharsets.UTF_8),
            truncated, failure, cancelled);
    }

    /**
     * Jython buffers {@code sys.stdout}, so the last chunk of a script's output can
     * still be unwritten when {@code runCode} returns. Flush on the SAME thread,
     * while our state is still installed, or that tail is lost.
     */
    private void flushQuietly(ScriptManager scriptManager, PyObject locals) {
        try {
            PyCode flush = Py.compile_flags(
                "import sys\nsys.stdout.flush()\nsys.stderr.flush()\n",
                "<script-ide-flush>", CompileMode.exec, new CompilerFlags());
            Py.runCode(flush, locals, scriptManager.getGlobals());
        } catch (Throwable t) {
            // A failed flush costs at most a truncated tail; it must never mask the
            // script's own result.
            logger.debug("Flush after execution failed: {}", t.toString());
        }
    }

    /**
     * Give the private state the manager's modules and import path — see the class
     * Javadoc for why the map is copied rather than shared.
     */
    private void applyModuleRegistry(PySystemState state, PySystemState mgr) {
        try {
            if (mgr.modules instanceof PyStringMap map) {
                PyStringMap copy = map.copy();
                // sys.modules['sys'] IS the PySystemState. Repoint it at ours, or an
                // explicit sys.stdout/sys.stderr write goes to the manager's streams.
                copy.__setitem__("sys", state);
                state.modules = copy;
            } else {
                // Unexpected implementation: share rather than fail. Output stays
                // isolated for `print`; only explicit sys.* writes would leak, and
                // that beats refusing to run at all.
                logger.warn("sys.modules is a {}, not a PyStringMap — sharing it instead of "
                    + "copying. Explicit sys.stdout/sys.stderr writes may not be isolated.",
                    mgr.modules == null ? "null" : mgr.modules.getClass().getName());
                state.modules = mgr.modules;
            }
        } catch (RuntimeException e) {
            logger.warn("Could not copy the module registry ({}); sharing it instead.",
                e.getMessage());
            state.modules = mgr.modules;
        }

        // The import MACHINERY, not just the already-imported modules.
        //
        // Copying sys.modules alone only carries modules the manager has ALREADY
        // imported. Resolving one it has not — a project library script the user
        // just saved and is importing for the first time — needs Ignition's own
        // importer, which lives on meta_path/path_hooks. Without these, that
        // import fails with a bare "No module named X" while the resource plainly
        // exists on disk, which reads exactly like a failed save.
        //
        // Measured 01/09/2026: a freshly saved library script was unimportable
        // until these three were carried across.
        state.path = mgr.path;
        state.meta_path = mgr.meta_path;
        state.path_hooks = mgr.path_hooks;
        // Shared deliberately: it is a cache, and sharing it means a module the
        // manager resolves later is visible to us without another round trip.
        state.path_importer_cache = mgr.path_importer_cache;
    }

    /**
     * The manager's system state, re-probed whenever the manager itself changes.
     *
     * <p>The identity check is the point: a rebuilt library arrives as a new
     * ScriptManager, and a state cached from the previous one would keep serving
     * the previous library.</p>
     */
    private PySystemState managerState(ScriptManager scriptManager) {
        PySystemState cached = managerState;
        if (cached != null && managerStateOwner == scriptManager) {
            return cached;
        }
        synchronized (this) {
            if (managerState == null || managerStateOwner != scriptManager) {
                try {
                    // runCode leaves the manager's state on THIS thread.
                    scriptManager.runCode("pass\n", scriptManager.createLocalsMap(),
                        "<script-ide-probe>");
                } catch (Exception e) {
                    // "pass" cannot fail on its own merits, so this means the
                    // manager itself is unhealthy. Read the state anyway — runCode
                    // installs it before executing, so the probe has still done its
                    // job — and let the real execution surface the problem.
                    logger.warn("Probe snippet failed while resolving the manager's "
                        + "PySystemState: {}", e.toString());
                }
                managerState = Py.getSystemState();
                managerStateOwner = scriptManager;
            }
            return managerState;
        }
    }

    /**
     * Whether a Throwable is the platform cancelling a script rather than the
     * script failing.
     *
     * <p>Matched on class name because {@code ScriptManager.ScriptCanceledError} is
     * not part of the public SDK surface and referencing it directly would bind us
     * to an internal type.</p>
     */
    static boolean isCancellation(Throwable t) {
        for (Throwable c = t; c != null; c = c.getCause()) {
            String name = c.getClass().getName();
            if (name.contains("ScriptCanceled") || name.contains("ThreadDeath")) {
                return true;
            }
            if (c.getCause() == c) {
                break;
            }
        }
        return false;
    }

    /**
     * Captures output up to a cap, then silently drops the rest.
     *
     * <p>Deliberately does NOT stop the script: a chatty loop should lose its
     * output, not be killed halfway through whatever it was doing to the gateway.</p>
     */
    static final class BoundedOutputStream extends ByteArrayOutputStream {
        private final int limit;
        private boolean truncated;

        BoundedOutputStream(int limit) {
            this.limit = limit;
        }

        boolean truncated() {
            return truncated;
        }

        @Override
        public synchronized void write(int b) {
            if (size() >= limit) {
                truncated = true;
                return;
            }
            super.write(b);
        }

        @Override
        public synchronized void write(byte[] b, int off, int len) {
            int remaining = limit - size();
            if (remaining <= 0) {
                truncated = true;
                return;
            }
            if (len > remaining) {
                truncated = true;
                super.write(b, off, remaining);
                return;
            }
            super.write(b, off, len);
        }
    }
}
