package com.gaskony.scriptide.gateway.routes;

import com.gaskony.scriptide.common.ScriptIdePaths;
import com.gaskony.scriptide.gateway.lang.ProjectIndex;
import com.gaskony.scriptide.gateway.remote.RemoteClient;
import com.gaskony.scriptide.gateway.remote.RemoteGateways;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParseException;
import com.google.gson.JsonParser;
import com.inductiveautomation.ignition.gateway.dataroutes.RequestContext;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeSet;

/**
 * Development against production, in one window.
 *
 * <h2>What this answers, and what it refuses to answer</h2>
 *
 * <p>It answers "what is different over there". It cannot answer "make it the
 * same": {@link RemoteClient} has one verb and it is GET, so there is no code
 * path from this handler to a write on another gateway. That is the whole shape
 * of the feature, and it is a smaller feature than "sync two gateways" on
 * purpose. Promoting a change between gateways is a deployment with an approval,
 * a window and a rollback; an editor that could do it with a button would be
 * pretending otherwise.</p>
 *
 * <h2>Two requests, not two per script</h2>
 *
 * <p>The drift report compares CONTENT HASHES from {@link ProjectIndex#digest} —
 * one request here, one to the peer — rather than fetching every body from both
 * sides. A 200-script project would otherwise be 400 HTTP round trips to answer
 * a question whose answer is usually "nine of them differ". Bodies are fetched
 * one at a time, when a row is opened.</p>
 *
 * <h2>The peer must be running this module</h2>
 *
 * <p>Deliberately: the comparison is between two Script IDE corpora, so "every
 * body this IDE can open" means the same thing on both sides — including the
 * gateway event scripts, Web Dev handlers and named-query SQL that a project
 * export diff would miss. A peer that is not running it answers 404 to the
 * digest route, and the report says so in those words rather than reporting an
 * empty project as total drift.</p>
 */
public class RemoteRouteHandler {

    private static final Logger logger = LoggerFactory.getLogger(RemoteRouteHandler.class);

    /** HTTP 502 - this gateway is fine, the far one is not. */
    private static final int SC_BAD_GATEWAY = HttpServletResponse.SC_BAD_GATEWAY;

    private final ProjectIndex projectIndex;
    private final RemoteClient client;

    public RemoteRouteHandler(ProjectIndex projectIndex, RemoteClient client) {
        this.projectIndex = projectIndex;
        this.client = client;
    }

    // ==================== The list ====================

    /**
     * GET /api/remote/gateways - every peer the operator configured.
     *
     * <p>Emits the URL, which is not a secret and is the only way a user can tell
     * two gateways called "prod" apart. It never emits a token, and there is no
     * route that does: the tokens exist to be sent, not to be read back.</p>
     *
     * <p>It also reports whether THIS gateway accepts inbound reads, because the
     * link is symmetric in practice and half a configuration is the normal
     * failure. An operator who has set up the outbound half and not the inbound
     * one can see that here rather than from a 401 on the other machine.</p>
     */
    public Object gateways(RequestContext req, HttpServletResponse resp) throws IOException {
        JsonArray items = new JsonArray();
        for (RemoteGateways.Peer peer : RemoteGateways.peers()) {
            JsonObject item = new JsonObject();
            item.addProperty("name", peer.name());
            item.addProperty("label", peer.label());
            item.addProperty("url", peer.base().toString());
            item.addProperty("configured", !peer.incomplete());
            items.add(item);
        }
        JsonObject out = new JsonObject();
        out.add("gateways", items);
        out.addProperty("acceptsInbound", RemoteGateways.inboundToken().isPresent());
        // Named in the response so the empty state can tell the reader where to
        // go. A view that says only "no gateways configured" is a dead end.
        out.addProperty("configKey", RemoteGateways.PREFIX);
        return out;
    }

    // ==================== The local half ====================

    /**
     * GET /api/scripts/digest?project=X - a content hash per openable body.
     *
     * <p>Mounted on the peer-readable gate: this is the route another gateway
     * calls, and it is also the route this gateway calls on itself to build the
     * local side of a comparison. One implementation, so the two sides cannot
     * disagree about what counts as a body.</p>
     */
    public Object digest(RequestContext req, HttpServletResponse resp) throws IOException {
        String project = req.getParameter("project");
        if (project == null || project.isBlank()) {
            return HandlerSupport.error(resp, HttpServletResponse.SC_BAD_REQUEST,
                "Missing required 'project' parameter");
        }
        JsonObject out = new JsonObject();
        out.addProperty("project", project);
        out.add("bodies", digestArray(projectIndex.digest(project)));
        return out;
    }

    private static JsonArray digestArray(List<ProjectIndex.BodyDigest> bodies) {
        JsonArray items = new JsonArray();
        for (ProjectIndex.BodyDigest body : bodies) {
            JsonObject item = new JsonObject();
            item.addProperty("label", body.label());
            item.addProperty("path", body.resourcePath());
            item.addProperty("key", body.dataKey());
            item.addProperty("sha256", body.sha256());
            item.addProperty("chars", body.chars());
            items.add(item);
        }
        return items;
    }

    // ==================== Reading the far half ====================

    /** GET /api/remote/projects?gateway=X - the peer's project list. */
    public Object projects(RequestContext req, HttpServletResponse resp) throws IOException {
        Optional<RemoteGateways.Peer> peerOpt = resolve(req);
        if (peerOpt.isEmpty()) {
            return unknownGateway(req, resp);
        }
        try {
            RemoteClient.Reply reply =
                client.get(peerOpt.get(), ScriptIdePaths.ROUTE_PROJECTS, Map.of());
            return passThrough(reply, resp, peerOpt.get());
        } catch (RemoteClient.RemoteException e) {
            return HandlerSupport.error(resp, SC_BAD_GATEWAY, e.getMessage());
        }
    }

    /**
     * GET /api/remote/content - one body from the peer, as {@code text/plain}.
     *
     * <p>Takes {@code gateway}, {@code project}, {@code path} and an optional
     * {@code key}. Same media type as the local content read, so the same client
     * code handles both and a remote document is an ordinary read-only buffer
     * rather than a special case in the editor.</p>
     */
    public Object content(RequestContext req, HttpServletResponse resp) throws IOException {
        Optional<RemoteGateways.Peer> peerOpt = resolve(req);
        if (peerOpt.isEmpty()) {
            resp.setStatus(HttpServletResponse.SC_NOT_FOUND);
            return "No usable gateway named '" + String.valueOf(req.getParameter("gateway"))
                + "' is configured on this gateway.";
        }
        String project = req.getParameter("project");
        String path = req.getParameter("path");
        if (project == null || project.isBlank() || path == null || path.isBlank()) {
            resp.setStatus(HttpServletResponse.SC_BAD_REQUEST);
            return "Both 'project' and 'path' are required.";
        }
        String key = req.getParameter("key");
        Map<String, String> query = new LinkedHashMap<>();
        query.put("project", project);
        if (key != null && !key.isBlank()) {
            query.put("key", key);
        }
        // The path is one URL-ENCODED segment in the route template, exactly as
        // it is locally - see ROUTE_SCRIPT_CONTENT. Leaving it raw would split
        // into several segments on the far side and match no route at all.
        String route = "/api/scripts/content/"
            + java.net.URLEncoder.encode(path, java.nio.charset.StandardCharsets.UTF_8);
        try {
            RemoteClient.Reply reply = client.get(peerOpt.get(), route, query);
            resp.setStatus(reply.ok() ? HttpServletResponse.SC_OK : reply.status());
            return reply.body();
        } catch (RemoteClient.RemoteException e) {
            resp.setStatus(SC_BAD_GATEWAY);
            return e.getMessage();
        }
    }

    // ==================== The comparison ====================

    /** One body's standing between the two gateways. */
    private record Row(String label, String path, String key, String status,
                       int hereChars, int thereChars) {
    }

    /**
     * GET /api/remote/drift - what differs between this project and the peer's.
     *
     * <p>Takes {@code gateway}, {@code project} and an optional
     * {@code remoteProject}, which defaults to {@code project}: the common case
     * is the same project name on two gateways, and making the parameter
     * mandatory would put a second field in front of every user for the sake of
     * the rarer one.</p>
     */
    public Object drift(RequestContext req, HttpServletResponse resp) throws IOException {
        Optional<RemoteGateways.Peer> peerOpt = resolve(req);
        if (peerOpt.isEmpty()) {
            return unknownGateway(req, resp);
        }
        String project = req.getParameter("project");
        if (project == null || project.isBlank()) {
            return HandlerSupport.error(resp, HttpServletResponse.SC_BAD_REQUEST,
                "Missing required 'project' parameter");
        }
        String remoteProject = req.getParameter("remoteProject");
        if (remoteProject == null || remoteProject.isBlank()) {
            remoteProject = project;
        }

        Map<String, ProjectIndex.BodyDigest> here = byKey(projectIndex.digest(project));

        Map<String, ProjectIndex.BodyDigest> there;
        try {
            RemoteClient.Reply reply = client.get(peerOpt.get(),
                ScriptIdePaths.ROUTE_SCRIPTS_DIGEST, Map.of("project", remoteProject));
            if (reply.status() == HttpServletResponse.SC_NOT_FOUND) {
                return HandlerSupport.error(resp, SC_BAD_GATEWAY,
                    "'" + peerOpt.get().label() + "' answered 404 for the digest route. "
                    + "Either it is not running the Script IDE module, or it is running a "
                    + "version older than 1.17.0.");
            }
            if (!reply.ok()) {
                return HandlerSupport.error(resp, SC_BAD_GATEWAY,
                    "'" + peerOpt.get().label() + "' answered " + reply.status()
                    + " for project '" + remoteProject + "'.");
            }
            there = byKey(parseDigest(reply.body()));
        } catch (RemoteClient.RemoteException e) {
            return HandlerSupport.error(resp, SC_BAD_GATEWAY, e.getMessage());
        } catch (JsonParseException e) {
            return HandlerSupport.error(resp, SC_BAD_GATEWAY,
                "'" + peerOpt.get().label() + "' returned something that is not a digest.");
        }

        List<Row> rows = new ArrayList<>();
        for (String key : new TreeSet<>(union(here.keySet(), there.keySet()))) {
            ProjectIndex.BodyDigest a = here.get(key);
            ProjectIndex.BodyDigest b = there.get(key);
            String status;
            if (a == null) {
                status = "only-there";
            } else if (b == null) {
                status = "only-here";
            } else if (a.sha256().equals(b.sha256())) {
                status = "same";
            } else {
                status = "differs";
            }
            ProjectIndex.BodyDigest naming = a != null ? a : b;
            rows.add(new Row(naming.label(), naming.resourcePath(), naming.dataKey(), status,
                a == null ? -1 : a.chars(), b == null ? -1 : b.chars()));
        }

        JsonArray items = new JsonArray();
        int differing = 0;
        for (Row row : rows) {
            if (!"same".equals(row.status())) {
                differing++;
            }
            JsonObject item = new JsonObject();
            item.addProperty("label", row.label());
            item.addProperty("path", row.path());
            item.addProperty("key", row.key());
            item.addProperty("status", row.status());
            item.addProperty("hereChars", row.hereChars());
            item.addProperty("thereChars", row.thereChars());
            items.add(item);
        }

        JsonObject out = new JsonObject();
        out.addProperty("gateway", peerOpt.get().name());
        out.addProperty("gatewayLabel", peerOpt.get().label());
        out.addProperty("project", project);
        out.addProperty("remoteProject", remoteProject);
        out.addProperty("total", rows.size());
        out.addProperty("differing", differing);
        out.add("rows", items);
        return out;
    }

    // ==================== Helpers ====================

    /**
     * The peer named by {@code gateway}, or empty.
     *
     * <p>The ONLY place a URL is chosen, and it is chosen from the operator's
     * file rather than from anything the caller sent - see {@link RemoteGateways}
     * for why that is the security property the whole feature rests on. A peer
     * with no token configured is refused HERE rather than allowed to fail as a
     * 401 from the far side, because the two look identical on screen and only
     * one of them is fixable by the reader.</p>
     */
    private Optional<RemoteGateways.Peer> resolve(RequestContext req) {
        Optional<RemoteGateways.Peer> peer = RemoteGateways.peer(req.getParameter("gateway"));
        if (peer.isPresent() && peer.get().incomplete()) {
            logger.warn("Remote gateway '{}' has no .token configured; refusing to call it",
                peer.get().name());
            return Optional.empty();
        }
        return peer;
    }

    private static Object unknownGateway(RequestContext req, HttpServletResponse resp) {
        return HandlerSupport.error(resp, HttpServletResponse.SC_NOT_FOUND,
            "No usable gateway named '" + String.valueOf(req.getParameter("gateway"))
            + "'. Check com.gaskony.scriptide.remote.<name>.url and .token in "
            + "policy.properties on this gateway.");
    }

    /** Pass a peer's JSON straight through, or turn a failure into a 502. */
    private static Object passThrough(RemoteClient.Reply reply, HttpServletResponse resp,
                                      RemoteGateways.Peer peer) {
        if (!reply.ok()) {
            return HandlerSupport.error(resp, SC_BAD_GATEWAY,
                "'" + peer.label() + "' answered " + reply.status() + ".");
        }
        try {
            return JsonParser.parseString(reply.body());
        } catch (JsonParseException e) {
            return HandlerSupport.error(resp, SC_BAD_GATEWAY,
                "'" + peer.label() + "' returned something that is not JSON.");
        }
    }

    /** A peer's digest response, as records. Throws {@link JsonParseException}. */
    static List<ProjectIndex.BodyDigest> parseDigest(String body) {
        List<ProjectIndex.BodyDigest> out = new ArrayList<>();
        JsonElement root = JsonParser.parseString(body);
        if (!root.isJsonObject() || !root.getAsJsonObject().has("bodies")) {
            throw new JsonParseException("no 'bodies' array");
        }
        for (JsonElement element : root.getAsJsonObject().getAsJsonArray("bodies")) {
            JsonObject item = element.getAsJsonObject();
            out.add(new ProjectIndex.BodyDigest(
                item.has("label") ? item.get("label").getAsString() : "",
                item.get("path").getAsString(),
                item.has("key") ? item.get("key").getAsString() : "",
                item.get("sha256").getAsString(),
                item.has("chars") ? item.get("chars").getAsInt() : -1));
        }
        return out;
    }

    /**
     * Bodies keyed by path AND data key.
     *
     * <p>The key has to carry both: a Web Dev endpoint holds up to eight scripts
     * at one resource path, and keying on the path alone would silently compare
     * {@code doGet.py} here against {@code doPost.py} there.</p>
     */
    private static Map<String, ProjectIndex.BodyDigest> byKey(
            List<ProjectIndex.BodyDigest> bodies) {
        Map<String, ProjectIndex.BodyDigest> out = new LinkedHashMap<>();
        for (ProjectIndex.BodyDigest body : bodies) {
            out.put(body.resourcePath() + " " + body.dataKey(), body);
        }
        return out;
    }

    private static java.util.Set<String> union(java.util.Set<String> a, java.util.Set<String> b) {
        java.util.Set<String> out = new java.util.HashSet<>(a);
        out.addAll(b);
        return out;
    }
}
