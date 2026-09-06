package com.gaskony.scriptide.gateway.remote;

import com.gaskony.scriptide.common.ScriptIdePaths;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;

/**
 * Reads another gateway's Script IDE API. GET only, and structurally so.
 *
 * <h2>There is one verb here, and that is the security model</h2>
 *
 * <p>This class exposes {@link #get} and nothing else. Not "POST is not used
 * yet" — there is no method to call, so no future edit to a route handler can
 * turn a comparison into a write to production by passing a different string.
 * The compare view is read-only because the client cannot write, rather than
 * because the UI does not offer a button.</p>
 *
 * <h2>Every response is bounded before it is a String</h2>
 *
 * <p>The peer is trusted to be a gateway, not trusted to be well-behaved: a
 * misconfigured URL pointing at something that streams forever would otherwise
 * turn a compare click into an OutOfMemoryError on the gateway serving the IDE.
 * So the body is read through a capped stream ({@link #MAX_BODY_BYTES}) rather
 * than {@code BodyHandlers.ofString}, and a connect and a request timeout bound
 * how long a dead peer can hold a request thread.</p>
 *
 * <h2>Redirects are not followed</h2>
 *
 * <p>{@code Redirect.NEVER}. Following one would let the peer — or anything that
 * can answer as the peer — move the request to a URL the operator never wrote in
 * the file, which is the SSRF the name-not-URL rule in {@link RemoteGateways}
 * exists to prevent. A gateway behind a redirect is a configuration to fix, and
 * the error says so.</p>
 */
public final class RemoteClient {

    private static final Logger logger = LoggerFactory.getLogger(RemoteClient.class);

    /** Largest response body accepted from a peer. */
    public static final int MAX_BODY_BYTES = 8 * 1024 * 1024;

    /** How long to wait for the TCP/TLS handshake. */
    public static final Duration CONNECT_TIMEOUT = Duration.ofSeconds(6);

    /** How long to wait for the whole response. */
    public static final Duration REQUEST_TIMEOUT = Duration.ofSeconds(20);

    /** What a peer answered. */
    public record Reply(int status, String body, String etag) {

        public boolean ok() {
            return status >= 200 && status < 300;
        }
    }

    /** A peer that could not be reached, or answered something unusable. */
    public static final class RemoteException extends RuntimeException {
        private static final long serialVersionUID = 1L;

        public RemoteException(String message) {
            super(message);
        }

        public RemoteException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    private final HttpClient http;

    public RemoteClient() {
        this(HttpClient.newBuilder()
            .connectTimeout(CONNECT_TIMEOUT)
            .followRedirects(HttpClient.Redirect.NEVER)
            .build());
    }

    /** Test seam. */
    RemoteClient(HttpClient http) {
        this.http = http;
    }

    /**
     * GET one of the peer's Script IDE routes.
     *
     * @param route a {@code /api/...} constant from {@link ScriptIdePaths}, which
     *              is appended to the peer's base under {@code /data/scriptide}.
     *              The caller never supplies a host.
     * @param query query parameters, encoded here
     */
    public Reply get(RemoteGateways.Peer peer, String route, Map<String, String> query) {
        URI uri = URI.create(peer.base() + ScriptIdePaths.DATA_BASE + route + encode(query));
        HttpRequest request = HttpRequest.newBuilder(uri)
            .GET()
            .timeout(REQUEST_TIMEOUT)
            .header(RemoteGateways.TOKEN_HEADER, peer.token())
            .header("Accept", "application/json, text/plain")
            .build();
        try {
            HttpResponse<InputStream> response =
                http.send(request, HttpResponse.BodyHandlers.ofInputStream());
            String body = readCapped(response.body(), peer.name());
            String etag = response.headers().firstValue("ETag").orElse("");
            if (response.statusCode() == 401 || response.statusCode() == 403) {
                // Named rather than passed through, because the status alone sends
                // the reader to their OWN login page — and the credential at fault
                // is in a file on the other gateway.
                throw new RemoteException("The gateway '" + peer.label() + "' refused the "
                    + "remote-read token. Check com.gaskony.scriptide.remote.inboundToken "
                    + "there, and the matching .token here.");
            }
            return new Reply(response.statusCode(), body, etag);
        } catch (IOException e) {
            throw new RemoteException("Could not reach '" + peer.label() + "' at "
                + peer.base() + ": " + e.getMessage(), e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RemoteException("Interrupted while reading from '" + peer.label() + "'", e);
        }
    }

    /**
     * The body, refusing anything over the cap.
     *
     * <p>Refusing rather than truncating: a truncated script body would diff
     * against the local copy as a large deletion at the end, which is a WRONG
     * answer presented with the same confidence as a right one.</p>
     */
    private static String readCapped(InputStream in, String peerName) throws IOException {
        try (InputStream stream = in) {
            byte[] bytes = stream.readNBytes(MAX_BODY_BYTES + 1);
            if (bytes.length > MAX_BODY_BYTES) {
                logger.warn("Response from '{}' exceeds {} bytes; refusing it", peerName,
                    MAX_BODY_BYTES);
                throw new RemoteException("The gateway '" + peerName + "' returned more than "
                    + (MAX_BODY_BYTES / (1024 * 1024)) + " MB for one request.");
            }
            return new String(bytes, StandardCharsets.UTF_8);
        }
    }

    private static String encode(Map<String, String> query) {
        if (query == null || query.isEmpty()) {
            return "";
        }
        StringBuilder sb = new StringBuilder();
        for (Map.Entry<String, String> entry : query.entrySet()) {
            if (entry.getValue() == null) {
                continue;
            }
            sb.append(sb.length() == 0 ? '?' : '&')
                .append(URLEncoder.encode(entry.getKey(), StandardCharsets.UTF_8))
                .append('=')
                .append(URLEncoder.encode(entry.getValue(), StandardCharsets.UTF_8));
        }
        return sb.toString();
    }
}
