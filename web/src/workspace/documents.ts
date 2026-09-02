/**
 * The open-document model.
 *
 * One document is one script body the user has opened. `baseText` is what the
 * gateway last agreed to (the last read, or the last successful save) and `text`
 * is what the editor holds, so `dirty` is a derivation rather than a flag that
 * can drift out of step with the buffer.
 */
import type { ScriptEntry, ScriptOrigin } from '../api/scripts';

/**
 * Where a DOCUMENT comes from — a superset of {@link ScriptOrigin}.
 *
 * `'new'` has no equivalent on the server: it means this buffer was opened
 * without ever reading a resource, because none exists yet. Clicking an absent
 * Startup/Shutdown/Update row is the only way to reach it — see {@link
 * newUnsavedDoc}. The resource is created on the FIRST save, exactly like the
 * "New script…" dialog's own create, and {@link OpenDoc.origin} moves to
 * `'local'` the moment that succeeds (see `commitSaved` in Workspace.tsx).
 */
export type DocOrigin = ScriptOrigin | 'new';

export interface OpenDoc {
  /** Stable key: project + resource path. A script is per-project, not global. */
  uri: string;
  project: string;
  path: string;
  /**
   * The `.py` data key to write back to — the resource's own, from the listing.
   * Part of the document's identity: see docUri.
   */
  scriptKey: string;
  typeLabel: string;
  /** Short name for the tab strip. */
  label: string;
  origin: DocOrigin;
  /** Resource signature this edit is based on; the If-Match for the next save. */
  etag: string;
  /** The text as last agreed with the gateway. */
  baseText: string;
  /** The text in the editor right now. */
  text: string;
  /**
   * The user has explicitly overridden this inherited script in this tab.
   *
   * Meaningless on a local or already-overridden script; the ONLY thing it does
   * is unlock an `inherited` document. See {@link isLockedByInheritance}.
   */
  overridden: boolean;
}

/**
 * True when this document must not be edited because it is inherited from a
 * parent project and the user has not asked to override it.
 *
 * **Measured off the real Designer (8.3.8, 01/09/2026), not inferred.** An
 * inherited Project Library script there cannot be opened by double-clicking at
 * all: the context menu offers `Override Resource`, `Copy Path` and
 * `Open read-only`, and the last of those opens an editor headed
 * `Chart  (Read-Only)` whose buffer discards every keystroke. Only after
 * `Override Resource` does the header lose the suffix and the buffer accept
 * typing.
 *
 * This module opened inherited scripts straight into a writable buffer until
 * 1.4.0 and created the override silently on the first save — the opposite of
 * the Designer's "you must ask for it" model, and a way to fork a parent's
 * script by leaning on the keyboard.
 */
export function isLockedByInheritance(doc: OpenDoc): boolean {
  return doc.origin === 'inherited' && !doc.overridden;
}

/**
 * Documents are keyed by project, path AND data key.
 *
 * Project, because the same `ignition/startup` exists in every project and
 * keying on the path alone would silently alias them.
 *
 * The DATA KEY, because a Web Dev endpoint is one resource path holding up to
 * eight scripts — `doGet.py`, `doPost.py` and so on. Without it, opening doPost
 * on an endpoint whose doGet is already open finds the existing tab, shows the
 * WRONG script, and the next save writes doGet's buffer over doPost. Every other
 * resource has exactly one script, so its key never varies and the third segment
 * is stable for them.
 */
export function docUri(project: string, path: string, scriptKey?: string): string {
  return scriptKey ? `${project}::${path}::${scriptKey}` : `${project}::${path}`;
}

/**
 * True when the buffer differs from what the gateway last agreed to.
 *
 * A `'new'` document is ALWAYS dirty, even with an empty buffer: nothing has
 * been agreed with the gateway at all — there is no resource yet for
 * `baseText` to be "the last read of" — so text-equality would say "clean" for
 * a document that, if closed right now, discards a script nobody has created.
 */
export function isDirty(doc: OpenDoc): boolean {
  return doc.origin === 'new' || doc.text !== doc.baseText;
}

/**
 * Tab label. A singleton (startup/shutdown/update) has an empty name, so its
 * type label is the only thing that identifies it.
 */
export function labelFor(entry: ScriptEntry): string {
  // A Web Dev endpoint's tabs must say WHICH handler they are, or eight tabs on
  // one endpoint all read the same.
  if (entry.typeId === 'resources') {
    const method = entry.scriptKey.replace(/\.py$/, '');
    return `${entry.name}/${method}`;
  }
  return entry.name && entry.name.length > 0 ? entry.name : entry.typeLabel;
}

/** Build a document from a tree entry and the body just read for it. */
export function newDoc(entry: ScriptEntry, project: string, text: string, etag: string): OpenDoc {
  return {
    uri: docUri(project, entry.path, entry.scriptKey),
    project,
    path: entry.path,
    scriptKey: entry.scriptKey,
    typeLabel: entry.typeLabel,
    label: labelFor(entry),
    origin: entry.origin,
    // The listing's signature is a usable fallback, but the read's ETag is the
    // authority: the listing may have been fetched minutes ago.
    etag: etag || entry.signature,
    baseText: text,
    text,
    // Always false on open, whatever the origin. An override is a gesture, and
    // a document that starts overridden is a document nobody chose to fork.
    overridden: false,
  };
}

/**
 * Open a DRAFT for a singleton that does not exist on the gateway yet.
 *
 * The real Designer creates nothing until the user saves — clicking an absent
 * Startup/Shutdown/Update row there just opens an empty editor. Before 1.5.0
 * this module called `createScript` on the click itself, which meant browsing
 * the tree could add resources (and git diffs) to a live project with no
 * confirmation and no save. This is the fix: an ordinary buffer with no
 * gateway-agreed text and no ETag, `origin: 'new'`, that only becomes a real
 * resource on the first save (through the ordinary create path — see
 * ScriptResourceRouteHandler#write, which takes the create branch whenever the
 * resource does not already exist, base signature or none). Closing the tab
 * without saving discards it; nothing was ever written.
 */
export function newUnsavedDoc(params: {
  project: string;
  path: string;
  scriptKey: string;
  typeLabel: string;
  label: string;
}): OpenDoc {
  return {
    uri: docUri(params.project, params.path, params.scriptKey),
    project: params.project,
    path: params.path,
    scriptKey: params.scriptKey,
    typeLabel: params.typeLabel,
    label: params.label,
    origin: 'new',
    // No ETag: there is nothing on the gateway yet to match against, and the
    // write route does not ask for one on its create branch.
    etag: '',
    baseText: '',
    text: '',
    overridden: false,
  };
}
