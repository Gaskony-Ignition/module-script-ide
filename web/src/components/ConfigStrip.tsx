/**
 * The per-type attribute editor — a timer's delay and threading, a message
 * handler's thread type, a library script's hint scope.
 *
 * The fields shown are driven ENTIRELY by the `editable` array the attributes
 * endpoint returns; nothing here decides what a type supports. That array is the
 * server's measured allowlist, and a type whose Designer workspace was never
 * measured returns an empty one — for those this strip renders nothing at all
 * rather than offering a control whose write the server will refuse.
 *
 * The value types are not interchangeable and are not coerced here:
 * `sharedThread` is a boolean (timer), `threadType` is a case-sensitive string
 * (message handler). Sending the wrong one is accepted by the resource layer and
 * then behaves wrongly, with nothing in any log to say so.
 */
import type { AttributeValue } from '../api/scripts';
import './ConfigStrip.css';

export interface ConfigStripProps {
  /** Attribute names the server will accept for this resource type. */
  editable: string[];
  attributes: Record<string, AttributeValue>;
  onChange: (name: string, value: AttributeValue) => void;
  onSave: () => void;
  dirty: boolean;
  readOnly: boolean;
  saving?: boolean;
}

/** Attributes rendered as a checkbox. */
const BOOLEAN_FIELDS = new Set(['enabled', 'fixedDelay', 'sharedThread']);

const LABELS: Record<string, string> = {
  enabled: 'Enabled',
  delay: 'Delay (ms)',
  fixedDelay: 'Fixed delay',
  sharedThread: 'Shared thread',
  threadType: 'Thread type',
  hintScope: 'Hint scope',
};

/**
 * ApplicationScope bitmask. These four values are the only ones the server
 * accepts; anything else is written silently and then behaves unpredictably in
 * the Designer, which is why the control is a select and not a number box.
 */
const HINT_SCOPES: Array<{ value: number; label: string }> = [
  { value: 0, label: 'None' },
  { value: 1, label: 'Gateway' },
  { value: 2, label: 'Designer' },
  { value: 7, label: 'All' },
];

/** Exactly as the Designer writes them. Case-sensitive — do not title-case. */
const THREAD_TYPES = ['Shared', 'Dedicated'];

export default function ConfigStrip({
  editable,
  attributes,
  onChange,
  onSave,
  dirty,
  readOnly,
  saving = false,
}: ConfigStripProps) {
  // Body-only type: render nothing, not an empty bar.
  if (editable.length === 0) return null;

  return (
    <div className="config-strip" aria-label="Script settings">
      {editable.map((name) => (
        <label className="config-field" key={name}>
          <span className="config-label">{LABELS[name] ?? name}</span>
          {renderField(name, attributes[name], onChange, readOnly)}
        </label>
      ))}
      <button
        type="button"
        className="button config-save"
        onClick={onSave}
        // Attributes are a separate resource write from the body, so they get
        // their own button — saving the script must not silently push settings
        // the user only clicked through.
        disabled={readOnly || saving || !dirty}
      >
        {saving ? 'Saving settings…' : 'Save settings'}
      </button>
    </div>
  );
}

function renderField(
  name: string,
  value: AttributeValue | undefined,
  onChange: ConfigStripProps['onChange'],
  readOnly: boolean
) {
  if (BOOLEAN_FIELDS.has(name)) {
    return (
      <input
        type="checkbox"
        checked={value === true}
        disabled={readOnly}
        onChange={(e) => onChange(name, e.target.checked)}
      />
    );
  }
  if (name === 'delay') {
    return (
      <input
        type="number"
        min={0}
        // 24 hours, matching ScriptResourceTypes.MAX_TIMER_DELAY_MS. A larger
        // value is a 400 from the server, so the input stops it here.
        max={86400000}
        step={100}
        value={typeof value === 'number' ? value : ''}
        disabled={readOnly}
        onChange={(e) => onChange(name, Number(e.target.value))}
      />
    );
  }
  if (name === 'threadType') {
    return (
      <select
        value={typeof value === 'string' ? value : THREAD_TYPES[0]}
        disabled={readOnly}
        onChange={(e) => onChange(name, e.target.value)}
      >
        {THREAD_TYPES.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    );
  }
  if (name === 'hintScope') {
    return (
      <select
        value={typeof value === 'number' ? String(value) : '0'}
        disabled={readOnly}
        onChange={(e) => onChange(name, Number(e.target.value))}
      >
        {HINT_SCOPES.map((option) => (
          <option key={option.value} value={String(option.value)}>
            {option.label}
          </option>
        ))}
      </select>
    );
  }
  // An attribute this build does not know how to render. Shown read-only rather
  // than hidden: the server said it is editable, so silently dropping it would
  // hide a real capability behind a stale frontend.
  return <input type="text" value={String(value ?? '')} readOnly disabled />;
}
