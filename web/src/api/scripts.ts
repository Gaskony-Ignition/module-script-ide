/**
 * Typed client for the script-resource API.
 *
 * Mirrors ScriptResourceRouteHandler and ScriptAttributesRouteHandler. Two
 * things here are load-bearing rather than stylistic:
 *
 * 1. Every call sends `credentials: 'same-origin'` — the Gateway identifies the
 *    user by its own session cookie, and a fetch without it is anonymous even on
 *    a page the user is signed into.
 * 2. Resource paths are encoded with encodeURIComponent, so their slashes become
 *    %2F. See {@link scriptRouteUrl}.
 */
import { apiUrl } from './urls';

/** Resource types this IDE edits. Mirrors ScriptResourceTypes. */
export type ScriptTypeId =
  | 'script-python'
  | 'timer'
  | 'message'
  | 'scheduled'
  | 'tag-change'
  | 'startup'
  | 'shutdown'
  | 'update';

/** Where a resource comes from, relative to the project being edited. */
export type ScriptOrigin = 'local' | 'inherited' | 'override';

export interface ProjectSummary {
  name: string;
  /** False for an immutable project — the UI disables saving up front. */
  mutable: boolean;
}

export interface ScriptEntry {
  /** `<moduleId>/<typeId>[/<name>]`, e.g. `ignition/script-python/util/helpers`. */
  path: string;
  typeId: ScriptTypeId;
  /** Bare name within the type; empty string for a singleton (startup/shutdown/update). */
  name: string;
  /** Resource signature — the optimistic-concurrency token. */
  signature: string;
  dataKeys: string[];
  /**
   * The `.py` data key this resource actually carries. Always use this, never a
   * per-type default: a resource written by an older Designer can legitimately
   * differ, and writing to the wrong key adds a second key instead of updating
   * the script.
   */
  scriptKey: string;
  /** Human-readable type name, e.g. "Project Library". Drives the tree grouping. */
  typeLabel: string;
  singleton: boolean;
  origin: ScriptOrigin;
  /** Project that defines the resource — differs from the open one when inherited. */
  owner: string;
}

export interface ScriptTree {
  project: string;
  mutable: boolean;
  scripts: ScriptEntry[];
}

export interface ScriptContent {
  /** The script body, byte-for-byte as stored. Never trimmed. */
  text: string;
  /** The ETag the read returned — the resource signature. */
  etag: string;
}

export interface SaveResult {
  ok: true;
  /** The signature AFTER the write; becomes the next call's base. */
  signature?: string;
}

/** Attribute values the API accepts. Types are exact — see ScriptResourceTypes. */
export type AttributeValue = string | number | boolean;

export interface ScriptAttributes {
  path: string;
  signature: string;
  /**
   * Attribute names this resource type accepts. Empty means body-only, and the
   * UI must then render no attribute controls at all — the server rejects a
   * write for those types rather than guessing what the Designer writes.
   */
  editable: string[];
  attributes: Record<string, AttributeValue>;
}

/**
 * An API failure carrying the server's status and its `{error: "..."}` message.
 *
 * The status is part of the contract, not diagnostics: 409 means somebody else
 * changed the resource and must open the conflict dialog rather than be reported
 * as a generic failure.
 */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string
  ) {
    super(message);
    this.name = 'ApiError';
  }

  /** Concurrent edit — another Designer, or the web-designer module. */
  get isConflict(): boolean {
    return this.status === 409;
  }

  /** The write arrived with no base signature; re-read and retry. */
  get isMissingBaseSignature(): boolean {
    return this.status === 428;
  }
}

/** Header the Gateway's WebUiSession CSRF filter reads. Must match exactly. */
const CSRF_HEADER = 'X-CSRF-Token';

/**
 * URL for a per-resource route.
 *
 * `RouteGroup` matches `:path` as a SINGLE segment, so the resource path's own
 * slashes MUST be percent-encoded — `ignition/script-python/util/helpers`
 * becomes `ignition%2Fscript-python%2Futil%2Fhelpers`. Passing it raw produces
 * a multi-segment URL that matches no route and 404s, which reads exactly like
 * a missing script.
 */
export function scriptRouteUrl(base: '/api/scripts/content' | '/api/scripts/attributes', path: string, project: string): string {
  const query = new URLSearchParams({ project });
  return `${apiUrl(`${base}/${encodeURIComponent(path)}`)}?${query.toString()}`;
}

/** Turn a non-OK response into an ApiError carrying the server's message. */
async function toApiError(response: Response): Promise<ApiError> {
  let message = `HTTP ${response.status}`;
  try {
    const text = await response.text();
    if (text) {
      // Error bodies are {error: "..."} — but a proxy or the servlet container
      // can answer with plain HTML, so parsing must not itself throw.
      try {
        const parsed = JSON.parse(text) as { error?: string };
        message = parsed.error ?? text;
      } catch {
        message = text;
      }
    }
  } catch {
    /* body unreadable — the status alone is the message */
  }
  return new ApiError(response.status, message);
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

async function postJson(url: string, body: unknown, csrfToken: string | undefined, baseSignature: string): Promise<SaveResult> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
    // If-Match wins over the body's baseSignature server-side; both are sent so
    // the write still carries its precondition if a proxy strips the header.
    'If-Match': baseSignature,
  };
  if (csrfToken) {
    headers[CSRF_HEADER] = csrfToken;
  }
  const response = await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    headers,
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw await toApiError(response);
  }
  return (await response.json()) as SaveResult;
}

/** GET /api/projects */
export async function fetchProjects(): Promise<ProjectSummary[]> {
  const body = await getJson<{ projects: ProjectSummary[] }>(apiUrl('/api/projects'));
  return body.projects ?? [];
}

/** GET /api/scripts?project=X */
export async function fetchScriptTree(project: string): Promise<ScriptTree> {
  const query = new URLSearchParams({ project });
  const body = await getJson<ScriptTree>(`${apiUrl('/api/scripts')}?${query.toString()}`);
  return { ...body, scripts: body.scripts ?? [] };
}

/**
 * GET /api/scripts/content/:path — the raw body plus its ETag.
 *
 * The response is text/plain, NOT JSON: it is a Python source file and must not
 * pass through a JSON parser, which would normalise nothing useful and could
 * fail on a lone backslash.
 */
export async function readScriptContent(
  project: string,
  path: string,
  key?: string
): Promise<ScriptContent> {
  let url = scriptRouteUrl('/api/scripts/content', path, project);
  if (key) {
    url += `&key=${encodeURIComponent(key)}`;
  }
  const response = await fetch(url, {
    credentials: 'same-origin',
    headers: { Accept: 'text/plain' },
  });
  if (!response.ok) {
    throw await toApiError(response);
  }
  return { text: await response.text(), etag: readEtag(response) };
}

/**
 * The ETag, stripped of the quoting an intermediary may add.
 *
 * The handler sets the bare signature, but a caching proxy is entitled to
 * rewrite it as `W/"..."`, and the server compares If-Match by exact string —
 * so a quoted value round-trips as a permanent 409.
 */
function readEtag(response: Response): string {
  const raw = response.headers.get('ETag') ?? '';
  return raw.replace(/^W\//, '').replace(/^"(.*)"$/, '$1');
}

export interface SaveContentRequest {
  project: string;
  path: string;
  /** Sent verbatim. Nothing here trims it or appends a newline — see CodeEditor. */
  source: string;
  /** The resource's own script data key, from the listing. */
  key?: string;
  /** The ETag from the read this edit started from. */
  baseSignature: string;
  csrfToken?: string;
}

/** POST /api/scripts/content/:path */
export function saveScriptContent(request: SaveContentRequest): Promise<SaveResult> {
  return postJson(
    scriptRouteUrl('/api/scripts/content', request.path, request.project),
    { source: request.source, key: request.key, baseSignature: request.baseSignature },
    request.csrfToken,
    request.baseSignature
  );
}

/** GET /api/scripts/attributes/:path */
export async function readScriptAttributes(project: string, path: string): Promise<ScriptAttributes> {
  const body = await getJson<ScriptAttributes>(
    scriptRouteUrl('/api/scripts/attributes', path, project)
  );
  return { ...body, editable: body.editable ?? [], attributes: body.attributes ?? {} };
}

export interface SaveAttributesRequest {
  project: string;
  path: string;
  attributes: Record<string, AttributeValue>;
  baseSignature: string;
  csrfToken?: string;
}

/** POST /api/scripts/attributes/:path */
export function saveScriptAttributes(request: SaveAttributesRequest): Promise<SaveResult> {
  return postJson(
    scriptRouteUrl('/api/scripts/attributes', request.path, request.project),
    { attributes: request.attributes, baseSignature: request.baseSignature },
    request.csrfToken,
    request.baseSignature
  );
}
