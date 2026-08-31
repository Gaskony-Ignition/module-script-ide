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
  const attrsDirty = activeAttrs
    ? // Both objects are built from the same server response and only ever have
      // their values replaced, so key order is stable and a JSON compare is a
      // sound equality test here.
      JSON.stringify(activeAttrs.attributes) !== JSON.stringify(activeAttrs.base)
    : false;

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
            />
          )}
          {docs.length === 0 && (
            <p className="code-editor-empty">Choose a script on the left to start editing.</p>
          )}
          {/* Mounted even with no documents: it owns the CodeMirror instances and
              unmounting it would destroy every one of them. */}
          <CodeEditor
            docs={docs}
            activeUri={activeUri}
            readOnly={readOnly}
            onChange={handleChange}
            onSave={(uri) => void saveDoc(uri)}
            lsp={lsp}
          />
        </section>
      </div>

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
