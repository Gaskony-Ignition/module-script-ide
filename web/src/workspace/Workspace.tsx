/**
 * The P1 editor workspace: project picker, script tree, tabs, editor, attribute
 * strip, and the conflict path.
 *
 * All mutable state for an open script lives in one place — the `docs` array —
 * because the alternative (state inside CodeMirror, a dirty flag beside it, an
 * ETag somewhere else) has three copies of the truth and no way to tell which is
 * right after a failed save. `dirty` is derived, and a save updates `baseText`
 * and `etag` together or not at all.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ApiError,
  createScript,
  deleteScript,
  fetchProjects,
  fetchScriptTree,
  readScriptAttributes,
  readScriptContent,
  saveScriptAttributes,
  saveScriptContent,
  type AttributeValue,
  type ProjectSummary,
  type ScriptEntry,
  type ScriptTree,
} from '../api/scripts';
import { lspUri, sharedLspClient } from '../api/lspClient';
import { sharedTransport } from '../api/lspTransport';
import type { SessionInfo } from '../api/session';
import CodeEditor from '../components/CodeEditor';
import ConfigStrip from '../components/ConfigStrip';
import ConflictDialog from '../components/ConflictDialog';
import FileTree from '../components/FileTree';
import NewScriptDialog from '../components/NewScriptDialog';
import OutlinePanel from '../components/OutlinePanel';
import ScriptConsole from '../components/ScriptConsole';
import StatusFooter from '../components/StatusFooter';
import TabStrip from '../components/TabStrip';
import { docUri, isDirty, newDoc, type OpenDoc } from './documents';
import './Workspace.css';

export interface WorkspaceProps {
  session: SessionInfo;
}

/** Attribute editing state for one open document. */
interface AttrState {
  /** Names the server will accept. Empty means the strip renders nothing. */
  editable: string[];
  attributes: Record<string, AttributeValue>;
  /** What the gateway last agreed to, so "dirty" is derived here too. */
  base: Record<string, AttributeValue>;
}

interface Conflict {
  uri: string;
  label: string;
  mine: string;
  theirs: string;
  /** The signature the gateway's current copy carries — the base for a force. */
  theirsEtag: string;
}

type Notice = { kind: 'error' | 'info'; text: string } | null;

/**
 * How much of the editing area the console occupies.
 *
 * `split` is the default when the console is opened from the rail, because the
 * reason to open a console is almost always to try something against the script
 * you are looking at — replacing that script with the console would defeat the
 * purpose. `full` exists for when the console IS the task.
 */
type ConsoleMode = 'hidden' | 'split' | 'full';

export default function Workspace({ session }: WorkspaceProps) {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [project, setProject] = useState<string>('');
  const [tree, setTree] = useState<ScriptTree | null>(null);
  const [treeError, setTreeError] = useState<string>('');
  const [docs, setDocs] = useState<OpenDoc[]>([]);
  const [activeUri, setActiveUri] = useState<string | null>(null);
  const [attrs, setAttrs] = useState<Record<string, AttrState>>({});
  const [saving, setSaving] = useState(false);
  const [savingAttrs, setSavingAttrs] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const [conflict, setConflict] = useState<Conflict | null>(null);
  const [consoleMode, setConsoleMode] = useState<ConsoleMode>('hidden');
  const [outlineOpen, setOutlineOpen] = useState(true);
  const [creating, setCreating] = useState(false);
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<ScriptEntry | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  // Bumped on every edit so the outline re-requests. A counter rather than the
  // text itself: the effect only needs to know THAT it changed.
  const [docRevision, setDocRevision] = useState(0);

  // Saves are fired from a CodeMirror keybinding as well as from the button, and
  // both read the CURRENT docs array. Keeping it in a ref avoids handing the
  // editor a callback that closes over a stale render.
  const docsRef = useRef(docs);
  docsRef.current = docs;

  // One client for the whole workspace, and through it one socket for the whole
  // tab. Built lazily on first use, so nothing connects until a script is
  // actually opened.
  const lsp = useMemo(() => sharedLspClient(), []);

  // The same instance the client above is built on — `sharedTransport()` is a
  // singleton, so the footer reports the state of the very socket the editor is
  // using, not a second one opened to watch it.
  const transport = useMemo(() => sharedTransport(), []);

  const activeDoc = useMemo(
    () => docs.find((d) => d.uri === activeUri) ?? null,
    [docs, activeUri]
  );

  /**
   * Writes are refused for two independent reasons and the UI must say which:
   * the user lacks the role, or the project itself is immutable (inherited or
   * locked). Reporting a single "read-only" sends people to the wrong fix.
   */
  const readOnlyReason = !session.writable
    ? 'You are signed in without script-edit permission, so the editor is read-only.'
    : tree && !tree.mutable
      ? `Project "${tree.project}" is not mutable on this gateway, so the editor is read-only.`
      : '';
  const readOnly = readOnlyReason.length > 0;

  useEffect(() => {
    let cancelled = false;
    fetchProjects()
      .then((list) => {
        if (cancelled) return;
        setProjects(list);
        // Prefer a project that can actually be written to; falling back to the
        // first one still shows something useful in read-only mode.
        const preferred = list.find((p) => p.mutable) ?? list[0];
        if (preferred) setProject(preferred.name);
      })
      .catch((e: unknown) => {
        if (!cancelled) setTreeError(describe(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!project) return;
    let cancelled = false;
    setTree(null);
    setTreeError('');
    fetchScriptTree(project)
      .then((next) => {
        if (!cancelled) setTree(next);
      })
      .catch((e: unknown) => {
        if (!cancelled) setTreeError(describe(e));
      });
    return () => {
      cancelled = true;
    };
  }, [project]);

  const openScript = useCallback(
    async (entry: ScriptEntry) => {
      const uri = docUri(project, entry.path);
      if (docsRef.current.some((d) => d.uri === uri)) {
        setActiveUri(uri);
        return;
      }
      try {
        const content = await readScriptContent(project, entry.path, entry.scriptKey);
        setDocs((current) =>
          current.some((d) => d.uri === uri)
            ? current
            : [...current, newDoc(entry, project, content.text, content.etag)]
        );
        setActiveUri(uri);
        setNotice(null);
      } catch (e: unknown) {
        setNotice({ kind: 'error', text: `Could not open ${entry.path}: ${describe(e)}` });
        return;
      }
      // Attributes are a second request and a second concern: a script whose
      // body opened fine is still usable if its settings could not be read.
      try {
        const read = await readScriptAttributes(project, entry.path);
        setAttrs((current) => ({
          ...current,
          [uri]: { editable: read.editable, attributes: read.attributes, base: read.attributes },
        }));
      } catch {
        setAttrs((current) => ({ ...current, [uri]: { editable: [], attributes: {}, base: {} } }));
      }
    },
    [project]
  );

  const handleChange = useCallback((uri: string, text: string) => {
    setDocs((current) => current.map((d) => (d.uri === uri ? { ...d, text } : d)));
    setDocRevision((n) => n + 1);
  }, []);

  const closeDoc = useCallback((uri: string) => {
    // Computed from the ref rather than inside a setState updater: an updater
    // must be pure, and React runs it twice under StrictMode.
    const current = docsRef.current;
    const index = current.findIndex((d) => d.uri === uri);
    if (index < 0) return;
    const next = current.filter((d) => d.uri !== uri);
    setDocs(next);
    // Closing the active tab moves to its right-hand neighbour, or its left one
    // if it was last — the same rule every editor uses.
    setActiveUri((active) =>
      active === uri ? (next[index] ?? next[index - 1])?.uri ?? null : active
    );
    setAttrs((attributes) => {
      const remaining = { ...attributes };
      delete remaining[uri];
      return remaining;
    });
  }, []);

  /** Apply a successful write: base text and signature move together. */
  const commitSaved = useCallback((uri: string, saved: string, signature: string | undefined) => {
    setDocs((current) =>
      current.map((d) =>
        d.uri === uri
          ? {
              ...d,
              baseText: saved,
              // A save that returns no signature leaves the old one in place;
              // the next write then 409s rather than overwriting blindly.
              etag: signature ?? d.etag,
              // A first save against an inherited script created a local
              // override, so the tree badge is now stale for this entry.
              origin: d.origin === 'inherited' ? 'override' : d.origin,
            }
          : d
      )
    );
  }, []);

  /** Read the gateway's current copy and raise the conflict dialog against it. */
  const raiseConflict = useCallback(async (doc: OpenDoc) => {
    try {
      const current = await readScriptContent(doc.project, doc.path, doc.scriptKey);
      setConflict({
        uri: doc.uri,
        label: doc.label,
        mine: doc.text,
        theirs: current.text,
        theirsEtag: current.etag,
      });
    } catch (e: unknown) {
      setNotice({
        kind: 'error',
        text: `This script changed on the gateway, and re-reading it also failed: ${describe(e)}`,
      });
    }
  }, []);

  const saveDoc = useCallback(
    async (uri: string, baseSignature?: string) => {
      const doc = docsRef.current.find((d) => d.uri === uri);
      if (!doc || readOnly) return;
      setSaving(true);
      setNotice(null);
      // Capture the text being written: the user can keep typing during the
      // round trip, and baseText must become what the gateway actually stored.
      const source = doc.text;
      try {
        const result = await saveScriptContent({
          project: doc.project,
          path: doc.path,
          source,
          key: doc.scriptKey,
          baseSignature: baseSignature ?? doc.etag,
          csrfToken: session.csrfToken,
        });
        commitSaved(uri, source, result.signature);
        // The server does nothing with didSave today, but it is the notification
        // a future diagnostics pass will hang off, and sending it is free. Note
        // the LSP document URI is NOT this workspace `uri`: documents are keyed
        // `ignition://<project>/<path>` on the wire and `project::path` here.
        lsp.didSave(lspUri(doc.project, doc.path));
        setConflict(null);
        setNotice({ kind: 'info', text: `Saved ${doc.label}.` });
      } catch (e: unknown) {
        if (e instanceof ApiError && e.isConflict) {
          await raiseConflict(doc);
        } else {
          setNotice({ kind: 'error', text: `Could not save ${doc.label}: ${describe(e)}` });
        }
      } finally {
        setSaving(false);
      }
    },
    [commitSaved, lsp, raiseConflict, readOnly, session.csrfToken]
  );

  const resolveReloadTheirs = useCallback(() => {
    if (!conflict) return;
    const { uri, theirs, theirsEtag } = conflict;
    setDocs((current) =>
      current.map((d) => (d.uri === uri ? { ...d, text: theirs, baseText: theirs, etag: theirsEtag } : d))
    );
    setConflict(null);
    setNotice({ kind: 'info', text: 'Reloaded the gateway copy. Your edits were discarded.' });
  }, [conflict]);

  const resolveKeepMine = useCallback(async () => {
    if (!conflict) return;
    const doc = docsRef.current.find((d) => d.uri === conflict.uri);
    if (!doc) return;
    // Re-read rather than reusing the signature captured when the dialog opened:
    // the gateway may have been written again while the user read the diff, and
    // saving against a stale signature just 409s a second time.
    try {
      const current = await readScriptContent(doc.project, doc.path, doc.scriptKey);
      if (current.text !== conflict.theirs) {
        setConflict({ ...conflict, theirs: current.text, theirsEtag: current.etag });
        setNotice({
          kind: 'error',
          text: 'The gateway copy changed again while this dialog was open. Review the new diff.',
        });
        return;
      }
      await saveDoc(conflict.uri, current.etag);
    } catch (e: unknown) {
      setNotice({ kind: 'error', text: `Could not overwrite: ${describe(e)}` });
    }
  }, [conflict, saveDoc]);

  const changeAttribute = useCallback((uri: string, name: string, value: AttributeValue) => {
    setAttrs((current) => {
      const state = current[uri];
      if (!state) return current;
      return { ...current, [uri]: { ...state, attributes: { ...state.attributes, [name]: value } } };
    });
  }, []);

  const saveAttributes = useCallback(
    async (uri: string) => {
      const doc = docsRef.current.find((d) => d.uri === uri);
      const state = attrs[uri];
      if (!doc || !state || readOnly) return;
      setSavingAttrs(true);
      setNotice(null);
      try {
        const result = await saveScriptAttributes({
          project: doc.project,
          path: doc.path,
          attributes: state.attributes,
          // The resource signature is one value covering body AND attributes, so
          // an attribute write uses the document's ETag and updates it in turn.
          baseSignature: doc.etag,
          csrfToken: session.csrfToken,
        });
        setDocs((current) =>
          current.map((d) => (d.uri === uri ? { ...d, etag: result.signature ?? d.etag } : d))
        );
        setAttrs((current) => ({ ...current, [uri]: { ...state, base: state.attributes } }));
        setNotice({ kind: 'info', text: 'Saved settings.' });
      } catch (e: unknown) {
        // A conflict on the settings is not shown in the diff dialog — there is
        // no text to diff. Say what happened and re-read, so the next attempt
        // starts from the gateway's current values.
        setNotice({ kind: 'error', text: `Could not save settings: ${describe(e)}` });
        if (e instanceof ApiError && e.isConflict) {
          try {
            const read = await readScriptAttributes(doc.project, doc.path);
            setAttrs((current) => ({
              ...current,
              [uri]: { editable: read.editable, attributes: read.attributes, base: read.attributes },
            }));
            const content = await readScriptContent(doc.project, doc.path, doc.scriptKey);
            setDocs((current) =>
              current.map((d) => (d.uri === uri ? { ...d, etag: content.etag } : d))
            );
          } catch {
            /* leave the stale values on screen — the notice already says why */
          }
        }
      } finally {
        setSavingAttrs(false);
      }
    },
    [attrs, readOnly, session.csrfToken]
  );

  const activeAttrs = activeUri ? attrs[activeUri] : undefined;
  // The tree entry behind the open tab, for its resource type. Looked up rather
  // than stored on the doc: the tree is re-read after every create and delete,
  // and a copy on the doc would go stale the first time that happened.
  const activeEntry = useMemo(
    () => tree?.scripts.find((entry) => entry.path === activeDoc?.path),
    [tree, activeDoc]
  );
  const attrsDirty = activeAttrs
    ? // Both objects are built from the same server response and only ever have
      // their values replaced, so key order is stable and a JSON compare is a
      // sound equality test here.
      JSON.stringify(activeAttrs.attributes) !== JSON.stringify(activeAttrs.base)
    : false;

  // ---- create ----------------------------------------------------------

  const doCreate = useCallback(
    async (name: string) => {
      setCreateBusy(true);
      setCreateError(null);
      const path = `ignition/script-python/${name}`;
      try {
        await createScript({ project, path, csrfToken: session.csrfToken });
        setCreating(false);
        // Re-read the tree rather than splicing the new entry in: the server
        // decides the signature and the data key, and inventing either here
        // would give the first save a base it never agreed to.
        const refreshed = await fetchScriptTree(project);
        setTree(refreshed);
        const entry = refreshed.scripts.find((candidate) => candidate.path === path);
        if (entry) {
          await openScript(entry);
        }
        setNotice({ kind: 'info', text: `Created ${name}.` });
      } catch (e) {
        setCreateError(describe(e));
      } finally {
        setCreateBusy(false);
      }
    },
    [openScript, project, session.csrfToken]
  );

  // ---- delete ----------------------------------------------------------

  const doDelete = useCallback(async () => {
    const entry = pendingDelete;
    if (!entry) return;
    setDeleteBusy(true);
    try {
      await deleteScript({
        project,
        path: entry.path,
        baseSignature: entry.signature,
        csrfToken: session.csrfToken,
      });
      setPendingDelete(null);
      // Close the tab too — leaving an editor open on a resource that no longer
      // exists means the next Ctrl+S recreates it, silently undoing the delete.
      closeDoc(docUri(project, entry.path));
      setTree(await fetchScriptTree(project));
      setNotice({ kind: 'info', text: `Deleted ${entry.name || entry.typeLabel}.` });
    } catch (e) {
      const message =
        e instanceof ApiError && e.isConflict
          ? 'That script changed on the gateway since this list was loaded. '
            + 'Nothing was deleted — reopen it to see the current version.'
          : describe(e);
      setNotice({ kind: 'error', text: message });
      setPendingDelete(null);
    } finally {
      setDeleteBusy(false);
    }
  }, [closeDoc, pendingDelete, project, session.csrfToken]);

  // ---- navigation ------------------------------------------------------

  /** Move the caret in the active editor to a zero-based line. */
  const jumpToLine = useCallback((line: number, character: number) => {
    // The editor owns its CodeMirror views, so the jump is published as a DOM
    // event on the document rather than plumbed through five components. The
    // editor listens for it and moves the view that has the matching URI.
    window.dispatchEvent(
      new CustomEvent('scriptide:reveal', { detail: { line, character } })
    );
  }, []);

  const openConsole = useCallback(() => {
    setConsoleMode((current) => (current === 'hidden' ? 'split' : current));
  }, []);

  /** Open the console in its own browser tab, on the current project. */
  const popOutConsole = useCallback(() => {
    const url = `${window.location.pathname}?view=console&project=${encodeURIComponent(project)}`;
    const handle = window.open(url, '_blank');
    if (handle) {
      try {
        handle.opener = null;
      } catch {
        /* same-origin, so this is hygiene rather than an exposure */
      }
      // Popped out means popped out — leaving a second console in this tab
      // would give two REPLs that look alike and do not share locals.
      setConsoleMode('hidden');
    } else {
      setNotice({
        kind: 'error',
        text: 'The browser blocked the pop-out. Allow popups for this gateway, '
          + 'or keep using the console in this tab.',
      });
    }
  }, [project]);

  return (
    <main className="workspace">
      <div className="workspace-toolbar">
        <label className="workspace-project">
          <span className="config-label">Project</span>
          <select
            value={project}
            onChange={(e) => setProject(e.target.value)}
            disabled={projects.length === 0}
          >
            {projects.length === 0 && <option value="">No projects</option>}
            {projects.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name}
                {p.mutable ? '' : ' (read-only)'}
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          className="button"
          onClick={() => activeUri && void saveDoc(activeUri)}
          disabled={!activeDoc || readOnly || saving || !isDirty(activeDoc)}
        >
          {saving ? 'Saving…' : 'Save script'}
        </button>

        <span className="workspace-toolbar-gap" />

        <button
          type="button"
          className="button"
          aria-pressed={consoleMode !== 'hidden'}
          onClick={() =>
            setConsoleMode((current) => (current === 'hidden' ? 'split' : 'hidden'))
          }
        >
          Console
        </button>
        <button
          type="button"
          className="button"
          aria-pressed={outlineOpen}
          onClick={() => setOutlineOpen((open) => !open)}
        >
          Outline
        </button>

        {readOnly && (
          <span className="workspace-readonly" role="status">
            {readOnlyReason}
          </span>
        )}
        {notice && (
          <span className={`workspace-notice is-${notice.kind}`} role="status">
            {notice.text}
          </span>
        )}
      </div>

      <div className="workspace-body">
        {/* The rail is a column, not just the tree: the tree scrolls inside it
            and the footer stays pinned to the bottom edge, so a project with
            eight scripts no longer leaves half the rail as bare background. */}
        <div className="workspace-rail">
          {tree ? (
            <FileTree
              scripts={tree.scripts}
              selectedPath={activeDoc?.path ?? null}
              onSelect={(entry) => void openScript(entry)}
              consoleSelected={consoleMode !== 'hidden'}
              onSelectSpecial={openConsole}
              // Create and delete are offered only when the session can actually
              // perform them. A visible button that always 403s teaches people
              // the tool is broken rather than that they lack a role.
              onCreate={readOnly ? undefined : () => { setCreateError(null); setCreating(true); }}
              onDelete={readOnly ? undefined : (entry) => setPendingDelete(entry)}
            />
          ) : (
            <nav className="file-tree" aria-label="Scripts">
              <p className="file-tree-empty muted">
                {treeError ? treeError : 'Loading scripts…'}
              </p>
            </nav>
          )}
          <StatusFooter scripts={tree?.scripts ?? []} transport={transport} />
        </div>

        {/* The editor half is ALWAYS mounted, even when the console is full
            width — it owns every CodeMirror instance, and unmounting it would
            destroy the undo history and scroll position of every open tab. It
            is hidden with a class instead. */}
        <div className={`workspace-panes pane-mode-${consoleMode}`}>
          <section className="workspace-editor">
            <TabStrip
              docs={docs}
              activeUri={activeUri}
              onSelect={setActiveUri}
              onClose={closeDoc}
            />
            {activeUri && activeAttrs && (
              <ConfigStrip
                editable={activeAttrs.editable}
                attributes={activeAttrs.attributes}
                onChange={(name, value) => changeAttribute(activeUri, name, value)}
                onSave={() => void saveAttributes(activeUri)}
                dirty={attrsDirty}
                readOnly={readOnly}
                saving={savingAttrs}
                typeId={activeEntry?.typeId}
                unconfigurableReason={
                  activeEntry?.typeId === 'tag-change'
                    ? 'Tag Change settings are not editable here yet — the Designer\'s tag-path '
                      + 'list has not been measured, and writing a guessed key would put a value '
                      + 'on the gateway that the Designer never reads. Configure it in the '
                      + 'Designer; the script body is fully editable here.'
                    : undefined
                }
              />
            )}
            {docs.length === 0 && (
              <p className="code-editor-empty">Choose a script on the left to start editing.</p>
            )}
            <CodeEditor
              docs={docs}
              activeUri={activeUri}
              readOnly={readOnly}
              onChange={handleChange}
              onSave={(uri) => void saveDoc(uri)}
              lsp={lsp}
            />
          </section>

          {consoleMode !== 'hidden' && (
            <section className="workspace-console-pane">
              <div className="pane-head">
                <span className="pane-title">Script Console</span>
                <span className="console-spacer" />
                <button
                  type="button"
                  aria-pressed={consoleMode === 'split'}
                  onClick={() => setConsoleMode('split')}
                  title="Side by side with the editor"
                >
                  Split
                </button>
                <button
                  type="button"
                  aria-pressed={consoleMode === 'full'}
                  onClick={() => setConsoleMode('full')}
                  title="Fill the editing area"
                >
                  Full
                </button>
                <button type="button" onClick={popOutConsole} title="Open in a new browser tab">
                  Pop out
                </button>
                <button type="button" onClick={() => setConsoleMode('hidden')} aria-label="Close console">
                  ×
                </button>
              </div>
              {/* Keyed on the project so switching projects gives a fresh console
                  rather than one whose locals belong to the old project. */}
              <ScriptConsole
                key={project}
                project={project}
                csrfToken={session.csrfToken}
                canExecute={session.canExecute !== false && !readOnly}
                onOpenFrame={(path, line) => {
                  const entry = tree?.scripts.find((candidate) => candidate.path === path);
                  if (entry) {
                    void openScript(entry).then(() => jumpToLine(line - 1, 0));
                  }
                }}
              />
            </section>
          )}
        </div>

        {outlineOpen && (
          <OutlinePanel
            uri={activeUri ? lspUri(activeDoc?.project ?? project, activeDoc?.path ?? '') : null}
            revision={docRevision}
            lsp={lsp}
            onJump={jumpToLine}
          />
        )}
      </div>

      {creating && (
        <NewScriptDialog
          existingNames={
            tree?.scripts
              .filter((entry) => entry.typeId === 'script-python')
              .map((entry) => entry.name) ?? []
          }
          busy={createBusy}
          error={createError}
          onCreate={(name) => void doCreate(name)}
          onCancel={() => setCreating(false)}
        />
      )}

      {pendingDelete && (
        <div className="newscript-backdrop" role="presentation">
          <div
            className="newscript-dialog"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="delete-title"
          >
            <h2 id="delete-title">Delete {pendingDelete.name || pendingDelete.typeLabel}?</h2>
            <p className="muted">
              This removes the script from <strong>{project}</strong> on the gateway.
              It cannot be undone from here.
            </p>
            <div className="newscript-actions">
              <button type="button" onClick={() => setPendingDelete(null)} disabled={deleteBusy}>
                Cancel
              </button>
              <button type="button" className="danger" onClick={() => void doDelete()} disabled={deleteBusy}>
                {deleteBusy ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {conflict && (
        <ConflictDialog
          label={conflict.label}
          mine={conflict.mine}
          theirs={conflict.theirs}
          busy={saving}
          onReloadTheirs={resolveReloadTheirs}
          onKeepMine={() => void resolveKeepMine()}
          onCancel={() => setConflict(null)}
        />
      )}
    </main>
  );
}

/** Human-readable text for anything thrown by the client. */
function describe(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  return e instanceof Error ? e.message : String(e);
}
