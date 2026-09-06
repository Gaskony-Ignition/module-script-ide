/**
 * The Tests panel: what this project declares, and what happens when it runs.
 *
 * A bottom-panel view rather than a side-bar one, next to the console and the
 * Problems list, because a test result is OUTPUT — you read it after asking for
 * something, and you want the editor still visible while you do.
 *
 * **Three outcomes, never two.** A `fail` is an assertion that is not true; an
 * `error` is a test that did not get far enough to have an opinion. Collapsing
 * them into "failed" sends you to read an assertion that never executed, which
 * is the wrong half of the file.
 *
 * **The discovery rule is on screen whenever the list is empty.** A convention
 * nobody can see reads as a broken feature: the first thing a person does with
 * an empty test panel is wonder whether it works.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  fetchTests, runTests,
  type TestListing, type TestResult, type TestRun,
} from '../api/tests';
import { IconPlay } from './Icons';
import './TestsPanel.css';

export interface TestsPanelProps {
  project: string;
  csrfToken: string | undefined;
  /** False for a reader who cannot execute — the run button is then absent. */
  canRun: boolean;
  /** Open the module that holds a test, at the `def`. */
  onOpenTest: (moduleName: string, line: number) => void;
}

/** The word each status gets, and the class that colours it. */
const STATUS_WORD: Record<TestResult['status'], string> = {
  pass: 'passed',
  fail: 'failed',
  error: 'errored',
};

export default function TestsPanel({
  project, csrfToken, canRun, onOpenTest,
}: TestsPanelProps) {
  const [listing, setListing] = useState<TestListing | null>(null);
  const [run, setRun] = useState<TestRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());

  const reload = useCallback(() => {
    if (!project) return;
    fetchTests(project)
      .then(setListing)
      .catch((e: unknown) => {
        setListing(null);
        setError(e instanceof Error ? e.message : String(e));
      });
  }, [project]);

  useEffect(() => {
    // Results belong to the project that produced them. Left standing across a
    // project switch they would be read as the new project's.
    setRun(null);
    setError('');
    reload();
  }, [project, reload]);

  const start = useCallback(async (ids?: string[]) => {
    setBusy(true);
    setError('');
    try {
      setRun(await runTests(project, ids, csrfToken));
    } catch (e: unknown) {
      setRun(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [project, csrfToken]);

  const toggle = useCallback((id: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const byId = new Map<string, TestResult>();
  for (const result of run?.results ?? []) {
    byId.set(result.id, result);
  }

  return (
    <div className="tests-panel">
      <div className="tests-panel-bar">
        <span className="tests-panel-count">
          {listing ? `${listing.total} ${listing.total === 1 ? 'test' : 'tests'}` : 'Loading…'}
        </span>
        {run && (
          <span className="tests-panel-tally" role="status">
            <span className="tests-tally-pass">{run.passed} passed</span>
            {run.failed > 0 && <span className="tests-tally-fail">{run.failed} failed</span>}
            {run.errored > 0 && <span className="tests-tally-error">{run.errored} errored</span>}
            <span className="tests-panel-elapsed">{run.elapsedMs} ms</span>
          </span>
        )}
        {canRun && (
          <button
            type="button"
            className="button tests-panel-run"
            disabled={busy || !listing || listing.total === 0}
            onClick={() => void start()}
          >
            <IconPlay size={14} />
            {busy ? 'Running…' : 'Run all'}
          </button>
        )}
      </div>

      {error && <p className="tests-panel-error" role="alert">{error}</p>}

      {listing && listing.total === 0 && (
        <p className="tests-panel-empty">
          No tests in this project. {listing.convention}
        </p>
      )}

      {listing && listing.total > 0 && (
        <div className="tests-panel-body">
          {listing.modules.map((module) => (
            <section key={module.module} className="tests-module">
              <header className="tests-module-head">
                <span className="tests-module-name">{module.module}</span>
                {module.hasSetUp && <span className="tests-module-tag">setUp</span>}
                {module.hasTearDown && <span className="tests-module-tag">tearDown</span>}
                {canRun && (
                  <button
                    type="button"
                    className="tests-module-run"
                    disabled={busy}
                    onClick={() => void start(module.tests.map((t) => t.id))}
                  >
                    Run
                  </button>
                )}
              </header>
              <ul className="tests-module-list">
                {module.tests.map((test) => {
                  const result = byId.get(test.id);
                  const open = expanded.has(test.id);
                  return (
                    <li key={test.id}>
                      <div className={`tests-row${result ? ` is-${result.status}` : ''}`}>
                        {/* A glyph as well as a colour, and the word in the
                            detail below: colour alone fails on a projector. */}
                        <span className="tests-row-mark" aria-hidden="true">
                          {result
                            ? result.status === 'pass' ? '✓' : result.status === 'fail' ? '✕' : '!'
                            : '·'}
                        </span>
                        <button
                          type="button"
                          className="tests-row-name"
                          onClick={() => onOpenTest(module.module, test.line)}
                          title={test.id}
                        >
                          {test.class ? `${test.class}.${test.function}` : test.function}
                        </button>
                        {result && (
                          <span className="tests-row-elapsed">{result.elapsedMs} ms</span>
                        )}
                        {result && result.status !== 'pass' && (
                          <button
                            type="button"
                            className="tests-row-toggle"
                            aria-expanded={open}
                            onClick={() => toggle(test.id)}
                          >
                            {open ? 'Hide' : 'Why'}
                          </button>
                        )}
                        {canRun && (
                          <button
                            type="button"
                            className="tests-row-run"
                            disabled={busy}
                            onClick={() => void start([test.id])}
                            aria-label={`Run ${test.id}`}
                          >
                            <IconPlay size={12} />
                          </button>
                        )}
                      </div>
                      {result && open && (
                        <div className="tests-row-detail">
                          <p className="tests-row-message">
                            <strong>{STATUS_WORD[result.status]}</strong>
                            {result.message ? ` — ${result.message}` : ''}
                          </p>
                          {result.traceback && (
                            <pre className="tests-row-trace">{result.traceback}</pre>
                          )}
                          {result.output && (
                            <>
                              <p className="tests-row-caption">Output</p>
                              <pre className="tests-row-output">
                                {result.output}
                                {result.outputTruncated && '\n… truncated'}
                              </pre>
                            </>
                          )}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      )}

      {listing && listing.total > 0 && (
        // Said once, at the bottom, rather than in a tooltip nobody opens. It is
        // the one thing about this runner that will surprise someone who knows
        // pytest, and finding it out from a flaky test is worse than reading it.
        <p className="tests-panel-note">
          A run is one execution: the tests share an interpreter, so module-level
          state carries between them. {listing.convention}
        </p>
      )}
    </div>
  );
}
