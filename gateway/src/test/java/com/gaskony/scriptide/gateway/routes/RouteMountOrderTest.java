package com.gaskony.scriptide.gateway.routes;

import com.gaskony.scriptide.common.ScriptIdePaths;
import com.inductiveautomation.ignition.gateway.dataroutes.RouteGroup;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import java.util.ArrayList;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;

/**
 * Guards the one ordering property that is a correctness bug rather than a style
 * preference.
 *
 * <p>{@code RouteGroupImpl.findMatchingRoute} streams routes in INSERTION order,
 * filters by method and path, then takes {@code findFirst()}. There is no
 * most-specific-wins rule. So the {@code "/*"} catch-all, which matches every
 * path, must be mounted after every {@code /api/...} route.</p>
 *
 * <p>Get it wrong and there is no error anywhere — the API simply starts
 * returning the HTML shell instead of JSON, which presents as a baffling
 * client-side parse failure a long way from the cause.</p>
 */
class RouteMountOrderTest {

    /** Records the path of every route mounted, in order. */
    private static List<String> recordMountedPaths() {
        List<String> mounted = new ArrayList<>();
        RouteGroup routes = Mockito.mock(RouteGroup.class);

        Mockito.when(routes.newRoute(anyString())).thenAnswer(invocation -> {
            String path = invocation.getArgument(0);
            // RETURNS_SELF covers the whole fluent chain (type/method/accessControl/
            // handler/...), so this mock does not have to track the builder's API.
            RouteGroup.RouteMounter mounter =
                Mockito.mock(RouteGroup.RouteMounter.class, Mockito.RETURNS_SELF);
            // mount() is the commit point — record only when a route is really mounted.
            Mockito.doAnswer(ignored -> {
                mounted.add(path);
                return null;
            }).when(mounter).mount();
            return mounter;
        });

        new ScriptIdeRouteRegistrar(null).mountRoutes(routes);
        return mounted;
    }

    @Test
    @DisplayName("the SPA catch-all is mounted LAST, so it cannot shadow the API")
    void catchAllIsMountedLast() {
        List<String> mounted = recordMountedPaths();

        assertThat(mounted)
            .as("no routes were recorded — the test's RouteGroup mock has drifted "
                + "from the registrar and is asserting nothing")
            .isNotEmpty();

        assertThat(mounted.get(mounted.size() - 1))
            .as("the \"/*\" splat must be mounted last; first-match-wins means "
                + "anything after it is unreachable")
            .isEqualTo(ScriptIdePaths.ROUTE_SPA_CATCH_ALL);
    }

    @Test
    @DisplayName("every API route is mounted before the catch-all")
    void apiRoutesPrecedeTheCatchAll() {
        List<String> mounted = recordMountedPaths();
        int catchAllIndex = mounted.indexOf(ScriptIdePaths.ROUTE_SPA_CATCH_ALL);

        assertThat(catchAllIndex).as("catch-all route was never mounted").isGreaterThanOrEqualTo(0);

        List<String> apiRoutes = mounted.stream().filter(p -> p.startsWith("/api/")).toList();
        assertThat(apiRoutes)
            .as("no /api routes mounted — either the registrar changed or the mock broke")
            .isNotEmpty();

        for (String api : apiRoutes) {
            assertThat(mounted.indexOf(api))
                .as("API route %s is mounted after the catch-all and is therefore unreachable", api)
                .isLessThan(catchAllIndex);
        }
    }

    @Test
    @DisplayName("the session probe is mounted")
    void sessionProbeIsMounted() {
        assertThat(recordMountedPaths()).contains(ScriptIdePaths.ROUTE_AUTH_SESSION);
    }
}
