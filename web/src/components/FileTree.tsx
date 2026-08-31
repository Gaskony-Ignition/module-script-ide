/**
 * The left rail: every editable script in the open project.
 *
 * Grouped by resource type, in the order ScriptResourceTypes declares them so
 * the rail reads the same way as the Designer's own project browser. Project
 * Library entries carry slash-separated package names (`util/helpers`) and are
 * shown as a nested, collapsible tree; every other type is a flat list, because
 * every other type is genuinely flat on the gateway.
 */
import { useMemo, useState } from 'react';
import type { ScriptEntry, ScriptTypeId } from '../api/scripts';
import './FileTree.css';

export interface FileTreeProps {
  scripts: ScriptEntry[];
  /** Path of the entry currently being edited, if any. */
  selectedPath: string | null;
  onSelect: (entry: ScriptEntry) => void;
}

/**
 * Display order of the type groups. Matches ScriptResourceTypes.all()'s
 * insertion order — the listing endpoint does not promise an order, so the
 * client fixes one rather than letting the rail reshuffle between reads.
 */
const TYPE_ORDER: ScriptTypeId[] = [
  'script-python',
  'timer',
  'message',
  'startup',
  'shutdown',
  'update',
  'scheduled',
  'tag-change',
];

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

export default function FileTree({ scripts, selectedPath, onSelect }: FileTreeProps) {
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());

  const groups = useMemo(() => {
    const byType = new Map<string, ScriptEntry[]>();
    for (const entry of scripts) {
      const list = byType.get(entry.typeId);
      if (list) list.push(entry);
      else byType.set(entry.typeId, [entry]);
    }
    // Known types first in their declared order, then anything the gateway sent
    // that this build does not know about — better shown than silently dropped.
    const ordered = [
      ...TYPE_ORDER.filter((t) => byType.has(t)),
      ...[...byType.keys()].filter((t) => !TYPE_ORDER.includes(t as ScriptTypeId)),
    ];
    return ordered.map((typeId) => {
      const entries = byType.get(typeId) ?? [];
      return { typeId, label: entries[0]?.typeLabel ?? typeId, entries };
    });
  }, [scripts]);

  function toggle(key: string) {
    setCollapsed((previous) => {
      const next = new Set(previous);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  if (scripts.length === 0) {
    return (
      <nav className="file-tree" aria-label="Scripts">
        <p className="file-tree-empty muted">No editable scripts in this project.</p>
      </nav>
    );
  }

  return (
    <nav className="file-tree" aria-label="Scripts">
      {groups.map((group) => {
        const groupKey = `type:${group.typeId}`;
        const isCollapsed = collapsed.has(groupKey);
        return (
          <section className="file-tree-group" key={group.typeId}>
            <button
              type="button"
              className="file-tree-header"
              aria-expanded={!isCollapsed}
              onClick={() => toggle(groupKey)}
            >
              <Chevron open={!isCollapsed} />
              <span>{group.label}</span>
              <span className="file-tree-count">{group.entries.length}</span>
            </button>
            {!isCollapsed &&
              (group.typeId === 'script-python' ? (
                <PackageBranch
                  node={buildPackageTree(group.entries)}
                  depth={0}
                  collapsed={collapsed}
                  onToggle={toggle}
                  selectedPath={selectedPath}
                  onSelect={onSelect}
                />
              ) : (
                <ul className="file-tree-list">
                  {[...group.entries]
                    .sort((a, b) => a.name.localeCompare(b.name))
                    .map((entry) => (
                      <ScriptRow
                        key={entry.path}
                        entry={entry}
                        depth={1}
                        selectedPath={selectedPath}
                        onSelect={onSelect}
                      />
                    ))}
                </ul>
              ))}
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
}

function PackageBranch({ node, depth, collapsed, onToggle, selectedPath, onSelect }: BranchProps) {
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
}

function ScriptRow({ entry, depth, selectedPath, onSelect }: RowProps) {
  const selected = entry.path === selectedPath;
  return (
    <li>
      <button
        type="button"
        className={`file-tree-item${selected ? ' is-selected' : ''}`}
        style={{ paddingLeft: indent(depth) }}
        aria-current={selected ? 'true' : undefined}
        onClick={() => onSelect(entry)}
      >
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

function Chevron({ open }: { open: boolean }) {
  return (
    <span className={`file-tree-chevron${open ? ' is-open' : ''}`} aria-hidden="true">
      ▸
    </span>
  );
}
