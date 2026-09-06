package com.gaskony.scriptide.gateway.remote;

import com.gaskony.scriptide.gateway.term.PolicySource;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.URI;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Optional;

/**
 * The other gateways this one may READ from, and the token it will answer other
 * gateways with.
 *
 * <h2>The whole feature is off until an operator turns it on</h2>
 *
 * <p>Nothing here has a default that does anything. With no {@code remote.*}
 * lines in {@code policy.properties} the list is empty, the compare view says so,
 * and the inbound token check denies every caller — which is the state every
 * existing gateway is already in, so shipping this changes nothing until somebody
 * writes the file on purpose. That is the same rule {@link PolicySource} states
 * for the terminal, and for the same reason: the file is a security control, and
 * a security control that arrives switched on is a vulnerability with a release
 * note.</p>
 *
 * <h2>The client sends a NAME, never a URL</h2>
 *
 * <p>This is the load-bearing property of the whole design, and it is worth
 * stating plainly because the obvious API is the wrong one. A route that took
 * {@code ?url=} and fetched it would be a server-side request forgery primitive
 * mounted inside a gateway — any authenticated user could aim the gateway's own
 * network position at {@code 169.254.169.254}, at a database admin port, at
 * anything the gateway can reach and the browser cannot. So the client sends
 * {@code ?gateway=prod}, that name is looked up HERE, and a name that is not in
 * the file resolves to nothing. The set of reachable URLs is exactly the set the
 * operator wrote down.</p>
 *
 * <h2>The file</h2>
 *
 * <pre>
 * # Outbound: gateways this one may read from. The name (`prod`) is yours.
 * com.gaskony.scriptide.remote.prod.url   = https://prod.example.com:8043
 * com.gaskony.scriptide.remote.prod.label = Production
 * com.gaskony.scriptide.remote.prod.token = &lt;the remote's inbound token&gt;
 *
 * # Inbound: the token THIS gateway will accept on its read-only routes.
 * # Absent means no gateway may read this one. There is no default value.
 * com.gaskony.scriptide.remote.inboundToken = &lt;a long random string&gt;
 * </pre>
 *
 * <p>The token is a shared secret rather than anything cleverer, and that is a
 * decision with a stated cost. It is symmetric, it does not expire, and rotating
 * it means editing two files. What it buys is that the credential lives in the
 * one file the operator already owns at 0600 — the same file that can turn the
 * terminal off — instead of in a project resource, a database table or a UI this
 * module would then have to protect. An OAuth client credential would be better
 * and would need a token endpoint, a refresh path and a store; that is a larger
 * thing than the read-only compare it would be protecting.</p>
 *
 * <p><b>{@code inboundToken} is deliberately not a per-caller credential.</b> It
 * says "a Script IDE on a gateway I trust may READ my scripts". It grants no
 * write, no execution and no terminal — see {@code SessionSecurity} — so the
 * worst a leaked one does is disclose source that every authenticated user of
 * that gateway can already read.</p>
 */
public final class RemoteGateways {

    private static final Logger logger = LoggerFactory.getLogger(RemoteGateways.class);

    /** Prefix for every remote-gateway key. */
    public static final String PREFIX = "com.gaskony.scriptide.remote";

    /** The token this gateway accepts from another gateway's Script IDE. */
    public static final String INBOUND_TOKEN_KEY = PREFIX + ".inboundToken";

    /**
     * The header a peer presents it in.
     *
     * <p>Not {@code Authorization}: that header is the platform's, and a value
     * this module invented sitting in it would be read by every filter in front
     * of us as a bearer token the gateway itself should understand.</p>
     */
    public static final String TOKEN_HEADER = "X-ScriptIDE-Remote-Token";

    /**
     * The shortest inbound token that will be accepted.
     *
     * <p>A refusal, not a warning. An operator who pastes {@code changeme} into
     * the file has configured something that reads as a security control and is
     * not one, and the failure mode of accepting it is silent.</p>
     */
    public static final int MIN_TOKEN_CHARS = 24;

    private RemoteGateways() { /* config accessor */ }

    /**
     * One configured peer.
     *
     * @param name  the operator's own key for it, and the only thing a client
     *              ever sends
     * @param label what the UI shows; defaults to the name
     * @param base  the peer's gateway root, with no trailing slash
     * @param token the peer's inbound token, or empty when none was configured —
     *              which is a misconfiguration the list surfaces rather than
     *              hides, because the request would otherwise fail as a 403 the
     *              user cannot act on
     */
    public record Peer(String name, String label, URI base, String token) {

        /** True when this peer is missing the token it will certainly be asked for. */
        public boolean incomplete() {
            return token == null || token.isBlank();
        }
    }

    /** Every peer in the file, in name order. Never null; empty means the feature is off. */
    public static List<Peer> peers() {
        List<Peer> out = new ArrayList<>();
        for (String name : PolicySource.childNames(PREFIX)) {
            // `inboundToken` lives under the same prefix and is not a peer. It is
            // the one reserved name, which is why it is camelCase and peer names
            // in the docs are not.
            if ("inboundToken".equals(name)) {
                continue;
            }
            String url = PolicySource.value(PREFIX + "." + name + ".url");
            if (url == null) {
                logger.warn("Remote gateway '{}' has no .url and is being ignored", name);
                continue;
            }
            URI base;
            try {
                base = normalise(url);
            } catch (IllegalArgumentException e) {
                logger.warn("Remote gateway '{}' has an unusable url ({}); ignoring it: {}",
                    name, url, e.getMessage());
                continue;
            }
            String label = PolicySource.value(PREFIX + "." + name + ".label");
            String token = PolicySource.value(PREFIX + "." + name + ".token");
            out.add(new Peer(name, label == null || label.isBlank() ? name : label, base,
                token == null ? "" : token));
        }
        return List.copyOf(out);
    }

    /** The peer with this name, or empty. The ONLY way a URL is ever chosen. */
    public static Optional<Peer> peer(String name) {
        if (name == null || name.isBlank()) {
            return Optional.empty();
        }
        return peers().stream().filter(p -> p.name().equals(name)).findFirst();
    }

    /**
     * The inbound token in force, or empty when this gateway answers no peer.
     *
     * <p>A token below {@link #MIN_TOKEN_CHARS} is treated as ABSENT and logged
     * once per read. Silently accepting it would leave an operator believing the
     * link is authenticated when it is guessable.</p>
     */
    public static Optional<String> inboundToken() {
        String configured = PolicySource.value(INBOUND_TOKEN_KEY);
        if (configured == null || configured.isBlank()) {
            return Optional.empty();
        }
        if (configured.length() < MIN_TOKEN_CHARS) {
            logger.warn("{} is only {} characters; at least {} are required, so remote reads "
                + "of this gateway stay DISABLED", INBOUND_TOKEN_KEY, configured.length(),
                MIN_TOKEN_CHARS);
            return Optional.empty();
        }
        return Optional.of(configured);
    }

    /**
     * Whether {@code presented} is this gateway's inbound token.
     *
     * <p>Constant-time in the length it compares, via
     * {@link java.security.MessageDigest#isEqual}. A short-circuiting
     * {@code String.equals} on a secret leaks its prefix to anyone who can time a
     * few thousand requests, and this one sits in front of every script in every
     * project.</p>
     */
    public static boolean acceptsInbound(String presented) {
        Optional<String> expected = inboundToken();
        if (expected.isEmpty() || presented == null || presented.isBlank()) {
            return false;
        }
        byte[] a = expected.get().getBytes(java.nio.charset.StandardCharsets.UTF_8);
        byte[] b = presented.getBytes(java.nio.charset.StandardCharsets.UTF_8);
        return java.security.MessageDigest.isEqual(a, b);
    }

    /**
     * A configured URL reduced to a scheme, host and port, with nothing else.
     *
     * <p>Path, query and fragment are DROPPED rather than preserved: every route
     * this module fetches is built by appending to this base, and a configured
     * value carrying its own query string would produce URLs whose parameters
     * silently outrank the ones the client asked for.</p>
     *
     * @throws IllegalArgumentException when the value is not an absolute http(s)
     *         URL with a host
     */
    static URI normalise(String raw) {
        URI uri;
        try {
            uri = URI.create(raw.trim());
        } catch (IllegalArgumentException e) {
            throw new IllegalArgumentException("not a URL");
        }
        String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);
        if (!"http".equals(scheme) && !"https".equals(scheme)) {
            throw new IllegalArgumentException("scheme must be http or https");
        }
        if (uri.getHost() == null || uri.getHost().isBlank()) {
            throw new IllegalArgumentException("no host");
        }
        String authority = uri.getPort() < 0
            ? uri.getHost()
            : uri.getHost() + ":" + uri.getPort();
        return URI.create(scheme + "://" + authority);
    }
}
