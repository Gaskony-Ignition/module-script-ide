/**
 * The CodeMirror 6 editing surface.
 *
 * Two decisions here are the whole point of the component and must not be
 * "tidied":
 *
 * **Byte fidelity.** The real Designer writes tabs, never spaces, and no
 * terminating newline. If this editor normalises either, every subsequent git
 * diff of the project is noise and a two-line change reads as a rewritten file.
 * So: `indentUnit` is a literal tab, Tab inserts a tab, `lineSeparator` is
 * pinned to `\n` (without it CodeMirror splits on CR/LF/CRLF and rejoins with
 * `\n`, silently rewriting a CRLF file), and nothing anywhere trims the document
 * or appends to it.
 *
 * **Language intelligence is per view, not per component.** The LSP extensions
 * are built into each view's initial state and close over that document's URI,
 * so the server's copy of a buffer is opened and closed with the view that owns
 * it. See lspExtension.ts.
 *
 * **One EditorView per open document, kept mounted.** The cheaper design — one
 * view whose EditorState is swapped on tab switch — throws away scroll position
 * and undo history on every switch, and CodeMirror has no supported way to
 * restore the scroll offset of a state it is not showing. Inactive views are
 * hidden with `display:none` instead, so switching tabs is free and everything
 * the user had survives.
 */
import { useCallback, useEffect, useRef } from 'react';
import { Annotation, EditorState, Compartment, type Extension } from '@codemirror/state';
import { EditorView, keymap } from '@codemirror/view';
import { defaultKeymap, historyKeymap, indentLess, insertTab } from '@codemirror/commands';
import type { LspClient } from '../api/lspClient';
import { isLockedByInheritance, type OpenDoc } from '../workspace/documents';
import { lspExtension } from './lspExtension';
import { attachDiagnostics } from './lspDiagnostics';
import { lspUri } from '../api/lspClient';
import { lintGutter } from '@codemirror/lint';
import {
  byteFidelity, editorTheme, findAndReplace, folding, goToLine, pythonSurface, sqlSurface,
} from './editorCore';
import './CodeEditor.css';

export interface CodeEditorProps {
  docs: OpenDoc[];
  activeUri: string | null;
  /**
   * Session/project-wide read-only: no edit permission, or an immutable
   * project. A document can ALSO be read-only on its own account — see
   * {@link isLockedByInheritance} — so this is one of two inputs, never the
   * whole answer.
   */
  readOnly: boolean;
  onChange: (uri: string, text: string) => void;
  /** Ctrl/Cmd+S. Fired with the URI of the view that had focus. */
  onSave: (uri: string) => void;
  /**
   * The shared language client, or null/undefined for none.
   *
   * Optional so a test — or a gateway where the socket never came up — gets a
   * plain editor rather than a broken one. It is read when a view is created and
   * never reconfigured: swapping the client under a live document would leave
   * the old server holding a file nobody will ever close.
   */
  lsp?: LspClient | null;
  /**
   * Hide the buffer without unmounting a single view.
   *
   * The named-query editor's Settings and Testing tabs take the whole editor
   * area, and unmounting this component to make room would destroy every open
   * document's CodeMirror view along with its undo history and scroll offset.
   * `[hidden]` is forced to win globally in index.css precisely so a component
   * can stay mounted and off screen — see the note there.
   */
  hidden?: boolean;
}

/**
 * What a `scriptide:reveal` event carries.
 *
 * `uri` is the WORKSPACE document key (`project::path::key`), not the LSP one —
 * the views here are keyed by document. Omitting it means "the active view",
 * which is what the outline panel wants: it is always describing the tab you are
 * looking at.
 */
export interface RevealDetail {
  uri?: string;
  /** Zero-based. */
  line: number;
  character?: number;
}

/** One CodeMirror instance plus the DOM node it owns and its read-only switch. */
interface MountedView {
  host: HTMLDivElement;
  view: EditorView;
  readOnlySwitch: Compartment;
  /** Unsubscribes this view from its document's diagnostics. */
  detachDiagnostics?: () => void;
}

export default function CodeEditor({
  docs, activeUri, readOnly, onChange, onSave, lsp, hidden = false,
}: CodeEditorProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const viewsRef = useRef(new Map<string, MountedView>());
  // Read through a ref so `applyReveal` has one identity for the life of the
  // component: it is a dependency of the listener effect, and rebinding a window
  // listener on every tab switch is how a reveal arrives at a listener that has
  // just been removed.
  const activeUriRef = useRef(activeUri);
  activeUriRef.current = activeUri;

  // The extensions are built once per view and then never rebuilt, so the
  // callbacks they close over are read through refs — otherwise every render
  // with a new callback identity would need a full reconfigure, and a
  // reconfigure resets things a reconfigure has no business resetting.
  const onChangeRef = useRef(onChange);
  const onSaveRef = useRef(onSave);
  const lspRef = useRef(lsp);
  onChangeRef.current = onChange;
  onSaveRef.current = onSave;
  lspRef.current = lsp;

  // Create a view for each newly opened doc, destroy the ones that were closed.
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const views = viewsRef.current;
    const open = new Set(docs.map((d) => d.uri));

    for (const [uri, mounted] of views) {
      if (!open.has(uri)) {
        mounted.detachDiagnostics?.();
        mounted.view.destroy();
        mounted.host.remove();
        views.delete(uri);
      }
    }

    for (const doc of docs) {
      if (views.has(doc.uri)) continue;
      const host = document.createElement('div');
      host.className = 'code-editor-host';
      host.dataset.uri = doc.uri;
      root.appendChild(host);
      const readOnlySwitch = new Compartment();
      const view = new EditorView({
        parent: host,
        state: EditorState.create({
          doc: doc.text,
          extensions: baseExtensions(
            doc,
            onChangeRef,
            onSaveRef,
            readOnlySwitch,
            readOnly || isLockedByInheritance(doc),
            lspRef.current
          ),
        }),
      });
      // Diagnostics are PUSHED by the server, so the view subscribes rather than
      // polling. The unsubscribe is stored with the view and called on destroy —
      // without it a closed tab keeps a listener alive that dispatches into a
      // destroyed view, which throws inside the transport's message handler.
      const client = lspRef.current;
      // Subscribe with the LSP uri, NOT doc.uri. The workspace keys documents as
      // "Project::path" while the language server keys them as
      // "ignition://Project/path", and the server publishes diagnostics against the
      // latter. Using doc.uri here subscribes to a key nothing ever publishes, so
      // every diagnostic is silently dropped and the editor looks clean however
      // broken the code is.
      const detachDiagnostics = client
        ? attachDiagnostics(view, client, lspUri(doc.project, doc.path, doc.scriptKey))
        : undefined;
      views.set(doc.uri, { host, view, readOnlySwitch, detachDiagnostics });
    }
  }, [docs, readOnly]);

  // Destroy everything on unmount. Separate from the sync effect above so that
  // effect can depend on `docs` without tearing every view down each render.
  useEffect(() => {
    const views = viewsRef.current;
    return () => {
      for (const mounted of views.values()) {
        mounted.detachDiagnostics?.();
        mounted.view.destroy();
        mounted.host.remove();
      }
      views.clear();
    };
  }, []);

  // Push text that changed OUTSIDE the editor (a conflict reload, a re-read)
  // into the view. A change that came from the view itself round-trips back
  // here identical, so the equality check makes this a no-op and there is no
  // feedback loop.
  useEffect(() => {
    for (const doc of docs) {
      const mounted = viewsRef.current.get(doc.uri);
      if (!mounted) continue;
      const current = mounted.view.state.doc.toString();
      if (current !== doc.text) {
        mounted.view.dispatch({
          changes: { from: 0, to: current.length, insert: doc.text },
          annotations: externalUpdate.of(true),
        });
      }
    }
  }, [docs]);

  // Read-only is reconfigured rather than baked into the initial state, because
  // BOTH of its inputs change under an open tab: a user's permissions can be
  // revoked, and overriding an inherited script unlocks that one document
  // without touching any other. Hence per-view, keyed on the doc — a single
  // dispatch over every view would unlock the whole tab strip.
  useEffect(() => {
    for (const doc of docs) {
      const mounted = viewsRef.current.get(doc.uri);
      if (!mounted) continue;
      mounted.view.dispatch({
        effects: mounted.readOnlySwitch.reconfigure(
          readOnlyExtension(readOnly || isLockedByInheritance(doc))
        ),
      });
    }
  }, [docs, readOnly]);

  // Show exactly one view. Hidden rather than unmounted — see the file comment.
  useEffect(() => {
    for (const [uri, mounted] of viewsRef.current) {
      mounted.host.style.display = uri === activeUri ? 'block' : 'none';
    }
  }, [docs, activeUri]);

  /**
   * Reveal a line, for the outline panel, a clicked traceback frame, a search
   * result and go-to-definition.
   *
   * Driven by a window event rather than a prop, because the caller is two
   * components away and the alternative is threading an imperative handle
   * through everything in between.
   *
   * **A reveal whose view does not exist yet is REMEMBERED, not dropped.** Every
   * cross-file jump opens a script and then asks for a line in it, and the open
   * is React state: the view for that URI is created by an effect on the next
   * render, which has not run when the caller's `await` resolves. The
   * traceback-frame path had this race from 1.5.0 and lost the line silently
   * whenever the file was not already open — the tab appeared at line 1 and
   * nothing said why. Holding one pending reveal and applying it when the view
   * appears fixes every caller at once.
   */
  const pendingRevealRef = useRef<RevealDetail | null>(null);

  const applyReveal = useCallback((detail: RevealDetail): boolean => {
    const uri = detail.uri ?? activeUriRef.current;
    if (!uri) return false;
    const mounted = viewsRef.current.get(uri);
    if (!mounted) return false;
    const { view } = mounted;
    // Clamp: the symbol table can be a moment behind the buffer, and asking
    // CodeMirror for a line past the end throws rather than saturating.
    const lineNumber = Math.min(Math.max(detail.line + 1, 1), view.state.doc.lines);
    const line = view.state.doc.line(lineNumber);
    const pos = Math.min(line.from + (detail.character ?? 0), line.to);
    view.dispatch({
      selection: { anchor: pos },
      // Centred rather than CodeMirror's default, so the target does not land
      // against the bottom edge with no context under it.
      effects: EditorView.scrollIntoView(pos, { y: 'center' }),
    });
    view.focus();
    return true;
  }, []);

  useEffect(() => {
    function onReveal(event: Event) {
      const detail = (event as CustomEvent<RevealDetail>).detail;
      if (!detail) return;
      if (!applyReveal(detail)) {
        pendingRevealRef.current = detail;
      }
    }
    window.addEventListener('scriptide:reveal', onReveal);
    return () => window.removeEventListener('scriptide:reveal', onReveal);
  }, [applyReveal]);

  // Drain a pending reveal once the view it wanted exists. Runs after the effect
  // that creates views, because it is declared after it.
  useEffect(() => {
    const pending = pendingRevealRef.current;
    if (!pending) return;
    if (applyReveal(pending)) {
      pendingRevealRef.current = null;
    }
  }, [docs, activeUri, applyReveal]);

  return <div className="code-editor" hidden={hidden} ref={rootRef} data-testid="code-editor" />;
}

/**
 * Marks a transaction as coming from the workspace rather than the keyboard — a
 * conflict reload or a re-read. Those must land even in a read-only editor,
 * which is otherwise refusing every document change.
 */
const externalUpdate = Annotation.define<boolean>();

function readOnlyExtension(readOnly: boolean): Extension {
  if (!readOnly) {
    return [EditorState.readOnly.of(false), EditorView.editable.of(true)];
  }
  return [
    EditorState.readOnly.of(true),
    EditorView.editable.of(false),
    // EditorState.readOnly is ADVISORY: it is a flag commands are expected to
    // check, and not all of them do — insertTab happily edits a read-only
    // document. So the guarantee is made here instead, by cancelling any
    // document change that did not come from the workspace itself. Measured,
    // not assumed: without this the Tab key edits a read-only script.
    EditorState.transactionFilter.of((tr) =>
      tr.docChanged && !tr.annotation(externalUpdate) ? [] : tr
    ),
  ];
}

function baseExtensions(
  doc: OpenDoc,
  onChangeRef: React.MutableRefObject<CodeEditorProps['onChange']>,
  onSaveRef: React.MutableRefObject<CodeEditorProps['onSave']>,
  readOnlySwitch: Compartment,
  readOnly: boolean,
  lsp: LspClient | null | undefined
): Extension[] {
  const uri = doc.uri;
  // The language is the document's, not the component's. Everything else —
  // theme, find and replace, folding, go-to-line, byte fidelity — is identical
  // for both, because a query and the script that calls it are one piece of
  // work and two editors that behave differently would make them two tools.
  const isQuery = doc.kind === 'named-query';
  return [
    ...(isQuery ? sqlSurface : pythonSurface),
    ...findAndReplace,
    // Files only — the console shares pythonSurface and has no use for either.
    ...folding,
    goToLine,

    // ---- byte fidelity ---- see editorCore. Shared with the Script Console, so
    // a tab means the same thing in both.
    ...byteFidelity,

    keymap.of([
      {
        key: 'Mod-s',
        // preventDefault stops the browser's own Save Page dialog; returning
        // true also marks the event handled for CodeMirror.
        preventDefault: true,
        run: () => {
          onSaveRef.current(uri);
          return true;
        },
      },
      // insertTab inserts the indentUnit — a literal tab, per the facet above.
      { key: 'Tab', run: insertTab, shift: indentLess },
      ...defaultKeymap,
      ...historyKeymap,
    ]),

    editorTheme,
    readOnlySwitch.of(readOnlyExtension(readOnly)),

    // Last, so a language feature can never shadow a byte-fidelity facet above:
    // later extensions lose precedence ties in CodeMirror, and `indentUnit` and
    // the line separator are not negotiable.
    // The gutter marker matters as much as the inline squiggle: an error several
    // hundred lines away is otherwise invisible until you scroll onto it.
    //
    // NEVER on a SQL view. The language server is a Jython server: it would
    // parse the SQL as Python, publish a syntax error for every line of it, and
    // hold a document nothing will ever close. 1.7.0 ships no SQL intelligence
    // at all (NAMED-QUERIES.md §4) — the database's own error on a test run is
    // the diagnostic.
    ...(lsp && !isQuery
      ? [lintGutter(), lspExtension(lsp, { project: doc.project, path: doc.path, scriptKey: doc.scriptKey })]
      : []),

    EditorView.updateListener.of((update) => {
      if (!update.docChanged) return;
      // toString() returns the document verbatim: no trimming, no appended
      // trailing newline. That string is what gets POSTed.
      onChangeRef.current(uri, update.state.doc.toString());
    }),
  ];
}
