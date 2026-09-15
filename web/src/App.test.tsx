import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';

const WEB_ROOT = resolve(__dirname, '..');

/**
 * The version read from disk, NOT imported the way App.tsx imports it.
 *
 * Importing the same module would compare the app against itself and pass just
 * as happily for a hardcoded string that happened to be current — which is the
 * exact regression this file exists to stop, because a stale label is
 * indistinguishable from a correct one until someone checks a gateway.
 */
const packageVersion = (JSON.parse(readFileSync(resolve(WEB_ROOT, 'package.json'), 'utf8')) as {
  version: string;
}).version;

beforeEach(() => {
  // The header renders before the probe settles, but letting a real fetch go out
  // leaves an unhandled rejection landing in the middle of another test file.
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.reject(new Error('offline in tests')))
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('header version', () => {
  it('shows the version package.json currently carries', async () => {
    render(<App />);

    expect(screen.getByText(`v${packageVersion}`)).toBeInTheDocument();
    // Settle the probe inside the test rather than after it, so the state
    // update happens under act().
    await waitFor(() => expect(screen.getByText(/Cannot reach the Gateway API/)).toBeInTheDocument());
  });

  it('takes it from package.json rather than a literal in the TSX', () => {
    const source = readFileSync(resolve(WEB_ROOT, 'src/App.tsx'), 'utf8');

    expect(source).toMatch(/import \{ version \} from '\.\.\/package\.json'/);
    // Any dotted number in the file would be a second place the version lives,
    // and the two would diverge on the first release that forgot this one.
    expect(source).not.toMatch(/\d+\.\d+\.\d+/);
  });
});
