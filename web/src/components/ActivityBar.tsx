/**
 * The far-left activity bar, VS Code style.
 *
 * Its job is to make the side bar COLLAPSIBLE without hiding navigation:
 * clicking the active view collapses it to just this strip, and clicking any
 * view reopens it on that view. A toolbar above the tree could not do that — it
 * would disappear along with the thing it controls.
 *
 * It is also where a new top-level area is added, which is why Web Dev is a view
 * here rather than another section inside the script tree: named queries will be
 * a third, and three unrelated resource trees stacked in one scrolling column
 * stops being navigable.
 *
 * The lower group is different in kind and is separated by the gap between them:
 * those two open the bottom PANEL rather than the side bar. Script Console used
 * to be a row in the script tree, where it read as a script among scripts;
 * Nigel asked for it out of the tree once it had an icon of its own.
 *
 * There is no Search icon. Find and replace live in the editor on Ctrl+F and
 * Ctrl+H, and an icon that opened the script tree under the heading "Scripting"
 * was a promise of a view that does not exist.
 */
import type { ReactNode } from 'react';
import { IconFiles, IconGlobe, IconPlay, IconTerminal } from './Icons';
import './ActivityBar.css';

/** Side-bar views. */
export type ViewId = 'scripts' | 'webdev';

/** Bottom-panel views. */
export type PanelId = 'console' | 'terminal';

export interface ActivityBarProps {
  /** The side-bar view, whether or not the side bar is showing. */
  active: ViewId;
  /** False when the side bar is collapsed to the strip. */
  expanded: boolean;
  onSelect: (view: ViewId) => void;
  /** The panel tab, or null when the panel is closed. */
  activePanel: PanelId | null;
  onSelectPanel: (panel: PanelId) => void;
}

const VIEWS: Array<{ id: ViewId; label: string; icon: ReactNode }> = [
  { id: 'scripts', label: 'Scripting', icon: <IconFiles size={22} /> },
  { id: 'webdev', label: 'Web Dev', icon: <IconGlobe size={22} /> },
];

const PANELS: Array<{ id: PanelId; label: string; icon: ReactNode }> = [
  { id: 'console', label: 'Script Console', icon: <IconPlay size={18} /> },
  { id: 'terminal', label: 'Terminal', icon: <IconTerminal size={22} /> },
];

export default function ActivityBar({
  active, expanded, onSelect, activePanel, onSelectPanel,
}: ActivityBarProps) {
  return (
    <nav className="activity-bar" aria-label="Views">
      {VIEWS.map((view) => {
        const isActive = view.id === active && expanded;
        return (
          <button
            key={view.id}
            type="button"
            className={`activity-item${isActive ? ' is-active' : ''}`}
            // aria-pressed rather than aria-current: this is a toggle, and the
            // active view can be pressed again to collapse the side bar.
            aria-pressed={isActive}
            // The label is the only name this control has — there is no visible
            // text — so it carries both the accessible name and the tooltip.
            aria-label={view.label}
            title={view.label}
            onClick={() => onSelect(view.id)}
          >
            {view.icon}
          </button>
        );
      })}

      <span className="activity-spacer" />

      {PANELS.map((panel) => {
        const isActive = panel.id === activePanel;
        return (
          <button
            key={panel.id}
            type="button"
            className={`activity-item${isActive ? ' is-active' : ''}`}
            aria-pressed={isActive}
            aria-label={panel.label}
            title={panel.label}
            onClick={() => onSelectPanel(panel.id)}
          >
            {panel.icon}
          </button>
        );
      })}
    </nav>
  );
}
