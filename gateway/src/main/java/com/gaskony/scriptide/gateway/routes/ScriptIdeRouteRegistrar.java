package com.gaskony.scriptide.gateway.routes;

import com.gaskony.scriptide.common.ScriptIdePaths;
import com.gaskony.scriptide.gateway.security.SessionSecurity;
import com.inductiveautomation.ignition.gateway.dataroutes.AccessControlStrategy;
import com.inductiveautomation.ignition.gateway.dataroutes.HttpMethod;
import com.inductiveautomation.ignition.gateway.dataroutes.RouteGroup;
import com.inductiveautomation.ignition.gateway.model.GatewayContext;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Registers every Gateway HTTP route the module serves.
 *
 * <p>Convention, matching the rest of the suite:
 * {@code newRoute(path).type(...).method(...).accessControl(...).handler(...).mount()},
 * with {@code .method(HttpMethod.POST)} set EXPLICITLY on every POST route —
 * omitting it silently defaults to GET, which is a documented past regression in
 * this estate.</p>
 *
 * <p><b>Ordering is a correctness property, not a style preference.</b>
 * {@code RouteGroupImpl.findMatchingRoute} streams routes in insertion order,
 * filters by method and path, then takes {@code findFirst()}. There is no
 * most-specific-wins. The {@code "/*"} SPA catch-all matches every path, so it
 * MUST be mounted last; mounted earlier it shadows every API route and the only
 * symptom is that the API starts returning HTML. {@code RouteMountOrderTest}
 * asserts the catch-all is mounted last.</p>
 *
 * <p>The LSP/execution WebSocket is deliberately NOT registered here.
 * {@code RouteGroup} has no protocol-upgrade path, so it is a Jetty servlet
 * registered in the hook's {@code startup()} — see {@code ScriptIdeModuleHook}.</p>
 */
public class ScriptIdeRouteRegistrar {

    private static final Logger logger = LoggerFactory.getLogger(ScriptIdeRouteRegistrar.class);

    private final SpaAssetRouteHandler spaAssetRouteHandler;
    private final AuthRouteHandler authRouteHandler;
    private final ScriptResourceRouteHandler scriptResourceRouteHandler;
    private final ScriptAttributesRouteHandler scriptAttributesRouteHandler;
    private final WebDevConfigRouteHandler webDevConfigRouteHandler;
    private final NamedQueryRouteHandler namedQueryRouteHandler;
    private final NamedQueryTestRouteHandler namedQueryTestRouteHandler;

    public ScriptIdeRouteRegistrar(GatewayContext context) {
        this.spaAssetRouteHandler = new SpaAssetRouteHandler();
        this.authRouteHandler = new AuthRouteHandler();
        // context is null only in the mount-order unit test, which never invokes a
        // handler — it just records the paths and their order.
        var projectManager = context == null ? null : context.getProjectManager();
        this.scriptResourceRouteHandler = new ScriptResourceRouteHandler(projectManager);
        this.scriptAttributesRouteHandler =
            new ScriptAttributesRouteHandler(projectManager, scriptResourceRouteHandler);
        this.webDevConfigRouteHandler = new WebDevConfigRouteHandler(projectManager);
        this.namedQueryRouteHandler = new NamedQueryRouteHandler(projectManager, context);
        // The execution service and the audit recorder are SUPPLIERS, not values.
        // Both are published by the hook into ScriptIdeSocketRegistry at startup
        // and cleared at shutdown, so a route that captured them here would hold a
        // reference to a dead service after a redeploy — and the null a supplier
        // returns is what the test route turns into a clean 503.
        this.namedQueryTestRouteHandler = new NamedQueryTestRouteHandler(projectManager,
            com.gaskony.scriptide.gateway.ws.ScriptIdeSocketRegistry::getExecutionService,
            com.gaskony.scriptide.gateway.ws.ScriptIdeSocketRegistry::getExecAudit);
    }

    /**
     * Mounts every route on the supplied group.
     *
     * <p>Add new {@code /api/...} routes ABOVE the catch-all block at the bottom.
     * Never below it.</p>
     */
    public void mountRoutes(RouteGroup routes) {
        AccessControlStrategy open = SessionSecurity.publicAccess();

        // ==================== Auth (open, self-describing) ====================
        // Must answer for anonymous callers, so the SPA can distinguish
        // "not signed in" from "backend broken".

        routes.newRoute(ScriptIdePaths.ROUTE_AUTH_SESSION)
            .type(RouteGroup.TYPE_JSON)
            .accessControl(open)
            .handler(authRouteHandler::session)
            .mount();

        // ==================== Scripts (read: authed, write: admin) ====================
        // Reads are open to any authenticated user so a non-admin still gets the
        // full language intelligence; only mutation needs Administrator.

        AccessControlStrategy authed = SessionSecurity.requireAuthenticated();
        AccessControlStrategy admin = SessionSecurity.requireAdministrator();

        routes.newRoute(ScriptIdePaths.ROUTE_PROJECTS)
            .type(RouteGroup.TYPE_JSON)
            .accessControl(authed)
            .handler(scriptResourceRouteHandler::projects)
            .mount();

        routes.newRoute(ScriptIdePaths.ROUTE_SCRIPTS)
            .type(RouteGroup.TYPE_JSON)
            .accessControl(authed)
            .handler(scriptResourceRouteHandler::tree)
            .mount();

        // text/plain: a script body is Python source, not JSON.
        routes.newRoute(ScriptIdePaths.ROUTE_SCRIPT_CONTENT)
            .type(RouteGroup.TYPE_PLAIN_TEXT)
            .accessControl(authed)
            .handler(scriptResourceRouteHandler::read)
            .mount();

        // .method(POST) is set EXPLICITLY — omitting it silently defaults to GET,
        // and the route then shadows the read above instead of accepting writes.
        routes.newRoute(ScriptIdePaths.ROUTE_SCRIPT_CONTENT)
            .method(HttpMethod.POST)
            .type(RouteGroup.TYPE_JSON)
            .accessControl(admin)
            .handler(scriptResourceRouteHandler::write)
            .mount();

        // Same explicit-method rule as the POST above. DELETE is admin-gated and
        // requires If-Match, so it cannot be reached by a stray link or a GET.
        routes.newRoute(ScriptIdePaths.ROUTE_SCRIPT_CONTENT)
            .method(HttpMethod.DELETE)
            .type(RouteGroup.TYPE_JSON)
            .accessControl(admin)
            .handler(scriptResourceRouteHandler::delete)
            .mount();

        routes.newRoute(ScriptIdePaths.ROUTE_SCRIPT_ATTRIBUTES)
            .type(RouteGroup.TYPE_JSON)
            .accessControl(authed)
            .handler(scriptAttributesRouteHandler::read)
            .mount();

        routes.newRoute(ScriptIdePaths.ROUTE_SCRIPT_ATTRIBUTES)
            .method(HttpMethod.POST)
            .type(RouteGroup.TYPE_JSON)
            .accessControl(admin)
            .handler(scriptAttributesRouteHandler::write)
            .mount();

        // ==================== Web Dev endpoint config ====================
        // Its own route because a Web Dev endpoint has NO editable resource.json
        // attributes — everything the Designer shows lives in a config.json data
        // file. See WebDevConfigRouteHandler.

        routes.newRoute(ScriptIdePaths.ROUTE_WEBDEV_CONFIG)
            .type(RouteGroup.TYPE_JSON)
            .accessControl(authed)
            .handler(webDevConfigRouteHandler::read)
            .mount();

        routes.newRoute(ScriptIdePaths.ROUTE_WEBDEV_CONFIG)
            .method(HttpMethod.POST)
            .type(RouteGroup.TYPE_JSON)
            .accessControl(admin)
            .handler(webDevConfigRouteHandler::write)
            .mount();

        // ==================== Named queries ====================
        // A named query and the Python that calls it are one piece of work, which
        // is the whole point of batch E. Same gate split as the scripts above:
        // reads authenticated, writes Administrator.

        routes.newRoute(ScriptIdePaths.ROUTE_NAMED_QUERIES)
            .type(RouteGroup.TYPE_JSON)
            .accessControl(authed)
            .handler(namedQueryRouteHandler::list)
            .mount();

        // text/plain: a named query's body is SQL, not JSON.
        routes.newRoute(ScriptIdePaths.ROUTE_NAMED_QUERY_CONTENT)
            .type(RouteGroup.TYPE_PLAIN_TEXT)
            .accessControl(authed)
            .handler(namedQueryRouteHandler::readContent)
            .mount();

        // .method(POST) set EXPLICITLY — omitting it silently defaults to GET, and
        // the route then shadows the read above instead of accepting writes.
        routes.newRoute(ScriptIdePaths.ROUTE_NAMED_QUERY_CONTENT)
            .method(HttpMethod.POST)
            .type(RouteGroup.TYPE_JSON)
            .accessControl(admin)
            .handler(namedQueryRouteHandler::writeContent)
            .mount();

        routes.newRoute(ScriptIdePaths.ROUTE_NAMED_QUERY_CONTENT)
            .method(HttpMethod.DELETE)
            .type(RouteGroup.TYPE_JSON)
            .accessControl(admin)
            .handler(namedQueryRouteHandler::delete)
            .mount();

        routes.newRoute(ScriptIdePaths.ROUTE_NAMED_QUERY_SETTINGS)
            .type(RouteGroup.TYPE_JSON)
            .accessControl(authed)
            .handler(namedQueryRouteHandler::readSettings)
            .mount();

        routes.newRoute(ScriptIdePaths.ROUTE_NAMED_QUERY_SETTINGS)
            .method(HttpMethod.POST)
            .type(RouteGroup.TYPE_JSON)
            .accessControl(admin)
            .handler(namedQueryRouteHandler::writeSettings)
            .mount();

        routes.newRoute(ScriptIdePaths.ROUTE_NAMED_QUERY_RENAME)
            .method(HttpMethod.POST)
            .type(RouteGroup.TYPE_JSON)
            .accessControl(admin)
            .handler(namedQueryRouteHandler::rename)
            .mount();

        // Administrator, not authed: a test-run is arbitrary SQL against a live
        // database and must not have a softer gate than running the equivalent
        // Python in the console. The handler re-checks ExecPolicy per request for
        // the same reason the exec socket does.
        routes.newRoute(ScriptIdePaths.ROUTE_NAMED_QUERY_TEST)
            .method(HttpMethod.POST)
            .type(RouteGroup.TYPE_JSON)
            .accessControl(admin)
            .handler(namedQueryTestRouteHandler::test)
            .mount();

        // ==================== SPA static assets (catch-all) ====================
        // MUST BE LAST — see the class Javadoc. Open access: the shell has to load
        // so the Gateway login can be presented; the API routes above enforce auth.
        // As defence in depth the handler itself 404s any unmatched /api/... path
        // rather than leaking the index.html shell to an API client.

        routes.newRoute(ScriptIdePaths.ROUTE_SPA_CATCH_ALL)
            .type(RouteGroup.TYPE_TEXT_HTML)
            .accessControl(AccessControlStrategy.OPEN_ROUTE)
            .handler(spaAssetRouteHandler::handle)
            .mount();

        logger.info("Script IDE routes registered");
    }
}
