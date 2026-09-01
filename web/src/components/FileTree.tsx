/**
 * The left rail: every editable script in the open project, plus the console.
 *
 * The "Scripting" heading belongs to the RAIL, not to this component — the rail
 * shows the active view's name and this tree is one of several views it hosts.
 * Rendering it here as well printed it twice.
 *
 * The shape follows the Designer's project browser (Nigel, 01/09/2026), because
 * anyone using this has the Designer's layout in their head already:
 *
 *   Scripting
 *   ├── Gateway Events
 *   │   ├── Message
 *   │   ├── Timer
 *   │   └── …
 *   ├── Project Library
 *   │   └── util/helpers
 *   └── Script Console
 *
 * The one departure is Script Console, which the Designer keeps on a toolbar
 * rather than in the tree. It sits here deliberately (Nigel): in a browser it is
 * another thing you open, not another window.
 *
 * Project Library entries carry slash-separated package names and are shown as a
 * nested, collapsible tree; each gateway event type is a flat list, because each
 * is genuinely flat on the gateway.
 */
import { useMemo, useState } from 'react';
import type { ScriptEntry, ScriptTypeId } from '../api/scripts';
import { IconFolder, IconPlus, IconTerminal, IconTrash, iconForType } from './Icons';
import { Chevron } from './Chevron';
import './FileTree.css';

/** Non-script destinations the rail can select. */
export type SpecialTarget = 'console';

export interface FileTreeProps {
  scripts: ScriptEntry[];
  /** Path of the entry currently being edited, if any. */
  selectedPath: string | null;
  onSelect: (entry: ScriptEntry) => void;
  /** Selected when the console is the active surface. */
  consoleSelected?: boolean;
  onSelectSpecial?: (target: SpecialTarget) => void;
  /** Offered only when the session may write — omit to hide create/delete. */
  onCreate?: (typeId: ScriptTypeId) => void;
  onDelete?: (entry: ScriptEntry) => void;
}

/**
 * Gateway event types, in the Designer's own order. Project Library is handled
 * separately because it is a package tree rather than a flat list.
 */
/** Types the platform stores as ONE resource with no name segment. */
const SINGLETON_TYPES = new Set<string>(['startup', 'shutdown', 'update']);

const GATEWAY_EVENT_TYPES: ScriptTypeId[] = [
  'startup',
  'shutdown',
  'update',
  'timer',
  'message',
  'scheduled',
  'tag-change',
];

const LIBRARY_TYPE: ScriptTypeId = 'script-python';

/**
 * Labels for a type with no scripts in the open project.
 *
 * Needed because the label normally comes from an ENTRY, and an empty folder
 * has none — which is exactly the folder someone is about to create the first
 * script in.
 */
const TYPE_LABELS: Record<string, string> = {
  timer: 'Timer',
  message: 'Message Handler',
  scheduled: 'Scheduled',
  'tag-change': 'Tag Change',
  startup: 'Startup',
  shutdown: 'Shutdown',
  update: 'Update',
};

interface PackageNode {
  /** Segment name, e.g. `util`. Empty for the root. */
  name: string;
  /** Full package path, used as the collapse key. */
  key: string;
  children: PackageNode[];
  scripts: ScriptEntry[];
}

function emptyNode(name: string, key: string): PackageNode {
  return { name, key, children: [], scripts: [] };
}

/** Build the package tree for the Project Library group. */
export function buildPackageTree(entries: ScriptEntry[]): PackageNode {
  const root = emptyNode('', '');
  for (const entry of entries) {
    const segments = entry.name.split('/').filter((s) => s.length > 0);
    const leaf = segments.pop();
    let node = root;
    for (const segment of segments) {
      const key = node.key ? `${node.key}/${segment}` : segment;
      let child = node.children.find((c) => c.name === segment);
      if (!child) {
        child = emptyNode(segment, key);
        node.children.push(child);
      }
      node = child;
    }
    // A singleton or a name-less entry still needs a row; fall back to its label.
    node.scripts.push({ ...entry, name: leaf ?? entry.typeLabel });
  }
  sortNode(root);
  return root;
}

function sortNode(node: PackageNode) {
  node.children.sort((a, b) => a.name.localeCompare(b.name));
  node.scripts.sort((a, b) => a.name.localeCompare(b.name));
  node.children.forEach(sortNode);
}

export default function FileTree({
  scripts,
  selectedPath,
  onSelect,
  consoleSelected = false,
  onSelectSpecial,
  onCreate,
  onDelete,
}: FileTreeProps) {
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());

  const { library, eventGroups, unknownGroups } = useMemo(() => {
    const byType = new Map<string, ScriptEntry[]>();
    for (const entry of scripts) {
      const list = byType.get(entry.typeId);
      if (list) list.push(entry);
      else byType.set(entry.typeId, [entry]);
    }
    const known = new Set<string>([LIBRARY_TYPE, ...GATEWAY_EVENT_TYPES]);
    return {
      library: byType.get(LIBRARY_TYPE) ?? [],
      // EVERY event type, not only the ones with scripts in them. The Designer
      // shows all four folders even when empty, and an empty folder is the only
      // place to click "new" for that type — filtering them out made it
      // impossible to create the first script of a kind.
      eventGroups: GATEWAY_EVENT_TYPES.map((typeId) => {
        const entries = byType.get(typeId) ?? [];
        return { typeId, label: entries[0]?.typeLabel ?? TYPE_LABELS[typeId] ?? typeId, entries };
      }),
      // Anything the gateway sent that this build does not know about — better
      // shown under its own heading than silently dropped.
      unknownGroups: [...byType.keys()]
        .filter((t) => !known.has(t))
        .map((typeId) => {
          const entries = byType.get(typeId) ?? [];
          return { typeId, label: entries[0]?.typeLabel ?? typeId, entries };
        }),
    };
  }, [scripts]);

  function toggle(key: string) {
    setCollapsed((previous) => {
      const next = new Set(previous);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const eventsCollapsed = collapsed.has('group:gateway-events');
  const libraryCollapsed = collapsed.has('group:library');

  return (
    <nav className="file-tree" aria-label="Scripting">
      {/* ---- Gateway Events ---- */}
      <section className="file-tree-group">
        <button
          type="button"
          className="file-tree-header"
          aria-expanded={!eventsCollapsed}
          onClick={() => toggle('group:gateway-events')}
        >
          <Chevron open={!eventsCollapsed} />
          <span>Gateway Events</span>
          <span className="file-tree-count">
            {eventGroups.reduce((total, g) => total + g.entries.length, 0)}
          </span>
        </button>
        {!eventsCollapsed &&
          (eventGroups.length === 0 && !onCreate ? (
            <p className="file-tree-empty muted">None in this project.</p>
          ) : (
            eventGroups.map((group) => {
              const key = `type:${group.typeId}`;
              const isCollapsed = collapsed.has(key);
              // From the TYPE, not from an entry: an empty folder has no entry
              // to ask, and startup/shutdown/update must not offer "new".
              const singleton = group.entries[0]?.singleton
                ?? SINGLETON_TYPES.has(group.typeId);
              return (
                <div key={group.typeId}>
                  <div className="file-tree-header-row">
                    <button
                      type="button"
                      className="file-tree-package"
                      style={{ paddingLeft: indent(1) }}
                      aria-expanded={!isCollapsed}
                      onClick={() => toggle(key)}
                    >
                      <Chevron open={!isCollapsed} />
                      {iconForType(group.typeId, { className: 'file-tree-icon' })}
                      <span>{group.label}</span>
                      <span className="file-tree-count">{group.entries.length}</span>
                    </button>
                    {/* A singleton cannot have a second instance, so it gets no
                        add button — the Designer does not offer one either. */}
                    {onCreate && !singleton && (
                      <button
                        type="button"
                        className="file-tree-action"
                        title={`New ${group.label} script`}
                        aria-label={`New ${group.label} script`}
                        onClick={() => onCreate(group.typeId)}
                      >
                        <IconPlus size={13} />
                      </button>
                    )}
                  </div>
                  {!isCollapsed && group.entries.length === 0 && (
                    <p className="file-tree-empty muted" style={{ paddingLeft: indent(2) }}>
                      {singleton ? 'Not defined in this project.' : 'None yet.'}
                    </p>
                  )}
                  {!isCollapsed && (
                    <ul className="file-tree-list">
                      {[...group.entries]
                        .sort((a, b) => a.name.localeCompare(b.name))
                        .map((entry) => (
                          <ScriptRow
                            key={entry.path}
                            entry={entry}
                            depth={2}
                            selectedPath={selectedPath}
                            onSelect={onSelect}
                            onDelete={onDelete}
                          />
                        ))}
                    </ul>
                  )}
                </div>
              );
            })
          ))}
      </section>

      {/* ---- Project Library ---- */}
      <section className="file-tree-group">
        <div className="file-tree-header-row">
          <button
            type="button"
            className="file-tree-header"
            aria-expanded={!libraryCollapsed}
            onClick={() => toggle('group:library')}
          >
            <Chevron open={!libraryCollapsed} />
            <span>Project Library</span>
            <span className="file-tree-count">{library.length}</span>
          </button>
          {onCreate && (
            <button
              type="button"
              className="file-tree-action"
              title="New library script"
              aria-label="New library script"
              onClick={() => onCreate('script-python')}
            >
              <IconPlus size={13} />
            </button>
          )}
        </div>
        {!libraryCollapsed &&
          (library.length === 0 ? (
            <p className="file-tree-empty muted">No library scripts yet.</p>
          ) : (
            <PackageBranch
              node={buildPackageTree(library)}
              depth={0}
              collapsed={collapsed}
              onToggle={toggle}
              selectedPath={selectedPath}
              onSelect={onSelect}
              onDelete={onDelete}
            />
          ))}
      </section>

      {/* ---- anything unrecognised ---- */}
      {unknownGroups.map((group) => {
        const key = `type:${group.typeId}`;
        const isCollapsed = collapsed.has(key);
        return (
          <section className="file-tree-group" key={group.typeId}>
            <button
              type="button"
              className="file-tree-header"
              aria-expanded={!isCollapsed}
              onClick={() => toggle(key)}
            >
              <Chevron open={!isCollapsed} />
              <span>{group.label}</span>
              <span className="file-tree-count">{group.entries.length}</span>
            </button>
            {!isCollapsed && (
              <ul className="file-tree-list">
                {group.entries.map((entry) => (
                  <ScriptRow
                    key={entry.path}
                    entry={entry}
                    depth={1}
                    selectedPath={selectedPath}
                    onSelect={onSelect}
                    onDelete={onDelete}
                  />
                ))}
              </ul>
            )}
          </section>
        );
      })}

      {/* ---- Script Console ---- */}
      {onSelectSpecial && (
        <section className="file-tree-group">
          <button
            type="button"
            className={`file-tree-header file-tree-leaf${consoleSelected ? ' is-selected' : ''}`}
            aria-current={consoleSelected ? 'true' : undefined}
            onClick={() => onSelectSpecial('console')}
          >
            <IconTerminal size={14} className="file-tree-icon" />
            <span>Script Console</span>
          </button>
        </section>
      )}
    </nav>
  );
}

interface BranchProps {
  node: PackageNode;
  depth: number;
  collapsed: Set<string>;
  onToggle: (key: string) => void;
  selectedPath: string | null;
  onSelect: (entry: ScriptEntry) => void;
  onDelete?: (entry: ScriptEntry) => void;
}

function PackageBranch({
  node,
  depth,
  collapsed,
  onToggle,
  selectedPath,
  onSelect,
  onDelete,
}: BranchProps) {
  return (
    <ul className="file-tree-list">
      {node.children.map((child) => {
        const key = `pkg:${child.key}`;
        const isCollapsed = collapsed.has(key);
        return (
          <li key={child.key}>
            <button
              type="button"
              className="file-tree-package"
              style={{ paddingLeft: indent(depth + 1) }}
              aria-expanded={!isCollapsed}
              onClick={() => onToggle(key)}
            >
              <Chevron open={!isCollapsed} />
              <IconFolder size={14} className="file-tree-icon" />
              <span>{child.name}</span>
            </button>
            {!isCollapsed && (
              <PackageBranch
                node={child}
                depth={depth + 1}
                collapsed={collapsed}
                onToggle={onToggle}
                selectedPath={selectedPath}
                onSelect={onSelect}
                onDelete={onDelete}
              />
            )}
          </li>
        );
      })}
      {node.scripts.map((entry) => (
        <ScriptRow
          key={entry.path}
          entry={entry}
          depth={depth + 1}
          selectedPath={selectedPath}
          onSelect={onSelect}
          onDelete={onDelete}
        />
      ))}
    </ul>
  );
}

interface RowProps {
  entry: ScriptEntry;
  depth: number;
  selectedPath: string | null;
  onSelect: (entry: ScriptEntry) => void;
  onDelete?: (entry: ScriptEntry) => void;
}

function ScriptRow({ entry, depth, selectedPath, onSelect, onDelete }: RowProps) {
  const selected = entry.path === selectedPath;
  // Only a script this project OWNS can be deleted. An inherited one has nothing
  // here to remove, and the server 404s it — so the button is absent rather than
  // present and failing.
  const deletable = Boolean(onDelete) && entry.origin !== 'inherited' && !entry.singleton;
  return (
    <li className="file-tree-row">
      <button
        type="button"
        className={`file-tree-item${selected ? ' is-selected' : ''}`}
        style={{ paddingLeft: indent(depth) }}
        aria-current={selected ? 'true' : undefined}
        onClick={() => onSelect(entry)}
      >
        {iconForType(entry.typeId, { size: 14, className: 'file-tree-icon' })}
        <span className="file-tree-name">{entry.name || entry.typeLabel}</span>
        {/* Inheritance is not decoration: editing an inherited script CREATES a
            local override rather than changing the parent, and the user has to
            know that before they type. */}
        {entry.origin !== 'local' && (
          <span className={`badge badge-${entry.origin}`} title={originTitle(entry)}>
            {entry.origin}
          </span>
        )}
      </button>
      {deletable && (
        <button
          type="button"
          className="file-tree-action file-tree-delete"
          title={`Delete ${entry.name}`}
          aria-label={`Delete ${entry.name}`}
          onClick={() => onDelete?.(entry)}
        >
          <IconTrash size={13} />
        </button>
      )}
    </li>
  );
}

function originTitle(entry: ScriptEntry): string {
  return entry.origin === 'inherited'
    ? `Inherited from ${entry.owner}. Saving creates a local override.`
    : `Overrides a copy inherited from a parent project.`;
}

/** Indentation per tree level, in the token scale. */
function indent(depth: number): string {
  return `calc(var(--space-2) + ${depth} * var(--space-4))`;
}


