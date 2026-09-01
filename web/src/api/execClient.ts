/**
 * Typed client for the execution channel.
 *
 * Shares the ONE authenticated WebSocket with the language server — see
 * LspTransport. `on('exec', …)` plus `send('exec', …)` is the entire surface
 * needed, and this file deliberately knows nothing about JSON-RPC: the exec
 * channel is a plain request/event protocol, not RPC.
 *
 * Two properties of the server protocol shape everything here:
 *
 * 1. **Output is not streamed.** ScriptIdeSocket sends `started` immediately and
 *    then a single `finished` carrying the whole stdout and stderr. A long run
 *    therefore shows nothing until it ends, which is why the UI has a running
 *    state at all rather than just appending text.
 * 2. **The console keeps its locals; a file run does not.** Omitting `target`
 *    marks the run as a console run, and the server then reuses that project's
 *    locals so the console behaves like a REPL. Sending a `target` gets fresh
 *    locals every time, because a script file is not a REPL and carrying state
 *    between runs of one makes results depend on invisible history.
 */
import { sharedTransport } from './lspTransport';
import type { LspTransport } from './lspTransport';

/** The server's `error` describing a Python failure, from TracebackFormatter. */
export interface ExecErrorFrame {
  /** Resource path when the frame is in a project script, else absent. */
  path?: string;
  /** Dotted module name for a project-library frame, e.g. `util.helpers`. */
  module?: string;
  line: number;
  functionName?: string;
  /** True when this frame is in the source the user just ran. */
  isTarget?: boolean;
}

export interface ExecError {
  type: string;
  message: string;
  frames: ExecErrorFrame[];
  /** The rendered traceback, for when a frame cannot be resolved to a file. */
  text?: string;
}

export interface ExecResult {
  executionId: string;
  stdout: string;
  stderr: string;
  /** Output hit the server's cap and was cut — the rest is gone, not pending. */
  truncated: boolean;
  /** The run was stopped rather than completing or failing. */
  cancelled: boolean;
  ok: boolean;
  error?: ExecError;
}

export interface RunRequest {
  project: string;
  source: string;
  csrfToken?: string;
  /**
   * The resource being run. OMIT for a console run — its presence is what tells
   * the server this is a file, and the server keys REPL locals on its absence.
   */
  target?: string;
  /**
   * Blank lines the client prepended so a selection run's traceback line numbers
   * still match the editor. The server subtracts it back off.
   */
  lineOffset?: number;
}

export type ExecEvent =
  | { kind: 'started'; executionId: string }
  | { kind: 'stopping'; executionId: string; detail?: string }
  | { kind: 'finished'; result: ExecResult }
  | { kind: 'error'; message: string };

/** Shape of anything arriving on the exec channel. Validated, never trusted. */
interface RawExecMessage {
  event?: string;
  executionId?: string;
  detail?: string;
  error?: string | ExecError;
  stdout?: string;
  stderr?: string;
  truncated?: boolean;
  cancelled?: boolean;
  ok?: boolean;
}

/**
 * Normalise one incoming frame.
 *
 * `error` is overloaded by the server: a STRING at the top level is a channel
 * error (execution disabled, not an admin, bad CSRF), while an OBJECT inside a
 * `finished` frame is a Python traceback. Conflating them shows "TypeError" when
 * what actually happened is "you are not an administrator", so they are split
 * here rather than at the call site.
 */
export function toExecEvent(raw: unknown): ExecEvent | null {
  if (!raw || typeof raw !== 'object') {
    return null;
  }
  const msg = raw as RawExecMessage;

  if (typeof msg.error === 'string') {
    return { kind: 'error', message: msg.error };
  }
  if (msg.event === 'started' && msg.executionId) {
    return { kind: 'started', executionId: msg.executionId };
  }
  if (msg.event === 'stopping' && msg.executionId) {
    return { kind: 'stopping', executionId: msg.executionId, detail: msg.detail };
  }
  if (msg.event === 'finished' && msg.executionId) {
    return {
      kind: 'finished',
      result: {
        executionId: msg.executionId,
        stdout: msg.stdout ?? '',
        stderr: msg.stderr ?? '',
        truncated: msg.truncated === true,
        cancelled: msg.cancelled === true,
        ok: msg.ok === true,
        error: typeof msg.error === 'object' && msg.error !== null
          ? (msg.error as ExecError)
          : undefined,
      },
    };
  }
  return null;
}

export class ExecClient {
  constructor(private readonly transport: LspTransport = sharedTransport()) {}

  /** Subscribe to normalised exec events. Returns an unsubscribe function. */
  subscribe(listener: (event: ExecEvent) => void): () => void {
    // Open the socket NOW, when the console mounts, rather than leaving it to
    // the first run.
    //
    // `send()` connects lazily but still returns false for the attempt that
    // triggered it, so without this the first Run a user ever clicks reports
    // "not connected" and does nothing — measured 01/09/2026 in the browser.
    // It is worse in the popped-out console, which has no language client to
    // have opened the socket for it, so EVERY first run failed there.
    // connect() is idempotent.
    this.transport.connect();
    return this.transport.on('exec', (msg) => {
      const event = toExecEvent(msg);
      if (event) {
        listener(event);
      }
    });
  }

  /**
   * Start a run. Returns false if the socket is not open — the caller should
   * surface that rather than leaving a spinner up forever, because there is no
   * queueing: a send on a closed socket is simply dropped.
   */
  run(request: RunRequest): boolean {
    const msg: Record<string, unknown> = {
      action: 'run',
      project: request.project,
      source: request.source,
    };
    if (request.csrfToken) {
      msg.csrfToken = request.csrfToken;
    }
    // Only set when present: an explicit undefined would still serialise as a
    // key for some encoders, and the server keys console-vs-file on `has`.
    if (request.target !== undefined) {
      msg.target = request.target;
    }
    if (request.lineOffset) {
      msg.lineOffset = request.lineOffset;
    }
    return this.transport.send('exec', msg);
  }

  /** Ask the gateway to stop a run. Best-effort — see the Stop UI copy. */
  stop(executionId: string, csrfToken?: string): boolean {
    const msg: Record<string, unknown> = { action: 'stop', executionId };
    if (csrfToken) {
      msg.csrfToken = csrfToken;
    }
    return this.transport.send('exec', msg);
  }
}

let shared: ExecClient | null = null;

/** The process-wide client, sharing the process-wide transport. */
export function sharedExecClient(): ExecClient {
  if (!shared) {
    shared = new ExecClient();
  }
  return shared;
}
