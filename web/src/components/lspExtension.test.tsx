import { startCompletion } from '@codemirror/autocomplete';
import { EditorView } from '@codemirror/view';
import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LspClient, lspUri, type CompletionItem } from '../api/lspClient';
import { LspTransport } from '../api/lspTransport';
import { FakeSocket } from '../test/fakeSocket';
import type { OpenDoc } from '../workspace/documents';
import CodeEditor from './CodeEditor';
import {
  completionType,
  documentationText,
  isDeprecated,
  markdownToText,
  toCompletions,
} from './lspExtension';

const neverResolves = () => new Promise<CompletionItem>(() => undefined);

describe('LSP kind → CodeMirror completion type', () => {
  // The type string picks the icon and its colour class; an unmapped kind
  // renders a blank gutter beside the label, which reads as a broken popup
  // rather than as a missing mapping.
  it.each([
    [9, 'namespace', 'Module — system, system.tag'],
    [3, 'function', 'Function — readBlocking'],
    [10, 'property', 'Property — a constant on a module'],
    [2, 'method', 'Method'],
    [6, 'variable', 'Variable'],
    [7, 'class', 'Class'],
    [14, 'keyword', 'Keyword'],
  ])('maps kind %i to %s (%s)', (kind, expected) => {
    expect(completionType(kind as number)).toBe(expected);
  });

  it('leaves the type undefined for a kind it does not know', () => {
    expect(completionType(undefined)).toBeUndefined();
    expect(completionType(9999)).toBeUndefined();
  });
});

describe('completion mapping', () => {
  const items: CompletionItem[] = [
    { label: 'tag', kind: 9, data: { dottedPath: 'system.tag' } },
    {
      label: 'readBlocking',
      kind: 3,
      detail: 'readBlocking(tagPaths, [timeout])',
      data: { dottedPath: 'system.tag.readBlocking' },
    },
    { label: 'read', kind: 3, tags: [1], data: { dottedPath: 'system.tag.read' } },
    { label: 'VERSION', kind: 10, data: { dottedPath: 'system.VERSION' } },
  ];

  it('maps every item to a CodeMirror completion with the right type', () => {
    const options = toCompletions(items, neverResolves);
    expect(options.map((option) => [option.label, option.type])).toEqual([
      ['tag', 'namespace'],
      ['readBlocking', 'function'],
      ['read', 'function'],
      ['VERSION', 'property'],
    ]);
  });

  it('keeps the server’s signature as the detail line', () => {
    const [, readBlocking] = toCompletions(items, neverResolves);
    expect(readBlocking?.detail).toBe('readBlocking(tagPaths, [timeout])');
  });

  it('sorts a deprecated item below the rest without hiding it', () => {
    // The gateway really does have these names, so removing them would be a lie;
    // ranking them last is the honest treatment.
    const options = toCompletions(items, neverResolves);
    expect(isDeprecated(items[2] as CompletionItem)).toBe(true);
    expect(options[2]?.boost).toBeLessThan(0);
    expect(options[1]?.boost).toBe(0);
  });

  it('does not fetch documentation until the info panel asks for it', async () => {
    // Documentation is deliberately absent from the completion response, to keep
    // the popup fast. Resolving all hundred items up front would undo exactly
    // that, so resolve must be called per item, on demand.
    const resolve = vi.fn(async (item: CompletionItem) => ({
      ...item,
      documentation: { kind: 'markdown' as const, value: '**Reads** a `tag`.' },
    }));
    const options = toCompletions(items, resolve);
    expect(resolve).not.toHaveBeenCalled();

    const info = await (options[1]?.info as (c: unknown) => Promise<Node | null>)(options[1]);
    expect(resolve).toHaveBeenCalledTimes(1);
    expect(resolve).toHaveBeenCalledWith(items[1]);
    // Rendered as plain text — no markdown library, and nothing goes near
    // innerHTML.
    expect((info as HTMLElement).textContent).toContain('Reads a tag.');
    expect((info as HTMLElement).innerHTML).not.toContain('<b');
  });

  it('still shows the detail line when resolve fails', async () => {
    const options = toCompletions(items, () => Promise.reject(new Error('socket dropped')));
    const info = await (options[1]?.info as (c: unknown) => Promise<Node | null>)(options[1]);
    expect((info as HTMLElement).textContent).toContain('readBlocking(tagPaths, [timeout])');
  });
});

describe('markdown as plain text', () => {
  it('strips the syntax the server sends rather than rendering it', () => {
    const markdown = [
      '```python',
      'readBlocking(tagPaths, [timeout])',
      '```',
      '',
      '**Deprecated.**',
      '',
      'Reads the value of `tagPaths`.',
      '',
      '**Parameters**',
      '',
      '- `tagPaths` *(optional, default `None`)* — the tags to read',
    ].join('\n');
    const text = markdownToText(markdown);
    expect(text).toContain('readBlocking(tagPaths, [timeout])');
    expect(text).toContain('Reads the value of tagPaths.');
    expect(text).toContain('• tagPaths (optional, default None) — the tags to read');
    expect(text).not.toContain('```');
    expect(text).not.toContain('**');
    expect(text).not.toContain('`');
  });

  it('leaves plaintext MarkupContent alone', () => {
    expect(documentationText({ kind: 'plaintext', value: '  a * b  ' })).toBe('a * b');
  });

  it('accepts the bare-string form of documentation', () => {
    expect(documentationText('`plain`')).toBe('plain');
    expect(documentationText(undefined)).toBe('');
  });
});

// ============================ wiring ============================

const SOURCE = 'def compute(values):\n\treturn sum(values)';

function doc(overrides: Partial<OpenDoc> = {}): OpenDoc {
  return {
    uri: 'P::ignition/script-python/util/helpers',
    project: 'P',
    path: 'ignition/script-python/util/helpers',
    scriptKey: 'code.py',
    overridden: false,
    typeLabel: 'Project Library',
    label: 'helpers',
    origin: 'local',
    etag: 'sig-1',
    baseText: SOURCE,
    text: SOURCE,
    ...overrides,
  };
}

describe('CodeEditor with a language client', () => {
  beforeEach(() => {
    FakeSocket.reset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  function client() {
    const transport = new LspTransport({
      url: () => 'ws://gateway.test/system/scriptide',
      createSocket: FakeSocket.factory,
    });
    const lsp = new LspClient(transport);
    transport.connect();
    FakeSocket.latest().open();
    FakeSocket.latest().clear();
    return lsp;
  }

  it('opens the document on the server when a view is created, and closes it with the view', () => {
    const lsp = client();
    const { rerender } = render(
      <CodeEditor
        docs={[doc()]}
        activeUri={doc().uri}
        readOnly={false}
        onChange={vi.fn()}
        onSave={vi.fn()}
        lsp={lsp}
      />
    );
    expect(FakeSocket.latest().methods()).toEqual([
      'initialize',
      'initialized',
      'textDocument/didOpen',
    ]);
    const open = FakeSocket.latest().frames()[2];
    expect(open?.project).toBe('P');
    expect(open?.msg).toMatchObject({
      params: {
        textDocument: { uri: lspUri('P', 'ignition/script-python/util/helpers'), text: SOURCE },
      },
    });

    FakeSocket.latest().clear();
    rerender(
      <CodeEditor
        docs={[]}
        activeUri={null}
        readOnly={false}
        onChange={vi.fn()}
        onSave={vi.fn()}
        lsp={lsp}
      />
    );
    // Closing the tab destroys the view, and the server must forget the file —
    // otherwise its document set drifts from the editor's for the life of the
    // connection.
    expect(FakeSocket.latest().methods()).toEqual(['textDocument/didClose']);
  });

  it('sends an incremental didChange as the user types, and never rewrites the buffer', () => {
    const lsp = client();
    const onChange = vi.fn();
    render(
      <CodeEditor
        docs={[doc()]}
        activeUri={doc().uri}
        readOnly={false}
        onChange={onChange}
        onSave={vi.fn()}
        lsp={lsp}
      />
    );
    FakeSocket.latest().clear();

    const host = document.querySelector<HTMLElement>('.code-editor-host .cm-editor');
    const view = host ? EditorView.findFromDOM(host) : null;
    if (!view) throw new Error('no EditorView mounted');
    view.dispatch({ changes: { from: view.state.doc.length, insert: '\n\t# tail' } });

    const change = FakeSocket.latest().frames()[0];
    expect((change?.msg as { method: string }).method).toBe('textDocument/didChange');
    const params = (change?.msg as { params: { contentChanges: { range?: unknown; text: string }[] } })
      .params;
    expect(params.contentChanges).toHaveLength(1);
    expect(params.contentChanges[0]?.range).toBeDefined();
    expect(params.contentChanges[0]?.text).toBe('\n\t# tail');

    // The byte-fidelity guarantee still holds with the LSP extensions loaded:
    // nothing in them touches the document.
    const [, saved] = onChange.mock.calls[0] as [string, string];
    expect(saved).toBe(SOURCE + '\n\t# tail');
    expect(saved).not.toContain('    ');
  });

  /** The mounted view for the visible document. */
  function activeView(): EditorView {
    const host = document.querySelector<HTMLElement>('.code-editor-host .cm-editor');
    const view = host ? EditorView.findFromDOM(host) : null;
    if (!view) throw new Error('no EditorView mounted');
    return view;
  }

  /** Answer the pending request for `method`, then let the promises settle. */
  async function reply(method: string, result: unknown): Promise<void> {
    const frame = FakeSocket.latest()
      .frames()
      .find((f) => (f.msg as { method?: string }).method === method);
    if (!frame) {
      throw new Error(`no ${method} request was sent; saw ${FakeSocket.latest().methods().join(', ')}`);
    }
    await act(async () => {
      FakeSocket.latest().deliver({
        ch: 'lsp',
        msg: { jsonrpc: '2.0', id: (frame.msg as { id: number }).id, result },
      });
    });
  }

  it('asks the gateway for completions on an explicit request, and shows them', async () => {
    const lsp = client();
    render(
      <CodeEditor
        docs={[doc({ baseText: 'system.', text: 'system.' })]}
        activeUri={doc().uri}
        readOnly={false}
        onChange={vi.fn()}
        onSave={vi.fn()}
        lsp={lsp}
      />
    );
    const view = activeView();
    await act(async () => {
      view.dispatch({ selection: { anchor: view.state.doc.length } });
      FakeSocket.latest().clear();
      startCompletion(view);
      // CodeMirror runs completion sources on a debounce even for an explicit
      // request, so the frame is not on the wire until that fires.
      await new Promise((resolve) => setTimeout(resolve, 100));
    });

    const request = FakeSocket.latest()
      .frames()
      .find((f) => (f.msg as { method?: string }).method === 'textDocument/completion');
    expect(request).toBeDefined();
    // Position is where the cursor is, in LSP's zero-based, UTF-16 coordinates.
    expect((request?.msg as { params: { position: unknown } }).params.position).toEqual({
      line: 0,
      character: 7,
    });

    await reply('textDocument/completion', {
      isIncomplete: false,
      items: [
        { label: 'tag', kind: 9, data: { dottedPath: 'system.tag' } },
        { label: 'db', kind: 9, data: { dottedPath: 'system.db' } },
      ],
    });

    const labels = Array.from(document.querySelectorAll('.cm-completionLabel')).map(
      (node) => node.textContent
    );
    // Exactly the gateway's answer. lang-python's own sources are silenced after
    // a dot: `memoryview` is not a member of `system`, and offering it there
    // reads as the IDE not knowing what `system` is.
    // Sorted, because the popup's ordering is CodeMirror's business — what
    // matters is that the set is exactly the gateway's.
    expect(labels.sort()).toEqual(['db', 'tag']);
  });

  it('still offers Python built-ins and locals for a bare word', async () => {
    const lsp = client();
    render(
      <CodeEditor
        docs={[doc({ baseText: 'mem', text: 'mem' })]}
        activeUri={doc().uri}
        readOnly={false}
        onChange={vi.fn()}
        onSave={vi.fn()}
        lsp={lsp}
      />
    );
    const view = activeView();
    await act(async () => {
      view.dispatch({ selection: { anchor: view.state.doc.length } });
      FakeSocket.latest().clear();
      startCompletion(view);
      await new Promise((resolve) => setTimeout(resolve, 100));
    });
    await reply('textDocument/completion', { isIncomplete: false, items: [] });

    const labels = Array.from(document.querySelectorAll('.cm-completionLabel')).map(
      (node) => node.textContent
    );
    // The gateway's hint tree has no local variables and no Python built-ins, so
    // dropping lang-python's sources outright would lose them for good.
    expect(labels).toContain('memoryview');
  });

  it('asks for signature help when a call is opened, and drops it when the call closes', async () => {
    const lsp = client();
    render(
      <CodeEditor
        docs={[doc({ baseText: 'system.tag.readBlocking', text: 'system.tag.readBlocking' })]}
        activeUri={doc().uri}
        readOnly={false}
        onChange={vi.fn()}
        onSave={vi.fn()}
        lsp={lsp}
      />
    );
    const view = activeView();
    FakeSocket.latest().clear();
    await act(async () => {
      view.dispatch({
        changes: { from: view.state.doc.length, insert: '(' },
        selection: { anchor: view.state.doc.length + 1 },
      });
    });

    await reply('textDocument/signatureHelp', {
      signatures: [
        {
          label: 'readBlocking(tagPaths, [timeout])',
          parameters: [{ label: 'tagPaths' }, { label: '[timeout]' }],
        },
      ],
      activeSignature: 0,
      activeParameter: 0,
    });

    const tooltip = document.querySelector('.cm-lsp-signature');
    expect(tooltip?.textContent).toContain('readBlocking(tagPaths, [timeout])');
    // The parameter the cursor is on is the one emphasised.
    expect(document.querySelector('.cm-lsp-signature-active')?.textContent).toBe('tagPaths');

    await act(async () => {
      view.dispatch({
        changes: { from: view.state.doc.length, insert: ')' },
        selection: { anchor: view.state.doc.length + 1 },
      });
    });
    expect(document.querySelector('.cm-lsp-signature')).toBeNull();
  });

  it('runs with no client at all, so a dead socket is not a dead editor', () => {
    render(
      <CodeEditor
        docs={[doc()]}
        activeUri={doc().uri}
        readOnly={false}
        onChange={vi.fn()}
        onSave={vi.fn()}
        lsp={null}
      />
    );
    expect(document.querySelectorAll('.code-editor-host')).toHaveLength(1);
    expect(FakeSocket.instances).toHaveLength(0);
  });
});
