package com.gaskony.scriptide.gateway.routes;

import com.gaskony.scriptide.common.ScriptResourceTypes;
import com.inductiveautomation.ignition.common.resourcecollection.ResourcePath;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * The folder-versus-singleton distinction.
 *
 * <p>Found live on 01/09/2026, not by reasoning: a project holding
 * {@code ignition/scheduled/Probe Scheduled} also reports a resource at bare
 * {@code ignition/scheduled} — the containing folder — with a real signature, an
 * empty name and no data keys. Nothing for it exists on disk; the runtime
 * collection synthesises it, and every event-script folder with children has
 * one.</p>
 *
 * <p>Before the guard this test protects, that row appeared in the rail labelled
 * "Scheduled" (indistinguishable from a singleton) and a save against it returned
 * <b>200</b> while hanging a {@code cronExpression} attribute off a directory.</p>
 *
 * <p>The trap is that the obvious fix — "reject an empty name" — is wrong.
 * Startup, shutdown and update are addressed with exactly that shape, so a
 * blanket rule hides three real scripts. The type has to decide.</p>
 */
class ContainerPathTest {

    @ParameterizedTest(name = "folder path refused: {0}")
    @ValueSource(strings = {
        "ignition/scheduled",
        "ignition/timer",
        "ignition/message",
        "ignition/tag-change",
        "ignition/script-python",
    })
    @DisplayName("a nameless path on a non-singleton type is a folder, and is refused")
    void namelessNonSingletonIsAFolder(String encoded) {
        ResourcePath path = HandlerSupport.decodePath(encoded);
        // isResourceTypeFolder(), NOT getName(). getName() on this path returns
        // the TYPE ("scheduled"), never blank — the first version of this guard
        // used it and therefore did nothing at all. This assertion is the one
        // that caught that.
        assertThat(path.isResourceTypeFolder()).isTrue();
        assertThat(path.getName())
            .as("getName() is not the name segment here — do not use it for this check")
            .isNotBlank();
        assertThat(isSingletonType(path))
            .as("%s is not a singleton type, so the type folder is not addressable", encoded)
            .isFalse();
    }

    @ParameterizedTest(name = "singleton path accepted: {0}")
    @ValueSource(strings = { "ignition/startup", "ignition/shutdown", "ignition/update" })
    @DisplayName("the three singletons are addressed with an empty name and must NOT be refused")
    void singletonsKeepTheirEmptyName(String encoded) {
        ResourcePath path = HandlerSupport.decodePath(encoded);
        // Same SHAPE as a type folder — which is precisely why the guard cannot
        // be shape-based and has to consult the type.
        assertThat(path.isResourceTypeFolder()).isTrue();
        assertThat(isSingletonType(path))
            .as("%s IS a singleton — refusing it would hide a real script", encoded)
            .isTrue();
    }

    @Test
    @DisplayName("a named script on a non-singleton type is unaffected")
    void namedScriptsAreFine() {
        ResourcePath path = HandlerSupport.decodePath("ignition/scheduled/Probe Scheduled");
        assertThat(path.isResourceTypeFolder()).isFalse();
        assertThat(path.getPath().toString()).isEqualTo("Probe Scheduled");
        // The space is real: the platform accepts it as a directory name, and it
        // was the resource that exposed the phantom sibling in the first place.
        assertThat(HandlerSupport.encodePath(path))
            .isEqualTo("ignition/scheduled/Probe Scheduled");
    }

    private static boolean isSingletonType(ResourcePath path) {
        return ScriptResourceTypes.byTypeId(path.getResourceType().typeId())
            .map(ScriptResourceTypes.ScriptType::singleton)
            .orElse(false);
    }
}
