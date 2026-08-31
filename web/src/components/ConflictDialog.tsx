/**
 * Shown when a save comes back 409 — the resource changed on the gateway since
 * this tab read it.
 *
 * This is a P1 requirement rather than polish. The gateway's script resources are
 * not owned by this IDE: a Designer, or the web-designer module, can be editing
 * the same resource on the same gateway at the same time. Without this dialog the
 * only two options a user gets are "lose their work" and "lose yours", and
 * neither is offered as a choice.
 *
 * "Keep mine" is a deliberate force: it re-reads to obtain the CURRENT signature
 * and saves against that, which is exactly the overwrite the 409 prevented. It is
 * safe only because the other version is on screen beside it.
 */
import { useMemo } from 'react';
import { diffLines } from '../workspace/lineDiff';
import './ConflictDialog.css';

export interface ConflictDialogProps {
  label: string;
  /** The buffer in this tab. */
  mine: string;
  /** What the gateway holds now. */
  theirs: string;
  /** Who last wrote the gateway's copy, when the server told us. */
  theirsOwner?: string;
  busy?: boolean;
  onReloadTheirs: () => void;
  onKeepMine: () => void;
  onCancel: () => void;
}

export default function ConflictDialog({
  label,
  mine,
  theirs,
  theirsOwner,
  busy = false,
  onReloadTheirs,
  onKeepMine,
  onCancel,
}: ConflictDialogProps) {
  const rows = useMemo(() => diffLines(mine, theirs), [mine, theirs]);

  return (
    <div className="conflict-backdrop" role="presentation">
      <div className="conflict-dialog" role="dialog" aria-modal="true" aria-labelledby="conflict-title">
        <h2 id="conflict-title">{label} changed on the gateway</h2>
        <p className="muted">
          Somebody else saved this script after you opened it
          {theirsOwner ? ` (${theirsOwner})` : ''}. Your changes were not written.
        </p>

        <div className="conflict-diff" aria-label="Differences">
          <div className="conflict-column-heads">
            <span>Yours (in this tab)</span>
            <span>On the gateway</span>
          </div>
          <ol className="conflict-rows">
            {rows.map((row, index) => (
              <li key={index} className={`conflict-row conflict-${row.kind}`}>
                <code className="conflict-side">{row.left ?? ''}</code>
                <code className="conflict-side">{row.right ?? ''}</code>
              </li>
            ))}
          </ol>
        </div>

        <div className="conflict-actions">
          <button type="button" className="button" onClick={onReloadTheirs} disabled={busy}>
            Reload theirs (discard mine)
          </button>
          <button type="button" className="button button-danger" onClick={onKeepMine} disabled={busy}>
            Keep mine (overwrite theirs)
          </button>
          <button type="button" className="button button-quiet" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
