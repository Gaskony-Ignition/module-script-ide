import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { DriftReport, RemoteGateways } from '../api/remote';

vi.mock('../api/remote', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/remote')>()),
  fetchRemoteGateways: vi.fn(),
  fetchDrift: vi.fn(),
}));

import { fetchDrift, fetchRemoteGateways } from '../api/remote';
import RemotePanel from './RemotePanel';

const PEER = { name: 'prod', label: 'Production', url: 'https://prod:8043', configured: true };

function listing(overrides: Partial<RemoteGateways> = {}): RemoteGateways {
  return {
    gateways: [PEER],
    acceptsInbound: true,
    configKey: 'com.gaskony.scriptide.remote',
    ...overrides,
  };
}

function report(overrides: Partial<DriftReport> = {}): DriftReport {
  return {
    gateway: 'prod',
    gatewayLabel: 'Production',
    project: 'MyProject',
    remoteProject: 'MyProject',
    total: 3,
    differing: 1,
    rows: [
      { label: 'util.helpers', path: 'ignition/script-python/util/helpers', key: 'code.py',
        status: 'differs', hereChars: 120, thereChars: 90 },
      { label: 'util.other', path: 'ignition/script-python/util/other', key: 'code.py',
        status: 'same', hereChars: 40, thereChars: 40 },
      { label: 'Hourly', path: 'ignition/timer/Hourly', key: 'code.py',
        status: 'only-here', hereChars: 20, thereChars: -1 },
    ],
    ...overrides,
  };
}

beforeEach(() => {
  vi.mocked(fetchRemoteGateways).mockReset();
  vi.mocked(fetchDrift).mockReset();
});

describe('RemotePanel', () => {
  // The empty state has to be a way FORWARD. A view that says only "none
  // configured" is a dead end, and the reader has no way to guess that the
  // answer is a properties file on the gateway.
  it('shows the property names to set when no peer is configured', async () => {
    vi.mocked(fetchRemoteGateways).mockResolvedValue(listing({ gateways: [] }));
    render(<RemotePanel project="MyProject" onCompare={vi.fn()} />);
    expect(await screen.findByText(/com\.gaskony\.scriptide\.remote\.prod\.url/)).toBeTruthy();
    expect(screen.getByText(/inboundToken/)).toBeTruthy();
  });

  it('says that nothing here can write to another gateway', async () => {
    vi.mocked(fetchRemoteGateways).mockResolvedValue(listing({ gateways: [] }));
    render(<RemotePanel project="MyProject" onCompare={vi.fn()} />);
    expect(await screen.findByText(/nothing here can write to another gateway/i)).toBeTruthy();
  });

  it('preselects the only configured gateway', async () => {
    vi.mocked(fetchRemoteGateways).mockResolvedValue(listing());
    render(<RemotePanel project="MyProject" onCompare={vi.fn()} />);
    const select = await screen.findByLabelText('Gateway to compare with');
    await waitFor(() => expect((select as HTMLSelectElement).value).toBe('prod'));
  });

  // A peer with a url and no token would 401 on every call, and a 401 from
  // another machine reads on screen exactly like a login problem on this one.
  it('disables a peer that has no token configured', async () => {
    vi.mocked(fetchRemoteGateways).mockResolvedValue(listing({
      gateways: [{ ...PEER, configured: false }],
    }));
    render(<RemotePanel project="MyProject" onCompare={vi.fn()} />);
    const option = await screen.findByRole('option', { name: /no token configured/ });
    expect((option as HTMLOptionElement).disabled).toBe(true);
  });

  it('warns when this gateway will not answer a peer', async () => {
    vi.mocked(fetchRemoteGateways).mockResolvedValue(listing({ acceptsInbound: false }));
    render(<RemotePanel project="MyProject" onCompare={vi.fn()} />);
    expect(await screen.findByText(/does not answer remote reads/i)).toBeTruthy();
  });

  it('lists every body, matching ones included', async () => {
    vi.mocked(fetchRemoteGateways).mockResolvedValue(listing());
    vi.mocked(fetchDrift).mockResolvedValue(report());
    render(<RemotePanel project="MyProject" onCompare={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Compare' }));
    // A report showing only the differences cannot be told apart from one that
    // read nothing at all.
    expect(await screen.findByText('util.other')).toBeTruthy();
    expect(screen.getByText('util.helpers')).toBeTruthy();
  });

  it('states the count of differences rather than only listing them', async () => {
    vi.mocked(fetchRemoteGateways).mockResolvedValue(listing());
    vi.mocked(fetchDrift).mockResolvedValue(report());
    render(<RemotePanel project="MyProject" onCompare={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Compare' }));
    expect(await screen.findByText(/1 of 3 differ from Production/)).toBeTruthy();
  });

  it('says so plainly when everything matches', async () => {
    vi.mocked(fetchRemoteGateways).mockResolvedValue(listing());
    vi.mocked(fetchDrift).mockResolvedValue(report({ differing: 0 }));
    render(<RemotePanel project="MyProject" onCompare={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Compare' }));
    expect(await screen.findByText(/All 3 match Production\./)).toBeTruthy();
  });

  // Nothing to put in the second pane, so the gesture the row promises cannot
  // be performed. Disabled rather than absent: the row is still the answer to
  // "is it over there".
  it('disables a row that exists on only one gateway', async () => {
    vi.mocked(fetchRemoteGateways).mockResolvedValue(listing());
    vi.mocked(fetchDrift).mockResolvedValue(report());
    render(<RemotePanel project="MyProject" onCompare={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Compare' }));
    const rows = await screen.findAllByRole('button', { name: /Hourly/ });
    expect((rows[0] as HTMLButtonElement).disabled).toBe(true);
  });

  it('hands the peer, the remote project and the row to onCompare', async () => {
    const onCompare = vi.fn();
    vi.mocked(fetchRemoteGateways).mockResolvedValue(listing());
    vi.mocked(fetchDrift).mockResolvedValue(report({ remoteProject: 'Prod' }));
    render(<RemotePanel project="MyProject" onCompare={onCompare} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Compare' }));
    fireEvent.click(await screen.findByRole('button', { name: /util\.helpers/ }));
    expect(onCompare).toHaveBeenCalledWith(
      PEER, 'Prod',
      expect.objectContaining({ path: 'ignition/script-python/util/helpers', key: 'code.py' })
    );
  });

  it('sends a differently named remote project when one is typed', async () => {
    vi.mocked(fetchRemoteGateways).mockResolvedValue(listing());
    vi.mocked(fetchDrift).mockResolvedValue(report());
    render(<RemotePanel project="Dev" onCompare={vi.fn()} />);
    await screen.findByLabelText('Gateway to compare with');
    fireEvent.change(screen.getByLabelText('Project name on the other gateway'),
      { target: { value: 'Prod' } });
    fireEvent.click(screen.getByRole('button', { name: 'Compare' }));
    await waitFor(() => expect(fetchDrift).toHaveBeenCalledWith('prod', 'Dev', 'Prod'));
  });

  // A report belongs to one (peer, project) pair. Left standing after either
  // changes it would be read as the new pair's answer.
  it('drops the report when the project changes', async () => {
    vi.mocked(fetchRemoteGateways).mockResolvedValue(listing());
    vi.mocked(fetchDrift).mockResolvedValue(report());
    const view = render(<RemotePanel project="MyProject" onCompare={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Compare' }));
    await screen.findByText('util.helpers');
    view.rerender(<RemotePanel project="Other" onCompare={vi.fn()} />);
    await waitFor(() => expect(screen.queryByText('util.helpers')).toBeNull());
  });

  it('reports a failure instead of an empty comparison', async () => {
    vi.mocked(fetchRemoteGateways).mockResolvedValue(listing());
    vi.mocked(fetchDrift).mockImplementation(
      () => Promise.reject(new Error('Could not reach Production'))
    );
    render(<RemotePanel project="MyProject" onCompare={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Compare' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not reach Production');
  });
});
