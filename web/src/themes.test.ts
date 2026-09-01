/**
 * Guards on the GENERATED theme stylesheet.
 *
 * These run in the ordinary test suite, not only when someone regenerates, and
 * that is the point: `tools/build-themes.py` has its own assertions but they
 * only fire if it is run, and the committed CSS is what actually ships. The
 * 1.2.0 aurora bug — two themes with one palette between them — was in the
 * committed file for a whole release with every test passing.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { THEMES } from './themes';

const here = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(join(here, 'themes.generated.css'), 'utf8');

/** Every `:root[data-theme="x"] { ... }` block, as id -> {token: value}. */
function blocks(): Map<string, Map<string, string>> {
  const out = new Map<string, Map<string, string>>();
  const re = /:root\[data-theme="([^"]+)"\]\s*\{([^}]*)\}/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(css)) !== null) {
    const tokens = new Map<string, string>();
    for (const line of match[2].split(';')) {
      const [name, ...rest] = line.split(':');
      if (name?.trim().startsWith('--')) {
        tokens.set(name.trim(), rest.join(':').trim());
      }
    }
    out.set(match[1], tokens);
  }
  return out;
}

describe('themes.generated.css', () => {
  it('has a block for every theme the picker offers', () => {
    // A picker option with no stylesheet block is an option that does nothing.
    const ids = [...blocks().keys()];
    expect(ids.sort()).toEqual(THEMES.map((t) => t.id).sort());
  });

  it('gives no two themes the same palette', () => {
    // "Glass Aurora — Teal" and "Glass Aurora — Violet" resolved to identical
    // values in 1.2.0 apart from one syntax colour, so the picker offered two
    // names for one theme and the teal one rendered violet.
    const seen = new Map<string, string>();
    const clashes: string[] = [];
    for (const [id, tokens] of blocks()) {
      const key = [...tokens.entries()].sort().map(([k, v]) => `${k}=${v}`).join('|');
      const first = seen.get(key);
      if (first) clashes.push(`${first} == ${id}`);
      else seen.set(key, id);
    }
    expect(clashes).toEqual([]);
  });

  it('never sets the UI font from a pack', () => {
    // A pack names a typeface as part of a brand — `newsprint-night` asks for
    // Georgia — and applying it set the file tree, the tab strip and every
    // button in a serif. A theme here is a palette; the font stacks live in
    // index.css beside each other so they line up.
    expect(css).not.toContain('--font-sans');
    expect(css).not.toContain('--font-mono');
  });

  it('declares color-scheme in every block', () => {
    // Without it Chrome's "auto dark mode for web contents" repaints the page's
    // own colours, and no headless check can reproduce it. It has cost this
    // estate several releases.
    for (const id of blocks().keys()) {
      const block = css.slice(css.indexOf(`:root[data-theme="${id}"]`));
      expect(block.slice(0, block.indexOf('}'))).toMatch(/color-scheme:\s*(dark|light)/);
    }
  });

  it('qualifies every selector with :root', () => {
    // `:root` and `[data-theme]` have IDENTICAL specificity, so a bare
    // `[data-theme="x"]` block only wins on source order — and index.css is
    // bundled after this file. Measured in the browser: data-theme changed and
    // not one colour did.
    const bare = css.match(/(^|[^:\w\]])\[data-theme=/gm);
    expect(bare).toBeNull();
  });
});
