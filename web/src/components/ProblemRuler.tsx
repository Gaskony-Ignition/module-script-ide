/**
 * The overview ruler — a mark per problem, beside the editor.
 *
 * The Designer puts a narrow strip down the right of the code area with a mark
 * in line with every line that has a problem; hovering one shows the message.
 * Nigel asked for that here (03/09/2026) and for one thing the Designer does not
 * do: **be able to take the text away**, to paste into a search or a message.
 *
 * Why this and not the Problems panel, which already existed: a defect
 * indicator you have to go and find has failed. Problems lists only documents
 * open as TABS, and it lives in a panel that starts collapsed — so a broken
 * line reported perfectly by the language server showed nothing at all until
 * you went looking ("it said no problems in the open script"). The ruler is
 * always on screen next to the code it describes.
 *
 * **Position is proportional to the document, not to the viewport.** The whole
 * point is to see a problem that is scrolled off screen — a ruler that only
 * marked visible lines would tell you what the squiggles already do.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { lspUri, type LspClient, type LspDiagnostic } from '../api/lspClient';
import type { OpenDoc } from '../workspace/documents';
import { copyText } from './clipboard';
import './ProblemRuler.css';

export interface ProblemRulerProps {
  /** The document being shown. Null hides the ruler entirely. */
  doc: OpenDoc | null;
  lsp?: LspClient | null;
  /** Move the caret to a problem and, where the workspace offers it, reveal it. */
  onSelect: (line: number, character: number) => void;
}

/** LSP DiagnosticSeverity → the word used in the class and the label. */
export function severityName(severity: number | undefined): string {
  switch (severity) {
    case 1:
      return 'error';
    case 2:
      return 'warning';
    case 3:
      return 'info';
    default:
      return 'hint';
  }
}

/**
 * Where a mark sits, as a percentage of the ruler's height.
 *
 * Clamped so that a diagnostic on the last line is still fully on screen rather
 * than half-drawn past the bottom edge, and so that a document shorter than one
 * line — which happens while a buffer is empty — does not divide by zero.
 */
export function markOffset(line: number, lineCount: number): number {
  if (lineCount <= 1) return 0;
  const ratio = Math.min(1, Math.max(0, line / (lineCount - 1)));
  return Math.round(ratio * 10000) / 100;
}

/** The worst severity in a set — the one a merged mark should take. */
export function worstSeverity(diagnostics: LspDiagnostic[]): number {
  return diagnostics.reduce(
    (worst, d) => Math.min(worst, d.severity ?? 4),
    4
  );
}

export default function ProblemRuler({ doc, lsp, onSelect }: ProblemRulerProps) {
  const [diagnostics, setDiagnostics] = useState<LspDiagnostic[]>([]);
  const [copied, setCopied] = useState<string | null>(null);

  const serverUri = doc && doc.kind === 'script'
    ? lspUri(doc.project, doc.path, doc.scriptKey)
    : null;

  useEffect(() => {
    setDiagnostics([]);
    if (!lsp || !serverUri) return;
    // The client replays the last diagnostics it holds on subscribe, so a ruler
    // mounted after the server published still draws them. Without that, the
    // marks would only appear on the NEXT keystroke.
    return lsp.onDiagnostics(serverUri, setDiagnostics);
  }, [lsp, serverUri]);

  const lineCount = useMemo(
    () => (doc ? doc.text.split('\n').length : 0),
    [doc]
  );

  /**
   * One mark per LINE, not per diagnostic.
   *
   * A parser routinely reports several problems on one line, and three marks
   * stacked at identical offsets read as one mark with a dirty edge — while
   * making the tooltip show whichever happened to be on top. Merged, the mark
   * takes the worst severity and the tooltip lists all of them.
   */
  const marks = useMemo(() => {
    const byLine = new Map<number, LspDiagnostic[]>();
    for (const diagnostic of diagnostics) {
      const line = diagnostic.range.start.line;
      byLine.set(line, [...(byLine.get(line) ?? []), diagnostic]);
    }
    return [...byLine.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([line, group]) => ({
        line,
        group,
        severity: severityName(worstSeverity(group)),
        offset: markOffset(line, lineCount),
        text: group.map((d) => d.message).join('\n'),
      }));
  }, [diagnostics, lineCount]);

  const copy = useCallback((key: string, text: string) => {
    // Through `copyText`, NOT `navigator.clipboard` directly: this gateway is
    // served over HTTP, where the async Clipboard API does not exist at all and
    // an optional call is a silent no-op. See clipboard.ts.
    void copyText(text).then((ok) => {
      if (!ok) return;
      setCopied(key);
      window.setTimeout(() => setCopied((c) => (c === key ? null : c)), 1200);
    });
  }, []);

  if (!doc || doc.kind !== 'script') return null;

  return (
    <div
      className="problem-ruler"
      role="group"
      aria-label={marks.length === 0
        ? 'No problems in this script'
        : `${marks.length} line(s) with problems`}
    >
      {marks.map((mark) => (
        <div
          key={mark.line}
          className="problem-ruler-slot"
          style={{ top: `${mark.offset}%` }}
        >
          <button
            type="button"
            className={`problem-ruler-mark is-${mark.severity}`}
            aria-label={`${mark.severity} on line ${mark.line + 1}: ${mark.text}`}
            onClick={() => onSelect(mark.line, mark.group[0].range.start.character)}
          />
          {/* The card is a sibling of the mark and shown on hovering the SLOT,
              so the pointer can travel from the mark onto the card without it
              closing — which is what makes the copy button reachable at all. */}
          <div className="problem-ruler-card" role="tooltip">
            <div className="problem-ruler-where">
              Line {mark.line + 1} · {mark.severity}
            </div>
            {mark.group.map((d, i) => (
              <p key={`${d.message}:${i}`} className="problem-ruler-message">
                {d.message}
              </p>
            ))}
            <button
              type="button"
              className="problem-ruler-copy"
              onClick={(event) => {
                event.stopPropagation();
                copy(String(mark.line), mark.text);
              }}
            >
              {copied === String(mark.line) ? 'Copied' : 'Copy'}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
