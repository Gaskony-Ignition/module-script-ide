package com.gaskony.scriptide.gateway.security;

import com.inductiveautomation.ignition.common.auth.web.WebAuthUser;
import com.inductiveautomation.ignition.gateway.dataroutes.AccessControlStrategy;
import com.inductiveautomation.ignition.gateway.dataroutes.RequestContext;
import com.inductiveautomation.ignition.gateway.dataroutes.RouteAccess;
import com.inductiveautomation.ignition.gateway.dataroutes.RouteMounterContext;
import com.inductiveautomation.ignition.gateway.web.session.WebUiSession;
import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Optional;

/**
 * The module's single security primitive, used by BOTH the REST route strategies
 * and the WebSocket upgrade handshake.
 *
 * <p>There is deliberately only one of these. web-designer's own
 * {@code HandlerSupport.securityFor} Javadoc records what happens when a security
 * check gets duplicated: the two copies drift, and the copy that does not get the
 * fix is the one that silently keeps letting people through.</p>
 *
 * <h2>Why there is no actor fallback</h2>
 *
 * <p>web-designer's {@code AccessControl} grants any non-session caller that
 * presents a non-empty {@code RequestContext.getActor()}, and its own class
 * Javadoc flags this MUST-VALIDATE: <i>"confirm browser requests cannot spoof an
 * actor that would bypass the session check"</i>. That question was never
 * resolved.</p>
 *
 * <p>This module drops the fallback entirely, on both reads and writes. Two
 * reasons, and they are decisions rather than omissions:</p>
 * <ol>
 *   <li>What sits behind this gate is <b>arbitrary code execution in the Gateway
 *       JVM</b>. An unvalidated bypass has no business in front of that.</li>
 *   <li>There is no legitimate non-browser caller. Nothing but the SPA talks to
 *       this module — there is no RPC surface and no scripted client.</li>
 * </ol>
 *
 * <p>If a scripted caller is ever genuinely needed, add a Gateway API token check,
 * not an actor string.</p>
 */
public final class SessionSecurity {

    private static final Logger logger = LoggerFactory.getLogger(SessionSecurity.class);

    /** Holding this role is what permits script execution and resource writes. */
    public static final String ADMIN_ROLE = "Administrator";

    private SessionSecurity() { /* utility class */ }

    // ==================== Shared primitives ====================

    /**
     * Resolve the authenticated user behind a request, if there is one.
     *
     * <p>Never throws — a lookup failure is treated as "anonymous", which is the
     * restrictive answer.</p>
     */
    public static Optional<WebAuthUser> authenticatedUser(RequestContext requestContext) {
        try {
            Optional<? extends WebUiSession> sessionOpt = WebUiSession.find(requestContext);
            if (sessionOpt.isEmpty()) {
                return Optional.empty();
            }
            return sessionOpt.get().getUserContext().getWebAuthUser().map(u -> (WebAuthUser) u);
        } catch (Exception e) {
            logger.debug("Session lookup failed; treating caller as anonymous: {}", e.getMessage());
            return Optional.empty();
        }
    }

    /** True when the given user holds the {@code Administrator} role. */
    public static boolean isAdministrator(WebAuthUser user) {
        return user.getRoles().stream().anyMatch(ADMIN_ROLE::equalsIgnoreCase);
    }

    /**
     * Same-origin check for a WebSocket upgrade.
     *
     * <p>WebSockets get no CORS preflight, so the {@code Origin} header is the
     * only thing standing between a logged-in user's browser and a hostile page
     * opening an authenticated socket to this module. An ABSENT Origin is allowed
     * (non-browser clients such as the deploy gate's own check do not send one);
     * a PRESENT Origin whose host differs from {@code Host} is rejected.</p>
     */
    public static boolean isSameOrigin(HttpServletRequest request) {
        String origin = request.getHeader("Origin");
        if (origin == null || origin.isBlank()) {
            return true;
        }
        String host = request.getHeader("Host");
        if (host == null || host.isBlank()) {
            return false;
        }
        try {
            java.net.URI originUri = java.net.URI.create(origin);
            String originAuthority = originUri.getPort() < 0
                ? originUri.getHost()
                : originUri.getHost() + ":" + originUri.getPort();
            if (originAuthority == null) {
                return false;
            }
            return originAuthority.equalsIgnoreCase(host);
        } catch (IllegalArgumentException e) {
            logger.debug("Rejecting WebSocket upgrade with unparseable Origin: {}", origin);
            return false;
        }
    }

    // ==================== Route strategies ====================

    /**
     * Grants any authenticated Gateway user, of any role. Anonymous callers get
     * {@link RouteAccess#UNAUTHORIZED} (HTTP 401). No actor fallback.
     */
    public static AccessControlStrategy requireAuthenticated() {
        return new AccessControlStrategy() {
            @Override
            public RouteAccess canAccess(RequestContext requestContext) {
                return authenticatedUser(requestContext).isPresent()
                    ? RouteAccess.GRANTED
                    : RouteAccess.UNAUTHORIZED;
            }

            @Override
            public Optional<String> getWwwAuthenticateHeader(RequestContext requestContext) {
                return Optional.of("Bearer realm=\"Ignition Gateway\"");
            }

            @Override
            public void validate(RouteMounterContext routeMounterContext) {
                // nothing to validate at mount time
            }
        };
    }

    /**
     * Grants only {@code Administrator}s. An authenticated non-admin gets
     * {@link RouteAccess#FORBIDDEN} (403); an anonymous caller gets 401. No actor
     * fallback — see the class Javadoc.
     */
    public static AccessControlStrategy requireAdministrator() {
        return new AccessControlStrategy() {
            @Override
            public RouteAccess canAccess(RequestContext requestContext) {
                Optional<WebAuthUser> userOpt = authenticatedUser(requestContext);
                if (userOpt.isEmpty()) {
                    return RouteAccess.UNAUTHORIZED;
                }
                if (isAdministrator(userOpt.get())) {
                    return RouteAccess.GRANTED;
                }
                logger.debug("Access denied: authenticated user lacks the {} role", ADMIN_ROLE);
                return RouteAccess.FORBIDDEN;
            }

            @Override
            public Optional<String> getWwwAuthenticateHeader(RequestContext requestContext) {
                return Optional.of("Bearer realm=\"Ignition Gateway\"");
            }

            @Override
            public void validate(RouteMounterContext routeMounterContext) {
                // nothing to validate at mount time
            }
        };
    }

    /**
     * Explicit "no auth" strategy, named for intent. Used only by the session
     * probe, which must answer for anonymous callers rather than 401, and by the
     * SPA shell, which must load so the Gateway login can be presented.
     */
    public static AccessControlStrategy publicAccess() {
        return new AccessControlStrategy() {
            @Override
            public RouteAccess canAccess(RequestContext requestContext) {
                return RouteAccess.GRANTED;
            }

            @Override
            public Optional<String> getWwwAuthenticateHeader(RequestContext requestContext) {
                return Optional.empty();
            }

            @Override
            public void validate(RouteMounterContext routeMounterContext) {
                // nothing to validate at mount time
            }
        };
    }
}
