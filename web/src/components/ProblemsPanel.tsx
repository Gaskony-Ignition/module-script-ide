/**
 * Problems: every open document's diagnostics in one list.
 *
 * The editor has shown an inline squiggle and a gutter marker since P5, and both
 * are per-file and only visible in the file you are looking at. With six tabs
 * open, a syntax error in the one you are not looking at is invisible until you
 * switch to it — which is exactly when it is least useful to find out.
 *
 * **Open documents only, and the empty state says so.** The gateway publishes
 * diagnostics for documents the language server holds, and it holds the ones
 * this client opened. A list headed "Problems" that silently covered a third of
 * the project would be worse than no list: an empty one would read as "the
 * project is clean".
 */
import { useEffect, useMemo, useState } from 'react';
import type { LspClient, LspDiagnostic } from '../api/lspClient';
import { lspUri } from '../api/lspClient';
import type { OpenDoc } from '../workspace/documents';
import { IconAlert } from './Icons';
import { copyText } from './clipboard';
import './ProblemsPanel.css';

export interface ProblemsPanelProps {
  docs: OpenDoc[];
  lsp: LspClient | null;
  /** Jump to a problem: the workspace document key, and where in it. */
  onOpen: (uri: string, line: number, character: number) => void;
}

/** One row: a diagnostic plus the document it belongs to. */
export interface ProblemRow {
  /** The WORKSPACE document key, which is what `onOpen` and the tabs use. */
  docUri: string;
  label: string;
  diagnostic: LspDiagnostic;
}

/**
 * Errors first, then by file, then by line.
 *
 * Severity leads because a list sorted only by position buries the one thing
 * that stops the script running under a dozen hints. Ties fall back to the
 * document label and line so the order is stable between renders — a list that
 * reshuffles as diagnostics are republished cannot be clicked reliably.
 */
export function sortProblems(rows: ProblemRow[]): ProblemRow[] {
  return [...rows].sort((a, b) => {
    const severityA = a.diagnostic.severity ?? 1;
    const severityB = b.diagnostic.severity ?? 1;
    return (
      severityA - severityB
      || a.label.localeCompare(b.label)
      || a.diagnostic.range.start.line - b.diagnostic.range.start.line
      || a.diagnostic.range.start.character - b.diagnostic.range.start.character
    );
  });
}

/** LSP DiagnosticSeverity → the word on the row. */
export function severityLabel(severity: number | undefined): string {
  switch (severity) {
    case 2:
      return 'warning';
    case 3:
      return 'info';
    case 4:
      return 'hint';
    default:
      return 'error';
  }
}

export default function ProblemsPanel({ docs, lsp, onOpen }: ProblemsPanelProps) {
  // Keyed by workspace document URI, so a closed tab's entry can be dropped
  // without touching anything else.
  const [byDoc, setByDoc] = useState<Record<string, LspDiagnostic[]>>({});
  /**
   * The (document key, server URI) pairs to subscribe to.
   *
   * Two keys per document, because the workspace and the language server do NOT
   * agree on one: the workspace uses `project::path::key` and the server
   * `ignition://project/path#key`. Subscribing with the wrong one is silent —
   * every diagnostic is dropped and the list stays empty however broken the code
   * is. That exact confusion cost a day in P5; see the LSP-key finding in
   * `docs/STATE.md`.
   */
  const subscriptions = useMemo(
    () => docs.map((doc) => ({
      docKey: doc.uri,
      serverUri: lspUri(doc.project, doc.path, doc.scriptKey),
    })),
    [docs]
  );

  // Resubscribed when the SET of open documents changes, not on every keystroke:
  // `docs` is a new array on every edit, and tearing every subscription down and
  // rebuilding it per character typed would drop pushes arriving in between.
  const subscriptionKey = subscriptions.map((s) => s.docKey).join('\n');

  useEffect(() => {
    if (!lsp) return;
    const unsubscribes = subscriptions.map(({ docKey, serverUri }) =>
      lsp.onDiagnostics(serverUri, (diagnostics) => {
        setByDoc((current) => ({ ...current, [docKey]: diagnostics }));
      })
    );
    // Drop anything that is no longer open, in the same pass that resubscribes:
    // a closed tab's problems must leave the list, and its own unsubscribe only
    // stops FUTURE updates — it does not retract what was already stored.
    const openKeys = new Set(subscriptions.map((s) => s.docKey));
    setByDoc((current) => {
      const next: Record<string, LspDiagnostic[]> = {};
      for (const [key, value] of Object.entries(current)) {
        if (openKeys.has(key)) next[key] = value;
      }
      return next;
    });
    return () => {
      for (const off of unsubscribes) off();
    };
    // `subscriptions` is derived from `docs` and changes identity on every edit;
    // the key above is what actually decides when to resubscribe.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subscriptionKey, lsp]);

  const rows = useMemo(() => {
    const out: ProblemRow[] = [];
    for (const doc of docs) {
      for (const diagnostic of byDoc[doc.uri] ?? []) {
        out.push({ docUri: doc.uri, label: doc.label, diagnostic });
      }
    }
    return sortProblems(out);
  }, [byDoc, docs]);

  if (docs.length === 0) {
    return <p className="problems-empty muted">Open a script to see its problems.</p>;
  }

  if (rows.length === 0) {
    return (
      <p className="problems-empty muted">
        No problems in the {docs.length === 1 ? 'open script' : `${docs.length} open scripts`}.
        Only open scripts are checked.
      </p>
    );
  }

  return (
    <div className="problems">
      <ul className="problems-list">
        {rows.map((row) => {
          const severity = severityLabel(row.diagnostic.severity);
          const line = row.diagnostic.range.start.line;
          const character = row.diagnostic.range.start.character;
          return (
            <li key={`${row.docUri}:${line}:${character}:${row.diagnostic.message}`}>
              <button
                type="button"
                className="problems-row"
                onClick={() => onOpen(row.docUri, line, character)}
              >
                <IconAlert size={14} className={`problems-icon is-${severity}`} />
                <span className="problems-message">{row.diagnostic.message}</span>
                <span className="problems-where">
                  {row.label} · {line + 1}:{character + 1}
                </span>
              </button>
              {/* Take the text away. A parser message is what you paste into a
                  search or a question, and selecting it out of a button by hand
                  is not something a button lets you do (Nigel, 03/09/2026). */}
              <button
                type="button"
                className="problems-copy"
                aria-label={`Copy: ${row.diagnostic.message}`}
                title="Copy this message"
                onClick={() => {
                  void copyText(
                    `${row.label}:${line + 1}:${character + 1} ${row.diagnostic.message}`
                  );
                }}
              >
                Copy
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
