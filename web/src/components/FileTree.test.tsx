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
    defined: true,
  }),
  entry({
    path: 'ignition/timer/Disabled',
    typeId: 'timer',
    name: 'Disabled',
    typeLabel: 'Timer',
    scriptKey: 'handleTimerEvent.py',
    enabled: false,
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
    // Startup is NOT one of them: it is a script, not a folder, so it must not
    // appear as an expandable header at all.
    expect(headers.some((h) => h.includes('Startup'))).toBe(false);
  });

  it('lists the four event FOLDERS before the three singleton scripts', () => {
    // Measured off the real 8.3 Designer (SCRIPTING.md §1): folders first, in
    // the order Message / Scheduled / Tag Change / Timer, then Shutdown /
    // Startup / Update as single scripts. Not alphabetical across the group.
    render(<FileTree scripts={SCRIPTS} selectedPath={null} onSelect={vi.fn()} />);
    const labels = screen
      .getAllByRole('button')
      .map((b) => (b.textContent ?? '').trim());
    const order = ['Message Handler', 'Scheduled', 'Tag Change', 'Timer',
      'Shutdown', 'Startup', 'Update']
      .map((name) => labels.findIndex((label) => label.startsWith(name)));
    expect(order.every((index) => index >= 0)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
  });

  it('renders a singleton as a row, never as a folder with one child', () => {
    render(<FileTree scripts={SCRIPTS} selectedPath={null} onSelect={vi.fn()} />);
    const startup = screen.getByRole('button', { name: /Startup/ });
    // A folder carries aria-expanded. Until 1.3.0 this one did, and the script
    // inside it was a second, nameless row — two things the Designer does not do.
    expect(startup.getAttribute('aria-expanded')).toBeNull();
  });

  it('creates a singleton the project does not have yet, from its row', () => {
    const onCreateSingleton = vi.fn();
    // No Update script anywhere in SCRIPTS — the row must still be there, and
    // clicking it is the only route to creating one.
    render(
      <FileTree
        scripts={SCRIPTS}
        selectedPath={null}
        onSelect={vi.fn()}
        onCreateSingleton={onCreateSingleton}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /Update/ }));
    expect(onCreateSingleton).toHaveBeenCalledWith('update');
  });

  it('badges a disabled event script', () => {
    // `enabled: false` is what the Designer marks in its own tree. Without the
    // badge a disabled timer looks identical to a running one.
    render(<FileTree scripts={SCRIPTS} selectedPath={null} onSelect={vi.fn()} />);
    const disabled = screen.getByRole('button', { name: /Disabled/ });
    expect(disabled.textContent).toContain('off');
    const running = screen.getByRole('button', { name: /Poller/ });
    expect(running.textContent).not.toContain('off');
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

  it('keeps the Script Console out of the tree', () => {
    // It was a row here in 1.1.0-1.2.0 and read as a script among scripts
    // (Nigel, 01/09/2026). It lives on the activity bar and in the bottom panel
    // now, and a second entry point in the tree would be two ways to open one
    // thing.
    render(<FileTree scripts={SCRIPTS} selectedPath={null} onSelect={vi.fn()} />);
    expect(screen.queryByRole('button', { name: 'Script Console' })).toBeNull();
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

  it('shows a singleton as exactly ONE row, labelled by its type', () => {
    render(<FileTree scripts={SCRIPTS} selectedPath={null} onSelect={vi.fn()} />);
    // ONE, not two. Until 1.3.0 there were two — a folder header and a nameless
    // row inside it — which is not how the Designer shows a single script.
    expect(screen.getAllByRole('button', { name: /Startup/ })).toHaveLength(1);
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
    // Every event folder is still listed — the Designer shows them when empty,
    // and an empty folder is the only place to create the first script of that
    // kind. So the message is per FOLDER, not one for the whole section.
    expect(screen.getAllByText('None yet.').length).toBeGreaterThan(0);
    // The three singletons are still listed — the Designer shows them whether
    // or not they exist — but as rows, dimmed, with the explanation on the
    // tooltip rather than as a paragraph where a script should be.
    for (const label of ['Shutdown', 'Startup', 'Update']) {
      const row = screen.getByRole('button', { name: new RegExp(label) });
      expect(row.getAttribute('title')).toContain('Not defined in this project');
    }
    expect(screen.getByText('No library scripts yet.')).toBeInTheDocument();
  });

  it('lists every gateway event folder even when the project has none of that type', () => {
    // Filtering empty folders out made it impossible to create the FIRST script
    // of a kind — there was nothing to click "new" on.
    render(<FileTree scripts={[]} selectedPath={null} onSelect={vi.fn()} onCreate={vi.fn()} />);
    for (const label of ['Timer', 'Message Handler', 'Scheduled', 'Tag Change']) {
      // The folder header carries a count; the sibling "+" carries the same
      // label, hence getAllBy — the assertion is that the folder EXISTS.
      expect(screen.getAllByRole('button', { name: new RegExp(label) }).length)
        .toBeGreaterThan(0);
    }
  });

  it('offers "new" per event type, but never for a singleton', () => {
    const onCreate = vi.fn();
    render(<FileTree scripts={[]} selectedPath={null} onSelect={vi.fn()} onCreate={onCreate} />);
    fireEvent.click(screen.getByRole('button', { name: 'New Timer script' }));
    expect(onCreate).toHaveBeenCalledWith('timer');
    // Startup/shutdown/update are ONE resource each; a second is not a thing
    // that can exist, and the Designer offers no "new" for them either.
    expect(screen.queryByRole('button', { name: 'New Startup script' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'New Shutdown script' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'New Update script' })).toBeNull();
  });
});

/**
 * Delete and Discard Overrides are different actions and must not share a word.
 *
 * Measured off the real 8.3.8 Designer (01/09/2026): the context menu on an
 * OVERRIDDEN resource has no `Delete` at all. It has `Discard Overrides`, whose
 * confirmation reads "return to its inherited state". The consequences are
 * genuinely different — a delete loses the script, a discard loses only this
 * project's edits and the script keeps running from the parent — so labelling
 * both "Delete" teaches people to click past the confirmation.
 */
describe('FileTree: discarding an override is not deleting', () => {
  it('offers no destructive action at all on a purely inherited script', () => {
    render(
      <FileTree
        scripts={SCRIPTS}
        selectedPath={null}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />
    );
    // `toplevel` is inherited: this project owns nothing to remove, and the
    // server 404s the attempt, so the button is absent rather than failing.
    expect(screen.queryByLabelText(/toplevel/i)).not.toBeInTheDocument();
  });

  it('labels the override action as a discard, naming the project it returns to', () => {
    render(
      <FileTree
        scripts={SCRIPTS}
        selectedPath={null}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />
    );
    const discard = screen.getByLabelText('Discard overrides on Poller');
    expect(discard).toBeInTheDocument();
    expect(discard.getAttribute('title')).toMatch(/inherited from/i);
    // The word that must NOT be there.
    expect(screen.queryByLabelText('Delete Poller')).not.toBeInTheDocument();
  });

  it('still calls Delete a delete on a script this project owns', () => {
    const onDelete = vi.fn();
    render(
      <FileTree
        scripts={SCRIPTS}
        selectedPath={null}
        onSelect={vi.fn()}
        onDelete={onDelete}
      />
    );
    fireEvent.click(screen.getByLabelText('Delete helpers'));
    expect(onDelete).toHaveBeenCalledTimes(1);
    expect(onDelete.mock.calls[0][0].origin).toBe('local');
  });

  it('says an inherited script is read-only, not that saving will fork it', () => {
    render(
      <FileTree scripts={SCRIPTS} selectedPath={null} onSelect={vi.fn()} />
    );
    // The 1.3.x badge promised "Saving creates a local override", which was true
    // of this module and NOT true of the Designer — and is no longer true here
    // either, because saving an inherited script is refused outright now.
    const badge = screen.getByTitle(/Inherited from ParentProject/);
    expect(badge.getAttribute('title')).toMatch(/read-only until you override it/i);
  });
});
