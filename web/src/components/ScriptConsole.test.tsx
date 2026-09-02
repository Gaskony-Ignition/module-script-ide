/**
 * The console's half of the 1.5.0 execution fixes.
 *
 * These are rendering assertions, not protocol ones — execClient.test.ts already
 * pins the wire. What is asserted here is what a person actually sees: output
 * appearing before the run ends, a traceback that reads like a traceback, one
 * divider per run, and a Reset that says it happened.
 */
import { fireEvent, render, screen, act } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ExecError, ExecEvent, RunRequest } from '../api/execClient';
import fixture from '../api/__fixtures__/execError.json';

/**
 * A stand-in for the shared exec client.
 *
 * Hoisted, because `vi.mock` is lifted above the imports and a factory that
 * closed over an ordinary const would read it before it was assigned.
 */
const harness = vi.hoisted(() => {
  const listeners: Array<(event: ExecEvent) => void> = [];
  const sent: Array<Record<string, unknown>> = [];
  return {
    listeners,
    sent,
    client: {
      subscribe(listener: (event: ExecEvent) => void) {
        listeners.push(listener);
        return () => {
          listeners.splice(listeners.indexOf(listener), 1);
        };
      },
      run(request: RunRequest) {
        sent.push({ action: 'run', ...request });
        return true;
      },
      stop(executionId: string) {
        sent.push({ action: 'stop', executionId });
        return true;
      },
      reset(project: string) {
        sent.push({ action: 'reset', project });
        return true;
      },
    },
  };
});

vi.mock('../api/execClient', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/execClient')>();
  return { ...actual, sharedExecClient: () => harness.client };
});

const ScriptConsole = (await import('./ScriptConsole')).default;

/** Push one server frame at the mounted console. */
function deliver(event: ExecEvent) {
  act(() => {
    harness.listeners.forEach((listener) => listener(event));
  });
}

function output(): string {
  return screen.getByLabelText('Output').textContent ?? '';
}

function renderConsole(props: Partial<React.ComponentProps<typeof ScriptConsole>> = {}) {
  return render(
    <ScriptConsole project="Demo" csrfToken="t" canExecute {...props} />
  );
}

beforeEach(() => {
  harness.listeners.length = 0;
  harness.sent.length = 0;
});

describe('ScriptConsole', () => {
  it('shows streamed output while the run is still going', () => {
    renderConsole();
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));
    deliver({ kind: 'started', executionId: 'x' });
    deliver({ kind: 'output', executionId: 'x', stream: 'stdout', text: '0\n' });

    // THE assertion for defect 2: this text is on screen with no `finished`
    // frame in sight. On 1.4.3 the pane was empty until the run ended.
    expect(output()).toContain('0');
    expect(screen.getByRole('button', { name: 'Running…' })).toBeDisabled();

    deliver({ kind: 'output', executionId: 'x', stream: 'stdout', text: '1\n' });
    // Consecutive chunks of one stream join one block; a chunk boundary is an
    // artefact of flushing, not something the reader should ever see.
    expect(document.querySelectorAll('.console-stdout')).toHaveLength(1);
    expect(document.querySelector('.console-stdout')?.textContent).toBe('0\n1\n');
  });

  it('separates runs with a divider and closes each with its verdict', () => {
    renderConsole();
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));
    expect(output()).toMatch(/▸ run 1 · \d{2}:\d{2}:\d{2}/);

    deliver({ kind: 'started', executionId: 'x' });
    deliver({
      kind: 'finished',
      result: { executionId: 'x', stdout: '', stderr: '', truncated: false,
        cancelled: false, ok: true },
    });
    expect(output()).toMatch(/— finished in \d+\.\d s —/);

    fireEvent.click(screen.getByRole('button', { name: 'Run' }));
    expect(output()).toContain('▸ run 2');
  });

  it('says stopped, not failed, when the gateway reports a cancellation', () => {
    renderConsole();
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));
    deliver({ kind: 'started', executionId: 'x' });
    fireEvent.click(screen.getByRole('button', { name: 'Stop' }));

    // The stop is sent with the id the server gave us — which it can now read,
    // because the socket thread is no longer parked inside the run.
    expect(harness.sent).toContainEqual({ action: 'stop', executionId: 'x' });
    expect(screen.getByText('(waiting for the script to reach a stopping point)'))
      .toBeInTheDocument();

    deliver({
      kind: 'finished',
      result: { executionId: 'x', stdout: '', stderr: '', truncated: false,
        cancelled: true, ok: false },
    });
    expect(output()).toContain('— stopped —');
    expect(output()).not.toContain('— failed —');
  });

  it('renders a traceback the way Python prints one', () => {
    renderConsole();
    deliver({
      kind: 'finished',
      result: { executionId: 'x', stdout: '', stderr: '', truncated: false,
        cancelled: false, ok: false, error: fixture.zeroDivision as ExecError },
    });

    // Defect 3, in full: the exception type as the headline, and every frame
    // naming its function. 1.4.3 showed "<console>, line 3" three times over.
    expect(output()).toContain('ZeroDivisionError: integer division or modulo by zero');
    expect(output()).toContain('File "<console>", line 2, in f');
    expect(output()).toContain('File "<console>", line 3, in <module>');
  });

  it('makes a library frame open its resource', () => {
    const onOpenFrame = vi.fn();
    renderConsole({ onOpenFrame });
    deliver({
      kind: 'finished',
      result: { executionId: 'x', stdout: '', stderr: '', truncated: false,
        cancelled: false, ok: false, error: fixture.libraryFrame as ExecError },
    });

    const link = screen.getByRole('button',
      { name: 'File "ignition/script-python/util/helpers", line 11, in load' });
    fireEvent.click(link);
    expect(onOpenFrame).toHaveBeenCalledWith('ignition/script-python/util/helpers', 11);
  });

  it('shows a syntax error with a caret and never the internal token', () => {
    renderConsole();
    deliver({
      kind: 'finished',
      result: { executionId: 'x', stdout: '', stderr: '', truncated: false,
        cancelled: false, ok: false, error: fixture.syntaxError as ExecError },
    });
    const text = output();
    // The line goes in the headline: a syntax error has no frames to carry it,
    // and where it happened is the only thing the reader can act on.
    expect(text).toContain(
      "SyntaxError: mismatched input '\\n' expecting COLON (line 1)");
    // Defect 4: no raw PyTuple, and nothing spelling our own file token.
    expect(text).not.toContain('script-ide');
    expect(text).not.toContain("('<console>', 1, 7");
    expect(document.querySelector('.console-caret')?.textContent)
      .toBe('if True\n      ^');
  });

  it('resets the console locals and says so', () => {
    renderConsole();
    fireEvent.click(screen.getByRole('button', { name: 'Reset' }));
    expect(harness.sent).toContainEqual({ action: 'reset', project: 'Demo' });

    // The note comes from the server's acknowledgement, not from the click: a
    // reset the gateway refused must not claim to have happened.
    expect(output()).not.toContain('— reset —');
    deliver({ kind: 'reset', project: 'Demo' });
    expect(output()).toContain('— reset —');
  });

  it('refuses Reset while something is running', () => {
    renderConsole();
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));
    deliver({ kind: 'started', executionId: 'x' });
    expect(screen.getByRole('button', { name: 'Reset' })).toBeDisabled();
  });

  it('offers Run file only when the workspace has one open', () => {
    const { unmount } = renderConsole();
    expect(screen.getByRole('button', { name: 'Run file' })).toBeDisabled();
    unmount();

    renderConsole({
      activeSource: {
        path: 'ignition/script-python/util/helpers',
        label: 'util.helpers',
        getSource: () => 'print 1\n',
      },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Run file' }));
    // `target` is what tells the server this is a file rather than the console,
    // and therefore that it gets fresh locals.
    expect(harness.sent[0]).toMatchObject({
      action: 'run',
      project: 'Demo',
      source: 'print 1\n',
      target: 'ignition/script-python/util/helpers',
      lineOffset: 0,
    });
  });

  it('sends a console run with no target at all, so the locals survive', () => {
    renderConsole();
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));
    expect(harness.sent[0]).not.toHaveProperty('target');
  });
});
