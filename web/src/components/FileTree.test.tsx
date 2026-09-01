import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import FileTree from './FileTree';
import type { ScriptEntry } from '../api/scripts';

function entry(overrides: Partial<ScriptEntry> & Pick<ScriptEntry, 'path' | 'typeId' | 'name' | 'typeLabel'>): ScriptEntry {
  return {
    signature: 'sig',
    dataKeys: ['code.py'],
    scriptKey: 'code.py',
    singleton: false,
    origin: 'local',
    owner: 'MyProject',
    ...overrides,
  };
}

const SCRIPTS: ScriptEntry[] = [
  entry({
    path: 'ignition/script-python/util/helpers',
    typeId: 'script-python',
    name: 'util/helpers',
    typeLabel: 'Project Library',
  }),
  entry({
    path: 'ignition/script-python/util/text/format',
    typeId: 'script-python',
    name: 'util/text/format',
    typeLabel: 'Project Library',
  }),
  entry({
    path: 'ignition/script-python/toplevel',
    typeId: 'script-python',
    name: 'toplevel',
    typeLabel: 'Project Library',
    origin: 'inherited',
    owner: 'ParentProject',
  }),
  entry({
    path: 'ignition/timer/Poller',
    typeId: 'timer',
    name: 'Poller',
    typeLabel: 'Timer',
    scriptKey: 'handleTimerEvent.py',
    origin: 'override',
  }),
  entry({
    path: 'ignition/startup',
    typeId: 'startup',
    // A singleton has no name segment at all — its type label is its identity.
    name: '',
    typeLabel: 'Startup',
    scriptKey: 'onStartup.py',
    singleton: true,
  }),
];

describe('FileTree', () => {
  it('follows the Designer shape: Gateway Events, then Project Library', () => {
    // The rail deliberately mirrors the Designer's project browser, so the order
    // of the two top-level sections is part of the contract rather than
    // incidental — someone navigating by muscle memory should not have to look.
    render(<FileTree scripts={SCRIPTS} selectedPath={null} onSelect={vi.fn()} />);
    const headers = screen
      .getAllByRole('button', { expanded: true })
      .map((b) => b.textContent ?? '');
    expect(headers[0]).toContain('Gateway Events');
    expect(headers.some((h) => h.includes('Project Library'))).toBe(true);
    // Event types are nested UNDER Gateway Events, not siblings of the library.
    expect(headers.some((h) => h.includes('Timer'))).toBe(true);
    expect(headers.some((h) => h.includes('Startup'))).toBe(true);
  });

  it('nests every gateway event type inside Gateway Events', () => {
    render(<FileTree scripts={SCRIPTS} selectedPath={null} onSelect={vi.fn()} />);
    const events = screen.getByRole('button', { name: /Gateway Events/ });
    fireEvent.click(events);
    // Collapsing the parent must hide the child types, which is the whole
    // difference between nesting them and merely listing them in order.
    expect(screen.queryByRole('button', { name: /Timer/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /Startup/ })).toBeNull();
    // Project Library is a sibling and must survive.
    expect(screen.getByRole('button', { name: /Project Library/ })).toBeTruthy();
  });

  it('offers the Script Console only when a handler is supplied', () => {
    const onSelectSpecial = vi.fn();
    const { unmount } = render(
      <FileTree scripts={SCRIPTS} selectedPath={null} onSelect={vi.fn()} />
    );
    expect(screen.queryByRole('button', { name: 'Script Console' })).toBeNull();
    unmount();

    render(
      <FileTree
        scripts={SCRIPTS}
        selectedPath={null}
        onSelect={vi.fn()}
        onSelectSpecial={onSelectSpecial}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Script Console' }));
    expect(onSelectSpecial).toHaveBeenCalledWith('console');
  });

  it('offers delete only for scripts this project owns', () => {
    const onDelete = vi.fn();
    render(
      <FileTree
        scripts={SCRIPTS}
        selectedPath={null}
        onSelect={vi.fn()}
        onDelete={onDelete}
      />
    );
    // `toplevel` is inherited: there is nothing in THIS project to delete, and
    // the server 404s it — so the affordance must be absent, not present and
    // failing.
    expect(screen.queryByRole('button', { name: 'Delete toplevel' })).toBeNull();
    // A singleton cannot be deleted either.
    expect(screen.queryByRole('button', { name: /Delete\s*$/ })).toBeNull();
    // A local one can.
    fireEvent.click(screen.getByRole('button', { name: 'Delete helpers' }));
    expect(onDelete).toHaveBeenCalledTimes(1);
  });

  it('hides create and delete entirely when no handlers are given', () => {
    // A non-admin session passes no handlers, and must see no affordance it
    // cannot use rather than a button that 403s.
    render(<FileTree scripts={SCRIPTS} selectedPath={null} onSelect={vi.fn()} />);
    expect(screen.queryByRole('button', { name: 'New library script' })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Delete / })).toBeNull();
  });

  it('renders project-library names as a nested package tree', () => {
    render(<FileTree scripts={SCRIPTS} selectedPath={null} onSelect={vi.fn()} />);
    // `util/helpers` and `util/text/format` collapse into one `util` package
    // with a nested `text` inside it, not two flat rows.
    expect(screen.getByRole('button', { name: /util/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /text/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'helpers' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'format' })).toBeInTheDocument();
    // The full slash-separated name is never shown as a single row.
    expect(screen.queryByText('util/helpers')).not.toBeInTheDocument();
  });

  it('collapses a package and hides everything under it', () => {
    render(<FileTree scripts={SCRIPTS} selectedPath={null} onSelect={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /util/ }));
    expect(screen.queryByRole('button', { name: 'helpers' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'format' })).not.toBeInTheDocument();
    // Siblings outside the package are unaffected.
    expect(screen.getByRole('button', { name: /toplevel/ })).toBeInTheDocument();
  });

  it('collapses a whole type group', () => {
    render(<FileTree scripts={SCRIPTS} selectedPath={null} onSelect={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /Timer/ }));
    expect(screen.queryByRole('button', { name: 'Poller' })).not.toBeInTheDocument();
  });

  it('shows a singleton under its own group, labelled by its type', () => {
    render(<FileTree scripts={SCRIPTS} selectedPath={null} onSelect={vi.fn()} />);
    // Two matches: the group header and the entry itself.
    expect(screen.getAllByRole('button', { name: /Startup/ }).length).toBeGreaterThanOrEqual(2);
  });

  it('badges anything that is not local, and leaves local entries unbadged', () => {
    render(<FileTree scripts={SCRIPTS} selectedPath={null} onSelect={vi.fn()} />);
    const inherited = screen.getByRole('button', { name: /toplevel/ });
    expect(within(inherited).getByText('inherited')).toBeInTheDocument();

    const override = screen.getByRole('button', { name: /Poller/ });
    expect(within(override).getByText('override')).toBeInTheDocument();

    const local = screen.getByRole('button', { name: 'helpers' });
    expect(within(local).queryByText(/inherited|override/)).not.toBeInTheDocument();
  });

  it('opens the entry that was clicked', () => {
    const onSelect = vi.fn();
    render(<FileTree scripts={SCRIPTS} selectedPath={null} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole('button', { name: 'helpers' }));
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ path: 'ignition/script-python/util/helpers' })
    );
  });

  it('marks the open entry as current', () => {
    render(
      <FileTree
        scripts={SCRIPTS}
        selectedPath="ignition/script-python/util/helpers"
        onSelect={vi.fn()}
      />
    );
    expect(screen.getByRole('button', { name: 'helpers' })).toHaveAttribute('aria-current', 'true');
    expect(screen.getByRole('button', { name: 'format' })).not.toHaveAttribute('aria-current');
  });

  it('says so per section when a project has nothing in it', () => {
    // Per section rather than one message for the whole rail: with the Designer
    // shape the two sections are independent, and a project with events but no
    // library scripts is ordinary. One global "nothing here" would be wrong for
    // it in both directions.
    render(<FileTree scripts={[]} selectedPath={null} onSelect={vi.fn()} />);
    expect(screen.getByText('None in this project.')).toBeInTheDocument();
    expect(screen.getByText('No library scripts yet.')).toBeInTheDocument();
  });
});
