import { EditorView } from '@codemirror/view';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import CodeEditor from './CodeEditor';
import type { OpenDoc } from '../workspace/documents';

/**
 * A body in the shape the real Designer writes it: tab indentation, and NO
 * terminating newline. Both halves of that are invariants — if the editor
 * normalises either, every later git diff of the project is noise.
 */
const DESIGNER_SOURCE =
  'def compute(values):\n' +
  '\ttotal = 0\n' +
  '\tfor value in values:\n' +
  '\t\tif value > 0:\n' +
  '\t\t\ttotal += value\n' +
  '\treturn total';

function doc(overrides: Partial<OpenDoc> = {}): OpenDoc {
  return {
    uri: 'P::ignition/script-python/util/helpers',
    project: 'P',
    path: 'ignition/script-python/util/helpers',
    scriptKey: 'code.py',
    typeLabel: 'Project Library',
    label: 'helpers',
    origin: 'local',
    etag: 'sig-1',
    baseText: DESIGNER_SOURCE,
    text: DESIGNER_SOURCE,
    ...overrides,
  };
}

/** The live CodeMirror view for the visible document. */
function activeView(): EditorView {
  const host = document.querySelector<HTMLElement>('.code-editor-host .cm-editor');
  const view = host ? EditorView.findFromDOM(host) : null;
  if (!view) throw new Error('no EditorView mounted');
  return view;
}

describe('CodeEditor byte fidelity', () => {
  it('round-trips tabs and a missing trailing newline through the editor', () => {
    const onChange = vi.fn();
    render(
      <CodeEditor
        docs={[doc()]}
        activeUri={doc().uri}
        readOnly={false}
        onChange={onChange}
        onSave={vi.fn()}
      />
    );

    const view = activeView();
    // The document as loaded is already byte-identical.
    expect(view.state.doc.toString()).toBe(DESIGNER_SOURCE);

    // Edit it the way a user would, then assert on the EXACT string the save
    // path would POST. This is the single most important assertion in P1.
    view.dispatch({ changes: { from: view.state.doc.length, insert: '\n\t# tail' } });

    expect(onChange).toHaveBeenCalledTimes(1);
    const [, saved] = onChange.mock.calls[0] as [string, string];
    expect(saved).toBe(DESIGNER_SOURCE + '\n\t# tail');
    expect(saved.endsWith('\n')).toBe(false);
    expect(saved).not.toContain('    ');
  });

  it('preserves CRLF line endings instead of rewriting them to LF', () => {
    // CodeMirror's default lineSeparator splits on CR, LF and CRLF and rejoins
    // with LF — so without the pinned separator, merely opening and saving a
    // CRLF file rewrites every line of it.
    const crlf = 'a = 1\r\nb = 2';
    const onChange = vi.fn();
    render(
      <CodeEditor
        docs={[doc({ baseText: crlf, text: crlf })]}
        activeUri={doc().uri}
        readOnly={false}
        onChange={onChange}
        onSave={vi.fn()}
      />
    );
    expect(activeView().state.doc.toString()).toBe(crlf);
  });

  it('preserves a trailing newline when the file genuinely has one', () => {
    const withNewline = 'x = 1\n';
    render(
      <CodeEditor
        docs={[doc({ baseText: withNewline, text: withNewline })]}
        activeUri={doc().uri}
        readOnly={false}
        onChange={vi.fn()}
        onSave={vi.fn()}
      />
    );
    expect(activeView().state.doc.toString()).toBe(withNewline);
  });
});

describe('CodeEditor keys', () => {
  it('inserts a literal tab on Tab, never spaces', () => {
    const onChange = vi.fn();
    render(
      <CodeEditor
        docs={[doc({ baseText: '', text: '' })]}
        activeUri={doc().uri}
        readOnly={false}
        onChange={onChange}
        onSave={vi.fn()}
      />
    );
    const view = activeView();
    fireEvent.keyDown(view.contentDOM, { key: 'Tab', code: 'Tab', keyCode: 9 });
    expect(view.state.doc.toString()).toBe('\t');
  });

  it('auto-indents with a tab after a colon', () => {
    const onChange = vi.fn();
    render(
      <CodeEditor
        docs={[doc({ baseText: 'if True:', text: 'if True:' })]}
        activeUri={doc().uri}
        readOnly={false}
        onChange={onChange}
        onSave={vi.fn()}
      />
    );
    const view = activeView();
    view.dispatch({ selection: { anchor: view.state.doc.length } });
    fireEvent.keyDown(view.contentDOM, { key: 'Enter', code: 'Enter', keyCode: 13 });
    expect(view.state.doc.toString()).toBe('if True:\n\t');
  });

  it('saves on Ctrl+S and does not let the browser handle it', () => {
    const onSave = vi.fn();
    render(
      <CodeEditor
        docs={[doc()]}
        activeUri={doc().uri}
        readOnly={false}
        onChange={vi.fn()}
        onSave={onSave}
      />
    );
    const view = activeView();
    const handled = fireEvent.keyDown(view.contentDOM, { key: 's', code: 'KeyS', ctrlKey: true });
    expect(onSave).toHaveBeenCalledWith(doc().uri);
    // fireEvent returns false when a handler called preventDefault.
    expect(handled).toBe(false);
  });
});

describe('CodeEditor view lifecycle', () => {
  const first = doc();
  const second = doc({
    uri: 'P::ignition/timer/Poller',
    path: 'ignition/timer/Poller',
    label: 'Poller',
    baseText: 'poll()',
    text: 'poll()',
  });

  it('keeps one mounted view per document and hides the inactive ones', () => {
    const { rerender } = render(
      <CodeEditor
        docs={[first, second]}
        activeUri={first.uri}
        readOnly={false}
        onChange={vi.fn()}
        onSave={vi.fn()}
      />
    );

    const hosts = () =>
      Array.from(document.querySelectorAll<HTMLElement>('.code-editor-host'));
    expect(hosts()).toHaveLength(2);
    expect(hosts().map((h) => h.style.display)).toEqual(['block', 'none']);

    rerender(
      <CodeEditor
        docs={[first, second]}
        activeUri={second.uri}
        readOnly={false}
        onChange={vi.fn()}
        onSave={vi.fn()}
      />
    );
    // Still two views: switching tabs hides one and shows the other rather than
    // swapping a single view's state, so scroll position and undo history live.
    expect(hosts()).toHaveLength(2);
    expect(hosts().map((h) => h.style.display)).toEqual(['none', 'block']);
  });

  it('destroys the view when its document is closed', () => {
    const { rerender } = render(
      <CodeEditor
        docs={[first, second]}
        activeUri={first.uri}
        readOnly={false}
        onChange={vi.fn()}
        onSave={vi.fn()}
      />
    );
    rerender(
      <CodeEditor
        docs={[first]}
        activeUri={first.uri}
        readOnly={false}
        onChange={vi.fn()}
        onSave={vi.fn()}
      />
    );
    expect(document.querySelectorAll('.code-editor-host')).toHaveLength(1);
  });

  it('refuses edits when read-only', () => {
    render(
      <CodeEditor
        docs={[doc()]}
        activeUri={doc().uri}
        readOnly
        onChange={vi.fn()}
        onSave={vi.fn()}
      />
    );
    const view = activeView();
    expect(view.state.readOnly).toBe(true);
    fireEvent.keyDown(view.contentDOM, { key: 'Tab', code: 'Tab', keyCode: 9 });
    expect(view.state.doc.toString()).toBe(DESIGNER_SOURCE);
  });

  it('adopts text changed outside the editor, such as a conflict reload', () => {
    const original = doc();
    const { rerender } = render(
      <CodeEditor
        docs={[original]}
        activeUri={original.uri}
        readOnly={false}
        onChange={vi.fn()}
        onSave={vi.fn()}
      />
    );
    const theirs = 'their\tversion';
    rerender(
      <CodeEditor
        docs={[{ ...original, text: theirs, baseText: theirs }]}
        activeUri={original.uri}
        readOnly={false}
        onChange={vi.fn()}
        onSave={vi.fn()}
      />
    );
    expect(activeView().state.doc.toString()).toBe(theirs);
  });
});

describe('CodeEditor container', () => {
  it('renders its host element even with nothing open', () => {
    render(
      <CodeEditor docs={[]} activeUri={null} readOnly={false} onChange={vi.fn()} onSave={vi.fn()} />
    );
    expect(screen.getByTestId('code-editor')).toBeInTheDocument();
    expect(document.querySelectorAll('.code-editor-host')).toHaveLength(0);
  });
});
