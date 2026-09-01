import { describe, expect, it } from 'vitest';
import { toExecEvent } from './execClient';

/**
 * Normalising the exec channel.
 *
 * The one thing worth guarding here is that `error` is overloaded by the server:
 * a STRING at the top level is a channel refusal (execution disabled, not an
 * administrator, bad CSRF), while an OBJECT inside a `finished` frame is a
 * Python traceback. Conflating them tells a user their script raised a
 * TypeError when what actually happened is that they lack a role.
 */
describe('toExecEvent', () => {
  it('reads a top-level string error as a channel refusal, not a script failure', () => {
    const event = toExecEvent({ error: 'Running scripts requires the Administrator role.' });
    expect(event).toEqual({
      kind: 'error',
      message: 'Running scripts requires the Administrator role.',
    });
  });

  it('reads an error OBJECT inside finished as the script traceback', () => {
    const event = toExecEvent({
      event: 'finished',
      executionId: 'x',
      ok: false,
      error: { type: 'TypeError', message: 'bad', frames: [] },
    });
    expect(event?.kind).toBe('finished');
    if (event?.kind !== 'finished') throw new Error('wrong kind');
    expect(event.result.error?.type).toBe('TypeError');
    expect(event.result.ok).toBe(false);
  });

  it('defaults every optional field on finished, so the UI never reads undefined', () => {
    const event = toExecEvent({ event: 'finished', executionId: 'x' });
    if (event?.kind !== 'finished') throw new Error('wrong kind');
    expect(event.result.stdout).toBe('');
    expect(event.result.stderr).toBe('');
    expect(event.result.truncated).toBe(false);
    expect(event.result.cancelled).toBe(false);
    // `ok` absent means NOT ok. Defaulting it true would report a failed run as
    // a success whenever the server omitted the field.
    expect(event.result.ok).toBe(false);
  });

  it('reads started and stopping', () => {
    expect(toExecEvent({ event: 'started', executionId: 'a' })).toEqual({
      kind: 'started',
      executionId: 'a',
    });
    expect(toExecEvent({ event: 'stopping', executionId: 'a', detail: 'interrupting' })).toEqual({
      kind: 'stopping',
      executionId: 'a',
      detail: 'interrupting',
    });
  });

  it('ignores anything it does not recognise rather than throwing', () => {
    // The socket is shared with the language server; an unexpected frame must
    // not take the console down.
    expect(toExecEvent(null)).toBeNull();
    expect(toExecEvent('nonsense')).toBeNull();
    expect(toExecEvent({ event: 'started' })).toBeNull(); // no executionId
    expect(toExecEvent({})).toBeNull();
  });
});
