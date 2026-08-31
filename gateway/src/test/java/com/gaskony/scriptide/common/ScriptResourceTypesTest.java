package com.gaskony.scriptide.common;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Locks down the measured differences between script resource types.
 *
 * <p>These are not tautologies. Every assertion here encodes something that was
 * measured from a resource the real Designer wrote and that a reasonable person
 * would otherwise get wrong by generalising from a sibling type.</p>
 */
class ScriptResourceTypesTest {

    @Test
    @DisplayName("a timer's threading flag is sharedThread; a message handler's is threadType")
    void threadingAttributesDifferBetweenTypes() {
        // The single most tempting thing to "tidy up" into one shared attribute.
        // They are different names AND different JSON types.
        var timer = ScriptResourceTypes.byTypeId(ScriptResourceTypes.TYPE_TIMER).orElseThrow();
        var message = ScriptResourceTypes.byTypeId(ScriptResourceTypes.TYPE_MESSAGE).orElseThrow();

        assertThat(timer.attributeAllowlist()).contains("sharedThread").doesNotContain("threadType");
        assertThat(message.attributeAllowlist()).contains("threadType").doesNotContain("sharedThread");
    }

    @Test
    @DisplayName("startup, shutdown and update are singletons; the rest are not")
    void singletonsAreMarked() {
        assertThat(ScriptResourceTypes.byTypeId(ScriptResourceTypes.TYPE_STARTUP)
            .orElseThrow().singleton()).isTrue();
        assertThat(ScriptResourceTypes.byTypeId(ScriptResourceTypes.TYPE_SHUTDOWN)
            .orElseThrow().singleton()).isTrue();
        assertThat(ScriptResourceTypes.byTypeId(ScriptResourceTypes.TYPE_UPDATE)
            .orElseThrow().singleton()).isTrue();
        assertThat(ScriptResourceTypes.byTypeId(ScriptResourceTypes.TYPE_TIMER)
            .orElseThrow().singleton()).isFalse();
        assertThat(ScriptResourceTypes.byTypeId(ScriptResourceTypes.TYPE_SCRIPT_PYTHON)
            .orElseThrow().singleton()).isFalse();
    }

    @Test
    @DisplayName("unmeasured types are body-only, so an attribute write cannot invent a value")
    void unmeasuredTypesRejectAttributeWrites() {
        // Deliberately empty until their Designer workspace is measured. If someone
        // "helpfully" fills these in from analogy, this test should fail and make
        // them justify it.
        assertThat(ScriptResourceTypes.byTypeId(ScriptResourceTypes.TYPE_SCHEDULED)
            .orElseThrow().attributeAllowlist()).isEmpty();
        assertThat(ScriptResourceTypes.byTypeId(ScriptResourceTypes.TYPE_TAG_CHANGE)
            .orElseThrow().attributeAllowlist()).isEmpty();
        assertThat(ScriptResourceTypes.byTypeId(ScriptResourceTypes.TYPE_SHUTDOWN)
            .orElseThrow().attributeAllowlist()).isEmpty();
        assertThat(ScriptResourceTypes.byTypeId(ScriptResourceTypes.TYPE_UPDATE)
            .orElseThrow().attributeAllowlist()).isEmpty();
    }

    @Test
    @DisplayName("each type's create-time data key matches what the Designer writes")
    void createKeysMatchTheDesigner() {
        assertThat(ScriptResourceTypes.byTypeId(ScriptResourceTypes.TYPE_SCRIPT_PYTHON)
            .orElseThrow().createKey()).isEqualTo("code.py");
        assertThat(ScriptResourceTypes.byTypeId(ScriptResourceTypes.TYPE_TIMER)
            .orElseThrow().createKey()).isEqualTo("handleTimerEvent.py");
        assertThat(ScriptResourceTypes.byTypeId(ScriptResourceTypes.TYPE_MESSAGE)
            .orElseThrow().createKey()).isEqualTo("handleMessage.py");
        assertThat(ScriptResourceTypes.byTypeId(ScriptResourceTypes.TYPE_SCHEDULED)
            .orElseThrow().createKey()).isEqualTo("handleScheduleEvent.py");
        assertThat(ScriptResourceTypes.byTypeId(ScriptResourceTypes.TYPE_STARTUP)
            .orElseThrow().createKey()).isEqualTo("onStartup.py");
    }

    @Test
    @DisplayName("only ignition/* script types are editable — not views, tags or anything else")
    void onlyScriptTypesAreEditable() {
        assertThat(ScriptResourceTypes.isEditable("ignition", "script-python")).isTrue();
        assertThat(ScriptResourceTypes.isEditable("ignition", "timer")).isTrue();
        // The routes are generic over <moduleId>/<typeId>, so this guard is what
        // stops an Administrator rewriting a Perspective view through the script
        // editor's endpoint.
        assertThat(ScriptResourceTypes.isEditable("com.inductiveautomation.perspective", "views"))
            .isFalse();
        assertThat(ScriptResourceTypes.isEditable("ignition", "named-query")).isFalse();
        assertThat(ScriptResourceTypes.isEditable("ignition", "nonsense")).isFalse();
    }

    @Test
    @DisplayName("hintScope values are the ApplicationScope bitmask, not an ordinal")
    void hintScopeValuesAreTheBitmask() {
        // 0=None, 1=Gateway, 2=Designer, 7=All. Notably 3..6 are NOT valid, which
        // an ordinal-style enum would happily allow.
        assertThat(ScriptResourceTypes.HINT_SCOPE_VALUES).containsExactlyInAnyOrder(0, 1, 2, 7);
    }

    @Test
    @DisplayName("threadType values are case-sensitive exactly as the Designer writes them")
    void threadTypeValuesAreCaseSensitive() {
        assertThat(ScriptResourceTypes.THREAD_TYPE_VALUES).containsExactlyInAnyOrder(
            "Shared", "Dedicated");
        assertThat(ScriptResourceTypes.THREAD_TYPE_VALUES).doesNotContain("shared", "dedicated");
    }
}
