/**
 * Open documents, one tab each.
 *
 * The dirty marker is derived from the document (text vs baseText), never stored
 * separately — a dirty flag and a buffer drift apart, and the one place that
 * shows up is a tab that says "saved" over unsaved work.
 */
import { isDirty, isLockedByInheritance, type OpenDoc } from '../workspace/documents';
import './TabStrip.css';

export interface TabStripProps {
  docs: OpenDoc[];
  activeUri: string | null;
  /**
   * Documents whose gateway copy has moved on since this tab was opened —
   * typically an edit made in the Designer. Derived in the workspace from the
   * listing's signature, not stored on the document.
   */
  staleUris?: ReadonlySet<string>;
  onSelect: (uri: string) => void;
  onClose: (uri: string) => void;
  /** Re-read one document from the gateway. Absent hides the affordance. */
  onPull?: (uri: string) => void;
}

export default function TabStrip({
  docs, activeUri, staleUris, onSelect, onClose, onPull,
}: TabStripProps) {
  if (docs.length === 0) return null;

  return (
    <div className="tab-strip" role="tablist" aria-label="Open scripts">
      {docs.map((doc) => {
        const dirty = isDirty(doc);
        const stale = staleUris?.has(doc.uri) ?? false;
        const active = doc.uri === activeUri;
        // Measured off the real Designer (see documents.ts): an inherited,
        // not-yet-overridden script opens headed "<name>  (Read-Only)". The
        // editor already refuses every keystroke — see CodeEditor — but until
        // now nothing on the TAB said so, and a tab strip with six scripts
        // open gave no way to tell which one that was without clicking each.
        const locked = isLockedByInheritance(doc);
        return (
          <div key={doc.uri} className={`tab${active ? ' is-active' : ''}`}>
            <button
              type="button"
              role="tab"
              aria-selected={active}
              className="tab-label"
              title={`${doc.project} · ${doc.path}`}
              onClick={() => onSelect(doc.uri)}
            >
              <span className="tab-name">
                {doc.label}
                {locked && <span className="tab-readonly"> (Read-Only)</span>}
              </span>
              {/* Rendered as a marker with a text alternative: a bare bullet is
                  invisible to a screen reader and to a test query alike. */}
              {dirty && (
                <span className="tab-dirty" aria-label="unsaved changes" title="Unsaved changes">
                  •
                </span>
              )}
            </button>
            {/* Stale is a DIFFERENT state from dirty and gets its own marker:
                dirty is "you have edits the gateway has not seen", stale is
                "the gateway has edits you have not seen". Both at once is the
                interesting case — that is a conflict waiting at the next save,
                and it is worth being able to see it before then. */}
            {stale && (
              <button
                type="button"
                className="tab-stale"
                aria-label={`${doc.label} changed on the gateway — pull`}
                title={dirty
                  ? 'Changed on the gateway, and you have unsaved edits. Pull to compare.'
                  : 'Changed on the gateway. Pull to load the current copy.'}
                onClick={(event) => {
                  event.stopPropagation();
                  onPull?.(doc.uri);
                }}
              >
                ↓
              </button>
            )}
            <button
              type="button"
              className="tab-close"
              aria-label={`Close ${doc.label}`}
              onClick={() => onClose(doc.uri)}
            >
              ×
            </button>
          </div>
        );
      })}
    </div>
  );
}
