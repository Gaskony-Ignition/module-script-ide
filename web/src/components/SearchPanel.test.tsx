import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { LspClient, TextSearchHit } from '../api/lspClient';
import SearchPanel from './SearchPanel';

function hit(module: string, line: number, text: string, character = 0): TextSearchHit {
  return {
    uri: `ignition://P/ignition/script-python/${module.replace(/\./g, '/')}`,
    module,
    line,
    character,
    text,
  };
}

function fakeLsp(overrides: Partial<Record<'searchText' | 'references', unknown>> = {}) {
  return {
    searchText: vi.fn().mockResolvedValue([]),
    references: vi.fn().mockResolvedValue([]),
    ...overrides,
  } as unknown as LspClient;
}

function renderPanel(overrides: Partial<React.ComponentProps<typeof SearchPanel>> = {}) {
  const props = {
    project: 'P',
    lsp: fakeLsp(),
    referencesRequest: null,
    onOpenLocation: vi.fn(),
    ...overrides,
  };
  const view = render(<SearchPanel {...props} />);
  return { ...props, view };
}

function searchFor(term: string) {
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: term } });
  fireEvent.submit(screen.getByRole('searchbox').closest('form')!);
}

describe('SearchPanel — text search', () => {
  it('says what it searches before anything has been run', () => {
    // "No results" for a search nobody has run is a lie about the project.
    renderPanel();
    expect(screen.getByRole('status')).toHaveTextContent(
      /Searches every Project Library script on the gateway/
    );
  });

  it('searches the gateway and groups results by file', async () => {
    const lsp = fakeLsp({
      searchText: vi.fn().mockResolvedValue([
        hit('util.helpers', 3, '\treturn compute(x)'),
        hit('util.helpers', 9, 'compute = 1'),
        hit('orders.intake', 2, 'from util.helpers import compute'),
      ]),
    });
    renderPanel({ lsp });
    searchFor('compute');
    expect(await screen.findByText('util.helpers')).toBeInTheDocument();
    expect(screen.getByText('orders.intake')).toBeInTheDocument();
    expect(screen.getAllByRole('button')).toHaveLength(3);
  });

  it('shows one-based line numbers against zero-based server lines', async () => {
    const lsp = fakeLsp({ searchText: vi.fn().mockResolvedValue([hit('util', 0, 'compute()')]) });
    renderPanel({ lsp });
    searchFor('compute');
    expect(await screen.findByText('1')).toBeInTheDocument();
  });

  it('opens a hit at its own line and column', async () => {
    const lsp = fakeLsp({
      searchText: vi.fn().mockResolvedValue([hit('util', 12, '\tcompute()', 4)]),
    });
    const props = renderPanel({ lsp });
    searchFor('compute');
    fireEvent.click(await screen.findByRole('button'));
    expect(props.onOpenLocation).toHaveBeenCalledWith(
      'ignition://P/ignition/script-python/util',
      12,
      4
    );
  });

  it('sends the case setting through, and re-runs when it is toggled', async () => {
    const searchText = vi.fn().mockResolvedValue([]);
    renderPanel({ lsp: fakeLsp({ searchText }) });
    searchFor('Compute');
    await waitFor(() => expect(searchText).toHaveBeenCalledWith('P', 'Compute', false));
    fireEvent.click(screen.getByLabelText('Match case'));
    // A toggle that changes the answer but not the list on screen reads as a
    // broken control, so the search re-runs immediately.
    await waitFor(() => expect(searchText).toHaveBeenCalledWith('P', 'Compute', true));
  });

  it('reports a failed search rather than showing an empty list', async () => {
    const lsp = fakeLsp({ searchText: vi.fn().mockRejectedValue(new Error('socket closed')) });
    renderPanel({ lsp });
    searchFor('compute');
    expect(await screen.findByText('socket closed')).toBeInTheDocument();
  });

  it('clears results when the project changes', async () => {
    // The URIs in them name the old project, so clicking one would try to open a
    // script the tree is no longer showing.
    const lsp = fakeLsp({ searchText: vi.fn().mockResolvedValue([hit('util', 1, 'compute()')]) });
    const { view, onOpenLocation } = renderPanel({ lsp });
    searchFor('compute');
    await screen.findByText('util');
    view.rerender(
      <SearchPanel project="Q" lsp={lsp} referencesRequest={null} onOpenLocation={onOpenLocation} />
    );
    expect(screen.queryByText('util')).not.toBeInTheDocument();
  });
});

describe('SearchPanel — references', () => {
  const request = { name: 'compute', nonce: 1 };

  it('runs a references lookup when one is requested from the editor', async () => {
    const references = vi.fn().mockResolvedValue([hit('util', 3, '\treturn compute(x)')]);
    renderPanel({ lsp: fakeLsp({ references }), referencesRequest: request });
    await waitFor(() => expect(references).toHaveBeenCalledWith('P', 'compute'));
    expect(await screen.findByText('util')).toBeInTheDocument();
  });

  it('says the results are matched by NAME, every time', async () => {
    // The server matches whole identifiers, not receivers, so two unrelated
    // `write` methods both appear. A list that did not say so would be read as a
    // find-references it is not, and the first rename from it breaks the other.
    const references = vi.fn().mockResolvedValue([hit('util', 3, 'compute()')]);
    renderPanel({ lsp: fakeLsp({ references }), referencesRequest: request });
    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent(/matched by NAME, not by type/)
    );
  });

  it('names the identifier the list is about', async () => {
    const references = vi.fn().mockResolvedValue([hit('util', 3, 'compute()')]);
    renderPanel({ lsp: fakeLsp({ references }), referencesRequest: request });
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(/compute/));
    // …and puts it in the box, so the next Enter widens it to a text search.
    expect(screen.getByRole('searchbox')).toHaveValue('compute');
  });

  it('re-runs when the same name is requested again', async () => {
    // The nonce is what makes a second Shift+F12 on the same identifier do
    // something: the name alone compares equal and the effect would not re-run.
    const references = vi.fn().mockResolvedValue([]);
    const { view, onOpenLocation } = renderPanel({
      lsp: fakeLsp({ references }),
      referencesRequest: request,
    });
    await waitFor(() => expect(references).toHaveBeenCalledTimes(1));
    const lsp = fakeLsp({ references });
    view.rerender(
      <SearchPanel
        project="P"
        lsp={lsp}
        referencesRequest={{ name: 'compute', nonce: 2 }}
        onOpenLocation={onOpenLocation}
      />
    );
    await waitFor(() => expect(references).toHaveBeenCalledTimes(2));
  });

  it('counts one result in the singular', async () => {
    const references = vi.fn().mockResolvedValue([hit('util', 3, 'compute()')]);
    renderPanel({ lsp: fakeLsp({ references }), referencesRequest: request });
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(/^1 place /));
  });
});
