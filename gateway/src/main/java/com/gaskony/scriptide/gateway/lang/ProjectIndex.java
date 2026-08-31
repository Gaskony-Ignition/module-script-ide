package com.gaskony.scriptide.gateway.lang;

import com.gaskony.scriptide.common.ScriptResourceTypes;
import com.inductiveautomation.ignition.common.resourcecollection.Resource;
import com.inductiveautomation.ignition.common.resourcecollection.RuntimeResourceCollection;
import com.inductiveautomation.ignition.common.script.ModuleLibrary;
import com.inductiveautomation.ignition.gateway.project.ProjectManager;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

/**
 * An index of every project-library module, so the IDE can navigate a project.
 *
 * <h2>Why this exists at all</h2>
 *
 * <p>Because the platform will not tell us. Spike S1 measured that
 * {@code getProjectScriptManager(p).getHintsTree()} is byte-for-byte the same tree
 * as the gateway's — root {@code [system]} — and contains no project library
 * modules, even though those modules are genuinely importable on that same
 * manager. So platform completions come from {@link HintIndex} and everything
 * about the user's OWN code has to come from here.</p>
 *
 * <h2>Staleness</h2>
 *
 * <p>Each module is cached against its resource signature. A sweep compares
 * signatures and re-parses only what changed, which is cheap because a signature
 * comparison does not read the body. That matters: the alternative is re-parsing
 * every script on every keystroke's worth of index lookup.</p>
 */
public final class ProjectIndex {

    private static final Logger logger = LoggerFactory.getLogger(ProjectIndex.class);

    /** Refuse to index a project larger than this, rather than stalling on it. */
    static final int MAX_MODULES = 5_000;

    private record Cached(String signature, ModuleSymbols symbols) {
    }

    private final ProjectManager projectManager;
    private final Map<String, Map<String, Cached>> byProject = new ConcurrentHashMap<>();

    public ProjectIndex(ProjectManager projectManager) {
        this.projectManager = projectManager;
    }

    /** Every indexed module of a project, refreshing anything stale first. */
    public Map<String, ModuleSymbols> modules(String project) {
        refresh(project);
        Map<String, Cached> cache = byProject.getOrDefault(project, Map.of());
        Map<String, ModuleSymbols> out = new ConcurrentHashMap<>();
        cache.forEach((name, cached) -> out.put(name, cached.symbols()));
        return out;
    }

    /** The symbols of one module, or empty if the project has no such module. */
    public Optional<ModuleSymbols> module(String project, String moduleName) {
        return Optional.ofNullable(modules(project).get(moduleName));
    }

    /**
     * Resolve a dotted name to a definition, e.g. {@code util.helpers.compute}.
     *
     * <p>Tries the longest module prefix first, so {@code a.b.c} prefers module
     * {@code a.b} member {@code c} over module {@code a} member {@code b.c} — which
     * is the resolution order Python itself uses.</p>
     */
    public Optional<Definition> resolve(String project, String dotted) {
        Map<String, ModuleSymbols> modules = modules(project);
        if (dotted == null || dotted.isBlank()) {
            return Optional.empty();
        }
        // Whole thing is a module: jump to its top.
        ModuleSymbols whole = modules.get(dotted);
        if (whole != null) {
            return Optional.of(new Definition(dotted, null, 0, 0));
        }
        int dot = dotted.lastIndexOf('.');
        while (dot > 0) {
            String moduleName = dotted.substring(0, dot);
            String member = dotted.substring(dot + 1);
            ModuleSymbols symbols = modules.get(moduleName);
            if (symbols != null) {
                return symbols.find(member)
                    .map(s -> new Definition(moduleName, s.name(), s.line(), s.column()));
            }
            dot = dotted.lastIndexOf('.', dot - 1);
        }
        return Optional.empty();
    }

    /** Where a definition lives: which module, and where in it. */
    public record Definition(String moduleName, String symbolName, int line, int column) {
    }

    /** Case-insensitive symbol search across a project, for Ctrl-T quick open. */
    public List<SymbolHit> search(String project, String query, int limit) {
        String needle = query == null ? "" : query.toLowerCase(Locale.ROOT);
        List<SymbolHit> hits = new ArrayList<>();
        for (Map.Entry<String, ModuleSymbols> entry : modules(project).entrySet()) {
            for (ModuleSymbols.Symbol symbol : entry.getValue().symbols()) {
                if (needle.isEmpty()
                    || symbol.name().toLowerCase(Locale.ROOT).contains(needle)) {
                    hits.add(new SymbolHit(entry.getKey(), symbol));
                    if (hits.size() >= limit) {
                        return hits;
                    }
                }
            }
        }
        return hits;
    }

    /** One search result. */
    public record SymbolHit(String moduleName, ModuleSymbols.Symbol symbol) {
    }

    /**
     * Re-parse whatever changed.
     *
     * <p>Signature-diffed rather than event-driven: the resource-change event
     * carries only the collection name, not which resources changed, so there is
     * nothing finer to react to. Comparing signatures recovers the exact delta and
     * does not read a single script body to do it.</p>
     */
    private void refresh(String project) {
        Optional<RuntimeResourceCollection> collectionOpt = projectManager.find(project);
        if (collectionOpt.isEmpty()) {
            byProject.remove(project);
            return;
        }
        Map<String, Cached> cache =
            byProject.computeIfAbsent(project, p -> new ConcurrentHashMap<>());

        List<Resource> scripts = new ArrayList<>();
        for (Resource resource : collectionOpt.get().getResources()) {
            var type = resource.getResourcePath().getResourceType();
            if (ScriptResourceTypes.IGNITION_MODULE.equals(type.moduleId())
                && ScriptResourceTypes.TYPE_SCRIPT_PYTHON.equals(type.typeId())) {
                scripts.add(resource);
            }
        }
        if (scripts.size() > MAX_MODULES) {
            logger.warn("Project '{}' has {} library scripts, above the {} cap — indexing the "
                + "first {} only. Navigation will be incomplete.",
                project, scripts.size(), MAX_MODULES, MAX_MODULES);
            scripts = scripts.subList(0, MAX_MODULES);
        }

        java.util.Set<String> seen = new java.util.HashSet<>();
        for (Resource resource : scripts) {
            String moduleName = moduleNameOf(resource);
            seen.add(moduleName);
            String signature = resource.getResourceSignature().toString();
            Cached existing = cache.get(moduleName);
            if (existing != null && existing.signature().equals(signature)) {
                continue;   // unchanged — do not re-read the body
            }
            String source = readSource(resource);
            cache.put(moduleName, new Cached(signature, ModuleSymbols.parse(moduleName, source)));
        }
        // Drop modules that no longer exist, or a deleted script keeps answering
        // go-to-definition forever.
        cache.keySet().retainAll(seen);
    }

    /** {@code ignition/script-python/util/helpers} → {@code util.helpers}. */
    static String moduleNameOf(Resource resource) {
        return resource.getResourcePath().getPath().toString().replace('/', '.');
    }

    private static String readSource(Resource resource) {
        try {
            String source = ModuleLibrary.deserializeScript(resource);
            return source == null ? "" : source;
        } catch (RuntimeException e) {
            logger.debug("Could not read {}: {}", resource.getResourcePath(), e.getMessage());
            return "";
        }
    }

    /** One matching line from a cross-file search. */
    public record TextHit(String moduleName, int line, int column, String lineText) {
    }

    /**
     * Plain-text search across every library script in a project.
     *
     * <p>Bodies are read on demand rather than held in the index: the index stores
     * names, kinds and positions only, because keeping every script's source in
     * memory is how an indexer turns a large project into a heap problem. Search is
     * rare and interactive, so paying the read then is the right trade.</p>
     *
     * <p>Results are capped and each line is truncated — a regex-like query that
     * matches every line of a 5,000-line file should return a usable answer, not a
     * megabyte of JSON.</p>
     */
    public List<TextHit> searchText(String project, String query, boolean caseSensitive,
                                    int limit) {
        List<TextHit> hits = new ArrayList<>();
        if (query == null || query.isEmpty()) {
            return hits;
        }
        Optional<RuntimeResourceCollection> collectionOpt = projectManager.find(project);
        if (collectionOpt.isEmpty()) {
            return hits;
        }
        String needle = caseSensitive ? query : query.toLowerCase(Locale.ROOT);

        for (Resource resource : collectionOpt.get().getResources()) {
            var type = resource.getResourcePath().getResourceType();
            if (!ScriptResourceTypes.IGNITION_MODULE.equals(type.moduleId())
                || !ScriptResourceTypes.TYPE_SCRIPT_PYTHON.equals(type.typeId())) {
                continue;
            }
            String source = readSource(resource);
            if (source.isEmpty()) {
                continue;
            }
            String moduleName = moduleNameOf(resource);
            String[] lines = source.split("\n", -1);
            for (int i = 0; i < lines.length; i++) {
                String haystack = caseSensitive ? lines[i] : lines[i].toLowerCase(Locale.ROOT);
                int at = haystack.indexOf(needle);
                if (at < 0) {
                    continue;
                }
                String text = lines[i];
                if (text.length() > 200) {
                    text = text.substring(0, 200) + "…";
                }
                hits.add(new TextHit(moduleName, i, at, text));
                if (hits.size() >= limit) {
                    return hits;
                }
            }
        }
        return hits;
    }

    /** Number of indexed modules in a project — for diagnostics and tests. */
    public int size(String project) {
        return byProject.getOrDefault(project, Map.of()).size();
    }
}
