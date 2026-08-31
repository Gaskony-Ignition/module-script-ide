/**
 * Open documents, one tab each.
 *
 * The dirty marker is derived from the document (text vs baseText), never stored
 * separately — a dirty flag and a buffer drift apart, and the one place that
 * shows up is a tab that says "saved" over unsaved work.
 */
import { isDirty, type OpenDoc } from '../workspace/documents';
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
              <span className="tab-name">{doc.label}</span>
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
