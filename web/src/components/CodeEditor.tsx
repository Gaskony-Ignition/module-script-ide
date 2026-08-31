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
import { useEffect, useRef } from 'react';
import { indentUnit, syntaxHighlighting, HighlightStyle, bracketMatching } from '@codemirror/language';
import { python } from '@codemirror/lang-python';
import { Annotation, EditorState, Compartment, type Extension } from '@codemirror/state';
import {
  EditorView,
  keymap,
  lineNumbers,
  highlightActiveLine,
  highlightActiveLineGutter,
  drawSelection,
  rectangularSelection,
  highlightSpecialChars,
} from '@codemirror/view';
import { defaultKeymap, history, historyKeymap, indentLess, insertTab } from '@codemirror/commands';
import { tags } from '@lezer/highlight';
import type { LspClient } from '../api/lspClient';
import type { OpenDoc } from '../workspace/documents';
import { lspExtension } from './lspExtension';
import { attachDiagnostics } from './lspDiagnostics';
import { lspUri } from '../api/lspClient';
import { lintGutter } from '@codemirror/lint';
import './CodeEditor.css';

export interface CodeEditorProps {
  docs: OpenDoc[];
  activeUri: string | null;
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
}

/**
 * Syntax colours, expressed with the design tokens rather than CodeMirror's own
 * defaults — those are tuned for a light page and are barely legible here.
 */
const highlightStyle = HighlightStyle.define([
  { tag: tags.keyword, color: 'var(--syntax-keyword)' },
  { tag: [tags.controlKeyword, tags.moduleKeyword], color: 'var(--syntax-keyword)' },
  { tag: [tags.name, tags.deleted, tags.character, tags.propertyName], color: 'var(--text-primary)' },
  { tag: [tags.function(tags.variableName), tags.labelName], color: 'var(--syntax-function)' },
  { tag: [tags.definition(tags.variableName)], color: 'var(--text-primary)' },
  { tag: [tags.className, tags.typeName], color: 'var(--syntax-type)' },
  { tag: [tags.number, tags.bool, tags.null], color: 'var(--syntax-number)' },
  { tag: [tags.string, tags.special(tags.string)], color: 'var(--syntax-string)' },
  { tag: [tags.comment, tags.lineComment, tags.blockComment], color: 'var(--syntax-comment)', fontStyle: 'italic' },
  { tag: [tags.operator, tags.punctuation], color: 'var(--text-secondary)' },
  { tag: tags.invalid, color: 'var(--error)' },
]);

const editorTheme = EditorView.theme(
  {
    '&': {
      height: '100%',
      backgroundColor: 'var(--bg-primary)',
      color: 'var(--text-primary)',
      fontSize: '13px',
    },
    '.cm-scroller': { fontFamily: 'var(--font-mono)', lineHeight: '1.55' },
    '.cm-content': { caretColor: 'var(--accent-primary)' },
    '.cm-gutters': {
      backgroundColor: 'var(--bg-secondary)',
      color: 'var(--text-muted)',
      border: 'none',
      borderRight: '1px solid var(--border-light)',
    },
    '.cm-activeLine': { backgroundColor: 'var(--bg-tertiary)' },
    '.cm-activeLineGutter': { backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-secondary)' },
    '&.cm-focused .cm-cursor': { borderLeftColor: 'var(--accent-primary)' },
    '&.cm-focused .cm-selectionBackground, .cm-selectionBackground, ::selection': {
      backgroundColor: 'var(--accent-primary-bg)',
    },
    '.cm-matchingBracket, &.cm-focused .cm-matchingBracket': {
      backgroundColor: 'var(--accent-primary-bg)',
      color: 'inherit',
    },
  },
  { dark: true }
);

/** One CodeMirror instance plus the DOM node it owns and its read-only switch. */
interface MountedView {
  host: HTMLDivElement;
  view: EditorView;
  readOnlySwitch: Compartment;
  /** Unsubscribes this view from its document's diagnostics. */
  detachDiagnostics?: () => void;
}

export default function CodeEditor({ docs, activeUri, readOnly, onChange, onSave, lsp }: CodeEditorProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const viewsRef = useRef(new Map<string, MountedView>());

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
          extensions: baseExtensions(doc, onChangeRef, onSaveRef, readOnlySwitch, readOnly, lspRef.current),
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
        ? attachDiagnostics(view, client, lspUri(doc.project, doc.path))
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

  // Read-only is a session/project fact, so it is reconfigured rather than baked
  // into the initial state — a user's permissions can change under an open tab.
  useEffect(() => {
    for (const mounted of viewsRef.current.values()) {
      mounted.view.dispatch({
        effects: mounted.readOnlySwitch.reconfigure(readOnlyExtension(readOnly)),
      });
    }
  }, [readOnly]);

  // Show exactly one view. Hidden rather than unmounted — see the file comment.
  useEffect(() => {
    for (const [uri, mounted] of viewsRef.current) {
      mounted.host.style.display = uri === activeUri ? 'block' : 'none';
    }
  }, [docs, activeUri]);

  return <div className="code-editor" ref={rootRef} data-testid="code-editor" />;
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
  return [
    lineNumbers(),
    highlightActiveLineGutter(),
    highlightSpecialChars(),
    history(),
    drawSelection(),
    rectangularSelection(),
    highlightActiveLine(),
    bracketMatching(),
    syntaxHighlighting(highlightStyle, { fallback: true }),
    python(),

    // ---- byte fidelity ----
    // A literal tab, so every indent CodeMirror generates (auto-indent after a
    // ':', indentMore, indentOnInput) is a tab and never spaces.
    indentUnit.of('\t'),
    // Tab width for DISPLAY and for the column arithmetic the Python indenter
    // does; it never converts a tab into spaces.
    EditorState.tabSize.of(4),
    // Pin the line separator. Left at its default, CodeMirror splits the document
    // on any of CR, LF or CRLF and rejoins with \n — so opening and saving a file
    // with CRLF endings rewrites every line, invisibly.
    EditorState.lineSeparator.of('\n'),

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
    ...(lsp ? [lintGutter(), lspExtension(lsp, { project: doc.project, path: doc.path })] : []),

    EditorView.updateListener.of((update) => {
      if (!update.docChanged) return;
      // toString() returns the document verbatim: no trimming, no appended
      // trailing newline. That string is what gets POSTed.
      onChangeRef.current(uri, update.state.doc.toString());
    }),
  ];
}
