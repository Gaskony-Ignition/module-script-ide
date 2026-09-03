/**
 * The Web Dev view: endpoints, and the HTTP methods each implements.
 *
 * Web Dev is its own activity-bar view rather than another section under
 * Scripting, because it is a different resource under a different module id and
 * because named queries will want the same treatment — three unrelated resource
 * trees stacked in one scrolling column stops being navigable.
 *
 * An endpoint is a FOLDER of up to eight handler scripts, so a row expands to
 * its methods rather than opening one file. Methods the endpoint does not
 * implement are shown greyed with an "add" affordance: that is the only way to
 * create `doPost.py` on an endpoint that currently has only `doGet.py`, and
 * hiding them made it impossible.
 */
import { useMemo } from 'react';
import { useStickySet } from '../workspace/viewState';
import type { ScriptEntry } from '../api/scripts';
import { IconGlobe, IconPlus, IconTrash } from './Icons';
import { Chevron } from './Chevron';
import './FileTree.css';

/** Every method an endpoint can implement, in the Designer's order. */
export const WEBDEV_METHODS = [
  'doGet', 'doPost', 'doPut', 'doDelete', 'doHead', 'doOptions', 'doTrace', 'doPatch',
] as const;

export interface WebDevTreeProps {
  /** Web Dev entries from the script listing — same endpoint, filtered by type. */
  endpoints: ScriptEntry[];
  selectedPath: string | null;
  /** Which method's script is open, so the right child row is highlighted. */
  selectedMethod?: string | null;
  onOpen: (entry: ScriptEntry, method: string) => void;
  /** Omitted when the session cannot write. */
  onCreate?: () => void;
  onDelete?: (entry: ScriptEntry) => void;
  onAddMethod?: (entry: ScriptEntry, method: string) => void;
  onEditConfig?: (entry: ScriptEntry) => void;
}

export default function WebDevTree({
  endpoints,
  selectedPath,
  selectedMethod,
  onOpen,
  onCreate,
  onDelete,
  onAddMethod,
  onEditConfig,
}: WebDevTreeProps) {
  // Sticky across an unmount — see useStickySet. This tree in particular was
  // called out for it: "everytime I go to that tab they return to being fully
  // expanded regardless of what I set it to" (Nigel, 03/09/2026).
  const [collapsed, setCollapsed] = useStickySet('webdev.collapsed');

  const sorted = useMemo(
    () => [...endpoints].sort((a, b) => a.name.localeCompare(b.name)),
    [endpoints]
  );

  function toggle(key: string) {
    setCollapsed((previous) => {
      const next = new Set(previous);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <nav className="file-tree" aria-label="Web Dev">
      <div className="file-tree-header-row">
        <div className="file-tree-header file-tree-static">
          <span>Endpoints</span>
          <span className="file-tree-count">{sorted.length}</span>
        </div>
        {onCreate && (
          <button
            type="button"
            className="file-tree-action"
            title="New Web Dev endpoint"
            aria-label="New Web Dev endpoint"
            onClick={onCreate}
          >
            <IconPlus size={13} />
          </button>
        )}
      </div>

      {sorted.length === 0 ? (
        <p className="file-tree-empty muted">No Web Dev endpoints in this project.</p>
      ) : (
        <ul className="file-tree-list">
          {sorted.map((entry) => {
            const key = `wd:${entry.path}`;
            const isCollapsed = collapsed.has(key);
            const implemented = new Set(entry.methods ?? []);
            return (
              <li key={entry.path}>
                <div className="file-tree-row">
                  <button
                    type="button"
                    className="file-tree-package"
                    aria-expanded={!isCollapsed}
                    onClick={() => toggle(key)}
                  >
                    <Chevron open={!isCollapsed} />
                    <IconGlobe size={14} className="file-tree-icon" />
                    <span className="file-tree-name">{entry.name}</span>
                    {entry.origin !== 'local' && (
                      <span className={`badge badge-${entry.origin}`}>{entry.origin}</span>
                    )}
                  </button>
                  {onEditConfig && (
                    <button
                      type="button"
                      className="file-tree-action"
                      title={`Settings for ${entry.name}`}
                      aria-label={`Settings for ${entry.name}`}
                      onClick={() => onEditConfig(entry)}
                    >
                      ⚙
                    </button>
                  )}
                  {onDelete && entry.origin !== 'inherited' && (
                    <button
                      type="button"
                      className="file-tree-action file-tree-delete"
                      title={`Delete ${entry.name}`}
                      aria-label={`Delete ${entry.name}`}
                      onClick={() => onDelete(entry)}
                    >
                      <IconTrash size={13} />
                    </button>
                  )}
                </div>

                {!isCollapsed && (
                  <ul className="file-tree-list">
                    {WEBDEV_METHODS.map((method) => {
                      const has = implemented.has(method);
                      const isSelected =
                        entry.path === selectedPath && method === selectedMethod;
                      if (!has) {
                        // Not implemented. Shown, not hidden — this is the only
                        // place to create doPost.py on a doGet-only endpoint.
                        return onAddMethod ? (
                          <li key={method} className="file-tree-row">
                            <button
                              type="button"
                              className="file-tree-item is-absent"
                              onClick={() => onAddMethod(entry, method)}
                              title={`Add ${method} to ${entry.name}`}
                            >
                              <IconPlus size={12} className="file-tree-icon" />
                              <span className="file-tree-name">{method}</span>
                            </button>
                          </li>
                        ) : null;
                      }
                      return (
                        <li key={method} className="file-tree-row">
                          <button
                            type="button"
                            className={`file-tree-item${isSelected ? ' is-selected' : ''}`}
                            aria-current={isSelected ? 'true' : undefined}
                            onClick={() => onOpen(entry, method)}
                          >
                            <span className="file-tree-method">{method}</span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </nav>
  );
}
