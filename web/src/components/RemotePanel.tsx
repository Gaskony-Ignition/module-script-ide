/**
 * The Compare view: this gateway against another one.
 *
 * Pick a peer, and every body this IDE can open is listed with whether it
 * matches over there. Clicking a row opens the peer's copy in the OTHER pane,
 * read-only, beside your own — which is the whole feature, and the reason it
 * lives in the split view rather than in a modal.
 *
 * **Read-only, all the way down.** There is no button here that writes, and the
 * server could not honour one if there were: the outbound client has a single
 * verb and it is GET. Promoting a change between gateways is a deployment with
 * an approval and a rollback, and an editor that offered it as a button would be
 * pretending otherwise.
 *
 * **A peer is chosen by NAME, never by URL.** The list comes from the gateway's
 * own `policy.properties`; this view has no field to type a host into, and that
 * is deliberate rather than unfinished — see `RemoteGateways` on the Java side.
 *
 * **`same` rows are shown, not hidden.** A drift report that lists only the
 * differences cannot be told apart from one that failed to read anything, and
 * "nothing differs" is the answer people most want to trust.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  fetchDrift, fetchRemoteGateways,
  type DriftReport, type DriftRow, type RemoteGateway,
} from '../api/remote';
import { IconGlobe } from './Icons';
import './RemotePanel.css';

export interface RemotePanelProps {
  /** The project on THIS gateway. */
  project: string;
  /** Open the peer's copy of one body beside the local one. */
  onCompare: (gateway: RemoteGateway, remoteProject: string, row: DriftRow) => void;
}

/** The words each status gets. Short, because the row is 22px. */
const STATUS_LABEL: Record<DriftRow['status'], string> = {
  same: 'same',
  differs: 'differs',
  'only-here': 'only here',
  'only-there': 'only there',
};

export default function RemotePanel({ project, onCompare }: RemotePanelProps) {
  const [gateways, setGateways] = useState<RemoteGateway[] | null>(null);
  const [acceptsInbound, setAcceptsInbound] = useState(false);
  const [configKey, setConfigKey] = useState('com.gaskony.scriptide.remote');
  const [selected, setSelected] = useState<string>('');
  const [remoteProject, setRemoteProject] = useState('');
  const [report, setReport] = useState<DriftReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    fetchRemoteGateways()
      .then((body) => {
        if (cancelled) return;
        setGateways(body.gateways);
        setAcceptsInbound(body.acceptsInbound);
        setConfigKey(body.configKey);
        // Preselect when there is exactly one: with a single peer the dropdown
        // is a formality, and making it a required first click adds a step to
        // the only configuration most gateways will ever have.
        if (body.gateways.length === 1 && body.gateways[0].configured) {
          setSelected(body.gateways[0].name);
        }
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setGateways([]);
        setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // The report belongs to one (peer, project) pair. Left standing after either
  // changes, it would be read as the new pair's answer.
  useEffect(() => {
    setReport(null);
  }, [selected, project, remoteProject]);

  const compare = useCallback(async () => {
    if (!selected || !project) return;
    setBusy(true);
    setError('');
    try {
      setReport(await fetchDrift(selected, project, remoteProject || undefined));
    } catch (e: unknown) {
      setReport(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [selected, project, remoteProject]);

  const peer = gateways?.find((g) => g.name === selected);

  if (gateways !== null && gateways.length === 0) {
    return (
      <div className="remote-panel">
        <p className="remote-panel-empty">
          No other gateway is configured. Add one to
          {' '}<code>policy.properties</code>{' '}
          on this gateway:
        </p>
        <pre className="remote-panel-config">
          {`${configKey}.prod.url   = https://prod:8043\n`}
          {`${configKey}.prod.label = Production\n`}
          {`${configKey}.prod.token = <the remote's inbound token>`}
        </pre>
        <p className="remote-panel-empty">
          The far gateway needs <code>{configKey}.inboundToken</code> set to that
          same value, and must be running this module. Reading is all either side
          can do — nothing here can write to another gateway.
        </p>
        {error && <p className="remote-panel-error" role="alert">{error}</p>}
      </div>
    );
  }

  return (
    <div className="remote-panel">
      <div className="remote-panel-form">
        <label className="remote-panel-field">
          <span>Compare with</span>
          <select
            value={selected}
            onChange={(event) => setSelected(event.target.value)}
            aria-label="Gateway to compare with"
          >
            <option value="">Choose a gateway…</option>
            {(gateways ?? []).map((gateway) => (
              <option key={gateway.name} value={gateway.name} disabled={!gateway.configured}>
                {gateway.label}
                {gateway.configured ? '' : ' (no token configured)'}
              </option>
            ))}
          </select>
        </label>
        <label className="remote-panel-field">
          <span>Project there</span>
          <input
            type="text"
            value={remoteProject}
            placeholder={project || 'same name'}
            onChange={(event) => setRemoteProject(event.target.value)}
            aria-label="Project name on the other gateway"
          />
        </label>
        <button
          type="button"
          className="button remote-panel-go"
          disabled={!selected || !project || busy}
          onClick={() => void compare()}
        >
          <IconGlobe size={15} />
          {busy ? 'Comparing…' : 'Compare'}
        </button>
      </div>

      {peer && (
        <p className="remote-panel-note">
          {peer.label} · <span className="remote-panel-url">{peer.url}</span>
        </p>
      )}
      {!acceptsInbound && (
        // Stated even though it does not affect the OUTBOUND direction: the link
        // is set up as a pair in practice, and someone comparing dev against
        // prod today is the person who will want prod comparing against dev
        // tomorrow.
        <p className="remote-panel-note">
          This gateway does not answer remote reads. Set <code>{configKey}.inboundToken</code> to
          let another one compare against it.
        </p>
      )}
      {error && <p className="remote-panel-error" role="alert">{error}</p>}

      {report && (
        <>
          <p className="remote-panel-status" role="status">
            {report.differing === 0
              ? `All ${report.total} match ${report.gatewayLabel}.`
              : `${report.differing} of ${report.total} differ from ${report.gatewayLabel}.`}
          </p>
          <ul className="remote-panel-rows">
            {report.rows.map((row) => (
              <li key={`${row.path}:${row.key}`}>
                <button
                  type="button"
                  className={`remote-panel-row is-${row.status}`}
                  // Only a body that exists on BOTH sides can be compared. One
                  // that exists on neither is not in the list at all, and one
                  // that exists on one side has nothing to put in the other pane.
                  disabled={row.status === 'only-here' || row.status === 'only-there'}
                  onClick={() => peer && onCompare(peer, report.remoteProject, row)}
                  title={`${row.path} · ${row.key}`}
                >
                  {/* A glyph AND a fill AND a word: colour alone fails for a
                      colour-blind reader and on a projector. */}
                  <span className="remote-panel-mark" aria-hidden="true">
                    {row.status === 'same' ? '=' : row.status === 'differs' ? '≠' : '·'}
                  </span>
                  <span className="remote-panel-label">{row.label}</span>
                  <span className="remote-panel-key">{row.key}</span>
                  <span className="remote-panel-status-word">{STATUS_LABEL[row.status]}</span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
