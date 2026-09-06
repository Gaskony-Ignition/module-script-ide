/**
 * Reading another gateway, through this one.
 *
 * The browser never talks to the far gateway. It could not: a second gateway is
 * a different origin with its own session, so a direct call would be blocked by
 * CORS before it was refused for having no cookie. Every request here goes to
 * THIS gateway, which makes the outbound call server-side with a token from a
 * file only its operator can write.
 *
 * That also means the client never sends a URL — only a configured NAME. See
 * `RemoteGateways` on the Java side for why that is the whole security property
 * and not an implementation detail.
 */
import { apiUrl } from './urls';
import { toApiError } from './scripts';

/** One peer, as this gateway's configuration describes it. */
export interface RemoteGateway {
  /** The operator's key for it — what every other call here sends. */
  name: string;
  label: string;
  url: string;
  /** False when the peer has a URL but no token, so calling it would 401. */
  configured: boolean;
}

export interface RemoteGateways {
  gateways: RemoteGateway[];
  /** Whether THIS gateway will answer a peer. Half a link is the usual failure. */
  acceptsInbound: boolean;
  /** The property prefix, so the empty state can say where to configure it. */
  configKey: string;
}

/** How one body stands between the two gateways. */
export type DriftStatus = 'same' | 'differs' | 'only-here' | 'only-there';

export interface DriftRow {
  label: string;
  path: string;
  key: string;
  status: DriftStatus;
  /** Character count on each side, or -1 where the body does not exist. */
  hereChars: number;
  thereChars: number;
}

export interface DriftReport {
  gateway: string;
  gatewayLabel: string;
  project: string;
  remoteProject: string;
  total: number;
  differing: number;
  rows: DriftRow[];
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, {
    credentials: 'same-origin',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    throw await toApiError(response);
  }
  return (await response.json()) as T;
}

/** GET /api/remote/gateways */
export async function fetchRemoteGateways(): Promise<RemoteGateways> {
  const body = await getJson<RemoteGateways>(apiUrl('/api/remote/gateways'));
  return { ...body, gateways: body.gateways ?? [] };
}

/** GET /api/remote/projects?gateway=X */
export async function fetchRemoteProjects(gateway: string): Promise<string[]> {
  const query = new URLSearchParams({ gateway });
  const body = await getJson<{ projects?: Array<{ name: string }> }>(
    `${apiUrl('/api/remote/projects')}?${query.toString()}`
  );
  return (body.projects ?? []).map((p) => p.name);
}

/**
 * GET /api/remote/drift — every body, and whether it matches.
 *
 * `remoteProject` is omitted when it equals `project`, which is the common
 * case; the server defaults it the same way.
 */
export async function fetchDrift(
  gateway: string,
  project: string,
  remoteProject?: string
): Promise<DriftReport> {
  const query = new URLSearchParams({ gateway, project });
  if (remoteProject && remoteProject !== project) {
    query.set('remoteProject', remoteProject);
  }
  const body = await getJson<DriftReport>(`${apiUrl('/api/remote/drift')}?${query.toString()}`);
  return { ...body, rows: body.rows ?? [] };
}

/**
 * GET /api/remote/content — one body from the peer.
 *
 * text/plain, exactly like the local content read, so a remote buffer is an
 * ordinary document rather than a special case in the editor. There is no ETag:
 * nothing will ever be written back against it.
 */
export async function readRemoteContent(
  gateway: string,
  project: string,
  path: string,
  key?: string
): Promise<string> {
  const query = new URLSearchParams({ gateway, project, path });
  if (key) {
    query.set('key', key);
  }
  const response = await fetch(`${apiUrl('/api/remote/content')}?${query.toString()}`, {
    credentials: 'same-origin',
    headers: { Accept: 'text/plain' },
  });
  if (!response.ok) {
    throw await toApiError(response);
  }
  return response.text();
}
