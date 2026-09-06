package com.gaskony.scriptide.gateway.remote;

import com.gaskony.scriptide.gateway.term.PolicySource;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * The configuration that decides which gateways this one may read, and which
 * gateway may read it.
 *
 * <p>Every assertion here is about a REFUSAL. The feature's whole safety comes
 * from what it will not do: it will not call a URL the operator did not write
 * down, it will not accept a token an operator could guess, and it will not
 * quietly treat half a configuration as a working one.</p>
 */
class RemoteGatewaysTest {

    private static final String PREFIX = RemoteGateways.PREFIX;

    /**
     * Leave the static policy source pointed at nothing.
     *
     * <p>Through the public {@code setPropertiesFile} rather than the
     * package-private test reset: this test lives in another package, and
     * widening a reset hook's visibility to reach it would put a "wipe the
     * security configuration" method on the production API.</p>
     */
    @AfterEach
    void reset() {
        PolicySource.setPropertiesFile(Path.of("/nonexistent/scriptide/policy.properties"));
    }

    private static void write(Path file, String body) throws IOException {
        Files.writeString(file, body);
        Files.setLastModifiedTime(file, FileTime.fromMillis(System.currentTimeMillis()));
    }

    private static Path pointAt(Path dir) {
        Path file = dir.resolve("policy.properties");
        PolicySource.setPropertiesFile(file);
        return file;
    }

    // ==================== The list ====================

    @Test
    @DisplayName("with no file at all, no gateway is reachable and none may read this one")
    void absentFileIsTheOffState(@TempDir Path dir) {
        pointAt(dir);

        assertThat(RemoteGateways.peers()).isEmpty();
        assertThat(RemoteGateways.inboundToken()).isEmpty();
        assertThat(RemoteGateways.acceptsInbound("anything")).isFalse();
    }

    @Test
    @DisplayName("a peer is read from the file, label and token included")
    void readsAPeer(@TempDir Path dir) throws IOException {
        write(pointAt(dir),
            PREFIX + ".prod.url=https://prod.example.com:8043\n"
            + PREFIX + ".prod.label=Production\n"
            + PREFIX + ".prod.token=abcdefghijklmnopqrstuvwxyz\n");

        List<RemoteGateways.Peer> peers = RemoteGateways.peers();
        assertThat(peers).hasSize(1);
        assertThat(peers.get(0).name()).isEqualTo("prod");
        assertThat(peers.get(0).label()).isEqualTo("Production");
        assertThat(peers.get(0).base().toString()).isEqualTo("https://prod.example.com:8043");
        assertThat(peers.get(0).incomplete()).isFalse();
    }

    @Test
    @DisplayName("a peer with no label is named by its own key")
    void labelDefaultsToTheName(@TempDir Path dir) throws IOException {
        write(pointAt(dir), PREFIX + ".prod.url=http://p:8088\n");
        assertThat(RemoteGateways.peers().get(0).label()).isEqualTo("prod");
    }

    @Test
    @DisplayName("a peer with no url is ignored rather than half-created")
    void urlIsRequired(@TempDir Path dir) throws IOException {
        write(pointAt(dir), PREFIX + ".prod.label=Production\n");
        assertThat(RemoteGateways.peers()).isEmpty();
    }

    @Test
    @DisplayName("a peer with no token is listed, and says it is incomplete")
    void missingTokenIsSurfacedNotHidden(@TempDir Path dir) throws IOException {
        // Listed rather than dropped: the operator has clearly meant to configure
        // it, and a peer that vanishes from the list gives them nothing to fix.
        write(pointAt(dir), PREFIX + ".prod.url=http://p:8088\n");
        assertThat(RemoteGateways.peers()).hasSize(1);
        assertThat(RemoteGateways.peers().get(0).incomplete()).isTrue();
    }

    @Test
    @DisplayName("inboundToken is not mistaken for a peer named 'inboundToken'")
    void reservedNameIsNotAPeer(@TempDir Path dir) throws IOException {
        write(pointAt(dir),
            RemoteGateways.INBOUND_TOKEN_KEY + "=0123456789012345678901234567\n");
        assertThat(RemoteGateways.peers()).isEmpty();
    }

    @Test
    @DisplayName("peers come back in a stable order, whatever a Hashtable does")
    void peersAreSorted(@TempDir Path dir) throws IOException {
        write(pointAt(dir),
            PREFIX + ".zulu.url=http://z:8088\n"
            + PREFIX + ".alpha.url=http://a:8088\n"
            + PREFIX + ".mike.url=http://m:8088\n");
        assertThat(RemoteGateways.peers()).extracting(RemoteGateways.Peer::name)
            .containsExactly("alpha", "mike", "zulu");
    }

    // ==================== Resolution by NAME ====================

    @Test
    @DisplayName("a name that is not in the file resolves to nothing")
    void unknownNameResolvesToNothing(@TempDir Path dir) throws IOException {
        write(pointAt(dir), PREFIX + ".prod.url=http://p:8088\n");
        assertThat(RemoteGateways.peer("staging")).isEmpty();
        assertThat(RemoteGateways.peer(null)).isEmpty();
        assertThat(RemoteGateways.peer("")).isEmpty();
    }

    @Test
    @DisplayName("a URL sent as a name is still just an unknown name")
    void aUrlIsNotAName(@TempDir Path dir) throws IOException {
        // The SSRF question, asked directly. There is no path from a caller's
        // string to a URL: names are looked up, never parsed.
        write(pointAt(dir), PREFIX + ".prod.url=http://p:8088\n");
        assertThat(RemoteGateways.peer("http://169.254.169.254/latest/meta-data/")).isEmpty();
        assertThat(RemoteGateways.peer("file:///etc/passwd")).isEmpty();
    }

    // ==================== The URL ====================

    @Test
    @DisplayName("a url keeps only its scheme, host and port")
    void normaliseStripsEverythingElse() {
        assertThat(RemoteGateways.normalise("https://h:8043/some/path?x=1#f").toString())
            .isEqualTo("https://h:8043");
        assertThat(RemoteGateways.normalise("  http://h  ").toString()).isEqualTo("http://h");
    }

    @Test
    @DisplayName("a non-http scheme, or no host, is refused")
    void normaliseRefusesTheRest() {
        assertThat(catching(() -> RemoteGateways.normalise("file:///etc/passwd")))
            .isInstanceOf(IllegalArgumentException.class);
        assertThat(catching(() -> RemoteGateways.normalise("ftp://h/")))
            .isInstanceOf(IllegalArgumentException.class);
        assertThat(catching(() -> RemoteGateways.normalise("not a url")))
            .isInstanceOf(IllegalArgumentException.class);
        assertThat(catching(() -> RemoteGateways.normalise("http:///nohost")))
            .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    @DisplayName("a peer whose url will not parse is dropped, not thrown from peers()")
    void unusableUrlDropsOnePeerOnly(@TempDir Path dir) throws IOException {
        write(pointAt(dir),
            PREFIX + ".bad.url=file:///etc/passwd\n"
            + PREFIX + ".good.url=http://g:8088\n");
        assertThat(RemoteGateways.peers()).extracting(RemoteGateways.Peer::name)
            .containsExactly("good");
    }

    // ==================== The inbound token ====================

    @Test
    @DisplayName("a short token is treated as ABSENT, not accepted")
    void shortTokenIsRefused(@TempDir Path dir) throws IOException {
        // Accepting it would leave an operator believing the link is
        // authenticated when it is guessable, which is worse than no link.
        write(pointAt(dir), RemoteGateways.INBOUND_TOKEN_KEY + "=changeme\n");
        assertThat(RemoteGateways.inboundToken()).isEmpty();
        assertThat(RemoteGateways.acceptsInbound("changeme")).isFalse();
    }

    @Test
    @DisplayName("a token of the required length is accepted, and only itself")
    void tokenMatchesExactly(@TempDir Path dir) throws IOException {
        String token = "x".repeat(RemoteGateways.MIN_TOKEN_CHARS);
        write(pointAt(dir), RemoteGateways.INBOUND_TOKEN_KEY + "=" + token + "\n");

        assertThat(RemoteGateways.acceptsInbound(token)).isTrue();
        assertThat(RemoteGateways.acceptsInbound(token + "y")).isFalse();
        assertThat(RemoteGateways.acceptsInbound(token.substring(1))).isFalse();
        assertThat(RemoteGateways.acceptsInbound("")).isFalse();
        assertThat(RemoteGateways.acceptsInbound(null)).isFalse();
    }

    @Test
    @DisplayName("with no inbound token, nothing is accepted — including a blank one")
    void noTokenMeansNoAccess(@TempDir Path dir) {
        pointAt(dir);
        assertThat(RemoteGateways.acceptsInbound("")).isFalse();
        assertThat(RemoteGateways.acceptsInbound(null)).isFalse();
        assertThat(RemoteGateways.acceptsInbound("x".repeat(64))).isFalse();
    }

    private static Throwable catching(Runnable action) {
        try {
            action.run();
            return null;
        } catch (Throwable t) {
            return t;
        }
    }
}
