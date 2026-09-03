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
const indexCss = readFileSync(join(here, 'index.css'), 'utf8');

/** The tokens the :root block in index.css defines, as a set. */
function defaults(): Set<string> {
  const root = indexCss.slice(indexCss.indexOf(':root {'));
  const body = root.slice(0, root.indexOf('\n}'));
  return new Set([...body.matchAll(/^\s*(--[\w-]+):/gm)].map((m) => m[1]));
}

/** Every value a given token takes across the ten themes. */
function values(token: string): string[] {
  return [...blocks().values()].map((t) => t.get(token) ?? '');
}

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
  it('gives every theme the geometry tokens, not just a palette', () => {
    // The 1.6.x themes were nineteen tokens each, all colour, so all ten were
    // one VS Code-shaped shell recoloured while the Perspective sessions beside
    // them read as ten products (Nigel, 02/09/2026). Geometry is what fixes
    // that, and a theme missing one of these silently falls back to another
    // theme's — the blocks are all :root-level, so nothing resets between them.
    const required = [
      '--radius', '--radius-panel', '--radius-row', '--rule-width',
      '--marker-width', '--shadow-card', '--shadow-popup', '--shadow-control',
      '--row-height', '--control-height', '--bg-chrome', '--border-strong',
    ];
    for (const [id, tokens] of blocks()) {
      const missing = required.filter((name) => !tokens.has(name));
      expect(`${id}: ${missing.join(', ')}`).toEqual(`${id}: `);
    }
  });

  it('declares every theme token as a :root default in index.css', () => {
    // Theme blocks are overrides, never the only definition. A token that
    // exists in nine themes and not the tenth must degrade to today's look
    // rather than to nothing — and a viewer on no theme at all (the picker
    // before it loads) has to get a complete stylesheet.
    const known = defaults();
    const orphans = new Set<string>();
    for (const tokens of blocks().values()) {
      for (const name of tokens.keys()) if (!known.has(name)) orphans.add(name);
    }
    expect([...orphans]).toEqual([]);
  });

  it('varies the geometry between themes', () => {
    // The point of the exercise. `newsprint-night` is square and flat,
    // `aurora-*` and `nord-*` are rounded, `industrial-*` carries the heaviest
    // active marker. If a pack edit ever collapses these to one value the
    // themes are back to being one shell recoloured, which is not something the
    // palette check above would notice.
    expect(new Set(values('--radius-panel')).size).toBeGreaterThanOrEqual(5);
    expect(new Set(values('--marker-width')).size).toBeGreaterThanOrEqual(3);
    expect(new Set(values('--shadow-popup')).size).toBeGreaterThanOrEqual(3);
    const square = blocks().get('newsprint-night');
    expect(square?.get('--radius-panel')).toBe('0');
    expect(square?.get('--shadow-popup')).toBe('none');
    expect(blocks().get('aurora-teal')?.get('--radius-panel')).not.toBe('0');
  });

  it('keeps --control-height a real height inside the band the chrome allows', () => {
    // "Set the height, not the padding" (Nigel, 02/09/2026). Below 20px a
    // <select> clips its own text and 13px row text loses its descenders.
    //
    // The ceiling was 26px while the toolbar and config strip were hardcoded
    // 34px. They derive from --control-height as of 1.7.1, so the air around a
    // control is 5px at every density and the band can be as wide as the packs
    // actually are.
    for (const [id, tokens] of blocks()) {
      for (const name of ['--control-height', '--row-height']) {
        const value = tokens.get(name) ?? '';
        expect(`${id} ${name} ${value}`).toMatch(/ (2[0-8])px$/);
      }
    }
  });

  it('leaves the ten themes GEOMETRICALLY distinct, not just recoloured', () => {
    // The defect this guards (Nigel, 03/09/2026: "still all look the same"):
    // 1.7.0 shipped per-theme geometry that every unit test passed and nobody
    // could see. The tokens were emitted, the selectors were right, the CSS
    // reached the browser — and _px clamped --radius-panel at 12px when five
    // packs ask for 16-18, and --radius-row at 6px when seven ask for 8. Seven
    // of the ten themes came out with byte-identical geometry.
    //
    // Colour was measured (theme_sweep.py) and geometry never was, so the
    // contrast sweep passed either way. This asserts the thing the eye reads.
    const signatures = new Map<string, string[]>();
    for (const [id, tokens] of blocks()) {
      const key = ['--radius', '--radius-panel', '--radius-row', '--row-height']
        .map((name) => tokens.get(name) ?? '?')
        .join('/');
      signatures.set(key, [...(signatures.get(key) ?? []), id]);
    }
    // Six or fewer means the clamps have flattened the packs again.
    expect(signatures.size).toBeGreaterThanOrEqual(7);
    // Three is the real ceiling: nord-dark, nord-light and leather-parchment
    // genuinely share a pack geometry and differ by palette alone. Four means
    // a band is squeezing packs together.
    for (const [key, ids] of signatures) {
      expect(`${ids.join(',')} share ${key}`).toMatch(
        new RegExp(`^[^,]+(,[^,]+){0,2} share `)
      );
    }
  });

  it('gives a shadowless theme a heavier border to float its layers with', () => {
    // Four of the ten packs name no shadow at all, and that is deliberate — an
    // industrial HMI is flat. What is NOT allowed is a palette floating over
    // code with neither a shadow nor a line: --border-strong is what the
    // dialogs and the quick-open palette fall back to, so every theme has one
    // whatever its shadow says.
    //
    // A glass pack draws its edge as a luminous hairline — `rgba(255,255,255,
    // 0.22)` is where the light catches a pane — so the value may be either a
    // hex or an rgba. What is asserted is that it EXISTS and, when translucent,
    // that it is meaningfully denser than the light one, which is what makes it
    // the heavier line the palette falls back to.
    for (const [id, tokens] of blocks()) {
      const strong = tokens.get('--border-strong') ?? '';
      expect(`${id} ${strong}`).toMatch(/(#[0-9a-f]{6}|rgba\([^)]+\))$/);
      const alpha = (value: string) =>
        Number(value.match(/rgba\([^,]+,[^,]+,[^,]+,\s*([\d.]+)\)/)?.[1] ?? '1');
      if (strong.startsWith('rgba')) {
        expect(`${id} strong=${alpha(strong)} light=${alpha(tokens.get('--border-light') ?? '')}`)
          .toSatisfy(() => alpha(strong) > alpha(tokens.get('--border-light') ?? '') * 1.5);
      }
    }
  });

  it('keeps each pack on the ground it was authored with', () => {
    // Nigel, 03/09/2026: the aurora pair "just look like a plain teal or
    // violet". They should not look like either — in Perspective both wear the
    // SAME violet ground (#1a1233) and differ only in which colour glows on it,
    // and that shared ground is what Glass Aurora is. This file used to mix the
    // page 30% toward the brand accent, which swung aurora-teal to hue 203 and
    // destroyed the family. The pack already tells siblings apart by accent.
    const teal = blocks().get('aurora-teal')?.get('--bg-primary');
    const violet = blocks().get('aurora-violet')?.get('--bg-primary');
    expect(`teal ${teal} / violet ${violet}`).toBe(`teal ${teal} / violet ${teal}`);
    expect(teal).toBe('#1a1233');
  });

  it('carries the glass packs as a MATERIAL, and leaves the others solid', () => {
    // The glass in Glass Aurora is not a colour, it is translucent white films
    // over a lit ground with a luminous hairline along each edge. Compositing
    // those to opaque hex — what this file did until 1.8.0 — turns three panes
    // of glass into three flat greys.
    //
    // Read from the pack, never switched on its name: `is_glass` counts
    // translucent surface tokens, so a new pack gets the right material without
    // the generator learning about it.
    const translucent = (value: string | undefined) => !!value?.startsWith('rgba');
    const glass = ['aurora-teal', 'aurora-violet'];
    for (const [id, tokens] of blocks()) {
      const isGlass = glass.includes(id);
      expect(`${id} films=${translucent(tokens.get('--bg-secondary'))}`)
        .toBe(`${id} films=${isGlass}`);
      expect(`${id} hairline=${translucent(tokens.get('--border-light'))}`)
        .toBe(`${id} hairline=${isGlass}`);
      expect(`${id} blur=${tokens.get('--blur-panel') !== 'none'}`)
        .toBe(`${id} blur=${isGlass}`);
      // The ground is opaque in EVERY theme. The editor is painted on it, and
      // a translucent editor ground is a legibility defect, not a material.
      expect(`${id} ${tokens.get('--bg-primary')}`).toMatch(/#[0-9a-f]{6}$/);
      // So is anything that has to occlude what scrolls under it.
      expect(`${id} ${tokens.get('--bg-solid')}`).toMatch(/#[0-9a-f]{6}$/);
    }
  });

  it('keeps a floating panel inside the band where it is actually glass', () => {
    // --surface on a glass pack is the pack's own 10% film: right over a page,
    // useless over an editor, where the code shows through and competes with
    // the palette's own rows. --glass-panel is that film composited and
    // re-emitted at a density that occludes without going solid.
    //
    // A BAND, not a floor. Too sheer and the code competes with the palette's
    // rows; too dense and `backdrop-filter` has nothing left to show — 0.94
    // was reviewed as "an opaque panel, not glass", which is the failure this
    // now catches from the other side.
    for (const [id, tokens] of blocks()) {
      const panel = tokens.get('--glass-panel') ?? '';
      const alpha = Number(panel.match(/rgba\([^,]+,[^,]+,[^,]+,\s*([\d.]+)\)/)?.[1] ?? '1');
      const glass = panel.startsWith('rgba');
      expect(`${id} panel alpha ${alpha} glass=${glass}`)
        .toSatisfy(() => (glass ? alpha >= 0.7 && alpha <= 0.9 : alpha === 1));
    }
  });

  it('never sets a font size, weight or family in a theme block', () => {
    // A pack names a typeface as part of a brand and this one asks for Georgia.
    // The `--font-*` check above catches the stacks; this catches the next way
    // in — a theme reaching for `font-size` or `font-weight` to look different,
    // which changes the app's rhythm rather than its palette.
    for (const [id] of blocks()) {
      const start = css.indexOf(`:root[data-theme="${id}"]`);
      const body = css.slice(start, css.indexOf('}', start));
      expect(`${id}: ${body.match(/font-[\w-]*\s*:/g)?.join(' ') ?? 'none'}`).toBe(`${id}: none`);
    }
  });
});
