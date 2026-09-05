package com.gaskony.scriptide.gateway.routes;

import com.gaskony.scriptide.gateway.runtime.ScriptErrors;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.inductiveautomation.ignition.gateway.dataroutes.RequestContext;
import com.inductiveautomation.ignition.gateway.model.GatewayContext;
import jakarta.servlet.http.HttpServletResponse;

import java.io.IOException;
import java.util.List;

/**
 * What this project's scripts are actually throwing, right now.
 *
 * <p>Authenticated rather than administrator-gated, matching every other READ in
 * this module: a non-administrator already sees the source of every script
 * through the tree, and gateway log lines about it are less than that. The
 * window is capped in {@link ScriptErrors} rather than trusted from the query,
 * so a caller cannot turn this into "scan the whole log".</p>
 */
public class RuntimeErrorsRouteHandler {

    private final GatewayContext context;

    public RuntimeErrorsRouteHandler(GatewayContext context) {
        this.context = context;
    }

    /** GET /api/runtime/errors?project=&minutes= */
    public Object errors(RequestContext req, HttpServletResponse resp) throws IOException {
        String project = req.getParameter("project");
        if (project == null || project.isBlank()) {
            return HandlerSupport.error(resp, HttpServletResponse.SC_BAD_REQUEST,
                "Missing required 'project' parameter");
        }
        long window = ScriptErrors.DEFAULT_WINDOW_MILLIS;
        String minutes = req.getParameter("minutes");
        if (minutes != null && !minutes.isBlank()) {
            try {
                window = Long.parseLong(minutes.trim()) * 60_000L;
            } catch (NumberFormatException e) {
                return HandlerSupport.error(resp, HttpServletResponse.SC_BAD_REQUEST,
                    "'minutes' must be a whole number");
            }
        }

        List<ScriptErrors.ScriptError> found =
            ScriptErrors.forProject(context, project, window);
        JsonArray items = new JsonArray();
        for (ScriptErrors.ScriptError error : found) {
            JsonObject item = new JsonObject();
            item.addProperty("logger", error.loggerName());
            item.addProperty("level", error.level());
            item.addProperty("message", error.message());
            item.addProperty("lastSeen", error.lastSeen());
            item.addProperty("count", error.count());
            if (error.exception() != null) {
                item.addProperty("exception", error.exception());
            }
            items.add(item);
        }
        JsonObject out = new JsonObject();
        out.add("errors", items);
        out.addProperty("windowMinutes", window / 60_000L);
        // Stated so the panel can say what it is showing. "What the gateway
        // logged ABOUT this project" is not the same claim as "errors this
        // project's scripts caused", and the UI must not imply the stronger one
        // — see the class comment on ScriptErrors for why the weaker rule is
        // the honest one available.
        out.addProperty("matchedBy", "project name in the log message or logger");
        return out;
    }
}
