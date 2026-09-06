import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { TestListing, TestRun } from '../api/tests';

vi.mock('../api/tests', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/tests')>()),
  fetchTests: vi.fn(),
  runTests: vi.fn(),
}));

import { fetchTests, runTests } from '../api/tests';
import TestsPanel from './TestsPanel';

const CONVENTION =
  "A test is a top-level def test_* (or a test_* method on a class named Test*) in a module "
  + "whose last name starts with 'test' or that sits under a 'tests' package.";

function listing(overrides: Partial<TestListing> = {}): TestListing {
  return {
    project: 'MyProject',
    total: 2,
    convention: CONVENTION,
    modules: [{
      module: 'orders.test_totals',
      hasSetUp: true,
      hasTearDown: false,
      tests: [
        { id: 'orders.test_totals.test_sums', function: 'test_sums', line: 4 },
        { id: 'orders.test_totals.test_rounds', function: 'test_rounds', line: 9 },
      ],
    }],
    ...overrides,
  };
}

function run(overrides: Partial<TestRun> = {}): TestRun {
  return {
    requested: 2,
    passed: 1,
    failed: 1,
    errored: 0,
    elapsedMs: 42,
    results: [
      { id: 'orders.test_totals.test_sums', module: 'orders.test_totals', function: 'test_sums',
        status: 'pass', message: '', traceback: '', output: '', outputTruncated: false,
        elapsedMs: 3 },
      { id: 'orders.test_totals.test_rounds', module: 'orders.test_totals',
        function: 'test_rounds', status: 'fail', message: 'expected 4, got 5',
        traceback: 'Traceback...\nAssertionError', output: 'about to round\n',
        outputTruncated: false, elapsedMs: 39 },
    ],
    ...overrides,
  };
}

beforeEach(() => {
  vi.mocked(fetchTests).mockReset();
  vi.mocked(runTests).mockReset();
});

describe('TestsPanel', () => {
  // A discovery convention nobody can see reads as a broken feature: the first
  // thing anyone does with an empty test panel is wonder whether it works.
  it('states the discovery rule when the project declares no tests', async () => {
    vi.mocked(fetchTests).mockResolvedValue(listing({ total: 0, modules: [] }));
    render(<TestsPanel project="P" csrfToken="t" canRun onOpenTest={vi.fn()} />);
    expect(await screen.findByText(new RegExp('module whose last name starts'))).toBeTruthy();
  });

  it('lists each module with its tests', async () => {
    vi.mocked(fetchTests).mockResolvedValue(listing());
    render(<TestsPanel project="P" csrfToken="t" canRun onOpenTest={vi.fn()} />);
    expect(await screen.findByText('orders.test_totals')).toBeTruthy();
    expect(screen.getByText('test_sums')).toBeTruthy();
    expect(screen.getByText('test_rounds')).toBeTruthy();
  });

  it('badges a module that brackets its tests with setUp', async () => {
    vi.mocked(fetchTests).mockResolvedValue(listing());
    render(<TestsPanel project="P" csrfToken="t" canRun onOpenTest={vi.fn()} />);
    expect(await screen.findByText('setUp')).toBeTruthy();
    expect(screen.queryByText('tearDown')).toBeNull();
  });

  // A visible Run that always 403s teaches people the tool is broken rather
  // than that they lack a role.
  it('offers no run button to a reader who cannot execute', async () => {
    vi.mocked(fetchTests).mockResolvedValue(listing());
    render(<TestsPanel project="P" csrfToken="t" canRun={false} onOpenTest={vi.fn()} />);
    await screen.findByText('orders.test_totals');
    expect(screen.queryByRole('button', { name: /Run all/ })).toBeNull();
  });

  it('runs everything with no id list', async () => {
    vi.mocked(fetchTests).mockResolvedValue(listing());
    vi.mocked(runTests).mockResolvedValue(run());
    render(<TestsPanel project="P" csrfToken="t" canRun onOpenTest={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: /Run all/ }));
    await waitFor(() => expect(runTests).toHaveBeenCalledWith('P', undefined, 't'));
  });

  it('runs one module with just its ids', async () => {
    vi.mocked(fetchTests).mockResolvedValue(listing());
    vi.mocked(runTests).mockResolvedValue(run());
    render(<TestsPanel project="P" csrfToken="t" canRun onOpenTest={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Run' }));
    await waitFor(() => expect(runTests).toHaveBeenCalledWith(
      'P', ['orders.test_totals.test_sums', 'orders.test_totals.test_rounds'], 't'
    ));
  });

  it('runs one test alone', async () => {
    vi.mocked(fetchTests).mockResolvedValue(listing());
    vi.mocked(runTests).mockResolvedValue(run());
    render(<TestsPanel project="P" csrfToken="t" canRun onOpenTest={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Run orders.test_totals.test_sums' }));
    await waitFor(() => expect(runTests).toHaveBeenCalledWith(
      'P', ['orders.test_totals.test_sums'], 't'
    ));
  });

  it('shows a tally of the three outcomes', async () => {
    vi.mocked(fetchTests).mockResolvedValue(listing());
    vi.mocked(runTests).mockResolvedValue(run({ errored: 2 }));
    render(<TestsPanel project="P" csrfToken="t" canRun onOpenTest={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: /Run all/ }));
    expect(await screen.findByText('1 passed')).toBeTruthy();
    expect(screen.getByText('1 failed')).toBeTruthy();
    expect(screen.getByText('2 errored')).toBeTruthy();
  });

  // An error is a test that never got far enough to have an opinion; calling it
  // "failed" sends the reader to an assertion that never executed.
  it('keeps fail and error distinct in the detail', async () => {
    vi.mocked(fetchTests).mockResolvedValue(listing());
    vi.mocked(runTests).mockResolvedValue(run({
      results: [{
        id: 'orders.test_totals.test_sums', module: 'orders.test_totals', function: 'test_sums',
        status: 'error', message: 'ImportError: no module named nope', traceback: 'tb',
        output: '', outputTruncated: false, elapsedMs: 1,
      }],
    }));
    render(<TestsPanel project="P" csrfToken="t" canRun onOpenTest={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: /Run all/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Why' }));
    expect(await screen.findByText('errored')).toBeTruthy();
    expect(screen.getByText(/ImportError/)).toBeTruthy();
  });

  it('offers no reason toggle on a test that passed', async () => {
    vi.mocked(fetchTests).mockResolvedValue(listing());
    vi.mocked(runTests).mockResolvedValue(run({
      results: [run().results[0]], passed: 1, failed: 0,
    }));
    render(<TestsPanel project="P" csrfToken="t" canRun onOpenTest={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: /Run all/ }));
    await screen.findByText('1 passed');
    expect(screen.queryByRole('button', { name: 'Why' })).toBeNull();
  });

  // What a test printed before it failed is the question a failure always
  // raises, and one interpreter per run means it has to be captured per test.
  it('shows the output a failing test produced', async () => {
    vi.mocked(fetchTests).mockResolvedValue(listing());
    vi.mocked(runTests).mockResolvedValue(run());
    render(<TestsPanel project="P" csrfToken="t" canRun onOpenTest={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: /Run all/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Why' }));
    expect(await screen.findByText(/about to round/)).toBeTruthy();
  });

  it('opens the module at the test definition', async () => {
    const onOpenTest = vi.fn();
    vi.mocked(fetchTests).mockResolvedValue(listing());
    render(<TestsPanel project="P" csrfToken="t" canRun onOpenTest={onOpenTest} />);
    fireEvent.click(await screen.findByText('test_rounds'));
    expect(onOpenTest).toHaveBeenCalledWith('orders.test_totals', 9);
  });

  it('says that a run shares one interpreter', async () => {
    vi.mocked(fetchTests).mockResolvedValue(listing());
    render(<TestsPanel project="P" csrfToken="t" canRun onOpenTest={vi.fn()} />);
    expect(await screen.findByText(/share an interpreter/)).toBeTruthy();
  });

  it('reports a refusal instead of an empty result set', async () => {
    vi.mocked(fetchTests).mockResolvedValue(listing());
    vi.mocked(runTests).mockImplementation(
      () => Promise.reject(new Error('Script execution is disabled on this gateway'))
    );
    render(<TestsPanel project="P" csrfToken="t" canRun onOpenTest={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: /Run all/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('execution is disabled');
  });

  // Results belong to the project that produced them: left standing across a
  // switch they would be read as the new project's.
  it('drops results when the project changes', async () => {
    vi.mocked(fetchTests).mockResolvedValue(listing());
    vi.mocked(runTests).mockResolvedValue(run());
    const view = render(<TestsPanel project="P" csrfToken="t" canRun onOpenTest={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: /Run all/ }));
    await screen.findByText('1 passed');
    view.rerender(<TestsPanel project="Q" csrfToken="t" canRun onOpenTest={vi.fn()} />);
    await waitFor(() => expect(screen.queryByText('1 passed')).toBeNull());
  });
});
