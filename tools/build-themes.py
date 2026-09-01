#!/usr/bin/env python3
"""
Generate the IDE's theme stylesheet from the estate's Perspective theme packs.

The Script IDE runs in a browser tab next to Perspective sessions wearing the
same ten themes, and two tools on one gateway looking like different products is
a worse outcome than either looking slightly wrong. So the colours are not
chosen here: they are DERIVED from `ignition-themes/packs/*.json`, which is the
source of truth for the estate's look (styles-v2 is retired and those ten packs
are the only surviving copy — see the workspace CLAUDE.md).

Run after `tools/sync-packs.sh` in ignition-themes, or whenever a pack changes:

    python3 tools/build-themes.py [--packs <dir>] [--out <file>]

The output is committed, deliberately. A generated file in the repo means the
module builds without a sibling checkout present, and `--check` in CI proves the
committed copy still matches the packs.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

# ---- colour primitives ----------------------------------------------------
#
# sRGB in 0-1 throughout, and WCAG relative luminance for contrast. Everything
# else in this file is built on these four.


def _parse(colour: str):
    """sRGB 0-1 from a hex or rgb()/rgba() string, or None if it is neither."""
    if not colour:
        return None
    c = colour.strip()
    if c.startswith("#"):
        c = c[1:]
        if len(c) == 3:
            c = "".join(ch * 2 for ch in c)
        if len(c) != 6:
            return None
        try:
            return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
        except ValueError:
            return None
    if c.startswith("rgba(") or c.startswith("rgb("):
        body = c[c.index("(") + 1:c.rindex(")")]
        parts = [x.strip() for x in body.replace("/", ",").split(",")]
        if len(parts) < 3:
            return None
        try:
            return tuple(float(x) / 255 for x in parts[:3])
        except ValueError:
            return None
    return None


def _luminance(rgb) -> float:
    def channel(v: float) -> float:
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _mix(rgb, towards, amount: float):
    return tuple(c + (t - c) * amount for c, t in zip(rgb, towards))


def _hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02x}" for c in rgb)


def _to_hsl(rgb):
    r, g, b = rgb
    hi, lo = max(rgb), min(rgb)
    lightness = (hi + lo) / 2
    if hi == lo:
        return 0.0, 0.0, lightness
    d = hi - lo
    sat = d / (2 - hi - lo) if lightness > 0.5 else d / (hi + lo)
    if hi == r:
        hue = ((g - b) / d) % 6
    elif hi == g:
        hue = (b - r) / d + 2
    else:
        hue = (r - g) / d + 4
    return hue / 6, sat, lightness


def _from_hsl(hsl):
    hue, sat, lightness = hsl
    if sat == 0:
        return (lightness, lightness, lightness)
    q = lightness * (1 + sat) if lightness < 0.5 else lightness + sat - lightness * sat
    p_ = 2 * lightness - q

    def channel(t):
        t = t % 1.0
        if t < 1 / 6:
            return p_ + (q - p_) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p_ + (q - p_) * (2 / 3 - t) * 6
        return p_

    return (channel(hue + 1 / 3), channel(hue), channel(hue - 1 / 3))


def lift_to_contrast(rgb, surfaces, minimum: float, dark: bool):
    """
    Move a colour to legibility **keeping its hue and saturation**.

    Mixing toward white is what the 1.2.0 generator did, and it desaturates: a
    brand teal lifted that way arrives grey-green and stops reading as the
    theme's colour at all. Raising HSL lightness keeps `#0f766e` recognisably
    teal, which is the entire reason a pack names a brand accent.

    The search is for the SMALLEST lightness change that clears the bar, tried
    in the direction that suits the theme's polarity first — a mid-tone brand on
    a mid-tone page can be illegible in both directions for several steps.

    Returns (rgb, wasAdjusted).
    """
    if all(_ratio(rgb, s) >= minimum for s in surfaces):
        return rgb, False
    hue, sat, lightness = _to_hsl(rgb)
    start = int(round(lightness * 100))
    up = list(range(start, 101))
    down = list(range(start, -1, -1))
    for value in (up + down) if dark else (down + up):
        candidate = _from_hsl((hue, sat, value / 100))
        if all(_ratio(candidate, s) >= minimum for s in surfaces):
            return candidate, True
    return ((1.0, 1.0, 1.0) if dark else (0.0, 0.0, 0.0)), True


def accent_bg(hex_colour: str, dark: bool) -> str:
    """A translucent wash of the accent, for selections and active rows."""
    return f"color-mix(in srgb, {hex_colour} {'30' if dark else '20'}%, transparent)"


# ---------------------------------------------------------------------------
# Why the IDE's neutrals are DERIVED, not mapped.
#
# The first version of this file mapped Perspective's surfaces straight onto the
# IDE's scale: surface.page -> --bg-primary, surface.sidebar -> --bg-secondary,
# surface.card -> --surface. It rendered five of the ten themes ILLEGIBLE, and
# the generator's own contrast check passed throughout, because it measured
# tokens against --bg-primary while the app paints most of its text on
# --bg-secondary.
#
# The mistake was treating a SEMANTIC palette as a lightness ramp. Perspective's
# "sidebar" is branded chrome, not "slightly off the page": in finance-ledger it
# is dark navy in a light theme, so dark body text landed on it at 2.07:1. The
# glass themes are worse — their surfaces are `rgba(255,255,255,0.06)`, which is
# not a colour at all and cannot be reasoned about without compositing.
#
# So: the neutral ramp is COMPUTED from the page colour, the way VS Code's own
# themes are built (editor, then sidebar a step off it, then borders). The pack
# supplies what a palette is actually for — the accent and the syntax hues — and
# every one of those is checked against every surface it can land on.
# ---------------------------------------------------------------------------

# Accent roles, and the pack tokens that might carry them, best first. The
# resolver picks the first that is LEGIBLE, not the first that exists — see
# pick_legible.
ACCENT_SOURCES: dict[str, tuple[str, ...]] = {
    "--accent-primary": ("accent.primary", "text.status-info", "accent.alarm-low"),
    "--error": ("text.status-alarm", "accent.alarm-high", "border.danger",
                "accent.delta-down", "accent.danger"),
    "--warning": ("text.status-warn", "text.readout-value-warn", "accent.alarm-med"),
    "--success": ("text.status-ok", "accent.delta-up", "surface.pill-dot"),
    "--syntax-keyword": ("accent.primary", "text.status-info", "accent.alarm-low"),
    "--syntax-string": ("text.status-ok", "accent.delta-up", "surface.pill-dot"),
    "--syntax-number": ("text.status-warn", "text.readout-value-warn", "accent.alarm-med"),
    "--syntax-type": ("accent.progress", "text.status-info", "accent.primary"),
    "--syntax-function": ("text.status-info", "accent.alarm-low", "accent.primary"),
    "--syntax-comment": ("text.muted",),
}

# How far each neutral sits from the page, as a fraction toward white (dark
# themes) or black (light themes). Modelled on VS Code's own steps: the side bar
# is a small lift off the editor, the panel/active row a little more, and the
# border is the first step that must be visible on its own.
DARK_RAMP = {"secondary": 0.05, "tertiary": 0.11, "surface": 0.07, "border": 0.18}
LIGHT_RAMP = {"secondary": 0.045, "tertiary": 0.10, "surface": 0.02, "border": 0.20}

# Text is placed by TARGET CONTRAST rather than by hue, so "muted" means the same
# thing in every theme instead of meaning whatever the pack happened to hold.
#
# 13:1 was the 1.2.0 setting and it renders body text very close to white, which
# is brighter than any editor ships and is tiring over a working day. VS Code's
# own default is #cccccc on #1f1f1f: 10.4:1. These targets put every theme in
# that neighbourhood, still comfortably past WCAG AAA's 7:1 for body text.
TEXT_TARGETS = {"primary": 10.5, "secondary": 6.2, "muted": 4.6}

# Every surface a foreground can land on. A colour must clear the bar on ALL of
# them, because the same token paints the tree (secondary), the editor (primary)
# and a hovered row (tertiary).
SURFACE_KEYS = ("--bg-primary", "--bg-secondary", "--bg-tertiary")

MIN_ACCENT_CONTRAST = 4.5
MIN_TEXT_CONTRAST = 4.5

# How much of the theme's brand accent is stirred into the neutral ground.
#
# Not decoration. `aurora-teal` and `aurora-violet` are byte-identical packs
# apart from `accent.primary` and `accent.progress` — in Perspective they read
# differently because the glass surfaces tint with the accent, and with a purely
# page-derived ramp the IDE rendered the teal theme in violet. A ground that
# carries a trace of the brand is how VS Code themes differ from one another
# too, and it is what makes two siblings tell apart at a glance.
#
# The mix changes HUE ONLY: the page's own lightness is restored afterwards.
# Without that, a pack whose brand accent is nearly white — `newsprint-night`
# resolves to #e8e2d6 — has its editor ground dragged three shades lighter than
# the pack asked for, which is a bigger change than the one being made.
ACCENT_TINT = 0.30


def opaque_page(tokens: dict, dark: bool) -> tuple[float, float, float]:
    """
    The page colour, guaranteed opaque.

    A translucent or missing value is not usable as a ramp base — the glass
    themes' surfaces are `rgba(255,255,255,0.06)` — so it falls back to a neutral
    of the right polarity rather than propagating an unusable value.
    """
    raw = tokens.get("surface.page")
    parsed = _parse(raw) if raw else None
    if parsed is None or (raw and raw.strip().startswith("rgba")):
        parsed = _parse(raw) if raw and not raw.strip().startswith("rgba") else None
    if parsed is None:
        return (0.12, 0.12, 0.14) if dark else (0.98, 0.98, 0.98)
    return parsed


def step(base: tuple[float, float, float], amount: float, dark: bool):
    """Move a colour off the page: lighter in a dark theme, darker in a light one."""
    target = (1.0, 1.0, 1.0) if dark else (0.0, 0.0, 0.0)
    return _mix(base, target, amount)


def text_at(page: tuple[float, float, float], target: float, dark: bool) -> str:
    """
    The text colour that hits `target` contrast against the page.

    Computed rather than taken from the pack: it is the only way "muted" means
    the same thing in all ten themes, and the packs disagree wildly about which
    token is meant to be read against a page at all.
    """
    ink = (1.0, 1.0, 1.0) if dark else (0.0, 0.0, 0.0)
    best, best_gap = ink, 1e9
    for i in range(0, 101):
        candidate = _mix(page, ink, i / 100)
        ratio = _ratio(candidate, page)
        gap = abs(ratio - target)
        if gap < best_gap:
            best, best_gap = candidate, gap
    return _hex(best)


def _ratio(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    la, lb = _luminance(a), _luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def pick_legible(tokens: dict, names: tuple[str, ...], surfaces: list, dark: bool,
                 minimum: float) -> tuple[str, bool]:
    """
    The first token the pack actually defines, lifted until it is legible.

    1.2.0 walked the candidate list and took the first that PASSED, which is how
    "Glass Aurora — Teal" came out violet: its brand `#0f766e` failed on the
    page, so the resolver fell through to `text.status-info`, a token the teal
    and violet packs share verbatim. The two themes then differed in one token
    out of eighteen and were indistinguishable on screen.

    A pack's brand colour is not interchangeable with its info colour. So the
    list is now a fallback for a token that is ABSENT, not for one that is dark:
    the first token present is kept and lifted in place, hue intact.
    """
    for name in names:
        raw = tokens.get(name)
        if not raw or raw == "transparent":
            continue
        rgb = _parse(raw)
        if rgb is None:
            continue
        lifted, adjusted = lift_to_contrast(rgb, surfaces, minimum, dark)
        return _hex(lifted), adjusted
    return _hex((0.5, 0.5, 0.5)), True


# Syntax roles in the order they keep their colour when two of them collide.
# Comment is first because a comment that stops looking muted reads as code;
# string and number next because they are the two a reader scans for. Type is
# last, and is the one that moves — in these packs it comes from
# `accent.progress`, which several of them set to a near-neighbour of the brand.
SYNTAX_PRIORITY = (
    "--syntax-comment", "--syntax-string", "--syntax-number",
    "--syntax-keyword", "--syntax-function", "--syntax-type",
)

# Below this RGB distance two syntax colours are indistinguishable on screen.
#
# Deliberately tight. A wider bar starts separating colours that a reader can
# already tell apart, and the separation is a hue rotation — which takes the
# colour off the pack's palette. Repainting Nord's function names pink to gain
# contrast it did not need is a worse outcome than the near-miss it fixed.
SYNTAX_MIN_DISTANCE = 0.07


def _distance(a, b) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def differentiate_syntax(out: dict, surfaces: list, dark: bool, pack_id: str,
                         report: list[str]) -> None:
    """
    Pull apart syntax colours that resolved to the same hue.

    Ten packs carry about six distinct hues between them, so two syntax roles
    landing on one colour is common rather than exotic — `aurora-teal` gave
    keyword `#18baad` and type `#15bdaa`, which is one colour with two names.
    Highlighting that does not distinguish is worse than no highlighting,
    because it looks deliberate.

    The later role in SYNTAX_PRIORITY is rotated in hue until it separates,
    then re-lifted so the rotation cannot cost legibility.
    """
    kept: list[tuple[str, tuple[float, float, float]]] = []
    for role in SYNTAX_PRIORITY:
        rgb = _parse(out[role])
        if rgb is None:
            continue
        clash = next((name for name, other in kept
                      if _distance(rgb, other) < SYNTAX_MIN_DISTANCE), None)
        if clash is None:
            kept.append((role, rgb))
            continue
        hue, sat, lightness = _to_hsl(rgb)
        for turn in (1, 2, 3, 4, 5, 6):
            trial = _from_hsl(((hue + 0.06 * turn) % 1.0, sat, lightness))
            trial, _ = lift_to_contrast(trial, surfaces, MIN_ACCENT_CONTRAST, dark)
            if all(_distance(trial, other) >= SYNTAX_MIN_DISTANCE for _, other in kept):
                out[role] = _hex(trial)
                kept.append((role, trial))
                report.append(f"  {pack_id}: {role} rotated off {clash} to {out[role]}")
                break
        else:
            kept.append((role, rgb))


def block(pack: dict, report: list[str]) -> str:
    tokens = pack["tokens"]
    dark = pack["dark"]
    ramp = DARK_RAMP if dark else LIGHT_RAMP

    raw_page = opaque_page(tokens, dark)

    # The brand accent, hue intact, legible on the page it will sit on. Resolved
    # BEFORE the ramp because the ramp is tinted with it.
    brand_source = next(
        (rgb for rgb in (_parse(tokens.get(name) or "") for name in ACCENT_SOURCES["--accent-primary"])
         if rgb is not None),
        None,
    )
    if brand_source is None:
        page = raw_page
    else:
        brand_seed, _ = lift_to_contrast(brand_source, [raw_page], MIN_ACCENT_CONTRAST, dark)
        mixed = _mix(raw_page, brand_seed, ACCENT_TINT)
        hue, sat, _ = _to_hsl(mixed)
        page = _from_hsl((hue, sat, _to_hsl(raw_page)[2]))

    secondary = step(page, ramp["secondary"], dark)
    tertiary = step(page, ramp["tertiary"], dark)
    surface = step(page, ramp["surface"], dark)
    border = step(page, ramp["border"], dark)
    surfaces = [page, secondary, tertiary]

    out = {
        "--bg-primary": _hex(page),
        "--bg-secondary": _hex(secondary),
        "--bg-tertiary": _hex(tertiary),
        "--surface": _hex(surface),
        "--border-light": _hex(border),
        "--text-primary": text_at(page, TEXT_TARGETS["primary"], dark),
        "--text-secondary": text_at(page, TEXT_TARGETS["secondary"], dark),
        "--text-muted": text_at(page, TEXT_TARGETS["muted"], dark),
    }

    # --text-muted is measured against the PAGE, but it also paints on the tree
    # (secondary) and hovered rows (tertiary), which are closer to it. Push it
    # until it clears the bar on the worst of them.
    muted = _parse(out["--text-muted"])
    ink = (1.0, 1.0, 1.0) if dark else (0.0, 0.0, 0.0)
    for i in range(0, 101):
        candidate = _mix(muted, ink, i / 100)
        if all(_ratio(candidate, s) >= MIN_TEXT_CONTRAST for s in surfaces):
            out["--text-muted"] = _hex(candidate)
            break

    # The pack's `font.body` is NOT copied through.
    #
    # A Perspective pack names a typeface as part of a brand — `newsprint-night`
    # asks for Georgia — and applying that to an IDE renders the file tree, the
    # tab strip and every button in a serif. VS Code themes have never changed
    # the UI font, for exactly this reason: a theme here is a palette. The one
    # stack lives in index.css, beside the mono stack it has to line up with.

    for role, names in ACCENT_SOURCES.items():
        minimum = 3.0 if role == "--syntax-comment" else MIN_ACCENT_CONTRAST
        colour, adjusted = pick_legible(tokens, names, surfaces, dark, minimum)
        out[role] = colour
        if adjusted:
            report.append(f'  {pack["id"]}: {role} nudged to {colour} '
                          f'(no pack token cleared {minimum}:1 on all surfaces)')

    differentiate_syntax(out, surfaces, dark, pack["id"], report)

    accent = out["--accent-primary"]
    out["--accent-primary-bg"] = accent_bg(accent, dark)

    lines = [f'/* {pack["label"]} — {"dark" if dark else "light"} */']
    # `:root[data-theme=...]`, not a bare attribute selector. `:root` and
    # `[data-theme]` have IDENTICAL specificity, so a bare selector only wins on
    # source order — and index.css is bundled after this file, so the theme was
    # silently overridden. Measured in the browser 01/09/2026: data-theme
    # changed and not one colour did.
    lines.append(f':root[data-theme="{pack["id"]}"] {{')
    # color-scheme is not decoration. Without it Chrome's "auto dark mode for
    # web contents" repaints the page's own colours, and no headless check can
    # reproduce it. This has cost the estate four releases.
    lines.append(f'  color-scheme: {"dark" if dark else "light"};')
    for key, value in out.items():
        lines.append(f"  {key}: {value};")
    lines.append("}")
    return "\n".join(lines), out


def generate(packs_dir: pathlib.Path) -> str:
    files = sorted(packs_dir.glob("*.json"))
    if not files:
        raise SystemExit(f"No packs found in {packs_dir}")
    packs = [json.loads(f.read_text()) for f in files]
    report: list[str] = []
    header = (
        "/*\n"
        " * GENERATED by tools/build-themes.py from the ignition-themes packs.\n"
        " * Do not edit by hand — edit the pack and regenerate, or the IDE and the\n"
        " * Perspective sessions beside it drift apart.\n"
        " *\n"
        " * The NEUTRALS are derived from each pack's page colour, not mapped from\n"
        " * its surfaces: Perspective's surfaces are semantic (a 'sidebar' is branded\n"
        " * chrome, dark even in a light theme) and mapping them onto a lightness\n"
        " * ramp made five of these ten themes illegible. The pack supplies the\n"
        " * accent and syntax hues, each checked against every surface it lands on.\n"
        " *\n"
        f" * {len(packs)} themes.\n"
        " */\n"
    )
    blocks = [block(p, report) for p in packs]

    # Two themes that generate the same eighteen values are one theme with two
    # names, and the picker then offers a choice that does nothing. This is the
    # 1.2.0 aurora bug expressed as an assertion — it shipped precisely because
    # nothing compared one theme's output against another's.
    seen: dict[str, str] = {}
    for pack, (_, out) in zip(packs, blocks):
        key = "|".join(f"{k}={v}" for k, v in sorted(out.items()))
        if key in seen:
            raise SystemExit(
                f"Themes '{seen[key]}' and '{pack['id']}' generate identical palettes. "
                "Their packs differ only in tokens this generator ignores — widen "
                "ACCENT_SOURCES or the accent tint rather than shipping two names "
                "for one theme."
            )
        seen[key] = pack["id"]

    css = header + "\n\n".join(text for text, _ in blocks) + "\n"
    if report:
        print(f"Contrast adjustments ({len(report)}):", file=sys.stderr)
        for line in report:
            print(line, file=sys.stderr)
    return css


def theme_list_ts(packs: list[dict]) -> str:
    """
    The TypeScript theme list.

    Emitted from the SAME packs as the CSS, in the same run, because the failure
    otherwise is silent: a name in the picker with no matching CSS block gives
    the viewer an option that does nothing at all.
    """
    lines = [
        "/**",
        " * GENERATED by tools/build-themes.py. Do not edit by hand.",
        " *",
        " * The picker's list, emitted from the same packs as themes.generated.css so",
        " * every option here has a stylesheet block to match.",
        " */",
        "export interface ThemeChoice {",
        "  id: string;",
        "  label: string;",
        "  dark: boolean;",
        "}",
        "",
        "export const THEMES: ThemeChoice[] = [",
    ]
    for pack in packs:
        label = json.dumps(pack["label"])
        dark = "true" if pack["dark"] else "false"
        lines.append(f"  {{ id: '{pack['id']}', label: {label}, dark: {dark} }},")
    lines += [
        "];",
        "",
        "export type ThemeId = (typeof THEMES)[number]['id'];",
        "",
        "/**",
        " * The default. A dark theme, because the editor is the whole page and this",
        " * is the closest of the ten to the palette the app shipped with in 1.0.",
        " */",
        "export const DEFAULT_THEME: ThemeId = 'nord-dark-frost';",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    here = pathlib.Path(__file__).resolve().parent.parent
    parser.add_argument(
        "--packs",
        type=pathlib.Path,
        default=here.parent.parent / "ignition-themes" / "packs",
    )
    parser.add_argument(
        "--out", type=pathlib.Path, default=here / "web" / "src" / "themes.generated.css"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the committed file is out of date",
    )
    args = parser.parse_args()

    css = generate(args.packs)
    packs = [json.loads(f.read_text()) for f in sorted(args.packs.glob("*.json"))]
    ts = theme_list_ts(packs)
    ts_out = args.out.parent / "themes.ts"

    if args.check:
        stale = []
        for path, wanted in ((args.out, css), (ts_out, ts)):
            if (path.read_text() if path.exists() else "") != wanted:
                stale.append(str(path))
        if stale:
            print(
                "Out of date, rerun tools/build-themes.py: " + ", ".join(stale),
                file=sys.stderr,
            )
            return 1
        print(f"{args.out.name} and {ts_out.name} are up to date")
        return 0

    args.out.write_text(css)
    ts_out.write_text(ts)
    print(f"Wrote {args.out} and {ts_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
