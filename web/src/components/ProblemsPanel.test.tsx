import { fireEvent, render, screen } from '@testing-library/react';
import { act } from 'react';
import { describe, expect, it, vi } from 'vitest';
import type { LspClient, LspDiagnostic } from '../api/lspClient';
import { lspUri } from '../api/lspClient';
import type { OpenDoc } from '../workspace/documents';
import { docUri } from '../workspace/documents';
import ProblemsPanel, { severityLabel, sortProblems, type ProblemRow } from './ProblemsPanel';

function doc(path: string, label: string): OpenDoc {
  return {
    kind: 'script',
    uri: docUri('P', path, 'code.py'),
    project: 'P',
    path,
    scriptKey: 'code.py',
    typeLabel: 'Project Library',
    label,
    origin: 'local',
    etag: 'sig',
    baseText: '',
    text: '',
    overridden: false,
  };
}

function diagnostic(line: number, message: string, severity = 1): LspDiagnostic {
  return {
    range: { start: { line, character: 2 }, end: { line, character: 6 } },
    severity,
    message,
    source: 'jython',
  };
}

/**
 * An LSP client that records its subscriptions and lets a test push to them.
 *
 * Push, not poll: diagnostics arrive from the gateway whenever it reparses, and
 * a fake that returned them from a call would test a design the server does not
 * have.
 */
function fakeLsp() {
  const listeners = new Map<string, (d: LspDiagnostic[]) => void>();
  const client = {
    onDiagnostics: vi.fn((uri: string, listener: (d: LspDiagnostic[]) => void) => {
      listeners.set(uri, listener);
      return () => listeners.delete(uri);
    }),
  } as unknown as LspClient;
  return {
    client,
    listeners,
    publish(uri: string, diagnostics: LspDiagnostic[]) {
      act(() => listeners.get(uri)?.(diagnostics));
    },
  };
}

describe('sortProblems', () => {
  const row = (label: string, line: number, severity: number): ProblemRow => ({
    docUri: `P::${label}`,
    label,
    diagnostic: diagnostic(line, `${label}:${line}`, severity),
  });

  it('puts errors above warnings, whatever file they are in', () => {
    // A list sorted by position alone buries the one thing that stops the script
    // running under a dozen hints from a file nobody is looking at.
    const sorted = sortProblems([row('zeta', 1, 2), row('alpha', 90, 1)]);
    expect(sorted.map((r) => r.label)).toEqual(['alpha', 'zeta']);
  });

  it('orders equal severities by file, then by line', () => {
    const sorted = sortProblems([row('b', 2, 1), row('a', 9, 1), row('a', 3, 1)]);
    expect(sorted.map((r) => `${r.label}:${r.diagnostic.range.start.line}`))
      .toEqual(['a:3', 'a:9', 'b:2']);
  });

  it('treats a diagnostic with no severity as an error, as LSP says to', () => {
    const noSeverity: ProblemRow = {
      docUri: 'P::x',
      label: 'x',
      diagnostic: { range: diagnostic(0, '').range, message: 'unset' },
    };
    expect(sortProblems([row('a', 0, 2), noSeverity])[0].diagnostic.message).toBe('unset');
  });

  it('does not mutate the array it was given', () => {
    const rows = [row('b', 1, 2), row('a', 1, 1)];
    sortProblems(rows);
    expect(rows[0].label).toBe('b');
  });
});

describe('severityLabel', () => {
  it.each([
    [1, 'error'],
    [2, 'warning'],
    [3, 'info'],
    [4, 'hint'],
    [undefined, 'error'],
  ])('maps severity %s to %s', (severity, expected) => {
    expect(severityLabel(severity as number | undefined)).toBe(expected);
  });
});

describe('ProblemsPanel', () => {
  it('subscribes with the SERVER key, not the workspace one', () => {
    // The two disagree — `P::path::key` here, `ignition://P/path` there — and
    // subscribing with the wrong one is completely silent: every diagnostic is
    // dropped and the panel stays empty however broken the code is. That exact
    // confusion cost a day in P5.
    const lsp = fakeLsp();
    const helpers = doc('ignition/script-python/util/helpers', 'helpers');
    render(<ProblemsPanel docs={[helpers]} lsp={lsp.client} onOpen={vi.fn()} />);
    expect(lsp.client.onDiagnostics).toHaveBeenCalledWith(
      lspUri('P', helpers.path, 'code.py'),
      expect.any(Function)
    );
  });

  it('lists a problem from a document that is not the active tab', () => {
    // The whole reason the panel exists: the inline squiggle and the gutter
    // marker are only visible in the file you are looking at.
    const lsp = fakeLsp();
    const a = doc('ignition/script-python/a', 'a');
    const b = doc('ignition/script-python/b', 'b');
    render(<ProblemsPanel docs={[a, b]} lsp={lsp.client} onOpen={vi.fn()} />);
    lsp.publish(lspUri('P', b.path, 'code.py'), [diagnostic(11, 'no viable alternative')]);
    expect(screen.getByText('no viable alternative')).toBeInTheDocument();
    expect(screen.getByText('b · 12:3')).toBeInTheDocument();
  });

  it('jumps to the document and position of a clicked problem', () => {
    const lsp = fakeLsp();
    const a = doc('ignition/script-python/a', 'a');
    const onOpen = vi.fn();
    render(<ProblemsPanel docs={[a]} lsp={lsp.client} onOpen={onOpen} />);
    lsp.publish(lspUri('P', a.path, 'code.py'), [diagnostic(4, 'bad indent')]);
    // Two buttons per row since 1.8.6 — open and copy — so the query names
    // the row by its message rather than taking the only button.
    fireEvent.click(screen.getByRole('button', { name: /^bad indent/ }));
    expect(onOpen).toHaveBeenCalledWith(a.uri, 4, 2);
  });

  it('drops a closed document\'s problems from the list', () => {
    // An unsubscribe only stops FUTURE updates; what was already stored has to
    // be removed as well, or a closed tab keeps reporting problems.
    const lsp = fakeLsp();
    const a = doc('ignition/script-python/a', 'a');
    const b = doc('ignition/script-python/b', 'b');
    const view = render(<ProblemsPanel docs={[a, b]} lsp={lsp.client} onOpen={vi.fn()} />);
    lsp.publish(lspUri('P', b.path, 'code.py'), [diagnostic(1, 'from b')]);
    expect(screen.getByText('from b')).toBeInTheDocument();
    view.rerender(<ProblemsPanel docs={[a]} lsp={lsp.client} onOpen={vi.fn()} />);
    expect(screen.queryByText('from b')).not.toBeInTheDocument();
  });

  it('says the check covers open scripts only, so an empty list is not "the project is clean"', () => {
    const lsp = fakeLsp();
    render(<ProblemsPanel docs={[doc('ignition/script-python/a', 'a')]} lsp={lsp.client} onOpen={vi.fn()} />);
    expect(screen.getByText(/Only open scripts are checked/)).toBeInTheDocument();
  });

  it('asks for a script to be opened when none is', () => {
    const lsp = fakeLsp();
    render(<ProblemsPanel docs={[]} lsp={lsp.client} onOpen={vi.fn()} />);
    expect(screen.getByText('Open a script to see its problems.')).toBeInTheDocument();
    expect(lsp.client.onDiagnostics).not.toHaveBeenCalled();
  });

  it('renders without a language client at all', () => {
    // A gateway whose socket never came up gets a plain editor, not a broken one.
    render(<ProblemsPanel docs={[doc('ignition/script-python/a', 'a')]} lsp={null} onOpen={vi.fn()} />);
    expect(screen.getByText(/Only open scripts are checked/)).toBeInTheDocument();
  });
});
