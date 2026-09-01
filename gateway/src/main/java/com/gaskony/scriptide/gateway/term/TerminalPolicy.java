package com.gaskony.scriptide.gateway.term;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.file.Files;
import java.nio.file.Path;

/**
 * The fleet-wide switches governing the Gateway terminal.
 *
 * <p>Read from system properties on EVERY call, exactly as {@code ExecPolicy} is,
 * so a gateway operator can turn the terminal off on a running gateway. Set them
 * in {@code data/ignition.conf} as {@code wrapper.java.additional.N=-Dkey=value}.</p>
 *
 * <h2>Why this defaults to on</h2>
 *
 * <p>A shell here runs as the <b>same operating-system user as the Gateway JVM</b>
 * and can reach exactly what that user can reach. An Administrator who can open
 * the Script Console can already call {@code java.lang.Runtime.exec} from Jython,
 * so the terminal grants no privilege that was not already reachable — it makes
 * it convenient, which is the point of a tool.</p>
 *
 * <p>That is an argument for parity with {@code execution.enabled}, not for
 * complacency: {@link #PROP_ENABLED} is a separate switch precisely so a site can
 * keep the Script Console and refuse the shell.</p>
 */
public final class TerminalPolicy {

    private static final Logger logger = LoggerFactory.getLogger(TerminalPolicy.class);

    private static final String PREFIX = "com.gaskony.scriptide.";

    /** Master kill switch for the terminal, independent of script execution. */
    public static final String PROP_ENABLED = PREFIX + "terminal.enabled";

    /** Whether opening a terminal demands the Administrator role. */
    public static final String PROP_REQUIRE_ADMIN = PREFIX + "terminal.requireAdmin";

    /** Must ALSO be set before {@link #PROP_REQUIRE_ADMIN} may be turned off. */
    public static final String PROP_ACKNOWLEDGE_RISK = PREFIX + "terminal.acknowledgeRisk";

    /** Absolute path of the shell to run. */
    public static final String PROP_SHELL = PREFIX + "terminal.shell";

    /** How many terminals one browser connection may hold open at once. */
    public static final String PROP_MAX_PER_SESSION = PREFIX + "terminal.maxPerSession";

    /** Minutes of silence after which a terminal is closed. */
    public static final String PROP_IDLE_MINUTES = PREFIX + "terminal.idleMinutes";

    /**
     * Whether a new terminal should try to become root.
     *
     * <p>Defaults to {@code true} (Nigel, 01/09/2026): the terminal exists to
     * administer a container, and a shell that cannot install a package or read
     * a log outside the data directory is a shell you have to leave to do the
     * work.</p>
     *
     * <p>It is a <b>try</b>, not a guarantee, and the distinction is the whole
     * design. Elevation only happens when the host already grants the Gateway's
     * own operating-system user passwordless {@code sudo}; the module never
     * carries a credential and never prompts for one. On a host that does not
     * grant it — which is every stock Ignition image — the probe fails in
     * milliseconds and the user gets the ordinary shell, told plainly which one
     * they got. Setting this true does not make a gateway more privileged; the
     * IMAGE decides that.</p>
     *
     * <p>Nor does it widen the module's threat model, for the same reason the
     * terminal itself did not: on a host where {@code sudo -n} succeeds for the
     * Gateway user, an Administrator can already reach a root shell from the
     * Script Console with {@code Runtime.exec}. What changes is convenience.</p>
     */
    public static final String PROP_PRIVILEGED = PREFIX + "terminal.privileged";

    public static final int DEFAULT_MAX_PER_SESSION = 3;
    public static final int MAX_MAX_PER_SESSION = 8;
    public static final long DEFAULT_IDLE_MINUTES = 120;

    /** Shells we are willing to launch, by absolute path. */
    private static final String[] SHELL_CANDIDATES = {"/bin/bash", "/usr/bin/bash", "/bin/sh"};

    /** Where {@code sudo} lives, best first. Absolute, for the reason argv is. */
    private static final String[] SUDO_CANDIDATES = {"/usr/bin/sudo", "/bin/sudo"};

    /** How long the passwordless-sudo probe may take before we give up on it. */
    private static final long SUDO_PROBE_TIMEOUT_SECONDS = 5;

    private TerminalPolicy() { /* static config accessor */ }

    public static boolean terminalEnabled() {
        return boolProperty(PROP_ENABLED, true);
    }

    /**
     * Whether the Administrator role is required to open a terminal.
     *
     * <p>Same two-flag shape as script execution, and for the same reason: a
     * single typo'd property must not hand a Gateway shell to every authenticated
     * user. When it IS turned off that is logged on every open, not once at
     * startup.</p>
     */
    public static boolean requireAdmin() {
        boolean requested = boolProperty(PROP_REQUIRE_ADMIN, true);
        if (requested) {
            return true;
        }
        if (!boolProperty(PROP_ACKNOWLEDGE_RISK, false)) {
            logger.warn("{}=false ignored: {} is not set. Opening a terminal still requires "
                + "the Administrator role.", PROP_REQUIRE_ADMIN, PROP_ACKNOWLEDGE_RISK);
            return true;
        }
        logger.warn("A GATEWAY SHELL IS OPEN TO EVERY AUTHENTICATED USER on this gateway "
            + "({}=false with {}=true). Any of them can run any command the Gateway's "
            + "operating-system user can run.", PROP_REQUIRE_ADMIN, PROP_ACKNOWLEDGE_RISK);
        return false;
    }

    /**
     * The shell to launch, as an absolute path that exists.
     *
     * <p>The property is validated rather than passed through: the value is
     * interpolated into the {@code script -c} string, so a value carrying shell
     * metacharacters would be a command-injection hole opened by a config typo.
     * Anything that is not an absolute path to an existing regular file is
     * refused and the built-in candidates are used instead.</p>
     */
    public static String shell() {
        String configured = System.getProperty(PROP_SHELL);
        if (configured != null && !configured.isBlank()) {
            String trimmed = configured.trim();
            if (isSafeShellPath(trimmed)) {
                return trimmed;
            }
            logger.warn("Ignoring {}='{}': it must be an absolute path to an existing "
                + "executable and contain no shell metacharacters.", PROP_SHELL, configured);
        }
        for (String candidate : SHELL_CANDIDATES) {
            if (Files.isExecutable(Path.of(candidate))) {
                return candidate;
            }
        }
        return null;
    }

    /** Package-visible so the unit test can exercise the rejection rules directly. */
    static boolean isSafeShellPath(String value) {
        if (!value.startsWith("/")) {
            return false;
        }
        // Allowlist, not a blocklist of metacharacters: the string is handed to a
        // shell, and enumerating everything a shell treats specially is exactly
        // the kind of list that is wrong the day someone finds the character it
        // missed.
        if (!value.matches("[A-Za-z0-9/._+-]+")) {
            return false;
        }
        Path path = Path.of(value);
        return Files.isRegularFile(path) && Files.isExecutable(path);
    }

    /**
     * The {@code sudo} to elevate through, or {@code null} for "run unprivileged".
     *
     * <p>Returns non-null only when ALL of these hold, checked in this order
     * because each is cheaper than the next:</p>
     *
     * <ol>
     *   <li>{@link #PROP_PRIVILEGED} is not turned off;</li>
     *   <li>a {@code sudo} binary exists at a known absolute path;</li>
     *   <li>{@code sudo -n true} actually succeeds as the Gateway's own user.</li>
     * </ol>
     *
     * <p>The third is the one that matters and it is a real execution, not an
     * inspection of {@code /etc/sudoers} — a file this user usually cannot read,
     * whose rules can come from six drop-ins and an LDAP plugin, and which is
     * the wrong thing to parse when you can simply ask. {@code -n} is
     * load-bearing: without it, sudo on a host that WOULD prompt sits waiting
     * for a password that no browser terminal can supply, and the shell looks
     * hung rather than unprivileged.</p>
     *
     * <p>Not cached. The probe costs a few milliseconds against an action a user
     * takes by hand, and caching it would make a gateway that gained or lost the
     * sudoers rule keep reporting the state it had at startup.</p>
     */
    public static String sudoForElevation() {
        if (!boolProperty(PROP_PRIVILEGED, true)) {
            return null;
        }
        String sudo = null;
        for (String candidate : SUDO_CANDIDATES) {
            if (Files.isExecutable(Path.of(candidate))) {
                sudo = candidate;
                break;
            }
        }
        if (sudo == null) {
            return null;
        }
        return passwordlessSudoWorks(sudo) ? sudo : null;
    }

    /** Ask sudo, rather than trying to predict what it would say. */
    private static boolean passwordlessSudoWorks(String sudo) {
        Process probe = null;
        try {
            probe = new ProcessBuilder(sudo, "-n", "true")
                .redirectErrorStream(true)
                .redirectOutput(ProcessBuilder.Redirect.DISCARD)
                .start();
            // No stdin at all: a sudo that decides to prompt anyway then fails
            // immediately instead of blocking on a read nobody will answer.
            probe.getOutputStream().close();
            if (!probe.waitFor(SUDO_PROBE_TIMEOUT_SECONDS, java.util.concurrent.TimeUnit.SECONDS)) {
                logger.debug("sudo probe timed out; treating the terminal as unprivileged");
                return false;
            }
            return probe.exitValue() == 0;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return false;
        } catch (Exception e) {
            logger.debug("sudo probe failed; treating the terminal as unprivileged", e);
            return false;
        } finally {
            if (probe != null && probe.isAlive()) {
                probe.destroyForcibly();
            }
        }
    }

    public static int maxPerSession() {
        return (int) clamp(longProperty(PROP_MAX_PER_SESSION, DEFAULT_MAX_PER_SESSION),
            1, MAX_MAX_PER_SESSION);
    }

    public static long idleMinutes() {
        return clamp(longProperty(PROP_IDLE_MINUTES, DEFAULT_IDLE_MINUTES), 1, 24 * 60);
    }

    private static boolean boolProperty(String key, boolean fallback) {
        String raw = System.getProperty(key);
        if (raw == null || raw.isBlank()) {
            return fallback;
        }
        if ("true".equalsIgnoreCase(raw.trim())) {
            return true;
        }
        if ("false".equalsIgnoreCase(raw.trim())) {
            return false;
        }
        logger.warn("Ignoring {}='{}': expected true or false. Using {}.", key, raw, fallback);
        return fallback;
    }

    private static long longProperty(String key, long fallback) {
        String raw = System.getProperty(key);
        if (raw == null || raw.isBlank()) {
            return fallback;
        }
        try {
            return Long.parseLong(raw.trim());
        } catch (NumberFormatException e) {
            logger.warn("Ignoring {}='{}': not a number. Using {}.", key, raw, fallback);
            return fallback;
        }
    }

    private static long clamp(long value, long min, long max) {
        return Math.max(min, Math.min(max, value));
    }
}
