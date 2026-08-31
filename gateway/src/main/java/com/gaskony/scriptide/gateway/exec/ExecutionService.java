package com.gaskony.scriptide.gateway.exec;

import com.inductiveautomation.ignition.common.script.ScriptManager;
import com.inductiveautomation.ignition.gateway.model.GatewayContext;
import org.python.core.PyObject;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Runs user scripts on a pool this module owns, and stops them as best it can.
 *
 * <h2>Why a dedicated pool</h2>
 *
 * <p>Never {@code context.getExecutorService()}. One user's {@code while True:}
 * on the gateway's own pool takes the gateway down — not this module, the gateway.
 * A bounded private pool means the worst case is that script execution stops
 * working while everything else keeps running.</p>
 *
 * <h2>Stop is best-effort, and the UI must say so</h2>
 *
 * <p>{@code ScriptManager.interrupt(tid)} installs a trace function that fires at
 * the next Python trace point. Measured in spike S1: a 15 s busy loop interrupted
 * at 3 s stopped at <b>3.0 s</b>; a {@code time.sleep(10)} interrupted at 2 s ran
 * the full <b>10.06 s</b>. Anything blocked inside a Java call — a JDBC query, a
 * socket read, {@code system.tag.readBlocking} with a long timeout — cannot be
 * stopped that way.</p>
 *
 * <p>Hence the ladder in {@link #requestStop}: interrupt, then
 * {@code Thread.interrupt()} (which does unblock sleeps and interruptible I/O),
 * then give up and mark the execution ABANDONED. You cannot kill a Java thread.
 * An abandoned thread permanently costs a pool slot, so it is counted and
 * surfaced rather than quietly tolerated.</p>
 */
public final class ExecutionService {

    private static final Logger logger = LoggerFactory.getLogger(ExecutionService.class);

    /** How long to wait after a Jython interrupt before escalating. */
    private static final long ESCALATE_TO_THREAD_INTERRUPT_MS = 5_000;

    /** How long after that before the execution is declared abandoned. */
    private static final long ESCALATE_TO_ABANDON_MS = 30_000;

    private final GatewayContext context;
    private final ThreadPoolExecutor pool;
    private final ScheduledExecutorService watchdog;

    /** In-flight executions by id. */
    private final Map<String, RunningExecution> running = new ConcurrentHashMap<>();

    /** One execution at a time per session, so nobody can fill the pool alone. */
    private final Map<String, String> executionBySession = new ConcurrentHashMap<>();

    private final Map<String, PrivateStateRunner> runnersByProject = new ConcurrentHashMap<>();

    private final AtomicLong abandonedCount = new AtomicLong();
    private final AtomicLong completedCount = new AtomicLong();

    public ExecutionService(GatewayContext context) {
        this.context = context;
        int size = ExecPolicy.maxConcurrent();
        ThreadFactory factory = new ThreadFactory() {
            private final AtomicInteger n = new AtomicInteger(1);

            @Override
            public Thread newThread(Runnable r) {
                Thread t = new Thread(r, "script-ide-exec-" + n.getAndIncrement());
                t.setDaemon(true);
                // Slightly below normal: a runaway user script should lose to the
                // gateway's own work when the CPU is contended.
                t.setPriority(Thread.NORM_PRIORITY - 1);
                return t;
            }
        };
        this.pool = new ThreadPoolExecutor(size, size, 0L, TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(Math.max(2, size * 2)), factory,
            new ThreadPoolExecutor.AbortPolicy());
        this.watchdog = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "script-ide-exec-watchdog");
            t.setDaemon(true);
            return t;
        });
        logger.info("Script IDE execution pool started with {} thread(s)", size);
    }

    /** One in-flight execution. */
    static final class RunningExecution {
        final String id;
        final String username;
        final String sessionId;
        final long startedAtMillis;
        volatile Thread thread;
        volatile boolean stopRequested;
        volatile boolean abandoned;

        RunningExecution(String id, String username, String sessionId) {
            this.id = id;
            this.username = username;
            this.sessionId = sessionId;
            this.startedAtMillis = System.currentTimeMillis();
        }
    }

    /** Thrown when the pool or the per-session limit refuses a request. */
    public static final class RejectedException extends RuntimeException {
        private static final long serialVersionUID = 1L;

        RejectedException(String message) {
            super(message);
        }
    }

    /**
     * Submit a script for execution and wait for it, up to the configured timeout.
     *
     * <p>Blocking by design: the caller is a WebSocket frame handler that wants a
     * result to send back, and the pool is what provides the isolation.</p>
     */
    public PrivateStateRunner.Outcome execute(String executionId, String project, String source,
                                              String fileName, PyObject locals,
                                              String username, String sessionId)
            throws InterruptedException {

        String previous = executionBySession.putIfAbsent(sessionId, executionId);
        if (previous != null) {
            throw new RejectedException(
                "You already have a script running. Stop it before starting another.");
        }

        RunningExecution execution = new RunningExecution(executionId, username, sessionId);
        running.put(executionId, execution);

        try {
            var future = pool.submit(() -> {
                execution.thread = Thread.currentThread();
                return runnerFor(project).run(source, fileName, locals);
            });

            long timeout = ExecPolicy.timeoutSeconds();
            try {
                return future.get(timeout, TimeUnit.SECONDS);
            } catch (java.util.concurrent.TimeoutException e) {
                logger.warn("Execution {} by '{}' exceeded {}s; stopping it",
                    executionId, username, timeout);
                requestStop(executionId);
                // Give the ladder a moment to land before reporting back.
                try {
                    return future.get(ESCALATE_TO_THREAD_INTERRUPT_MS, TimeUnit.MILLISECONDS);
                } catch (Exception ignored) {
                    return new PrivateStateRunner.Outcome("", "", false,
                        new IllegalStateException("Script exceeded the " + timeout
                            + "s time limit and was stopped."), true);
                }
            } catch (java.util.concurrent.ExecutionException e) {
                Throwable cause = e.getCause() == null ? e : e.getCause();
                return new PrivateStateRunner.Outcome("", "", false, cause,
                    PrivateStateRunner.isCancellation(cause));
            }
        } catch (RejectedExecutionException e) {
            throw new RejectedException(
                "Too many scripts are running on this gateway right now. Try again shortly.");
        } finally {
            running.remove(executionId);
            executionBySession.remove(sessionId, executionId);
            completedCount.incrementAndGet();
        }
    }

    /**
     * Ask an execution to stop. Best-effort — see the class Javadoc.
     *
     * @return a human-readable description of what was attempted, for the UI
     */
    public String requestStop(String executionId) {
        RunningExecution execution = running.get(executionId);
        if (execution == null) {
            return "That script is no longer running.";
        }
        execution.stopRequested = true;
        Thread thread = execution.thread;
        if (thread == null) {
            return "The script has not started yet; it will be stopped when it does.";
        }

        // Step 1 — the Jython interrupt. Fires at the next Python trace point.
        try {
            ScriptManager.interrupt(thread.getId());
        } catch (RuntimeException e) {
            logger.debug("ScriptManager.interrupt failed for {}: {}", executionId, e.getMessage());
        }

        // Steps 2 and 3 run on the watchdog so the caller's frame handler returns
        // immediately — the UI needs to say "Stopping…" now, not in 35 seconds.
        watchdog.schedule(() -> {
            if (!running.containsKey(executionId)) {
                return;
            }
            // Step 2 — unblocks Thread.sleep and interruptible I/O, which the
            // Jython interrupt cannot touch.
            logger.info("Execution {} did not stop at a trace point; interrupting its thread",
                executionId);
            thread.interrupt();

            watchdog.schedule(() -> {
                RunningExecution still = running.get(executionId);
                if (still == null) {
                    return;
                }
                // Step 3 — there is no step 4. A Java thread cannot be killed.
                still.abandoned = true;
                abandonedCount.incrementAndGet();
                logger.warn("Execution {} started by '{}' could not be stopped and has been "
                        + "ABANDONED. It still holds a pool thread. Abandoned total: {}.",
                    executionId, still.username, abandonedCount.get());
            }, ESCALATE_TO_ABANDON_MS - ESCALATE_TO_THREAD_INTERRUPT_MS, TimeUnit.MILLISECONDS);
        }, ESCALATE_TO_THREAD_INTERRUPT_MS, TimeUnit.MILLISECONDS);

        return "Stopping… waiting for the script to reach a stopping point. "
            + "A script blocked in a database or network call cannot be interrupted.";
    }

    /** Number of executions that could not be stopped. Non-zero is worth alerting on. */
    public long abandonedCount() {
        return abandonedCount.get();
    }

    /** A snapshot of one in-flight execution, for the Running Scripts panel. */
    public record ExecutionStatus(String id, String username, long runningForMillis,
                                  boolean stopRequested, boolean abandoned) {
    }

    /**
     * What is running right now.
     *
     * <p>This is what makes a best-effort Stop honest: a user who pressed Stop can
     * see that their script is still going and that we know it, rather than being
     * shown a button that appeared to work and did nothing.</p>
     */
    public List<ExecutionStatus> currentExecutions() {
        long now = System.currentTimeMillis();
        List<ExecutionStatus> out = new ArrayList<>(running.size());
        for (RunningExecution e : running.values()) {
            out.add(new ExecutionStatus(e.id, e.username, now - e.startedAtMillis,
                e.stopRequested, e.abandoned));
        }
        return out;
    }

    /** Number of executions currently in flight. */
    public int runningCount() {
        return running.size();
    }

    /** Total executions that have finished. */
    public long completedCount() {
        return completedCount.get();
    }

    /**
     * A runner per project, so each uses that project's own ScriptManager and
     * therefore sees that project's script library.
     */
    private PrivateStateRunner runnerFor(String project) {
        // The runner is cached; the MANAGER it uses is not — it holds a supplier and
        // resolves the project's current ScriptManager on every run, so a script the
        // user just saved is visible immediately. See PrivateStateRunner.
        return runnersByProject.computeIfAbsent(project, p ->
            new PrivateStateRunner(() -> context.getProjectManager().getProjectScriptManager(p)));
    }

    /** A fresh locals map for the given project — the REPL state of one console. */
    public PyObject newLocals(String project) {
        return context.getProjectManager().getProjectScriptManager(project).createLocalsMap();
    }

    /** Shut the pool down, without waiting forever on a script that will not stop. */
    public void shutdown() {
        watchdog.shutdownNow();
        pool.shutdownNow();
        try {
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                logger.warn("Execution pool did not terminate within 5s — {} execution(s) "
                    + "were still running.", running.size());
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        running.clear();
        executionBySession.clear();
        runnersByProject.clear();
        logger.info("Script IDE execution pool shut down");
    }
}
