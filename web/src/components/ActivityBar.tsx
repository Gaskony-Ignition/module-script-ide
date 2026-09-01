/**
 * The far-left activity bar, VS Code style.
 *
 * Its job is to make the rail COLLAPSIBLE without hiding navigation: clicking
 * the active view collapses the side bar to just this strip, and clicking any
 * view reopens it on that view. That is VS Code's behaviour, and it is the
 * reason the icons live in their own column rather than as a toolbar above the
 * tree — a toolbar would disappear along with the thing it controls.
 *
 * It is also where a new top-level area is added, which is why Web Dev is a
 * view here rather than another section inside the script tree: named queries
 * will be a third, and three unrelated resource trees stacked in one scrolling
 * column stops being navigable.
 */
import type { ReactNode } from 'react';
import { IconFiles, IconGlobe, IconSearch, IconTerminal } from './Icons';
import './ActivityBar.css';

export type ViewId = 'scripts' | 'webdev' | 'search' | 'console';

export interface ActivityBarProps {
  active: ViewId;
  /** False when the side bar is collapsed to the strip. */
  expanded: boolean;
  onSelect: (view: ViewId) => void;
}

const VIEWS: Array<{ id: ViewId; label: string; icon: ReactNode }> = [
  { id: 'scripts', label: 'Scripting', icon: <IconFiles size={22} /> },
  { id: 'webdev', label: 'Web Dev', icon: <IconGlobe size={22} /> },
  { id: 'search', label: 'Search', icon: <IconSearch size={22} /> },
  { id: 'console', label: 'Script Console', icon: <IconTerminal size={22} /> },
];

export default function ActivityBar({ active, expanded, onSelect }: ActivityBarProps) {
  return (
    <nav className="activity-bar" aria-label="Views">
      {VIEWS.map((view) => {
        const isActive = view.id === active;
        return (
          <button
            key={view.id}
            type="button"
            className={`activity-item${isActive && expanded ? ' is-active' : ''}`}
            // aria-pressed rather than aria-current: this is a toggle, and the
            // active view can be pressed again to collapse the side bar.
            aria-pressed={isActive && expanded}
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
    </nav>
  );
}
