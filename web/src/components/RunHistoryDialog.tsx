/**
 * What this user has run, kept across gateway restarts.
 *
 * The Designer's script console forgets everything the moment it closes, which
 * is why people keep scratch scripts in project libraries they never meant to
 * commit — a library module is the only place it offers that survives. This
 * console forgot too: `ExecAudit` records that a run HAPPENED and stores a
 * SHA-256 of the source rather than the source, because an audit table is not a
 * code store.
 *
 * ## Load, don't re-run
 *
 * The button says "Load into console" and that is all it does: the source goes
 * into the console's editor and the Run button is still yours to press. A
 * one-click re-run of something you wrote an hour ago, against a live gateway,
 * with no chance to read it first, is not a convenience.
 */
import { useEffect, useState } from 'react';
import { fetchRuns, type PastRun } from '../api/scripts';
import './RunHistoryDialog.css';

export interface RunHistoryDialogProps {
  onClose: () => void;
  /** Put this source into the console editor. */
  onLoad: (source: string) => void;
}

/** A run's timestamp as a local date and 24-hour time. */
export function runLabel(at: number): string {
  if (!at) return 'unknown time';
  return new Date(at).toLocaleString(undefined, {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

/** The first non-blank line, which is what a person recognises a run by. */
export function firstLine(source: string): string {
  const line = source.split('\n').find((row) => row.trim().length > 0) ?? '';
  return line.length > 70 ? `${line.slice(0, 70)}…` : line;
}

export default function RunHistoryDialog({ onClose, onLoad }: RunHistoryDialogProps) {
  const [runs, setRuns] = useState<PastRun[] | null>(null);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchRuns()
      .then((result) => {
        if (cancelled) return;
        setRuns(result.runs);
        if (result.runs.length > 0) setSelected(result.runs[0].id);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const current = runs?.find((run) => run.id === selected) ?? null;

  return (
    <div className="runhist-backdrop" role="presentation" onClick={onClose}>
      <div
        className="runhist-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Run history"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="runhist-head">
          <h2>Run history</h2>
          <button type="button" className="runhist-close" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </header>

        <div className="runhist-body">
          <div className="runhist-list">
            {error ? (
              <p className="runhist-empty muted">Could not read the run history: {error}</p>
            ) : runs === null ? (
              <p className="runhist-empty muted">Loading…</p>
            ) : runs.length === 0 ? (
              <p className="runhist-empty muted">
                Nothing run from this console yet. Every run is kept from now on, with its
                output, and survives a gateway restart.
              </p>
            ) : (
              <ul>
                {runs.map((run) => (
                  <li key={run.id}>
                    <button
                      type="button"
                      className={`runhist-run${selected === run.id ? ' is-selected' : ''}`}
                      onClick={() => setSelected(run.id)}
                    >
                      <span className="runhist-when">
                        {/* The outcome, as a glyph AND a class — a red row alone
                            is not a signal a colour-blind reader can use. */}
                        <span className={`runhist-mark is-${run.ok ? 'ok' : 'failed'}`}>
                          {run.ok ? '✓' : '✗'}
                        </span>
                        {runLabel(run.at)}
                        {run.project ? ` · ${run.project}` : ''}
                      </span>
                      <span className="runhist-first">{firstLine(run.source)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="runhist-detail">
            {current === null ? (
              <p className="runhist-empty muted">Select a run to see it.</p>
            ) : (
              <>
                <h3 className="runhist-section">Source</h3>
                <pre className="runhist-source">{current.source}</pre>
                <h3 className="runhist-section">
                  Output{current.outputTruncated ? ' (truncated)' : ''}
                </h3>
                <pre className="runhist-output">
                  {current.output || (current.error ? '' : 'No output.')}
                  {current.error ? `\n${current.error}` : ''}
                </pre>
              </>
            )}
          </div>
        </div>

        <footer className="runhist-foot">
          <p className="runhist-note muted">
            Loading puts the source in the console. It does not run it.
          </p>
          <div className="runhist-actions">
            <button type="button" className="button button-quiet" onClick={onClose}>
              Close
            </button>
            <button
              type="button"
              className="button"
              disabled={current === null}
              onClick={() => {
                if (current) {
                  onLoad(current.source);
                  onClose();
                }
              }}
            >
              Load into console
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
