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
  /** Web Dev endpoint. NOTE: a different module id — com.inductiveautomation.webdev. */
  | 'resources'
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
  /**
   * For a Web Dev endpoint: the HTTP methods it actually implements.
   *
   * Absent for every other type. Sent on the LISTING so the tree can show an
   * endpoint's verbs without a request per endpoint.
   */
  methods?: string[];
  /**
   * The event script's `enabled` attribute, when it has one.
   *
   * On the listing because the Designer badges a disabled script in its tree,
   * and asking per row would be one request per gateway event script.
   */
  enabled?: boolean;
  /**
   * Singletons only: whether the resource actually carries a script yet.
   *
   * The Designer shows Startup, Shutdown and Update whether or not they exist,
   * and renders the label bold once one does. Absent for every other type.
   */
  defined?: boolean;
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

// ==================== Create and delete ====================

/**
 * Create a new, empty Project Library script.
 *
 * There is no separate create route: POST to a path the project does not yet
 * define takes the server's create branch. The distinction that matters is the
 * PRECONDITION — a create must NOT send an If-Match, because there is no version
 * to match and sending one would make the server treat it as a modify of
 * something absent. So this deliberately does not go through {@link postJson},
 * which always sets the header.
 *
 * The body is created empty. The real Designer writes a zero-byte `code.py` for
 * a new library script, and matching that keeps a fresh script byte-identical
 * whichever tool made it.
 */
export async function createScript(request: {
  project: string;
  path: string;
  /** Initial body. Empty for a library script; a handler stub for an event. */
  source?: string;
  csrfToken?: string;
}): Promise<SaveResult> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  };
  if (request.csrfToken) {
    headers[CSRF_HEADER] = request.csrfToken;
  }
  const response = await fetch(
    scriptRouteUrl('/api/scripts/content', request.path, request.project),
    {
      method: 'POST',
      credentials: 'same-origin',
      headers,
      // No baseSignature: absent means create.
      body: JSON.stringify({ source: request.source ?? '' }),
    }
  );
  if (!response.ok) {
    throw await toApiError(response);
  }
  return (await response.json()) as SaveResult;
}

/**
 * DELETE /api/scripts/content/:path
 *
 * `baseSignature` is REQUIRED by the server (428 without it) and is the reason a
 * delete cannot discard an edit the user never saw: if the script changed since
 * the tree was listed, this fails with a 409 instead of destroying the newer
 * version.
 */
export async function deleteScript(request: {
  project: string;
  path: string;
  baseSignature: string;
  csrfToken?: string;
}): Promise<{ ok: true; deleted?: string }> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
    'If-Match': request.baseSignature,
  };
  if (request.csrfToken) {
    headers[CSRF_HEADER] = request.csrfToken;
  }
  const response = await fetch(
    scriptRouteUrl('/api/scripts/content', request.path, request.project),
    { method: 'DELETE', credentials: 'same-origin', headers }
  );
  if (!response.ok) {
    throw await toApiError(response);
  }
  return (await response.json()) as { ok: true; deleted?: string };
}

/**
 * Validate a proposed Project Library script name, returning an error string or
 * null.
 *
 * This is a real constraint, not input hygiene: a library script's resource name
 * becomes its Python module path, so `my-utils` creates a module that cannot be
 * imported by any syntax Python has — `import project.my-utils` is a parse error.
 * The Designer refuses such a name and so must this. Folders are allowed, since
 * `util/helpers` is an ordinary package path, but each segment must independently
 * be a valid identifier.
 */
export function validateScriptName(name: string, typeId: ScriptTypeId = 'script-python'): string | null {
  // Gateway event scripts are named RESOURCES, not modules. The Designer's own
  // fixture is called "Probe Scheduled" — with a space — so applying the Python
  // identifier rule to them would refuse names the Designer creates every day.
  // Only the project library's names become import paths.
  if (typeId !== 'script-python') {
    return validateEventScriptName(name);
  }
  return validateLibraryName(name);
}

/**
 * A gateway event script name.
 *
 * Permissive on purpose — the name becomes a directory on the gateway, and the
 * platform accepts spaces. What is refused is what would break the addressing:
 * a path separator (the route matches one segment), a leading or trailing space
 * (invisible, and it round-trips into a directory name nobody can retype), and
 * control characters.
 */
function validateEventScriptName(name: string): string | null {
  if (!name || !name.trim()) {
    return 'Enter a name';
  }
  if (name !== name.trim()) {
    return 'Name cannot start or end with a space';
  }
  if (name.includes('/') || name.includes('\\')) {
    return 'Name cannot contain "/" or "\\"';
  }
  // eslint-disable-next-line no-control-regex
  if (/[\u0000-\u001f\u007f]/.test(name)) {
    return 'Name cannot contain control characters';
  }
  if (name === '.' || name === '..') {
    return 'That name is reserved';
  }
  if (name.length > 120) {
    return 'Name is too long';
  }
  return null;
}

function validateLibraryName(name: string): string | null {
  if (!name || !name.trim()) {
    return 'Enter a name';
  }
  if (name !== name.trim()) {
    return 'Name cannot start or end with a space';
  }
  if (name.startsWith('/') || name.endsWith('/')) {
    return 'Name cannot start or end with "/"';
  }
  if (name.includes('//')) {
    return 'Name cannot contain an empty folder segment';
  }
  const segments = name.split('/');
  for (const segment of segments) {
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(segment)) {
      return `"${segment}" is not a valid Python name — letters, digits and `
        + 'underscores only, and it cannot start with a digit';
    }
    if (PYTHON_KEYWORDS.has(segment)) {
      return `"${segment}" is a Python keyword, so the module could never be imported`;
    }
  }
  return null;
}

/**
 * Python 2.7 keywords. Jython 2.7 is what runs these scripts, so this is the
 * py2 list — `print` and `exec` ARE keywords here and `True`/`False`/`None` are
 * not, which is the opposite of Python 3 on three counts.
 */
const PYTHON_KEYWORDS = new Set([
  'and', 'as', 'assert', 'break', 'class', 'continue', 'def', 'del', 'elif',
  'else', 'except', 'exec', 'finally', 'for', 'from', 'global', 'if', 'import',
  'in', 'is', 'lambda', 'not', 'or', 'pass', 'print', 'raise', 'return', 'try',
  'while', 'with', 'yield',
]);
