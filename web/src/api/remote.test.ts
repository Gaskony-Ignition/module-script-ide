import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from './scripts';
import {
  fetchDrift, fetchRemoteGateways, fetchRemoteProjects, readRemoteContent,
} from './remote';
import { apiUrl } from './urls';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function calledUrl(index = 0): string {
  return String(fetchMock.mock.calls[index][0]);
}

describe('remote client urls', () => {
  // The rule that cost 1.15.0 a broken release with 588 tests green: a mocked
  // fetch accepts any string, so a bare `/api/...` passes every unit test and
  // 404s on every real gateway, where the SPA is served from /data/scriptide/.
  // These assert the RESOLVED url, not that fetch was called.
  it('resolves every route through apiUrl', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ gateways: [], acceptsInbound: false }));
    await fetchRemoteGateways();
    expect(calledUrl()).toBe(apiUrl('/api/remote/gateways'));
  });

  it('resolves the drift route through apiUrl', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ rows: [] }));
    await fetchDrift('prod', 'MyProject');
    expect(calledUrl().startsWith(apiUrl('/api/remote/drift'))).toBe(true);
  });

  it('resolves the content route through apiUrl', async () => {
    fetchMock.mockResolvedValue(new Response('print 1', { status: 200 }));
    await readRemoteContent('prod', 'MyProject', 'ignition/script-python/util', 'code.py');
    expect(calledUrl().startsWith(apiUrl('/api/remote/content'))).toBe(true);
  });
});

describe('fetchDrift', () => {
  it('sends the gateway NAME, never a url', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ rows: [] }));
    await fetchDrift('prod', 'MyProject');
    const url = new URL(calledUrl(), 'http://gw');
    expect(url.searchParams.get('gateway')).toBe('prod');
    expect(calledUrl()).not.toContain('http');
  });

  // The server defaults it the same way. Sending it anyway would put a
  // redundant parameter on every request and make the two behaviours drift.
  it('omits remoteProject when it matches the local one', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ rows: [] }));
    await fetchDrift('prod', 'MyProject', 'MyProject');
    expect(calledUrl()).not.toContain('remoteProject');
  });

  it('sends remoteProject when the names differ', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ rows: [] }));
    await fetchDrift('prod', 'Dev', 'Prod');
    const url = new URL(calledUrl(), 'http://gw');
    expect(url.searchParams.get('remoteProject')).toBe('Prod');
  });

  it('defaults rows to an empty array so a caller never maps over undefined', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ total: 0, differing: 0 }));
    const report = await fetchDrift('prod', 'MyProject');
    expect(report.rows).toEqual([]);
  });

  it('raises an ApiError carrying the gateway status', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ error: 'no such gateway' }, 404));
    await expect(fetchDrift('nope', 'MyProject')).rejects.toBeInstanceOf(ApiError);
  });
});

describe('fetchRemoteGateways', () => {
  it('never expects a token field, because the server never sends one', async () => {
    fetchMock.mockResolvedValue(jsonResponse({
      gateways: [{ name: 'prod', label: 'Production', url: 'https://p:8043', configured: true }],
      acceptsInbound: true,
      configKey: 'com.gaskony.scriptide.remote',
    }));
    const body = await fetchRemoteGateways();
    expect(body.gateways[0]).not.toHaveProperty('token');
    expect(body.acceptsInbound).toBe(true);
  });

  it('survives a response with no gateways array at all', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ acceptsInbound: false }));
    const body = await fetchRemoteGateways();
    expect(body.gateways).toEqual([]);
  });
});

describe('fetchRemoteProjects', () => {
  it('flattens the peer project list to names', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ projects: [{ name: 'A' }, { name: 'B' }] }));
    expect(await fetchRemoteProjects('prod')).toEqual(['A', 'B']);
  });
});

describe('readRemoteContent', () => {
  it('asks for text/plain, because a script body is source and not JSON', async () => {
    fetchMock.mockResolvedValue(new Response('print 1', { status: 200 }));
    await readRemoteContent('prod', 'P', 'ignition/startup');
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>).Accept).toBe('text/plain');
  });

  it('passes the data key when there is one', async () => {
    fetchMock.mockResolvedValue(new Response('x', { status: 200 }));
    await readRemoteContent('prod', 'P', 'com.inductiveautomation.webdev/resources/api', 'doGet.py');
    const url = new URL(calledUrl(), 'http://gw');
    expect(url.searchParams.get('key')).toBe('doGet.py');
  });

  it('omits the key when the caller has none', async () => {
    fetchMock.mockResolvedValue(new Response('x', { status: 200 }));
    await readRemoteContent('prod', 'P', 'ignition/startup');
    expect(calledUrl()).not.toContain('key=');
  });
});
