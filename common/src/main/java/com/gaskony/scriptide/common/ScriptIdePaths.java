package com.gaskony.scriptide.common;

/**
 * Every route, mount and servlet path string the module uses, in one place.
 *
 * <p>The Gateway exposes a module's surfaces at:</p>
 * <ul>
 *   <li>{@code /res/{MOUNT_ALIAS}/*} — static resources from the mounted folder
 *       (declared by {@code getMountedResourceFolder()}).</li>
 *   <li>{@code /data/{MOUNT_ALIAS}/*} — routes mounted via
 *       {@code mountRouteHandlers(RouteGroup)}. Route constants below are
 *       relative to that base; the platform prefixes it automatically.</li>
 *   <li>{@code /system/{servletPath}} — servlets registered through
 *       {@code WebResourceManager.addServlet(...)}. NOT under {@code /data}.</li>
 * </ul>
 *
 * <p><b>The trailing slash on the SPA URL is load-bearing.</b>
 * {@code /data/scriptide} 404s; {@code /data/scriptide/} works. That is platform
 * dispatcher behaviour, measured on web-designer.</p>
 */
public final class ScriptIdePaths {

    private ScriptIdePaths() { /* constants only */ }

    // ==================== Mount points ====================

    /** Module mount alias — used for both {@code /res/} and {@code /data/}. */
    public static final String MOUNT_ALIAS = "scriptide";

    /** Base of every mounted route. */
    public static final String DATA_BASE = "/data/" + MOUNT_ALIAS;

    /**
     * The full-page SPA landing URL. Note the mandatory trailing slash — see the
     * class Javadoc; without it the platform dispatcher returns 404.
     */
    public static final String SPA_LAUNCH_TARGET = DATA_BASE + "/";

    /** Classpath-served launcher stub backing the Gateway home-page nav tile. */
    public static final String LAUNCHER_JS_RESOURCE_PATH = "/res/" + MOUNT_ALIAS + "/launcher.js";

    // ==================== Routes ====================

    /**
     * Catch-all splat for the SPA shell and its hashed assets.
     *
     * <p><b>MUST be mounted LAST.</b> {@code RouteGroupImpl.findMatchingRoute}
     * streams routes in insertion order, filters by method then path, and takes
     * {@code findFirst()} — first match wins, with no most-specific preference.
     * {@code "/*"} matches everything, so mounting it before any {@code /api/...}
     * route silently shadows every one of them.
     * {@code RouteMountOrderTest} asserts this.</p>
     */
    public static final String ROUTE_SPA_CATCH_ALL = "/*";

    /**
     * Self-describing session probe: {@code GET /api/auth/session}.
     *
     * <p>Mounted OPEN so it can answer {@code {authenticated:false}} for anonymous
     * callers rather than 401 — the SPA uses it to decide between rendering the
     * IDE and rendering a sign-in notice.</p>
     */
    public static final String ROUTE_AUTH_SESSION = "/api/auth/session";

    /** {@code GET /api/projects} — the projects this gateway can edit. */
    public static final String ROUTE_PROJECTS = "/api/projects";

    /**
     * {@code GET /api/scripts?project=X} — the whole editable script tree for one
     * project: project library packages plus every gateway event script, each with
     * its data keys, resource signature and inheritance origin.
     */
    public static final String ROUTE_SCRIPTS = "/api/scripts";

    /**
     * {@code GET|POST|DELETE /api/scripts/content/:path?project=X} — read, write
     * or delete one script body.
     *
     * <p>{@code :path} is {@code <moduleId>/<typeId>/<folder/name>},
     * URL-encoded into ONE route segment (slashes become {@code %2F}) because
     * RouteGroup matches a single segment. A two-segment value addresses a type's
     * singleton, which is how startup/shutdown/update are stored.</p>
     *
     * <p>POST creates when the path does not yet exist in the project and modifies
     * when it does; DELETE removes it. Both require Administrator, a CSRF token
     * and — for anything but a create — an {@code If-Match} signature.</p>
     */
    public static final String ROUTE_SCRIPT_CONTENT = "/api/scripts/content/:path";

    /**
     * {@code GET|POST /api/scripts/attributes/:path?project=X} — the resource's
     * {@code resource.json} attributes (a timer's delay, a handler's threading).
     *
     * <p>A separate route because the content write only calls {@code putData};
     * attributes survive untouched through {@code toBuilder()} and need
     * {@code putAttribute}, which the SDK keeps as a genuinely separate call.</p>
     */
    public static final String ROUTE_SCRIPT_ATTRIBUTES = "/api/scripts/attributes/:path";

    /**
     * {@code GET|POST /api/webdev/config/:path?project=X} — a Web Dev endpoint's
     * per-method settings.
     *
     * <p>Separate from the attributes route because a Web Dev resource has NO
     * editable {@code resource.json} attributes. Everything the Designer shows
     * for an endpoint — enabled, require-auth, require-https, required roles,
     * user source, retry count, per HTTP method — is inside a {@code config.json}
     * DATA FILE. Measured on a real gateway 01/09/2026.</p>
     */
    public static final String ROUTE_WEBDEV_CONFIG = "/api/webdev/config/:path";

    // ==================== Servlets (NOT under /data) ====================

    /**
     * Path spec for the combined LSP + execution WebSocket, registered via
     * {@code WebResourceManager.addServlet(...)} in the hook's {@code startup()}.
     * Resolves publicly to {@code /system/scriptide}.
     *
     * <p>It is a servlet, not a {@code RouteGroup} route, because {@code RouteGroup}
     * has no protocol-upgrade path. Spike S1 could not verify that a NEW alias
     * resolves as expected (that needs a built module) — it is the one unproven
     * assumption in the design, and the deploy gate's socket check exists for it.</p>
     */
    public static final String SOCKET_SERVLET_PATH = MOUNT_ALIAS;

    /** Public URL the servlet above resolves to. */
    public static final String SOCKET_PUBLIC_PATH = "/system/" + SOCKET_SERVLET_PATH;
}
