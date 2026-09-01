/**
 * The left rail: every editable script in the open project.
 *
 * The "Scripting" heading belongs to the RAIL, not to this component — the rail
 * shows the active view's name and this tree is one of several views it hosts.
 *
 * The shape is the real Designer's, and it is measured rather than guessed —
 * `web-designer/docs/design-handoff/real-designer/SCRIPTING.md` §1, captured
 * from an 8.3 Designer on 21/08/2026:
 *
 *   Scripting
 *   ├── Gateway Events
 *   │   ├── Message      (folder, shown even when empty)
 *   │   ├── Scheduled    (folder)
 *   │   ├── Tag Change   (folder)
 *   │   ├── Timer        (folder)
 *   │   ├── Shutdown     ← a SCRIPT, not a folder
 *   │   ├── Startup      ← a SCRIPT
 *   │   └── Update       ← a SCRIPT
 *   └── Project Library
 *       └── util/helpers
 *
 * **The four folders come first, then the three singletons.** Not alphabetical
 * across the group — folders-then-leaves, each alphabetical, which is the rule
 * the whole Designer tree follows. Until 1.3.0 this listed the singletons first
 * AND rendered them as collapsible folders containing one nameless row, which is
 * two things the Designer does not do (Nigel, 01/09/2026).
 *
 * Two row decorations are measured too: a singleton's label is **bold** once it
 * has been created, and a disabled event script carries a badge.
 *
 * Script Console is deliberately NOT here any more. It was a row in this tree in
 * 1.1.0–1.2.0, where it read as a script among scripts; it has its own icon on
 * the activity bar and its own tab in the bottom panel now.
 *
 * Project Library entries carry slash-separated package names and are shown as a
 * nested, collapsible tree; each gateway event type is a flat list, because each
 * is genuinely flat on the gateway.
 */
import { useMemo, useState } from 'react';
import type { ScriptEntry, ScriptTypeId } from '../api/scripts';
import { IconFolder, IconPlus, IconRevert, IconTrash, iconForType } from './Icons';
import { Chevron } from './Chevron';
import './FileTree.css';

export interface FileTreeProps {
  scripts: ScriptEntry[];
  /** Path of the entry currently being edited, if any. */
  selectedPath: string | null;
  onSelect: (entry: ScriptEntry) => void;
  /** Offered only when the session may write — omit to hide create/delete. */
  onCreate?: (typeId: ScriptTypeId) => void;
  onDelete?: (entry: ScriptEntry) => void;
  /**
   * Create a singleton that does not exist yet.
   *
   * Separate from {@link onCreate}, which opens a name dialog — a singleton has
   * no name to ask for. The Designer shows Startup, Shutdown and Update whether
   * or not they exist and writes the resource when you first save; here the row
   * creates it and opens it, which reaches the same place in one click.
   */
  onCreateSingleton?: (typeId: ScriptTypeId) => void;
}

/**
 * The four gateway event types the Designer shows as FOLDERS, in its order.
 *
 * Alphabetical by label, and shown even when the project has none of that type —
 * an empty folder is the only place to click "new" for its type, so filtering
 * them out makes the first script of a kind impossible to create.
 */
const GATEWAY_EVENT_FOLDERS: ScriptTypeId[] = [
  'message',
  'scheduled',
  'tag-change',
  'timer',
];

/**
 * The three the Designer shows as single SCRIPTS, in its order.
 *
 * The platform stores each as one resource with no name segment. They are not
 * folders and have no "new" affordance: there can only ever be one.
 */
const GATEWAY_EVENT_SINGLETONS: ScriptTypeId[] = ['shutdown', 'startup', 'update'];

const LIBRARY_TYPE: ScriptTypeId = 'script-python';

const GATEWAY_EVENT_TYPES: ScriptTypeId[] = [
  ...GATEWAY_EVENT_FOLDERS,
  ...GATEWAY_EVENT_SINGLETONS,
];

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
  onCreate,
  onDelete,
  onCreateSingleton,
}: FileTreeProps) {
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());

  const { library, eventGroups, singletons, unknownGroups } = useMemo(() => {
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
      eventGroups: GATEWAY_EVENT_FOLDERS.map((typeId) => {
        const entries = byType.get(typeId) ?? [];
        return { typeId, label: entries[0]?.typeLabel ?? TYPE_LABELS[typeId] ?? typeId, entries };
      }),
      // The three singletons are ROWS, not folders. Each is listed whether or
      // not it exists: `entry` is undefined until the project has one, and the
      // row is what creates it.
      singletons: GATEWAY_EVENT_SINGLETONS.map((typeId) => {
        const entry = (byType.get(typeId) ?? [])[0];
        return { typeId, label: entry?.typeLabel ?? TYPE_LABELS[typeId] ?? typeId, entry };
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
            {eventGroups.reduce((total, g) => total + g.entries.length, 0)
              + singletons.filter((s) => s.entry).length}
          </span>
        </button>
        {!eventsCollapsed && (
          <>
            {eventGroups.map((group) => {
              const key = `type:${group.typeId}`;
              const isCollapsed = collapsed.has(key);
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
                    {onCreate && (
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
                      None yet.
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
            })}

            {/* The three singletons: rows, at the same depth as a folder, after
                all four folders. Folders-then-leaves is the Designer's rule. */}
            <ul className="file-tree-list">
              {singletons.map((single) => (
                <SingletonRow
                  key={single.typeId}
                  typeId={single.typeId}
                  label={single.label}
                  entry={single.entry}
                  selectedPath={selectedPath}
                  onSelect={onSelect}
                  onDelete={onDelete}
                  onCreate={onCreateSingleton}
                />
              ))}
            </ul>
          </>
        )}
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

interface SingletonRowProps {
  typeId: ScriptTypeId;
  label: string;
  /** Undefined until this project actually has the script. */
  entry?: ScriptEntry;
  selectedPath: string | null;
  onSelect: (entry: ScriptEntry) => void;
  onDelete?: (entry: ScriptEntry) => void;
  onCreate?: (typeId: ScriptTypeId) => void;
}

/**
 * Shutdown, Startup or Update — one row, never a folder.
 *
 * The Designer lists all three whether or not the project has them, renders the
 * label **bold** once one exists, and offers no rename, cut or copy on them
 * (SCRIPTING.md §1.1 and §5.5). A row for one that does not exist is not dead:
 * clicking it creates the script, which is the only way to get a Startup script
 * into a project from here.
 */
function SingletonRow({
  typeId, label, entry, selectedPath, onSelect, onDelete, onCreate,
}: SingletonRowProps) {
  const selected = Boolean(entry) && entry?.path === selectedPath;
  const disabled = entry?.enabled === false;
  // `defined` comes from the listing; fall back to "it is listed at all", which
  // is what an older gateway response gives us.
  const exists = entry ? entry.defined !== false : false;
  return (
    <li className="file-tree-row">
      <button
        type="button"
        className={`file-tree-item${selected ? ' is-selected' : ''}`}
        style={{ paddingLeft: indent(1) }}
        aria-current={selected ? 'true' : undefined}
        title={exists ? undefined : `Not defined in this project — click to create the ${label} script.`}
        onClick={() => {
          if (entry && exists) {
            onSelect(entry);
          } else {
            onCreate?.(typeId);
          }
        }}
        disabled={!exists && !onCreate}
      >
        {iconForType(typeId, { size: 14, className: 'file-tree-icon' })}
        <span className={`file-tree-name${exists ? ' is-defined' : ' is-undefined'}`}>
          {label}
        </span>
        {disabled && <DisabledBadge />}
      </button>
      {entry && exists && onDelete && entry.origin !== 'inherited' && (
        <button
          type="button"
          className="file-tree-action file-tree-delete"
          title={`Delete the ${label} script`}
          aria-label={`Delete the ${label} script`}
          onClick={() => onDelete(entry)}
        >
          <IconTrash size={13} />
        </button>
      )}
    </li>
  );
}

/**
 * The Designer's "this event script is switched off" marker.
 *
 * A badge rather than dimming the row: dimming is already what an inherited or
 * unsaved row does, and three meanings on one visual channel is no meaning.
 */
function DisabledBadge() {
  return (
    <span className="badge badge-disabled" title="Disabled — this script will not run">
      off
    </span>
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
  // On an override, the same button means something else. The Designer offers
  // no Delete at all on an overridden resource — its menu has `Discard
  // Overrides`, and the difference is not pedantic: this removes the local copy
  // and the script keeps working, inherited from the parent. Calling that
  // "Delete" invites the user to think they are about to lose the script.
  const discards = entry.origin === 'override';
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
        {entry.enabled === false && <DisabledBadge />}
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
          className={`file-tree-action ${discards ? 'file-tree-discard' : 'file-tree-delete'}`}
          title={
            discards
              ? `Discard the local override of ${entry.name} and return to the copy inherited from ${entry.owner}`
              : `Delete ${entry.name}`
          }
          aria-label={
            discards ? `Discard overrides on ${entry.name}` : `Delete ${entry.name}`
          }
          onClick={() => onDelete?.(entry)}
        >
          {discards ? <IconRevert size={13} /> : <IconTrash size={13} />}
        </button>
      )}
    </li>
  );
}

function originTitle(entry: ScriptEntry): string {
  return entry.origin === 'inherited'
    ? `Inherited from ${entry.owner}. Read-only until you override it.`
    : `Overrides the copy inherited from ${entry.owner}. Discarding the override returns to it.`;
}

/** Indentation per tree level, in the token scale. */
function indent(depth: number): string {
  return `calc(var(--space-2) + ${depth} * var(--space-4))`;
}


