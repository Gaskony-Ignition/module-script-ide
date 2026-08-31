/**
 * The open-document model.
 *
 * One document is one script body the user has opened. `baseText` is what the
 * gateway last agreed to (the last read, or the last successful save) and `text`
 * is what the editor holds, so `dirty` is a derivation rather than a flag that
 * can drift out of step with the buffer.
 */
import type { ScriptEntry, ScriptOrigin } from '../api/scripts';

export interface OpenDoc {
  /** Stable key: project + resource path. A script is per-project, not global. */
  uri: string;
  project: string;
  path: string;
  /** The `.py` data key to write back to — the resource's own, from the listing. */
  scriptKey: string;
  typeLabel: string;
  /** Short name for the tab strip. */
  label: string;
  origin: ScriptOrigin;
  /** Resource signature this edit is based on; the If-Match for the next save. */
  etag: string;
  /** The text as last agreed with the gateway. */
  baseText: string;
  /** The text in the editor right now. */
  text: string;
}

/**
 * Documents are keyed by project AND path: the same `ignition/startup` exists in
 * every project, and keying on the path alone would silently alias them.
 */
export function docUri(project: string, path: string): string {
  return `${project}::${path}`;
}

/** True when the buffer differs from what the gateway last agreed to. */
export function isDirty(doc: OpenDoc): boolean {
  return doc.text !== doc.baseText;
}

/**
 * Tab label. A singleton (startup/shutdown/update) has an empty name, so its
 * type label is the only thing that identifies it.
 */
export function labelFor(entry: ScriptEntry): string {
  return entry.name && entry.name.length > 0 ? entry.name : entry.typeLabel;
}

/** Build a document from a tree entry and the body just read for it. */
export function newDoc(entry: ScriptEntry, project: string, text: string, etag: string): OpenDoc {
  return {
    uri: docUri(project, entry.path),
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
  };
}
