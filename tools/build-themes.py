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

# IDE token  <-  pack token. A missing pack token falls back to the next entry.
#
# The syntax colours have no pack equivalent — Perspective has no code editor —
# so they are derived from the pack's own accents rather than invented per
# theme, which keeps a light pack readable and a dark pack consistent.
MAPPING: dict[str, tuple[str, ...]] = {
    "--bg-primary": ("surface.page",),
    "--bg-secondary": ("surface.sidebar", "surface.card"),
    "--bg-tertiary": ("surface.status-neutral", "surface.chip"),
    "--surface": ("surface.card",),
    "--border-light": ("border.card", "border.sidebar"),
    "--text-primary": ("text.body",),
    "--text-secondary": ("text.table-header", "text.muted"),
    "--text-muted": ("text.muted",),
    "--accent-primary": ("accent.primary", "text.status-info", "accent.alarm-low"),
    # NOT accent.danger / accent.alarm-*: in a Perspective pack those are the
    # colours of a badge's SURFACE or of the text sitting ON that badge, so in
    # several packs accent.danger is literally #ffffff. The `text.status-*`
    # family is the one meant to be read against a page, which is what this IDE
    # does with it. Measured 01/09/2026 — finance-ledger and industrial-day-cyan
    # both produced a white error colour on a white page before this changed.
    "--error": ("text.status-alarm", "accent.alarm-high", "border.danger", "accent.delta-down", "accent.alarm-urgent", "accent.danger"),
    "--warning": ("text.status-warn", "text.readout-value-warn", "accent.alarm-med", "text.readout-unit-warn"),
    "--success": ("text.status-ok", "accent.delta-up", "surface.pill-dot"),
    "--font-sans": ("font.body",),
    # Syntax
    "--syntax-keyword": ("accent.primary", "text.status-info", "accent.alarm-low"),
    "--syntax-string": ("text.status-ok", "accent.delta-up", "surface.pill-dot"),
    "--syntax-comment": ("text.muted",),
    "--syntax-number": ("text.status-warn", "text.readout-value-warn", "accent.alarm-med", "text.readout-unit-warn"),
    "--syntax-type": ("accent.progress", "text.status-info", "accent.primary"),
    "--syntax-function": ("text.status-info", "accent.alarm-low", "accent.primary"),
}


def resolve(tokens: dict, names: tuple[str, ...]) -> str | None:
    for name in names:
        value = tokens.get(name)
        # "transparent" is a real Perspective value and a useless page
        # background — a transparent body lets the host's colour through, which
        # is exactly the auto-dark trap the estate rule warns about.
        if value and value != "transparent":
            return value
    return None


# ---- contrast ------------------------------------------------------------
#
# The estate has been here before: ignition-themes v1.5.1 shipped five themes
# whose --error was illegible against their own background, and the fix was to
# gate the token on measured contrast rather than to trust the palette. A pack's
# accent is chosen to sit on a Perspective CARD; this IDE paints it on the PAGE,
# which is a different colour, so a token that is fine there can fail here.
#
# WCAG relative luminance, and a 3:1 floor — the non-text threshold, which is
# the right one for a syntax colour or a border, and the same one the themes
# repo settled on.

MIN_CONTRAST = 3.0


def _parse(colour: str) -> tuple[float, float, float] | None:
    """Return sRGB 0-1, or None for anything not a plain hex or rgb()."""
    c = colour.strip()
    if c.startswith("#"):
        c = c[1:]
        if len(c) == 3:
            c = "".join(ch * 2 for ch in c)
        if len(c) != 6:
            return None
        try:
            return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore
        except ValueError:
            return None
    if c.startswith("rgba(") or c.startswith("rgb("):
        body = c[c.index("(") + 1:c.rindex(")")]
        parts = [p.strip() for p in body.split(",")]
        if len(parts) < 3:
            return None
        try:
            return tuple(float(p) / 255 for p in parts[:3])  # type: ignore
        except ValueError:
            return None
    return None


def _luminance(rgb: tuple[float, float, float]) -> float:
    def channel(v: float) -> float:
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float | None:
    """Contrast ratio, or None when either colour cannot be measured."""
    ca, cb = _parse(a), _parse(b)
    if ca is None or cb is None:
        return None
    la, lb = _luminance(ca), _luminance(cb)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _mix(rgb: tuple[float, float, float], towards: tuple[float, float, float], amount: float):
    return tuple(c + (t - c) * amount for c, t in zip(rgb, towards))


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02x}" for c in rgb)


def legible(colour: str, background: str, dark: bool) -> tuple[str, bool]:
    """
    Nudge `colour` towards white (dark theme) or black (light) until it clears
    MIN_CONTRAST against `background`.

    Returns the colour and whether it had to be changed, so the build can REPORT
    every adjustment. A silent correction would hide a bad pack; the point is to
    ship something legible AND to know the pack needs attention.
    """
    ratio = contrast(colour, background)
    if ratio is None or ratio >= MIN_CONTRAST:
        return colour, False
    rgb = _parse(colour)
    bg = _parse(background)
    if rgb is None or bg is None:
        return colour, False
    target = (1.0, 1.0, 1.0) if dark else (0.0, 0.0, 0.0)
    for step in range(1, 21):
        candidate = _mix(rgb, target, step * 0.05)
        if (_luminance(candidate) + 0.05) / (_luminance(bg) + 0.05) >= MIN_CONTRAST or \
           (_luminance(bg) + 0.05) / (_luminance(candidate) + 0.05) >= MIN_CONTRAST:
            return _hex(candidate), True
    return _hex(_mix(rgb, target, 1.0)), True


def accent_bg(hex_colour: str, dark: bool) -> str:
    """A translucent wash of the accent, for selections and active rows."""
    return f"color-mix(in srgb, {hex_colour} {'28' if dark else '18'}%, transparent)"


# Tokens painted ON the page background, which must therefore be legible
# against it. Backgrounds, borders and the text colours themselves are excluded:
# a border is meant to be low contrast, and forcing --text-muted to 3:1 would
# make "muted" indistinguishable from "primary".
FOREGROUND_TOKENS = frozenset({
    "--accent-primary",
    "--error",
    "--warning",
    "--success",
    "--syntax-keyword",
    "--syntax-string",
    "--syntax-number",
    "--syntax-type",
    "--syntax-function",
})


def block(pack: dict, report: list[str]) -> str:
    tokens = pack["tokens"]
    dark = pack["dark"]
    lines = [f'/* {pack["label"]} — {"dark" if dark else "light"} */']
    # `:root[data-theme=...]`, not a bare attribute selector. `:root` and
    # `[data-theme]` have IDENTICAL specificity, so a bare attribute selector
    # only wins on source order — and index.css's `:root` block is bundled after
    # this file, so the theme was silently overridden. Measured in the browser
    # 01/09/2026: data-theme changed, every colour did not.
    lines.append(f':root[data-theme="{pack["id"]}"] {{')
    # color-scheme is not decoration. Without it Chrome's "auto dark mode for
    # web contents" repaints the page's own colours, and no headless check can
    # reproduce it. This has cost the estate four releases.
    lines.append(f'  color-scheme: {"dark" if dark else "light"};')

    page = resolve(tokens, MAPPING["--bg-primary"]) or ("#000000" if dark else "#ffffff")
    accent = None
    for ide_token, pack_names in MAPPING.items():
        value = resolve(tokens, pack_names)
        if value is None:
            continue
        if ide_token in FOREGROUND_TOKENS:
            # Take the first candidate that is actually LEGIBLE on the page,
            # not merely the first that exists.
            #
            # The packs are not consistent about which token family is meant to
            # be read against a page: in finance-ledger the readable red is
            # `text.status-alarm` and `accent.danger` is white, while in
            # leather-night-tan `text.status-alarm` is itself an on-badge colour
            # and near-black on a near-black page. Preferring by NAME therefore
            # cannot work for all ten, and preferring by measured contrast does.
            chosen = None
            for candidate_name in pack_names:
                candidate = tokens.get(candidate_name)
                if not candidate or candidate == "transparent":
                    continue
                ratio = contrast(candidate, page)
                if ratio is not None and ratio >= MIN_CONTRAST:
                    chosen = candidate
                    break
            if chosen is not None:
                value = chosen
            else:
                # Nothing in the pack works here. Nudge the first candidate and
                # SAY SO — the pack has no page-legible colour for this role.
                fixed, changed = legible(value, page, dark)
                if changed:
                    ratio = contrast(value, page)
                    report.append(
                        f'  {pack["id"]}: {ide_token} {value} -> {fixed} '
                        f'(no pack token cleared {MIN_CONTRAST}:1 on {page}; '
                        f'best was {ratio:.2f}:1)'
                    )
                    value = fixed
        if ide_token == "--accent-primary":
            accent = value
        lines.append(f"  {ide_token}: {value};")
    if accent:
        lines.append(f"  --accent-primary-bg: {accent_bg(accent, dark)};")
    lines.append("}")
    return "\n".join(lines)


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
        f" * {len(packs)} themes.\n"
        " */\n"
    )
    css = header + "\n\n".join(block(p, report) for p in packs) + "\n"
    if report:
        # Printed, never swallowed: an adjusted token means the PACK is wrong for
        # a full-page background, and somebody should look at it.
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
