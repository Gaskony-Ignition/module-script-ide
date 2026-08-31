package com.gaskony.scriptide.gateway.routes;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * The client-supplied data key.
 *
 * <p>Defence in depth rather than a privilege boundary — reaching this code already
 * requires an Administrator with a valid CSRF token — but a data key has no business
 * containing a path separator, and this module should not be relying on the platform
 * to sanitise one.</p>
 */
class DataKeySafetyTest {

    @ParameterizedTest(name = "accepts: {0}")
    @ValueSource(strings = {
        "code.py", "handleTimerEvent.py", "handleMessage.py",
        "onStartup.py", "handleScheduleEvent.py", "onTagChange.py",
    })
    @DisplayName("every real script data key is accepted")
    void acceptsRealKeys(String key) {
        assertThat(ScriptResourceRouteHandler.isSafeDataKey(key)).isTrue();
    }

    @ParameterizedTest(name = "rejects: {0}")
    @ValueSource(strings = {
        "../../etc/passwd",
        "../code.py",
        "sub/code.py",
        "..\\code.py",
        "code.txt",
        "code.py.bak",
        "",
        "resource.json",
    })
    @DisplayName("anything that is not a plain .py filename is refused")
    void rejectsUnsafeKeys(String key) {
        assertThat(ScriptResourceRouteHandler.isSafeDataKey(key)).isFalse();
    }

    @Test
    @DisplayName("null is refused rather than throwing")
    void rejectsNull() {
        assertThat(ScriptResourceRouteHandler.isSafeDataKey(null)).isFalse();
    }

    @Test
    @DisplayName("an embedded NUL byte is refused")
    void rejectsNulByte() {
        // A NUL can truncate a filename in a native layer further down, turning
        // "code.py\u0000.txt" into something an extension check never saw.
        String withNul = "code.py" + '\u0000' + ".py";
        assertThat(ScriptResourceRouteHandler.isSafeDataKey(withNul)).isFalse();
    }

    @Test
    @DisplayName("the guard is not vacuous — a plainly valid key still passes")
    void guardIsNotVacuous() {
        // Guards that reject everything pass every rejection test. Assert the
        // positive case alongside, so a broken predicate cannot look healthy.
        assertThat(ScriptResourceRouteHandler.isSafeDataKey("code.py")).isTrue();
        // And a key that differs from a valid one ONLY by a separator is refused,
        // which is the property that actually matters.
        assertThat(ScriptResourceRouteHandler.isSafeDataKey("a/code.py")).isFalse();
    }
}
