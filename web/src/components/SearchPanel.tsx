/**
 * The Search view: project-wide text search, and the results of a references
 * lookup.
 *
 * Both land here rather than in a peek popup because they answer the same
 * question — "where else does this appear?" — and a results list you can leave
 * open while you read the code is more useful than one that closes when you
 * click a result. It is also the view `ActivityBar` said was missing since P4:
 * `scriptide/searchText` has been answered by the gateway since 1.0.0 and had no
 * caller.
 *
 * **References are labelled name-based on screen, every time.** The server
 * matches whole identifiers, not receivers (see `LspClient#references`), so two
 * unrelated `write` methods both appear. A results list that did not say so
 * would be read as a find-references it is not, and the first time someone
 * renamed from it they would break the other one.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { LspClient, TextSearchHit } from '../api/lspClient';
import { labelForLocation } from '../workspace/locations';
import { IconSearch } from './Icons';
import './SearchPanel.css';

/** What the results currently are. */
export type SearchMode = 'text' | 'references';

export interface SearchPanelProps {
  project: string;
  lsp: LspClient | null;
  /**
   * A references request from elsewhere — Shift+F12 in the editor.
   *
   * A counter rides with the name so pressing Shift+F12 twice on the same
   * identifier re-runs the search: the name alone would compare equal and the
   * second press would look like nothing happened.
   */
  referencesRequest: { name: string; nonce: number } | null;
  onOpenLocation: (uri: string, line: number, character: number) => void;
}

/** Results grouped by the file they are in, in the order the server sent them. */
function groupByFile(hits: TextSearchHit[]): Array<{ label: string; hits: TextSearchHit[] }> {
  const groups = new Map<string, { label: string; hits: TextSearchHit[] }>();
  for (const hit of hits) {
    const label = labelForLocation(hit);
    const group = groups.get(hit.uri);
    if (group) {
      group.hits.push(hit);
    } else {
      groups.set(hit.uri, { label, hits: [hit] });
    }
  }
  return [...groups.values()];
}

export default function SearchPanel({
  project, lsp, referencesRequest, onOpenLocation,
}: SearchPanelProps) {
  const [query, setQuery] = useState('');
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [hits, setHits] = useState<TextSearchHit[]>([]);
  const [mode, setMode] = useState<SearchMode>('text');
  /** The name a references list is FOR — shown in the heading. */
  const [subject, setSubject] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  /** Null until a search has actually run, so the empty view is not "no results". */
  const [searched, setSearched] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const runText = useCallback(
    async (term: string, matchCase: boolean) => {
      if (!lsp || !project || term.length === 0) {
        setHits([]);
        setSearched(false);
        return;
      }
      setMode('text');
      setSubject(term);
      setBusy(true);
      setError('');
      try {
        // caseSensitive is passed through the same request the server already
        // reads it from; it is not filtered here, or the result cap would be
        // applied before the case rule and silently lose matches.
        setHits(await lsp.searchText(project, term, matchCase));
      } catch (e: unknown) {
        setHits([]);
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
        setSearched(true);
      }
    },
    [lsp, project]
  );

  // A references request arrives from the editor. It sets the input to the name
  // too, so the box always says what the list below it is about — and so the
  // next Enter re-runs it as an ordinary text search, which is the honest
  // widening when the name-based list missed something.
  useEffect(() => {
    if (!referencesRequest || !lsp || !project) return;
    const { name } = referencesRequest;
    let cancelled = false;
    setQuery(name);
    setMode('references');
    setSubject(name);
    setBusy(true);
    setError('');
    lsp
      .references(project, name)
      .then((found) => {
        if (!cancelled) setHits(found);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setHits([]);
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (cancelled) return;
        setBusy(false);
        setSearched(true);
      });
    return () => {
      cancelled = true;
    };
  }, [lsp, project, referencesRequest]);

  // Changing project invalidates every result: the URIs in them name the old
  // one, and clicking a row would try to open a script from a project the tree
  // is no longer showing.
  useEffect(() => {
    setHits([]);
    setSearched(false);
    setError('');
  }, [project]);

  const groups = useMemo(() => groupByFile(hits), [hits]);

  return (
    <div className="search-panel">
      <form
        className="search-panel-form"
        onSubmit={(event) => {
          event.preventDefault();
          void runText(query, caseSensitive);
        }}
      >
        <div className="search-panel-input">
          <IconSearch size={14} />
          <input
            ref={inputRef}
            type="search"
            value={query}
            spellCheck={false}
            placeholder="Search the project library"
            aria-label="Search the project library"
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <label className="search-panel-case">
          <input
            type="checkbox"
            checked={caseSensitive}
            onChange={(event) => {
              const next = event.target.checked;
              setCaseSensitive(next);
              // Re-run immediately: a toggle that changes the answer but not the
              // list on screen reads as a broken control.
              if (searched && mode === 'text') void runText(query, next);
            }}
          />
          Match case
        </label>
      </form>

      <p className="search-panel-status" role="status">
        {busy
          ? 'Searching…'
          : error
            ? error
            : !searched
              ? 'Searches every Project Library script on the gateway, not just the open ones. '
                + 'Named-query SQL is not searched in this version.'
              : mode === 'references'
                ? `${hits.length} ${hits.length === 1 ? 'place' : 'places'} where “${subject}” `
                  + 'is written — matched by NAME, not by type, so unrelated members '
                  + 'with the same name are included.'
                : `${hits.length} ${hits.length === 1 ? 'result' : 'results'} for “${subject}”. `
                  + 'Named-query SQL is not searched in this version.'}
      </p>

      <div className="search-panel-results">
        {groups.map((group) => (
          <section key={group.label} className="search-panel-group">
            <h3 className="search-panel-file">{group.label}</h3>
            <ul>
              {group.hits.map((hit) => (
                <li key={`${hit.uri}:${hit.line}:${hit.character ?? 0}`}>
                  <button
                    type="button"
                    className="search-panel-hit"
                    onClick={() => onOpenLocation(hit.uri, hit.line, hit.character ?? 0)}
                  >
                    <span className="search-panel-line">{hit.line + 1}</span>
                    {/* The matching line verbatim, INCLUDING its indentation:
                        the shape of the code around a hit is most of what tells
                        you whether it is the one you wanted. */}
                    <span className="search-panel-text">{hit.text}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
