/**
 * A typed Language Server Protocol client over {@link LspTransport}.
 *
 * <h3>Positions</h3>
 *
 * LSP `character` offsets are **UTF-16 code units**, not code points and not
 * bytes (the spec's default `positionEncoding`, and what the Java server's
 * `TextDocument` assumes because Java strings are UTF-16 too). JavaScript
 * strings — and therefore CodeMirror's document offsets — are also indexed in
 * UTF-16 code units. So the conversion is arithmetic on the line start and
 * nothing else: no transcoding, and specifically no `Array.from()` or
 * `[...string]` spread, both of which count code POINTS and would silently
 * place the cursor one column early for every astral character earlier on the
 * line. An emoji is two units on both sides of the wire, and that agreement is
 * the whole reason the arithmetic is allowed to be this simple.
 *
 * The one genuine adjustment is line numbering: CodeMirror numbers lines from
 * 1, LSP from 0.
 *
 * <h3>Synchronisation</h3>
 *
 * `didChange` is incremental (the server advertises `textDocumentSync: 2`), and
 * every range is expressed in the coordinates of the document BEFORE the change
 * set was applied. See {@link contentChangesFor} for why the changes are sent in
 * reverse order.
 */
import type { ChangeSet, Text } from '@codemirror/state';
import { LspTransport, sharedTransport } from './lspTransport';

export interface Position {
  /** Zero-based. CodeMirror's line numbers are one-based — mind the gap. */
  line: number;
  /** Zero-based, in UTF-16 code units. */
  character: number;
}

export interface Range {
  start: Position;
  end: Position;
}

export interface TextDocumentContentChange {
  /** Absent means "the text is the whole new document". */
  range?: Range;
  text: string;
}

/** LSP MarkupContent, or the plain string older servers send. */
export type Documentation = string | { kind: 'markdown' | 'plaintext'; value: string };

export interface CompletionItem {
  label: string;
  /** LSP CompletionItemKind. This server emits 9 (Module), 3 (Function), 10 (Property). */
  kind?: number;
  /** A signature like `readBlocking(tagPaths, [timeout])`. */
  detail?: string;
  /** `[1]` is CompletionItemTag.Deprecated. */
  tags?: number[];
  /** Only present AFTER completionItem/resolve — deliberately, to keep the popup fast. */
  documentation?: Documentation;
  data?: { dottedPath?: string };
}

export interface CompletionList {
  isIncomplete: boolean;
  items: CompletionItem[];
}

export interface Hover {
  contents: Documentation;
  range?: Range;
}

export interface ParameterInformation {
  label: string;
  documentation?: Documentation;
}

export interface SignatureInformation {
  label: string;
  documentation?: Documentation;
  parameters?: ParameterInformation[];
}

export interface SignatureHelp {
  signatures: SignatureInformation[];
  activeSignature?: number;
  activeParameter?: number;
}

/** One problem the server found. Mirrors the LSP Diagnostic shape we consume. */
export interface LspDiagnostic {
  range: Range;
  /** LSP DiagnosticSeverity: 1 Error, 2 Warning, 3 Information, 4 Hint. */
  severity?: number;
  source?: string;
  message: string;
}

/** A `textDocument/publishDiagnostics` payload. */
export interface DiagnosticsForDocument {
  uri: string;
  /** The document version the server analysed. */
  version?: number;
  diagnostics: LspDiagnostic[];
}

export interface ServerCapabilities {
  textDocumentSync?: number;
  hoverProvider?: boolean;
  completionProvider?: { triggerCharacters?: string[]; resolveProvider?: boolean };
  signatureHelpProvider?: { triggerCharacters?: string[] };
}

export interface InitializeResult {
  capabilities: ServerCapabilities;
  serverInfo?: { name?: string; version?: string };
}

/**
 * Document URI for a script resource.
 *
 * `ignition://<project>/<resourcePath>` — the resource path exactly as
 * `scripts.ts` uses it, with its slashes intact. This is an opaque key to the
 * server, so nothing here percent-encodes it: the REST layer has to, because
 * the route matches a single path segment, and the socket does not.
 */
export function lspUri(project: string, resourcePath: string): string {
  return `ignition://${project}/${resourcePath}`;
}

/** CodeMirror document offset → LSP position. Clamped, so a stale offset cannot throw. */
export function offsetToPosition(doc: Text, offset: number): Position {
  const clamped = Math.max(0, Math.min(offset, doc.length));
  const line = doc.lineAt(clamped);
  // `clamped - line.from` is a count of UTF-16 code units, which is exactly what
  // LSP asks for. See the file comment before "simplifying" this.
  return { line: line.number - 1, character: clamped - line.from };
}

/** LSP position → CodeMirror document offset. The inverse, equally clamped. */
export function positionToOffset(doc: Text, position: Position): number {
  const lineNumber = Math.max(1, Math.min(position.line + 1, doc.lines));
  const line = doc.line(lineNumber);
  return Math.min(line.from + Math.max(0, position.character), line.to);
}

/**
 * A CodeMirror {@link ChangeSet} as LSP content changes.
 *
 * Two things make this correct rather than nearly correct:
 *
 * 1. Every position is computed against `before` — the document as it was when
 *    the change set was made. `iterChanges` hands out `fromA`/`toA` in exactly
 *    those coordinates.
 * 2. The changes are sent in REVERSE document order. LSP applies content
 *    changes in array order, each against the document produced by the one
 *    before it, whereas CodeMirror's are all against the original. Applying the
 *    last edit first means every earlier range is still valid when its turn
 *    comes, because an edit at a higher offset cannot move a lower one. A
 *    forward-order send is wrong the moment a single transaction carries two
 *    edits — which multi-cursor typing and a single Backspace over a selection
 *    both do.
 */
export function contentChangesFor(before: Text, changes: ChangeSet): TextDocumentContentChange[] {
  const collected: TextDocumentContentChange[] = [];
  changes.iterChanges((fromA, toA, _fromB, _toB, inserted) => {
    collected.push({
      range: { start: offsetToPosition(before, fromA), end: offsetToPosition(before, toA) },
      text: inserted.toString(),
    });
  });
  return collected.reverse();
}

/** What the client remembers about a document the server has been told about. */
interface TrackedDocument {
  uri: string;
  project: string;
  version: number;
  /**
   * The current content, held as CodeMirror's {@link Text} once the document has
   * been edited.
   *
   * Kept unflattened deliberately. The only thing that needs a string is a
   * (re)`didOpen`, which happens on a reconnect or a project switch; calling
   * `toString()` on every keystroke to keep a string field up to date would
   * rebuild the whole buffer per character typed, which is exactly the cost
   * incremental sync exists to avoid.
   */
  content: Text | string;
}

function contentString(document: TrackedDocument): string {
  return typeof document.content === 'string' ? document.content : document.content.toString();
}

/**
 * The LSP client.
 *
 * It owns the open-document set, because it is the only thing that can restore
 * it: `ScriptIdeSocket` builds a fresh `LanguageServer` both on a new connection
 * AND whenever the envelope's `project` changes, and either event leaves a
 * server that has never heard of any of our files.
 */
export class LspClient {
  private readonly documents = new Map<string, TrackedDocument>();
  /**
   * The project the server's current LanguageServer was built for.
   *
   * Null means "nothing is synchronised" — the state after a reconnect and the
   * state before the first document opens.
   */
  private syncedProject: string | null = null;
  private capabilitiesPromise: Promise<InitializeResult> | null = null;

  /** Diagnostic listeners, keyed by document uri. */
  private readonly diagnosticListeners =
    new Map<string, Set<(diagnostics: LspDiagnostic[]) => void>>();

  /**
   * The last diagnostics seen per uri.
   *
   * Kept because diagnostics are pushed, not polled: an editor that mounts after
   * the server has already published gets nothing until the next keystroke, so a
   * freshly opened file with an error would look clean.
   */
  private readonly lastDiagnostics = new Map<string, LspDiagnostic[]>();

  constructor(private readonly transport: LspTransport = sharedTransport()) {
    // Every connect, first or otherwise, starts from a server with no
    // documents. Resynchronising here rather than at the call sites means no
    // feature has to know that reconnection is a thing.
    this.transport.onOpen(() => this.resync());
    this.transport.on('lsp', (msg) => this.handleServerMessage(msg));
  }

  /**
   * Route a server-initiated message.
   *
   * Only notifications arrive here — the transport resolves anything carrying an
   * `id` against its own pending-request table before listeners see it.
   */
  private handleServerMessage(msg: unknown): void {
    const message = msg as { method?: string; params?: DiagnosticsForDocument } | null;
    if (!message || message.method !== 'textDocument/publishDiagnostics') {
      return;
    }
    const params = message.params;
    if (!params || typeof params.uri !== 'string') {
      return;
    }
    const diagnostics = Array.isArray(params.diagnostics) ? params.diagnostics : [];

    // Drop a payload older than the buffer it describes. The server tags each
    // publish with the version it analysed; without this check a slow parse can
    // land after a newer keystroke and re-show an error the user just fixed.
    const tracked = this.documents.get(params.uri);
    if (tracked && typeof params.version === 'number' && params.version < tracked.version) {
      return;
    }

    this.lastDiagnostics.set(params.uri, diagnostics);
    this.diagnosticListeners.get(params.uri)?.forEach((listener) => listener(diagnostics));
  }

  /**
   * Subscribe to diagnostics for one document. Returns an unsubscribe function.
   *
   * The listener fires immediately with the last known set, so an editor that
   * mounts after a publish still shows the problems that are already known.
   */
  onDiagnostics(uri: string, listener: (diagnostics: LspDiagnostic[]) => void): () => void {
    let listeners = this.diagnosticListeners.get(uri);
    if (!listeners) {
      listeners = new Set();
      this.diagnosticListeners.set(uri, listeners);
    }
    listeners.add(listener);
    const known = this.lastDiagnostics.get(uri);
    if (known) {
      listener(known);
    }
    return () => {
      const set = this.diagnosticListeners.get(uri);
      if (!set) {
        return;
      }
      set.delete(listener);
      if (set.size === 0) {
        this.diagnosticListeners.delete(uri);
      }
    };
  }

  /** The server's `initialize` result for a project, requested at most once per sync. */
  initialize(project: string): Promise<InitializeResult> {
    this.ensureSynced(project);
    return this.capabilitiesPromise ?? Promise.reject(new Error('Not initialised'));
  }

  /** Tell the server about a document, and start tracking it for resynchronisation. */
  didOpen(uri: string, project: string, text: string): void {
    const existing = this.documents.get(uri);
    const document: TrackedDocument = {
      uri,
      project,
      // Versions must increase for the life of a document, so a reopen
      // continues the sequence rather than restarting it.
      version: existing ? existing.version + 1 : 1,
      content: text,
    };
    this.documents.set(uri, document);
    // A sync that had to run has already sent didOpen for every document of the
    // project, this one included; sending it again would be a duplicate open.
    if (!this.ensureSynced(project)) {
      this.sendDidOpen(document);
    }
  }

  /**
   * Send an incremental change.
   *
   * `before` is the document the change set applies to — `update.startState.doc`,
   * not the current one.
   */
  didChange(uri: string, changes: ChangeSet, before: Text, after: Text): void {
    const document = this.documents.get(uri);
    if (!document) return;
    document.version++;
    document.content = after;
    // A fresh sync has just sent the current text in full, so the delta that
    // produced it is already accounted for.
    if (this.ensureSynced(document.project)) return;
    this.transport.notify(
      'lsp',
      'textDocument/didChange',
      {
        textDocument: { uri, version: document.version },
        contentChanges: contentChangesFor(before, changes),
      },
      document.project
    );
  }

  /** Notify a save. The server does nothing with it today; the notification is cheap and correct. */
  didSave(uri: string): void {
    const document = this.documents.get(uri);
    if (!document) return;
    if (this.ensureSynced(document.project)) return;
    this.transport.notify(
      'lsp',
      'textDocument/didSave',
      { textDocument: { uri }, text: contentString(document) },
      document.project
    );
  }

  didClose(uri: string): void {
    const document = this.documents.get(uri);
    if (!document) return;
    this.documents.delete(uri);
    // Only worth telling a server that has the document. If a sync is pending,
    // the resend simply will not include it.
    if (this.syncedProject === document.project) {
      this.transport.notify('lsp', 'textDocument/didClose', { textDocument: { uri } }, document.project);
    }
    // Drop the cached problems too, or reopening the file briefly shows the
    // diagnostics it had when it was last closed.
    this.lastDiagnostics.delete(uri);
  }

  /** Completions at a position. Returns [] rather than throwing on an unknown document. */
  async completion(uri: string, position: Position): Promise<CompletionItem[]> {
    const document = this.documents.get(uri);
    if (!document) return [];
    this.ensureSynced(document.project);
    const result = await this.transport.request<CompletionList | CompletionItem[] | null>(
      'lsp',
      'textDocument/completion',
      { textDocument: { uri }, position },
      document.project
    );
    if (!result) return [];
    return Array.isArray(result) ? result : (result.items ?? []);
  }

  /**
   * Fill in one item's documentation.
   *
   * The item is sent back verbatim — the server round-trips `data.dottedPath`
   * through it, and stripping fields would break the lookup.
   */
  async resolveCompletion(item: CompletionItem, project?: string): Promise<CompletionItem> {
    const target = project ?? this.syncedProject ?? undefined;
    const resolved = await this.transport.request<CompletionItem | null>(
      'lsp',
      'completionItem/resolve',
      item,
      target
    );
    return resolved ?? item;
  }

  async hover(uri: string, position: Position): Promise<Hover | null> {
    const document = this.documents.get(uri);
    if (!document) return null;
    this.ensureSynced(document.project);
    return await this.transport.request<Hover | null>(
      'lsp',
      'textDocument/hover',
      { textDocument: { uri }, position },
      document.project
    );
  }

  async signatureHelp(uri: string, position: Position): Promise<SignatureHelp | null> {
    const document = this.documents.get(uri);
    if (!document) return null;
    this.ensureSynced(document.project);
    return await this.transport.request<SignatureHelp | null>(
      'lsp',
      'textDocument/signatureHelp',
      { textDocument: { uri }, position },
      document.project
    );
  }

  /** Documents the server is believed to know about. For tests and diagnostics. */
  openDocumentCount(): number {
    return this.documents.size;
  }

  /**
   * Make sure the server has a LanguageServer for `project` holding every
   * document we have open in it.
   *
   * Deliberately SYNCHRONOUS. It would be tidier to await the `initialize`
   * response before sending anything else, and it would also be wrong: frames
   * are processed in order on the socket, but promise continuations are not, so
   * awaiting here lets a `didChange` overtake the `didOpen` it depends on. The
   * initialize response carries capabilities we already know from the module we
   * ship with, so nothing needs to wait for it.
   *
   * @returns true if a synchronisation actually ran, meaning didOpen has just
   *          been sent for every document of this project.
   */
  private ensureSynced(project: string): boolean {
    if (this.syncedProject === project) return false;
    // Switching the envelope's project makes the server throw its LanguageServer
    // away and build another, so the documents of the project we are leaving are
    // gone server-side. They are still in `documents`, and will be re-sent when
    // the user switches back.
    this.syncedProject = project;
    const initialized = this.transport.request<InitializeResult>(
      'lsp',
      'initialize',
      {
        processId: null,
        rootUri: `ignition://${project}`,
        capabilities: {
          textDocument: {
            synchronization: { dynamicRegistration: false },
            completion: {
              completionItem: { snippetSupport: false, resolveSupport: { properties: ['documentation'] } },
            },
            hover: { contentFormat: ['markdown', 'plaintext'] },
            signatureHelp: {
              signatureInformation: { documentationFormat: ['markdown', 'plaintext'] },
            },
          },
        },
      },
      project
    );
    // Nobody is obliged to call initialize(), so the stored promise gets its own
    // no-op catch: an initialize that times out on a dead socket must degrade to
    // "no answers", not to an unhandled rejection in the console.
    void initialized.catch(() => undefined);
    this.capabilitiesPromise = initialized;
    this.transport.notify('lsp', 'initialized', {}, project);
    for (const document of this.documents.values()) {
      if (document.project === project) {
        this.sendDidOpen(document);
      }
    }
    return true;
  }

  private sendDidOpen(document: TrackedDocument): void {
    this.transport.notify(
      'lsp',
      'textDocument/didOpen',
      {
        textDocument: {
          uri: document.uri,
          languageId: 'python',
          version: document.version,
          text: contentString(document),
        },
      },
      document.project
    );
  }

  /**
   * Re-establish the whole server-side view after a reconnect.
   *
   * Every open document is re-opened, project by project. Only the last
   * project's documents survive on the server — one LanguageServer per socket —
   * and that is fine: {@link ensureSynced} restores any other project the moment
   * something asks for it.
   */
  private resync(): void {
    this.syncedProject = null;
    this.capabilitiesPromise = null;
    const projects = new Set<string>();
    for (const document of this.documents.values()) {
      projects.add(document.project);
    }
    for (const project of projects) {
      this.ensureSynced(project);
    }
  }
}

let sharedClient: LspClient | null = null;

/** The app-wide client. Created on first use — importing this opens no socket. */
export function sharedLspClient(): LspClient {
  if (!sharedClient) {
    sharedClient = new LspClient();
  }
  return sharedClient;
}
