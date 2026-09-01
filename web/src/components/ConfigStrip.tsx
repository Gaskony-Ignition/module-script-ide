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
  /** Resource type, so the strip can show that type's Designer documentation. */
  typeId?: string;
  /**
   * Why this type has no editable settings, when it has none. Rendered instead
   * of nothing: a Tag Change script with no visible controls otherwise looks
   * like a bug in this IDE rather than a deliberate refusal.
   */
  unconfigurableReason?: string;
}

/**
 * Attributes rendered as a checkbox.
 *
 * `fixedDelay` is NOT one of them: the Designer shows it as a radio pair,
 * ● Fixed Delay / ○ Fixed Rate, and those are two named modes rather than one
 * on/off setting. A checkbox called "Fixed delay" leaves the user to work out
 * what unticking it does, and the answer — "fixed rate" — is a word that never
 * appears on screen.
 */
const BOOLEAN_FIELDS = new Set(['enabled', 'sharedThread']);

const LABELS: Record<string, string> = {
  enabled: 'Enabled',
  delay: 'Delay (ms)',
  fixedDelay: 'Delay type',
  sharedThread: 'Shared thread',
  threadType: 'Thread type',
  hintScope: 'Hint scope',
  cronExpression: 'Cron expression',
};

/**
 * The Designer's own explanatory text for each event type, and the parameters
 * its handler is called with.
 *
 * Both are STATIC in the Designer — they describe what the event type is and
 * what its handler receives. Neither is stored in `resource.json` and neither is
 * editable there, so neither is editable here: inventing a `description`
 * attribute would write a key the platform does not read and the Designer would
 * never show, which is the opposite of the two tools lining up.
 *
 * Wording is verbatim from the real Designer where it was measured
 * (web-designer `docs/design-handoff/real-designer/SCRIPTING.md` §5.1–5.4).
 */
const TYPE_DOCS: Record<
  string,
  { description: string; parameters?: Array<{ name: string; type: string; text: string }> }
> = {
  timer: {
    // Verbatim from the Designer, SCRIPTING.md §5.1. The 1.2.0 wording was a
    // paraphrase, which is the one thing a "parity" string must not be.
    description: 'Timer scripts that are always running on the Gateway',
  },
  message: {
    description:
      'Message handler scripts that run whenever the Gateway receives a script message',
    parameters: [
      {
        name: 'payload',
        type: 'dict',
        text: 'A dictionary that holds the objects passed to this message handler. '
          + "Retrieve them with a subscript, e.g. myObject = payload['argumentName']",
      },
    ],
  },
  startup: { description: 'Project startup script that runs in the Gateway' },
  shutdown: { description: 'Project shutdown script that runs in the Gateway' },
  update: { description: 'Project update script that runs in the Gateway' },
  scheduled: {
    description:
      'Scheduled scripts run on the Gateway according to a cron expression.',
  },
  'tag-change': {
    description:
      'Tag change scripts run on the Gateway when one of their configured tags changes.',
  },
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
  typeId,
  unconfigurableReason,
}: ConfigStripProps) {
  const docs = typeId ? TYPE_DOCS[typeId] : undefined;

  // Body-only type: still say what the script IS and why there is nothing to
  // configure, rather than rendering an empty bar or nothing at all.
  if (editable.length === 0) {
    if (!docs && !unconfigurableReason) return null;
    return (
      <div className="config-strip config-strip-docs" aria-label="Script settings">
        <TypeDocs docs={docs} />
        {unconfigurableReason && (
          <p className="config-note muted">{unconfigurableReason}</p>
        )}
      </div>
    );
  }

  return (
    <div className="config-strip" aria-label="Script settings">
      <TypeDocs docs={docs} />
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

/**
 * The Designer's description and handler parameters for this event type.
 *
 * Read-only by construction — see TYPE_DOCS. Rendered above the controls so the
 * page reads in the same order as the Designer's workspace.
 */
function TypeDocs({ docs }: { docs?: (typeof TYPE_DOCS)[string] }) {
  if (!docs) return null;
  return (
    <div className="config-docs">
      <p className="config-description">{docs.description}</p>
      {docs.parameters && docs.parameters.length > 0 && (
        <dl className="config-params">
          {docs.parameters.map((param) => (
            <div className="config-param" key={param.name}>
              <dt>
                <code>{param.name}</code>
                <span className="config-param-type muted">({param.type})</span>
              </dt>
              <dd className="muted">{param.text}</dd>
            </div>
          ))}
        </dl>
      )}
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
  if (name === 'fixedDelay') {
    // The Designer's radio pair. `true` is Fixed Delay and is the default it
    // writes on create.
    return (
      <span className="config-radio-pair">
        {[
          { value: true, label: 'Fixed Delay' },
          { value: false, label: 'Fixed Rate' },
        ].map((option) => (
          <label className="config-radio" key={String(option.value)}>
            <input
              type="radio"
              name="fixedDelay"
              checked={(value ?? true) === option.value}
              disabled={readOnly}
              onChange={() => onChange(name, option.value)}
            />
            {option.label}
          </label>
        ))}
      </span>
    );
  }
  if (name === 'cronExpression') {
    return (
      <input
        type="text"
        className="config-cron"
        value={String(value ?? '')}
        placeholder="*/30 * * * *"
        spellCheck={false}
        // Free text, not a builder. The gateway's scheduler is the arbiter of
        // what a valid expression is, and a builder here would quietly refuse
        // expressions the platform accepts.
        onChange={(e) => onChange(name, e.target.value)}
        disabled={readOnly}
      />
    );
  }
  // An attribute this build does not know how to render. Shown read-only rather
  // than hidden: the server said it is editable, so silently dropping it would
  // hide a real capability behind a stale frontend.
  return <input type="text" value={String(value ?? '')} readOnly disabled />;
}
