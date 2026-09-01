/**
 * Name a new Project Library script.
 *
 * Validation runs as the user types and the create button stays disabled until
 * the name is legal, because the failure it prevents is not cosmetic: a library
 * script's resource name IS its Python module path, so `my-utils` produces a
 * module that no `import` statement can name. Catching that after a round trip
 * would mean the gateway holds a resource the user can never use.
 *
 * Project Library only, deliberately. A timer or message handler also needs
 * attributes (a delay, a threading mode) whose Designer-written defaults this
 * module has not measured, and inventing them writes a value onto a live gateway
 * on the strength of a guess — the same rule that keeps `scheduled` and
 * `tag-change` attribute writes refused.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { validateScriptName } from '../api/scripts';
import './NewScriptDialog.css';

export interface NewScriptDialogProps {
  /** Existing library script names, so a collision is caught before the round trip. */
  existingNames: string[];
  busy?: boolean;
  error?: string | null;
  onCreate: (name: string) => void;
  onCancel: () => void;
}

export default function NewScriptDialog({
  existingNames,
  busy = false,
  error = null,
  onCreate,
  onCancel,
}: NewScriptDialogProps) {
  const [name, setName] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const taken = useMemo(() => new Set(existingNames), [existingNames]);
  const problem = useMemo(() => {
    if (!name) {
      return null; // Don't scold an empty field the user has not filled in yet.
    }
    const invalid = validateScriptName(name);
    if (invalid) {
      return invalid;
    }
    if (taken.has(name)) {
      return `${name} already exists in this project`;
    }
    return null;
  }, [name, taken]);

  const canCreate = name.trim().length > 0 && problem === null && !busy;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (canCreate) {
      onCreate(name);
    }
  }

  return (
    <div className="newscript-backdrop" role="presentation">
      <form
        className="newscript-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="newscript-title"
        onSubmit={submit}
        // Escape closes, matching every other dialog in the app.
        onKeyDown={(event) => {
          if (event.key === 'Escape') {
            event.stopPropagation();
            onCancel();
          }
        }}
      >
        <h2 id="newscript-title">New library script</h2>
        <label className="newscript-label" htmlFor="newscript-name">
          Name
        </label>
        <input
          id="newscript-name"
          ref={inputRef}
          className="newscript-input"
          value={name}
          spellCheck={false}
          autoComplete="off"
          placeholder="util/helpers"
          aria-describedby="newscript-hint"
          aria-invalid={problem ? 'true' : undefined}
          onChange={(event) => setName(event.target.value)}
          disabled={busy}
        />
        <p id="newscript-hint" className="newscript-hint muted">
          Use <code>/</code> for packages — <code>util/helpers</code> becomes
          {' '}
          <code>project.util.helpers</code>. The script starts empty.
        </p>

        {problem && (
          <p className="newscript-problem" role="alert">
            {problem}
          </p>
        )}
        {error && (
          <p className="newscript-problem" role="alert">
            {error}
          </p>
        )}

        <div className="newscript-actions">
          <button type="button" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="primary" disabled={!canCreate}>
            {busy ? 'Creating…' : 'Create'}
          </button>
        </div>
      </form>
    </div>
  );
}
