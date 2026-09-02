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
  onSelect: (uri: string) => void;
  onClose: (uri: string) => void;
}

export default function TabStrip({ docs, activeUri, onSelect, onClose }: TabStripProps) {
  if (docs.length === 0) return null;

  return (
    <div className="tab-strip" role="tablist" aria-label="Open scripts">
      {docs.map((doc) => {
        const dirty = isDirty(doc);
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
