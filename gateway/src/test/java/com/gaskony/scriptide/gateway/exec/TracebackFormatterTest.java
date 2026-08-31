package com.gaskony.scriptide.gateway.exec;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Frame-filename parsing. The spellings asserted here were MEASURED against a
 * real gateway in spike S1 — they are not guesses, and getting them wrong makes
 * a traceback frame silently unclickable.
 */
class TracebackFormatterTest {

    @Test
    @DisplayName("a project-library frame yields its dotted module name")
    void parsesLibraryFrame() {
        // Measured: Ignition spells a frame inside a project library module
        // "<module:spikelib>". That is what makes it resolvable back to
        // ignition/script-python/spikelib and therefore clickable.
        assertThat(TracebackFormatter.libraryModuleOf("<module:spikelib>")).isEqualTo("spikelib");
        assertThat(TracebackFormatter.libraryModuleOf("<module:util.helpers>"))
            .isEqualTo("util.helpers");
    }

    @Test
    @DisplayName("anything that is not a library frame yields null")
    void rejectsNonLibraryFrames() {
        assertThat(TracebackFormatter.libraryModuleOf(
            "<script-ide:MyProject:ignition/script-python/util>")).isNull();
        assertThat(TracebackFormatter.libraryModuleOf("<string>")).isNull();
        assertThat(TracebackFormatter.libraryModuleOf(null)).isNull();
        assertThat(TracebackFormatter.libraryModuleOf("")).isNull();
        // Malformed: prefix present but never closed.
        assertThat(TracebackFormatter.libraryModuleOf("<module:unterminated")).isNull();
        // Empty module name is not a usable target.
        assertThat(TracebackFormatter.libraryModuleOf("<module:>")).isNull();
    }

    @Test
    @DisplayName("a non-Python failure is still reported rather than dropped")
    void describesNonPythonFailure() {
        // A Java-level failure has no Python frames. Returning an empty object
        // would leave the user with a blank panel and no idea anything broke.
        var out = TracebackFormatter.describe(
            new IllegalStateException("pool exhausted"), "<script-ide:P:console>", 0);
        assertThat(out.get("type").getAsString()).isEqualTo("IllegalStateException");
        assertThat(out.get("message").getAsString()).contains("pool exhausted");
        assertThat(out.getAsJsonArray("frames")).isEmpty();
    }

    @Test
    @DisplayName("a null failure describes nothing rather than throwing")
    void handlesNullFailure() {
        assertThat(TracebackFormatter.describe(null, "<f>", 0).size()).isZero();
    }
}
