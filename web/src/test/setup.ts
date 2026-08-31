import '@testing-library/jest-dom/vitest';
import { configure } from '@testing-library/react';

// MUST stay strictly BELOW vite.config.ts's testTimeout (30 s). When the two are
// equal, the query timeout and the vitest watchdog expire together and the
// generic one wins the race: the failure reports only "Test timed out", with no
// DOM dump and no indication of which await hung. web-designer lost a real
// intermittent failure that way. Keeping this lower means Testing Library always
// gives up first and says what it was looking for.
configure({ asyncUtilTimeout: 10_000 });

/**
 * jsdom implements Range but not `Range.getClientRects`, and CodeMirror calls it
 * whenever it has to position something in the viewport — a completion popup, a
 * hover tooltip, the signature-help panel. The failure is caught internally, so
 * nothing breaks; it just prints a stack trace per measurement and buries the
 * real output of the run.
 *
 * Stubbed to "no geometry", which is the truthful answer in a headless DOM: the
 * tooltips still mount and can still be asserted on, they simply have no
 * position. A test that depends on WHERE something is drawn cannot be written
 * against jsdom in the first place, so nothing is being papered over here.
 */
if (typeof Range !== 'undefined' && !Range.prototype.getClientRects) {
  const empty = Object.assign([] as unknown as DOMRectList, {
    item: () => null,
  }) as DOMRectList;
  Range.prototype.getClientRects = () => empty;
  Range.prototype.getBoundingClientRect = () => new DOMRect();
}
