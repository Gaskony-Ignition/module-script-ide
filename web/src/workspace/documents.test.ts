import { describe, expect, it } from 'vitest';
import { emptySettings, type NamedQueryEntry, type NamedQuerySettings } from '../api/namedQueries';
import {
  docUri,
  isDirty,
  isLockedByInheritance,
  newQueryDoc,
  settingsEqual,
  type OpenDoc,
} from './documents';

function scriptDoc(overrides: Partial<OpenDoc> = {}): OpenDoc {
  return {
    uri: 'P::ignition/script-python/util/helpers::code.py',
    kind: 'script',
    project: 'P',
    path: 'ignition/script-python/util/helpers',
    scriptKey: 'code.py',
    typeLabel: 'Project Library',
    label: 'helpers',
    origin: 'local',
    etag: 'sig-1',
    baseText: 'x = 1',
    text: 'x = 1',
    overridden: false,
    ...overrides,
  };
}

function queryEntry(overrides: Partial<NamedQueryEntry> = {}): NamedQueryEntry {
  return {
    path: 'Orders/Totals',
    name: 'Totals',
    folder: 'Orders',
    signature: 'sig-1',
    origin: 'local',
    owner: 'P',
    ...overrides,
  };
}

function queryDoc(settings: NamedQuerySettings = emptySettings()): OpenDoc {
  return newQueryDoc({
    entry: queryEntry(),
    project: 'P',
    sql: 'SELECT 1',
    etag: 'sig-2',
    settings,
    databases: ['Postgres_Test'],
    editableSettings: [],
  });
}

describe('isDirty — scripts', () => {
  it('is clean while the buffer matches what the gateway agreed to', () => {
    expect(isDirty(scriptDoc())).toBe(false);
  });

  it('is dirty as soon as the buffer differs', () => {
    expect(isDirty(scriptDoc({ text: 'x = 2' }))).toBe(true);
  });

  it('is ALWAYS dirty for a draft, even with an empty buffer', () => {
    // Nothing has been agreed with the gateway at all, so text-equality would
    // say "clean" for a document that, if closed now, discards a script nobody
    // has created.
    expect(isDirty(scriptDoc({ origin: 'new', text: '', baseText: '' }))).toBe(true);
  });
});

describe('isDirty — named queries', () => {
  it('is clean when neither the SQL nor the settings have been touched', () => {
    expect(isDirty(queryDoc())).toBe(false);
  });

  it('is dirty on a SQL edit, as a script is', () => {
    expect(isDirty({ ...queryDoc(), text: 'SELECT 2' })).toBe(true);
  });

  it('is dirty on a SETTINGS edit with the SQL untouched', () => {
    // The settings are half the resource and are saved by the same Ctrl+S
    // against the same signature. Without this the Save button is disabled over
    // a change the user can see on screen.
    const doc = queryDoc();
    expect(isDirty({ ...doc, settings: { ...doc.settings!, cacheUnit: 'MIN' } })).toBe(true);
  });

  it('is dirty on a parameter added, removed or reordered', () => {
    const doc = queryDoc();
    const withParam: NamedQuerySettings = {
      ...doc.settings!,
      parameters: [{ type: 'Parameter', identifier: 'id', sqlType: 'Int4' }],
    };
    expect(isDirty({ ...doc, settings: withParam })).toBe(true);
    const reordered: NamedQuerySettings = {
      ...withParam,
      parameters: [
        { type: 'Parameter', identifier: 'other', sqlType: 'Int4' },
        { type: 'Parameter', identifier: 'id', sqlType: 'Int4' },
      ],
    };
    expect(isDirty({ ...doc, baseSettings: withParam, settings: reordered })).toBe(true);
  });

  it('is dirty on a security row added, and on one edited', () => {
    // A fresh query already carries ONE empty requirement (measured), so the
    // change to detect is a second row — or a value typed into the first.
    const doc = queryDoc();
    const rows = [{ zone: '', role: '' }, { zone: 'Plant', role: '' }];
    expect(isDirty({ ...doc, settings: { ...doc.settings!, permissions: rows } })).toBe(true);
    expect(
      isDirty({ ...doc, settings: { ...doc.settings!, permissions: [{ zone: 'Z', role: '' }] } })
    ).toBe(true);
  });

  it('is ALWAYS dirty while it is legacy, because saving is the repair', () => {
    // The gateway holds a resource it cannot read; the form shows the
    // platform's defaults rather than this query's values. Text-equality would
    // call that clean and disable the one control that fixes it.
    const doc = newQueryDoc({
      entry: queryEntry(),
      project: 'P',
      sql: 'SELECT 1',
      etag: 's',
      settings: emptySettings(),
      legacy: true,
    });
    expect(isDirty(doc)).toBe(true);
    expect(isDirty({ ...doc, legacy: false })).toBe(false);
  });

  it('never calls a SCRIPT dirty for the settings it does not have', () => {
    expect(isDirty(scriptDoc({ settings: emptySettings() }))).toBe(false);
  });
});

describe('settingsEqual', () => {
  it('compares structurally, so a rebuilt row with the same values is not a change', () => {
    // A JSON.stringify compare is what the script attributes strip can afford,
    // because both of its objects come from one server response and only ever
    // have values replaced. The UI REBUILDS parameter and permission rows, in
    // its own key order, and stringify would then report every read-back
    // document as dirty.
    const parameters = [{ type: 'Parameter' as const, identifier: 'id', sqlType: 'Int4' as const }];
    const a: NamedQuerySettings = { ...emptySettings(), parameters };
    const b: NamedQuerySettings = {
      ...emptySettings(),
      parameters: [{ sqlType: 'Int4', identifier: 'id', type: 'Parameter' }],
    };
    expect(settingsEqual(a, b)).toBe(true);
  });

  it('sees a difference in any field of any row', () => {
    const a: NamedQuerySettings = {
      ...emptySettings(),
      parameters: [{ type: 'Parameter', identifier: 'id', sqlType: 'Int4' }],
    };
    const b: NamedQuerySettings = {
      ...a,
      parameters: [{ type: 'Parameter', identifier: 'id', sqlType: 'Int8' }],
    };
    expect(settingsEqual(a, b)).toBe(false);
  });

  it('is false when only one side has settings at all', () => {
    expect(settingsEqual(emptySettings(), undefined)).toBe(false);
    expect(settingsEqual(undefined, undefined)).toBe(true);
  });
});

describe('newQueryDoc', () => {
  it('keys the document on the project, the path and the resource\u2019s data key', () => {
    // `query.sql` is a real data key — the content route reads it rather than
    // NamedQuery.getQuery(), which is what lets a legacy resource still open.
    // Keeping it in the URI also makes a collision with a script impossible.
    const doc = queryDoc();
    expect(doc.uri).toBe(docUri('P', 'Orders/Totals', 'query.sql'));
    expect(doc.scriptKey).toBe('query.sql');
  });

  it('carries the legacy flag through to the editor', () => {
    const doc = newQueryDoc({
      entry: queryEntry(),
      project: 'P',
      sql: 'SELECT 1',
      etag: 's',
      settings: emptySettings(),
      legacy: true,
    });
    expect(doc.legacy).toBe(true);
    // Absent means current, not unknown: the editor's notice is driven off it.
    expect(queryDoc().legacy).toBe(false);
  });

  it('starts with the settings as both the edit and the agreed version', () => {
    const doc = queryDoc();
    expect(doc.settings).toEqual(doc.baseSettings);
    expect(isDirty(doc)).toBe(false);
  });

  it('prefers the read ETag over the listing signature, which may be minutes old', () => {
    expect(queryDoc().etag).toBe('sig-2');
    expect(
      newQueryDoc({
        entry: queryEntry(),
        project: 'P',
        sql: '',
        etag: '',
        settings: emptySettings(),
      }).etag
    ).toBe('sig-1');
  });

  it('is locked by inheritance exactly as a script is, until it is overridden', () => {
    const inherited = newQueryDoc({
      entry: queryEntry({ origin: 'inherited', owner: 'Parent' }),
      project: 'P',
      sql: '',
      etag: 'sig',
      settings: emptySettings(),
    });
    expect(isLockedByInheritance(inherited)).toBe(true);
    expect(isLockedByInheritance({ ...inherited, overridden: true })).toBe(false);
  });
});
