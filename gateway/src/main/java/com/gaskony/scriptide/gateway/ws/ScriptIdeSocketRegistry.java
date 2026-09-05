package com.gaskony.scriptide.gateway.ws;

import com.gaskony.scriptide.gateway.exec.ExecAudit;
import com.gaskony.scriptide.gateway.exec.ExecutionService;
import com.gaskony.scriptide.gateway.term.TerminalService;
import com.inductiveautomation.ignition.gateway.model.GatewayContext;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Static holder for the Gateway context and the set of live sockets.
 *
 * <p>It exists because the Jetty container instantiates the servlet through its
 * <b>no-arg constructor</b> — there is nowhere to inject a {@link GatewayContext}.
 * The hook publishes the context here in {@code startup()} BEFORE registering the
 * servlet, and clears it in {@code shutdown()}.</p>
 *
 * <p>Tracking open sockets is not bookkeeping for its own sake: on shutdown every
 * one must be closed, or a socket outliving the module keeps a reference to a
 * dead context. From P2 this is also what lets a redeploy cancel in-flight script
 * executions rather than orphaning them.</p>
 */
public final class ScriptIdeSocketRegistry {

    private static final Logger logger = LoggerFactory.getLogger(ScriptIdeSocketRegistry.class);

    private static volatile GatewayContext context;
    private static volatile ExecutionService executionService;
    private static volatile ExecAudit execAudit;
    private static volatile TerminalService terminalService;
    private static volatile com.gaskony.scriptide.gateway.history.RunHistory runHistory;

    private static final Set<ScriptIdeSocket> OPEN_SOCKETS = ConcurrentHashMap.newKeySet();

    private ScriptIdeSocketRegistry() { /* static holder */ }

    /** Publish the context and services. Must run before the servlet registers. */
    public static void init(GatewayContext ctx) {
        context = ctx;
        executionService = new ExecutionService(ctx);
        execAudit = new ExecAudit(ctx);
        terminalService = new TerminalService(ctx);
        runHistory = new com.gaskony.scriptide.gateway.history.RunHistory(
            ctx.getSystemManager().getDataDir().toPath());
        logger.debug("Script IDE socket registry initialised");
    }

    /** The execution pool, or null when the module is not started. */
    public static ExecutionService getExecutionService() {
        return executionService;
    }

    /** The terminal pool, or null when the module is not started. */
    public static TerminalService getTerminalService() {
        return terminalService;
    }

    /**
     * Where finished executions are kept for the user who ran them.
     *
     * <p>Distinct from {@link #getExecAudit()} and not a replacement for it: the
     * audit is the estate's record that a run HAPPENED and stores a hash rather
     * than the code, and this is the user's own scratch history and stores the
     * source and the output. Different readers, different retention.</p>
     */
    public static com.gaskony.scriptide.gateway.history.RunHistory getRunHistory() {
        return runHistory;
    }

    /** The audit recorder, or null when the module is not started. */
    public static ExecAudit getExecAudit() {
        return execAudit;
    }

    /**
     * The Gateway context, or {@code null} if the module is not started.
     *
     * <p>Callers MUST null-check. A socket can in principle survive a shutdown
     * race, and a NullPointerException inside a WebSocket callback is invisible —
     * it kills the connection with no useful log line.</p>
     */
    public static GatewayContext getContext() {
        return context;
    }

    static void register(ScriptIdeSocket socket) {
        OPEN_SOCKETS.add(socket);
    }

    static void unregister(ScriptIdeSocket socket) {
        OPEN_SOCKETS.remove(socket);
    }

    /** Number of currently open sockets — surfaced for diagnostics and tests. */
    public static int openSocketCount() {
        return OPEN_SOCKETS.size();
    }

    /** Close every open socket and drop the context. Safe to call twice. */
    public static void shutdown() {
        int count = OPEN_SOCKETS.size();
        for (ScriptIdeSocket socket : Set.copyOf(OPEN_SOCKETS)) {
            try {
                socket.closeForShutdown();
            } catch (Exception e) {
                logger.debug("Error closing socket during shutdown: {}", e.getMessage());
            }
        }
        OPEN_SOCKETS.clear();
        // Shut the pool down AFTER closing sockets, so nothing new is submitted
        // into a dying executor.
        ExecutionService service = executionService;
        if (service != null) {
            service.shutdown();
        }
        // Terminals are OS processes, not threads: leaving one behind leaves a
        // shell running as the Gateway user with nothing reading its output.
        TerminalService terminals = terminalService;
        if (terminals != null) {
            terminals.shutdown();
        }
        terminalService = null;
        executionService = null;
        execAudit = null;
        context = null;
        if (count > 0) {
            logger.info("Closed {} Script IDE socket(s) during shutdown", count);
        }
    }
}
