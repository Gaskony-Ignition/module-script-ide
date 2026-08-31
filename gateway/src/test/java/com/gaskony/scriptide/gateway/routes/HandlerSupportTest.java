package com.gaskony.scriptide.gateway.routes;

import com.inductiveautomation.ignition.common.resourcecollection.ResourcePath;
import com.inductiveautomation.ignition.common.resourcecollection.ResourceType;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/** Path encoding/decoding — the whole addressing contract for every script route. */
class HandlerSupportTest {

    @Test
    @DisplayName("a normal script path round-trips")
    void roundTripsNormalPath() {
        ResourcePath decoded = HandlerSupport.decodePath("ignition/script-python/util/helpers");
        assertThat(decoded.getResourceType().moduleId()).isEqualTo("ignition");
        assertThat(decoded.getResourceType().typeId()).isEqualTo("script-python");
        assertThat(decoded.getPath().toString()).isEqualTo("util/helpers");
        assertThat(HandlerSupport.encodePath(decoded))
            .isEqualTo("ignition/script-python/util/helpers");
    }

    @Test
    @DisplayName("a two-segment path addresses a type's SINGLETON, with an empty name")
    void twoSegmentPathIsSingleton() {
        // Startup/shutdown/update are stored exactly this way — no name segment at
        // all. The equivalent case (page-config) bit web-designer, so it is asserted
        // here rather than assumed.
        ResourcePath decoded = HandlerSupport.decodePath("ignition/startup");
        assertThat(decoded.getResourceType().typeId()).isEqualTo("startup");
        assertThat(decoded.getPath().toString()).isEmpty();
        assertThat(HandlerSupport.encodePath(decoded)).isEqualTo("ignition/startup");
    }

    @Test
    @DisplayName("a trailing empty name segment is treated as a singleton, not a blank name")
    void trailingSlashIsSingleton() {
        assertThat(HandlerSupport.decodePath("ignition/startup/").getPath().toString()).isEmpty();
    }

    @ParameterizedTest(name = "rejects traversal: {0}")
    @ValueSource(strings = {
        "ignition/script-python/../../etc/passwd",
        "ignition/script-python/util/../../..",
        "ignition/script-python/./x",
    })
    @DisplayName("path-traversal segments are refused outright")
    void rejectsTraversal(String raw) {
        assertThatThrownBy(() -> HandlerSupport.decodePath(raw))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("traversal");
    }

    @ParameterizedTest(name = "rejects malformed: [{0}]")
    @ValueSource(strings = {"", "   ", "ignition", "/script-python", "ignition/"})
    @DisplayName("a malformed path is refused rather than guessed at")
    void rejectsMalformed(String raw) {
        assertThatThrownBy(() -> HandlerSupport.decodePath(raw))
            .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    @DisplayName("null is refused")
    void rejectsNull() {
        assertThatThrownBy(() -> HandlerSupport.decodePath(null))
            .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    @DisplayName("a '!'-prefixed folder is a legitimate name and is preserved")
    void preservesBangFolders() {
        // Shared libraries are conventionally named "!Library" so they sort first.
        // Rejecting '!' along with '.' would break them.
        ResourcePath decoded = HandlerSupport.decodePath("ignition/script-python/!Library/util");
        assertThat(decoded.getPath().toString()).isEqualTo("!Library/util");
    }

    @Test
    @DisplayName("encodePath is the exact inverse of decodePath for a nested name")
    void encodeIsInverseOfDecode() {
        String raw = "ignition/message/Handlers/OnOrder";
        assertThat(HandlerSupport.encodePath(HandlerSupport.decodePath(raw))).isEqualTo(raw);
    }

    @Test
    @DisplayName("a ResourcePath built directly encodes the same way")
    void encodesDirectlyBuiltPath() {
        ResourcePath rp = new ResourcePath(new ResourceType("ignition", "timer"), "PlantSim");
        assertThat(HandlerSupport.encodePath(rp)).isEqualTo("ignition/timer/PlantSim");
    }
}
