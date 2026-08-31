package com.gaskony.scriptide.common;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/**
 * The script resource types this IDE edits, and what the real Designer writes for
 * each.
 *
 * <p>Every value here is MEASURED from resources the real Ignition Designer
 * wrote — see web-designer's {@code docs/design-handoff/real-designer/SCRIPTING.md}
 * §5 and this module's {@code docs/spikes/S1.md}. Nothing here is inferred by
 * analogy, because the types genuinely differ from one another in ways that look
 * like they should not:</p>
 *
 * <ul>
 *   <li>A timer's threading flag is {@code sharedThread}, a <b>boolean</b>. A
 *       message handler's is {@code threadType}, a <b>case-sensitive string</b>
 *       ({@code "Shared"} / {@code "Dedicated"}). Do not generalise one onto the
 *       other.</li>
 *   <li>Startup, shutdown and update are <b>singletons</b>: their resource path
 *       has no name segment at all, so the encoded path is just
 *       {@code <moduleId>/<typeId>}.</li>
 *   <li>A project-library package directory gets <b>no resource of its own</b>,
 *       unlike a Perspective view folder.</li>
 * </ul>
 *
 * <h2>Why some types are read-only for attributes</h2>
 *
 * <p>{@link #attributeAllowlist} is empty for scheduled, tag-change, shutdown and
 * update. That is deliberate, not an oversight: their Designer workspaces were
 * never opened and measured, so nothing establishes what the Designer actually
 * writes. Guessing would put an invented value onto a live gateway on the strength
 * of somebody else's file. Measure with the {@code designer-drive} skill first,
 * then add the entry — it is one line.</p>
 */
public final class ScriptResourceTypes {

    private ScriptResourceTypes() { /* constants only */ }

    /** Module id every built-in script resource type lives under. */
    public static final String IGNITION_MODULE = "ignition";

    public static final String TYPE_SCRIPT_PYTHON = "script-python";
    public static final String TYPE_TIMER = "timer";
    public static final String TYPE_MESSAGE = "message";
    public static final String TYPE_SCHEDULED = "scheduled";
    public static final String TYPE_TAG_CHANGE = "tag-change";
    public static final String TYPE_STARTUP = "startup";
    public static final String TYPE_SHUTDOWN = "shutdown";
    public static final String TYPE_UPDATE = "update";

    /** One editable script resource type. */
    public static final class ScriptType {
        private final String typeId;
        private final String label;
        private final String createKey;
        private final boolean singleton;
        private final Set<String> attributeAllowlist;

        ScriptType(String typeId, String label, String createKey, boolean singleton,
                   Set<String> attributeAllowlist) {
            this.typeId = typeId;
            this.label = label;
            this.createKey = createKey;
            this.singleton = singleton;
            this.attributeAllowlist = Collections.unmodifiableSet(attributeAllowlist);
        }

        public String typeId() {
            return typeId;
        }

        /** Human-readable name for the file tree. */
        public String label() {
            return label;
        }

        /**
         * The data key to use when CREATING a resource of this type.
         *
         * <p>For an EXISTING resource, always use the key the resource actually
         * carries (the listing publishes {@code dataKeys}) — never look it up
         * here. A resource written by an older Designer can legitimately differ,
         * and silently writing to the wrong key creates a second key rather than
         * updating the script.</p>
         */
        public String createKey() {
            return createKey;
        }

        /** True when the type has exactly one resource, with an empty name segment. */
        public boolean singleton() {
            return singleton;
        }

        /** Attribute names writable for this type. Empty means "body only". */
        public Set<String> attributeAllowlist() {
            return attributeAllowlist;
        }
    }

    private static final Map<String, ScriptType> TYPES;

    static {
        Map<String, ScriptType> m = new LinkedHashMap<>();
        // Project Library. scope "A". hintScope is an ApplicationScope bitmask:
        // 0=None, 1=Gateway, 2=Designer, 7=All — each value set, saved and read
        // back against a real gateway.
        m.put(TYPE_SCRIPT_PYTHON, new ScriptType(
            TYPE_SCRIPT_PYTHON, "Project Library", "code.py", false,
            new LinkedHashSet<>(Set.of("hintScope"))));
        // Gateway timer. NOTE sharedThread is a BOOLEAN.
        m.put(TYPE_TIMER, new ScriptType(
            TYPE_TIMER, "Timer", "handleTimerEvent.py", false,
            new LinkedHashSet<>(Set.of("enabled", "delay", "fixedDelay", "sharedThread"))));
        // Gateway message handler. NOTE threadType is a case-sensitive STRING.
        m.put(TYPE_MESSAGE, new ScriptType(
            TYPE_MESSAGE, "Message Handler", "handleMessage.py", false,
            new LinkedHashSet<>(Set.of("enabled", "threadType"))));
        m.put(TYPE_STARTUP, new ScriptType(
            TYPE_STARTUP, "Startup", "onStartup.py", true,
            new LinkedHashSet<>(Set.of("enabled"))));
        // Below here: body-only until measured. See the class Javadoc.
        m.put(TYPE_SHUTDOWN, new ScriptType(
            TYPE_SHUTDOWN, "Shutdown", "onShutdown.py", true, new LinkedHashSet<>()));
        m.put(TYPE_UPDATE, new ScriptType(
            TYPE_UPDATE, "Update", "onUpdate.py", true, new LinkedHashSet<>()));
        m.put(TYPE_SCHEDULED, new ScriptType(
            TYPE_SCHEDULED, "Scheduled", "handleScheduleEvent.py", false, new LinkedHashSet<>()));
        m.put(TYPE_TAG_CHANGE, new ScriptType(
            TYPE_TAG_CHANGE, "Tag Change", "onTagChange.py", false, new LinkedHashSet<>()));
        TYPES = Collections.unmodifiableMap(m);
    }

    /** Every editable type, in the order the file tree should show them. */
    public static Map<String, ScriptType> all() {
        return TYPES;
    }

    /** Look up a type by its {@code typeId}, if this module edits it. */
    public static Optional<ScriptType> byTypeId(String typeId) {
        return Optional.ofNullable(TYPES.get(typeId));
    }

    /** True when {@code moduleId/typeId} is a script resource this IDE edits. */
    public static boolean isEditable(String moduleId, String typeId) {
        return IGNITION_MODULE.equals(moduleId) && TYPES.containsKey(typeId);
    }

    /**
     * Valid {@code hintScope} values (ApplicationScope bitmask). Anything else is
     * rejected rather than written — an invalid scope is accepted silently by the
     * resource layer and then behaves unpredictably in the Designer.
     */
    public static final Set<Integer> HINT_SCOPE_VALUES = Set.of(0, 1, 2, 7);

    /** Valid {@code threadType} values, case-sensitive as the Designer writes them. */
    public static final Set<String> THREAD_TYPE_VALUES = Set.of("Shared", "Dedicated");

    /** Upper bound on a timer's delay, in milliseconds (24 hours). */
    public static final long MAX_TIMER_DELAY_MS = 86_400_000L;
}
