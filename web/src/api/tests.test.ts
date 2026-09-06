import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, CSRF_HEADER } from './scripts';
import { fetchTests, runTests } from './tests';
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

function calledInit(index = 0): RequestInit {
  return fetchMock.mock.calls[index][1] as RequestInit;
}

describe('test client urls', () => {
  // The resolved url, not merely that fetch was called — see
  // the 1.15.0 note in CLAUDE.md.
  it('resolves the listing route through apiUrl', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ total: 0, modules: [] }));
    await fetchTests('MyProject');
    expect(calledUrl().startsWith(apiUrl('/api/tests'))).toBe(true);
    expect(calledUrl()).toContain('project=MyProject');
  });

  it('resolves the run route through apiUrl', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ results: [] }));
    await runTests('MyProject', undefined, 'tok');
    expect(calledUrl().startsWith(apiUrl('/api/tests/run'))).toBe(true);
  });
});

describe('fetchTests', () => {
  it('defaults modules to an empty array', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ project: 'P', total: 0, convention: 'x' }));
    expect((await fetchTests('P')).modules).toEqual([]);
  });

  it('raises an ApiError rather than returning an empty listing', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ error: 'nope' }, 500));
    await expect(fetchTests('P')).rejects.toBeInstanceOf(ApiError);
  });
});

describe('runTests', () => {
  it('POSTs with the CSRF token, because a run mutates the gateway', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ results: [] }));
    await runTests('P', ['m.test_a'], 'the-token');
    const init = calledInit();
    expect(init.method).toBe('POST');
    expect((init.headers as Record<string, string>)[CSRF_HEADER]).toBe('the-token');
  });

  it('sends an empty id list for "run everything"', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ results: [] }));
    await runTests('P', undefined, 'tok');
    expect(JSON.parse(String(calledInit().body))).toEqual({ ids: [] });
  });

  it('sends exactly the ids it was given', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ results: [] }));
    await runTests('P', ['m.test_a', 'm.Test.test_b'], 'tok');
    expect(JSON.parse(String(calledInit().body)).ids).toEqual(['m.test_a', 'm.Test.test_b']);
  });

  it('defaults results to an empty array', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ passed: 0, failed: 0, errored: 0 }));
    expect((await runTests('P', [], 'tok')).results).toEqual([]);
  });

  it('surfaces a 403 rather than reporting zero tests run', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ error: 'execution disabled' }, 403));
    await expect(runTests('P', [], 'tok')).rejects.toBeInstanceOf(ApiError);
  });
});
