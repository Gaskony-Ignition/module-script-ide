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
  it('groups by type label, in the declared order', () => {
    render(<FileTree scripts={SCRIPTS} selectedPath={null} onSelect={vi.fn()} />);
    const headers = screen
      .getAllByRole('button', { expanded: true })
      .map((b) => b.textContent ?? '');
    expect(headers[0]).toContain('Project Library');
    expect(headers.some((h) => h.includes('Timer'))).toBe(true);
    expect(headers.some((h) => h.includes('Startup'))).toBe(true);
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

  it('says so when a project has no editable scripts', () => {
    render(<FileTree scripts={[]} selectedPath={null} onSelect={vi.fn()} />);
    expect(screen.getByText('No editable scripts in this project.')).toBeInTheDocument();
  });
});
