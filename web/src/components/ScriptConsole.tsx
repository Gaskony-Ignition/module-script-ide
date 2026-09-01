/**
 * The Script Console: a scratch buffer that runs on the Gateway.
 *
 * The Designer's console is a REPL against the gateway's script manager, and
 * this is the same thing with an actual editor above it. Three behaviours are
 * deliberate and are the ones worth knowing:
 *
 * **Locals persist between runs, exactly like the Designer's.** The server keys
 * console locals on the ABSENCE of a `target`, so a name bound in one run is
 * still bound in the next. That is what makes it a console rather than a
 * scratch file, and it is also why "Clear output" does not reset them — losing
 * your bindings because you tidied the output would be a nasty surprise.
 *
 * **Run selection runs only the selection**, with the preceding lines replaced
 * by blank ones so a traceback still points at the line you can see. The offset
 * is sent so the server can subtract it back off.
 *
 * **Stop is best-effort and says so.** Jython's interrupt fires at the next
 * trace point: a busy loop stops in about three seconds, but a `time.sleep(10)`
 * blocked in Java runs its full ten. The button changes its own label rather
 * than pretending the script died.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { EditorState } from '@codemirror/state';
import { EditorView, keymap } from '@codemirror/view';
import { byteFidelity, editorTheme, findAndReplace, pythonKeymap, pythonSurface } from './editorCore';
import { sharedExecClient, type ExecError, type ExecEvent, type ExecResult } from '../api/execClient';
import './ScriptConsole.css';

export interface ScriptConsoleProps {
  project: string;
  csrfToken?: string;
  /** False when the session may not execute; the console renders read-only. */
  canExecute: boolean;
  /** Jump to a traceback frame that resolved to a project script. */
  onOpenFrame?: (path: string, line: number) => void;
}

/** One entry in the output log. Kept as a list so runs stay visually separated. */
interface OutputEntry {
  id: string;
  kind: 'stdout' | 'stderr' | 'note' | 'error';
  text: string;
  error?: ExecError;
}

const STARTER = '# Runs on the Gateway. Ctrl+Enter to run, Ctrl+Shift+Enter for the selection.\n';

export default function ScriptConsole({
  project,
  csrfToken,
  canExecute,
  onOpenFrame,
}: ScriptConsoleProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const viewRef = useRef<EditorView | null>(null);
  const [entries, setEntries] = useState<OutputEntry[]>([]);
  const [running, setRunning] = useState<string | null>(null);
  const [stopping, setStopping] = useState(false);
  const outputRef = useRef<HTMLDivElement | null>(null);

  const exec = useMemo(() => sharedExecClient(), []);

  const append = useCallback((entry: Omit<OutputEntry, 'id'>) => {
    if (!entry.text && !entry.error) {
      return;
    }
    setEntries((previous) => [
      ...previous,
      { ...entry, id: `${Date.now()}-${previous.length}` },
    ]);
  }, []);

  // ---- run / stop -------------------------------------------------------

  // Read through a ref inside the keymap: the extensions are built once, so a
  // closure over `running` would freeze at its first value and the Ctrl+Enter
  // binding would keep firing while a script was already running.
  const runRef = useRef<(selectionOnly: boolean) => void>(() => {});

  const doRun = useCallback(
    (selectionOnly: boolean) => {
      const view = viewRef.current;
      if (!view || running || !canExecute) {
        return;
      }
      const doc = view.state.doc;
      let source: string;
      let lineOffset = 0;
      if (selectionOnly) {
        const range = view.state.selection.main;
        if (range.empty) {
          append({ kind: 'note', text: 'Nothing selected.' });
          return;
        }
        // Pad with newlines rather than sending the raw selection, so line
        // numbers in a traceback match what the user is looking at.
        const startLine = doc.lineAt(range.from).number;
        lineOffset = startLine - 1;
        source = '\n'.repeat(lineOffset) + view.state.sliceDoc(range.from, range.to);
      } else {
        source = doc.toString();
      }
      if (!source.trim()) {
        append({ kind: 'note', text: 'Nothing to run.' });
        return;
      }
      const sent = exec.run({ project, source, csrfToken, lineOffset });
      if (!sent) {
        append({
          kind: 'error',
          text: 'Not connected to the gateway — the run was not sent. '
            + 'The connection retries on its own; try again in a moment.',
        });
        return;
      }
      // Optimistic: the server answers `started` almost immediately, but the
      // button must not stay clickable in the gap.
      setRunning('pending');
      setStopping(false);
    },
    [append, canExecute, csrfToken, exec, project, running]
  );

  runRef.current = doRun;

  const doStop = useCallback(() => {
    if (!running || running === 'pending') {
      return;
    }
    setStopping(true);
    exec.stop(running, csrfToken);
  }, [csrfToken, exec, running]);

  // ---- socket subscription ---------------------------------------------

  useEffect(() => {
    return exec.subscribe((event: ExecEvent) => {
      if (event.kind === 'started') {
        setRunning(event.executionId);
        return;
      }
      if (event.kind === 'stopping') {
        append({ kind: 'note', text: event.detail || 'Stopping…' });
        return;
      }
      if (event.kind === 'error') {
        setRunning(null);
        setStopping(false);
        append({ kind: 'error', text: event.message });
        return;
      }
      if (event.kind === 'finished') {
        setRunning(null);
        setStopping(false);
        appendResult(event.result);
      }
    });

    function appendResult(result: ExecResult) {
      if (result.stdout) {
        append({ kind: 'stdout', text: result.stdout });
      }
      if (result.stderr) {
        append({ kind: 'stderr', text: result.stderr });
      }
      if (result.cancelled) {
        append({ kind: 'note', text: 'Stopped.' });
      }
      if (result.error) {
        append({ kind: 'error', text: result.error.message, error: result.error });
      }
      if (result.truncated) {
        append({
          kind: 'note',
          text: 'Output was truncated — the rest was discarded, not withheld.',
        });
      }
      if (!result.stdout && !result.stderr && !result.error && !result.cancelled) {
        append({ kind: 'note', text: 'Done. No output.' });
      }
    }
  }, [append, exec]);

  // Keep the newest output visible without fighting a user who scrolled up.
  useEffect(() => {
    const node = outputRef.current;
    if (!node) return;
    const nearBottom = node.scrollHeight - node.scrollTop - node.clientHeight < 80;
    if (nearBottom) {
      node.scrollTop = node.scrollHeight;
    }
  }, [entries]);

  // ---- the editor -------------------------------------------------------

  useEffect(() => {
    const host = hostRef.current;
    if (!host || viewRef.current) {
      return;
    }
    const view = new EditorView({
      state: EditorState.create({
        doc: STARTER,
        extensions: [
          ...pythonSurface,
          ...byteFidelity,
          ...findAndReplace,
          keymap.of([
            {
              key: 'Mod-Enter',
              preventDefault: true,
              run: () => {
                runRef.current(false);
                return true;
              },
            },
            {
              key: 'Mod-Shift-Enter',
              preventDefault: true,
              run: () => {
                runRef.current(true);
                return true;
              },
            },
          ]),
          pythonKeymap,
          editorTheme,
        ],
      }),
      parent: host,
    });
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
  }, []);

  const busy = running !== null;

  return (
    <section className="console" aria-label="Script Console">
      <div className="console-toolbar">
        <button
          type="button"
          className="primary"
          onClick={() => doRun(false)}
          disabled={busy || !canExecute}
          title="Ctrl+Enter"
        >
          {busy ? 'Running…' : 'Run'}
        </button>
        <button
          type="button"
          onClick={() => doRun(true)}
          disabled={busy || !canExecute}
          title="Ctrl+Shift+Enter"
        >
          Run selection
        </button>
        <button type="button" onClick={doStop} disabled={!busy || running === 'pending'}>
          {stopping ? 'Stopping…' : 'Stop'}
        </button>
        {stopping && (
          <span className="console-hint muted">
            waiting for the script to reach a stopping point
          </span>
        )}
        <span className="console-spacer" />
        <span className="console-project muted" title="Scripts run in this project's scope">
          {project}
        </span>
        <button type="button" onClick={() => setEntries([])} disabled={entries.length === 0}>
          Clear output
        </button>
      </div>

      {!canExecute && (
        <p className="console-denied" role="status">
          Running scripts requires the Administrator role. You can still edit here;
          nothing will be sent to the gateway.
        </p>
      )}

      <div className="console-editor" ref={hostRef} />

      {/* The output is its own titled panel, not a region below the editor.
          Without the header and the rule it read as more editor, and people
          could not tell where their script stopped and its output began. */}
      <section className="console-output-panel" aria-label="Output">
        <header className="console-output-head">
          <span className="console-output-title">Output</span>
          {running && <span className="console-running" aria-live="polite">running…</span>}
          <span className="console-spacer" />
          <span className="console-output-count muted">
            {entries.length === 0 ? '' : `${entries.length} block${entries.length === 1 ? '' : 's'}`}
          </span>
        </header>
        <div className="console-output" ref={outputRef} aria-live="polite">
          {entries.length === 0 ? (
            <p className="muted console-empty">
              Nothing yet. Ctrl+Enter runs the buffer above on the Gateway.
            </p>
          ) : (
            entries.map((entry) => (
              <OutputBlock key={entry.id} entry={entry} onOpenFrame={onOpenFrame} />
            ))
          )}
        </div>
      </section>
    </section>
  );
}

function OutputBlock({
  entry,
  onOpenFrame,
}: {
  entry: OutputEntry;
  onOpenFrame?: (path: string, line: number) => void;
}) {
  return (
    <div className={`console-block console-${entry.kind}`}>
      <pre>{entry.text}</pre>
      {entry.error && (
        <Traceback error={entry.error} onOpenFrame={onOpenFrame} />
      )}
    </div>
  );
}

/**
 * The traceback, as clickable frames where the frame resolved to a resource.
 *
 * Frames are extracted structurally by the server, never by regex over rendered
 * text — so a frame either carries a real resource path or it does not, and only
 * the ones that do become buttons. A frame with no path still shows, because a
 * traceback with holes in it is worse than one with some unclickable lines.
 */
function Traceback({
  error,
  onOpenFrame,
}: {
  error: ExecError;
  onOpenFrame?: (path: string, line: number) => void;
}) {
  if (!error.frames || error.frames.length === 0) {
    return error.text ? <pre className="console-traceback">{error.text}</pre> : null;
  }
  return (
    <ol className="console-frames">
      {error.frames.map((frame, index) => {
        const label = `${frame.module ?? frame.path ?? '<console>'}`
          + `, line ${frame.line}`
          + (frame.functionName ? `, in ${frame.functionName}` : '');
        const clickable = Boolean(frame.path && onOpenFrame);
        return (
          <li key={`${frame.path ?? 'x'}-${frame.line}-${index}`}>
            {clickable ? (
              <button
                type="button"
                className="console-frame-link"
                onClick={() => onOpenFrame?.(frame.path as string, frame.line)}
              >
                {label}
              </button>
            ) : (
              <span className="console-frame">{label}</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
