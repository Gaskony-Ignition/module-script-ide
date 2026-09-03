"""Live checks for 1.4.0: inherited scripts are read-only, Script Hint Scope, root terminal.

Run against the real gateway after deploy_gate.py passes. Everything here is a
browser assertion, because every one of these three changes is invisible below
the UI: `EditorState.readOnly` is advisory so only the live view knows, a label
is a label, and whether a shell is root is a fact about a process the JVM
started and cannot be read off any config.

The inheritance checks need a project with a PARENT. `Site_Redgum_Sewer`
inherits `Template` on this gateway and its Project Library is almost entirely
inherited, which is why it is the fixture; SI_INHERIT_PROJECT overrides it.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gateway_session import CONFIG, GATEWAY_URL, login
from playwright.sync_api import sync_playwright

SPA = CONFIG.get("spa_path", "/data/scriptide/")
OUT = os.environ.get("SI_SHOT_DIR", "/tmp")
INHERIT_PROJECT = os.environ.get("SI_INHERIT_PROJECT", "Site_Redgum_Sewer")

res = []


def rec(n, ok, d=""):
    res.append((n, ok, d))
    print(f"  [{'PASS' if ok else 'FAIL'}] {n}: {d}")


def skip(n, d=""):
    # A pass with the reason stated, matching validate_v15_tree. A check that
    # cannot run on THIS gateway is not evidence of a defect, and dropping it
    # silently would leave the tally looking complete when it is not.
    res.append((n, True, d))
    print(f"  [SKIP] {n}: {d}")


def expand_tree(page, passes=6):
    """Open every branch of the script tree.

    The tree ships COLLAPSED from 1.6.0 (Nigel, 02/09/2026) — quick open is the
    fast path now, and a whole project's scripts open on landing is a column that
    has to be scrolled before anything can be chosen. Every suite that clicks a
    script row has to open its branch first, so this is the shared way to do it.

    Repeated, because opening a package reveals the packages nested inside it.
    """
    for _ in range(passes):
        shut = page.locator('.file-tree [aria-expanded="false"]')
        count = shut.count()
        if count == 0:
            return
        for index in range(count):
            try:
                shut.nth(index).click()
            except Exception:
                pass          # a click that re-renders the list is not a failure
        page.wait_for_timeout(120)


with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_context(viewport={"width": 1600, "height": 1000}).new_page()
    errs = []
    page.on("console", lambda m: errs.append(f"{m.text} @ {m.location.get('url','')}")
            if m.type == "error" and "/res/sys/" not in m.location.get("url", "")
            and "/data/app/session" not in m.location.get("url", "") else None)
    page.on("pageerror", lambda e: errs.append(str(e)))
    login(page)
    page.goto(GATEWAY_URL + SPA, wait_until="load", timeout=30000)
    page.wait_for_selector(".file-tree-header", timeout=20000)
    expand_tree(page)

    # ---------- 1. inheritance: read-only until overridden ----------
    #
    # The fixture project may simply not be on this gateway: the default,
    # Site_Redgum_Sewer, was removed from the rig with the water-suite projects,
    # and until 1.6.0 that made the whole suite CRASH in select_option with a
    # 30-second Playwright timeout and a stack trace — losing the terminal, hint
    # scope and chrome-sizing checks, none of which need it. An absent fixture is
    # a skip with its reason, exactly as validate_v15_tree already does.
    projects = page.locator(".workspace-project select option").all_inner_texts()
    have_project = any(option.strip().startswith(INHERIT_PROJECT) for option in projects)
    if have_project:
        page.select_option(".workspace-project select", INHERIT_PROJECT)
        page.wait_for_timeout(2500)
        inherited = page.locator(".file-tree-row:has(.badge-inherited) .file-tree-item").first
        have_fixture = inherited.count() > 0
        rec("FIXTURE: an inherited script exists to test against",
            have_fixture, f"project={INHERIT_PROJECT}")
        if not have_fixture:
            skip("INHERITANCE: read-only, override and save checks",
                 f"'{INHERIT_PROJECT}' has no inherited script — its parent is most "
                 "likely not marked inheritable, which is a project setting outside "
                 "this module")
    else:
        have_fixture = False
        skip("FIXTURE: an inherited script exists to test against",
             f"no project '{INHERIT_PROJECT}' on this gateway "
             f"(saw: {', '.join(p.strip() for p in projects) or 'none'}). "
             "Set SI_INHERIT_PROJECT to a project with an inheritable parent.")
        skip("INHERITANCE: read-only, override and save checks",
             "needs the fixture project above")

    if have_fixture:
        name = inherited.inner_text().strip().split("\n")[0]
        # No destructive action on a purely inherited row: this project owns
        # nothing to remove, and the server 404s the attempt.
        row = page.locator(".file-tree-row:has(.badge-inherited)").first
        rec("TREE: an inherited row offers no delete",
            row.locator(".file-tree-delete, .file-tree-discard").count() == 0, name)

        inherited.click()
        page.wait_for_timeout(2500)

        rec("EDIT: opening an inherited script says so",
            page.locator(".inherited-note").count() == 1,
            page.locator(".inherited-note").inner_text().replace("\n", " ")[:90]
            if page.locator(".inherited-note").count() else "no bar")

        # The assertion that matters. EditorState.readOnly is advisory, so the
        # only honest test is to type and look — exactly what was done to the
        # real Designer to establish the behaviour in the first place.
        before = page.evaluate(
            "document.querySelector('.code-editor-host:not([style*=none]) .cm-content').innerText")
        page.locator(".code-editor-host:not([style*=none]) .cm-content").click()
        page.keyboard.type("ZZZZ")
        page.wait_for_timeout(600)
        after = page.evaluate(
            "document.querySelector('.code-editor-host:not([style*=none]) .cm-content').innerText")
        rec("EDIT: typing into an inherited script changes nothing",
            before == after, f"{len(before)} chars before, {len(after)} after")

        save = page.locator("button", has_text="Save script").first
        rec("EDIT: Save is disabled on an inherited script",
            save.is_disabled(), "")

        # Ctrl+S is a separate path from the button and has its own guard.
        page.keyboard.press("Control+s")
        page.wait_for_timeout(1200)
        after_save = page.evaluate(
            "document.querySelector('.code-editor-host:not([style*=none]) .cm-content').innerText")
        rec("EDIT: Ctrl+S on an inherited script does not fork the parent",
            before == after_save and page.locator(".workspace-notice.is-error").count() == 0, "")

        page.screenshot(path=f"{OUT}/v14-inherited-readonly.png")

        # ---------- override unlocks it ----------
        override = page.locator(".inherited-note-action").first
        rec("OVERRIDE: the notice carries the action that unlocks it",
            override.count() == 1,
            override.inner_text() if override.count() else "absent")
        if override.count():
            override.click()
            page.wait_for_timeout(800)
            page.locator(".code-editor-host:not([style*=none]) .cm-content").click()
            page.keyboard.type("# overridden")
            page.wait_for_timeout(600)
            unlocked = page.evaluate(
                "document.querySelector('.code-editor-host:not([style*=none]) .cm-content').innerText")
            rec("OVERRIDE: the buffer accepts typing afterwards",
                "# overridden" in unlocked, "")
            rec("OVERRIDE: the notice now explains the save, not the lock",
                page.locator(".inherited-note.is-override").count() == 1,
                page.locator(".inherited-note").inner_text().replace("\n", " ")[:90]
                if page.locator(".inherited-note").count() else "")
            # NOTHING is written by overriding. The Designer stages it too — the
            # gateway filesystem had no copy of the script after Override
            # Resource, only after save. We deliberately do NOT save here.
            page.screenshot(path=f"{OUT}/v14-overridden.png")

    # ---------- 2. Script Hint Scope ----------
    # A Project Library script in ANY project; its allowlist is exactly this one
    # attribute, so the strip is the control plus its explanation.
    lib = page.locator(".file-tree-item").filter(has_not=page.locator(".badge")).first
    page.locator(".file-tree-group", has_text="PROJECT LIBRARY").locator(
        ".file-tree-item").first.click()
    page.wait_for_timeout(2000)
    strip = page.locator(".config-strip")
    if strip.count():
        rec("HINTS: the control carries the Designer's own name",
            "Script Hint Scope" in strip.inner_text(),
            strip.inner_text().replace("\n", " ")[:70])
        sel = page.locator(".config-field select").first
        if sel.count():
            opts = sel.locator("option").all_inner_texts()
            # ORDER, not membership. Measured off the 8.3.8 Designer: None,
            # Designer, Gateway, All — which is not the numeric order.
            rec("HINTS: options are in the Designer's order, not the bitmask's",
                opts == ["None", "Designer", "Gateway", "All"], f"{opts}")
        # No prose. The Designer says nothing about this control, and 1.4.0's
        # first attempt gave the rarest setting on the strip a paragraph, which
        # made it the loudest thing on it (Nigel, 01/09/2026).
        rec("HINTS: no explanatory prose on the strip",
            page.locator(".config-help").count() == 0, "")
        # Out of the way on the RIGHT, as the Designer places it. Measured
        # against the strip's own box rather than the viewport: the strip does
        # not span the window once the outline panel is open.
        field = page.locator(".config-field-trailing").first
        if field.count():
            fb = field.bounding_box()
            sb = strip.bounding_box()
            # LAST on the row, not merely right-of-centre. The first attempt at
            # this assertion accepted a control stranded mid-strip with the save
            # button beyond it — right-hand side, wrong end.
            others = page.locator(".config-strip > *:not(.config-field-trailing)")
            rights = [(lambda x: x["x"] + x["width"])(others.nth(i).bounding_box())
                      for i in range(others.count())]
            rec("HINTS: the control is the LAST thing on the strip",
                all(fb["x"] + fb["width"] >= r - 1 for r in rights),
                f"its right={fb['x'] + fb['width']:.0f}, others end at {max(rights):.0f}"
                if rights else "nothing else on the strip")
            rec("HINTS: it sits against the strip's right edge",
                (sb["x"] + sb["width"]) - (fb["x"] + fb["width"]) < 40,
                f"{(sb['x'] + sb['width']) - (fb['x'] + fb['width']):.0f}px of margin")
            rec("HINTS: it is smaller than the strip's ordinary text",
                float(field.locator(".config-label").evaluate(
                    "el => getComputedStyle(el).fontSize.replace('px','')")) <= 12,
                field.locator(".config-label").evaluate(
                    "el => getComputedStyle(el).fontSize"))
        else:
            rec("HINTS: the control is placed as a trailing field", False, "no trailing field")
        page.screenshot(path=f"{OUT}/v14-hint-scope.png")
    else:
        rec("HINTS: a Project Library script shows its settings strip", False, "no strip")

    # ---------- 3. the terminal is root ----------
    page.locator('button[aria-label="Terminal"]').click()
    page.wait_for_timeout(1000)
    page.wait_for_selector(".xterm", timeout=15000)
    page.wait_for_timeout(3500)
    # JS .focus(), NOT a click: xterm's helper textarea is positioned off-screen
    # and Playwright refuses to click it as "not visible". This is the form that
    # works in this suite — see validate_v13, where neither form does, for the
    # discrepancy nobody has explained yet.
    page.evaluate("() => document.querySelector('.xterm-helper-textarea').focus()")
    page.keyboard.type("id -u && id -un\n")
    page.wait_for_timeout(2500)
    rows = page.locator(".xterm-rows").inner_text()
    tail = rows.strip()[-120:].replace("\n", " | ")
    rec("TERM: the shell is running as root", "root" in rows.split("id -un")[-1], tail)

    page.keyboard.type("git --version\n")
    page.wait_for_timeout(2500)
    rows = page.locator(".xterm-rows").inner_text()
    # INFORMATIONAL, not a gate. git is not in the stock Ignition image and this
    # module does not put it there — the rig runs a standard image by Nigel's
    # standing rule (02/09/2026), and git is `apt-get install -y git` from this
    # very prompt, because the prompt is root. Failing the suite on it would be
    # asserting a property of the container, not of the module.
    rec("TERM: git presence on this gateway recorded", True,
        "git present" if "git version" in rows
        else "git NOT installed (stock image — apt-get install -y git from the terminal)")

    # The prompt itself has to SAY root, or the user has no standing signal that
    # this shell is privileged — bash prints # for uid 0 and $ otherwise.
    rec("TERM: the prompt marks the shell as privileged",
        "#" in rows.strip()[-400:], "")
    page.screenshot(path=f"{OUT}/v14-terminal-root.png")

    # ---------- 4. chrome sizing and row count (1.4.2) ----------
    # Nigel, 02/09/2026: "The drop downs all seem to be squished... the save
    # script button is bleeding into the edges... can't you make the hint scope
    # & Read only/override stuff all on 1 line so that it doesn't reduce the
    # script window unecessarily?"
    page.locator('button[aria-label="Terminal"]').click()   # close the panel again
    page.wait_for_timeout(400)
    page.locator(".file-tree-group", has_text="PROJECT LIBRARY").locator(
        ".file-tree-item").first.click()
    page.wait_for_timeout(1500)

    # Every control in the chrome is the same height, and none of them touches
    # the bar it sits in. A control sized by its padding and a select sized by
    # its own content never line up, which is what "squished" looked like.
    sizes = page.evaluate("""() => {
      const pick = (sel) => { const el = document.querySelector(sel); if (!el) return null;
        const r = el.getBoundingClientRect(); return { h: r.height, top: r.top, bottom: r.bottom }; };
      const bar = pick('.workspace-toolbar');
      return { bar,
               project: pick('.workspace-project select'),
               save: pick('.workspace-toolbar .button'),
               theme: pick('.theme-picker select'),
               hint: pick('.config-field-trailing select') };
    }""")
    controls = {k: v for k, v in sizes.items() if k != "bar" and v}
    heights = sorted({round(v["h"]) for v in controls.values()})
    rec("CHROME: every control in the chrome is one height",
        len(heights) == 1, f"{ {k: round(v['h']) for k, v in controls.items()} }")
    if sizes["bar"] and sizes["save"]:
        clearance = min(sizes["save"]["top"] - sizes["bar"]["top"],
                        sizes["bar"]["bottom"] - sizes["save"]["bottom"])
        rec("CHROME: the Save button does not touch the bar's edges",
            clearance >= 3, f"{clearance:.0f}px clearance")

    # THE row-count assertion. The inheritance notice and the settings used to
    # be two stacked rows above the code; they are one row now.
    #
    # Guarded on the same fixture as section 1: the notice only renders on an
    # inherited script, so with no inheritance fixture there is nothing to
    # measure. Skipped with its reason rather than left to time out.
    if not have_fixture:
        skip("LAYOUT: the inheritance notice shares the settings row",
             "no inherited script on this gateway — see the fixture skip above")
        skip("LAYOUT: chrome above the code stays under 80px",
             "needs an inherited script, which sets the taller chrome being measured")
        rows = None
    else:
        page.select_option(".workspace-project select", INHERIT_PROJECT)
        page.wait_for_timeout(2500)
        page.locator(".file-tree-row:has(.badge-inherited) .file-tree-item").first.click()
        page.wait_for_timeout(2000)
        rows = page.evaluate("""() => {
          const n = document.querySelector('.inherited-note');
          const s = document.querySelector('.config-strip');
          if (!n || !s) return null;
          return { sameRow: s.contains(n),
                   tops: [n.getBoundingClientRect().top, s.getBoundingClientRect().top] };
        }""")
        rec("LAYOUT: the inheritance notice shares the settings row",
            bool(rows and rows["sameRow"]),
            f"tops {rows['tops']}" if rows else "one of them is missing")
    if rows:
        chrome = page.evaluate("""() => {
          const ed = document.querySelector('.workspace-editor').getBoundingClientRect();
          const cm = document.querySelector('.code-editor-host:not([style*=none])');
          return cm ? cm.getBoundingClientRect().top - ed.top : null;
        }""")
        # Two 35px rows plus the tab strip was ~105px of chrome above the code on
        # an inherited script. One row brings it back under 80.
        rec("LAYOUT: chrome above the code stays under 80px",
            chrome is not None and chrome < 80, f"{chrome:.0f}px")
    page.screenshot(path=f"{OUT}/v14-one-row.png")

    # ---------- 5. the terminal fits its panel (1.4.3) ----------
    # Nigel, 02/09/2026: "The bottom of the text seems to be getting cut off
    # even though its a full screen?" FitAddon sizes from the computed height of
    # the element the canvas sits in and does NOT subtract that element's own
    # vertical padding, so 8px of padding-top fitted 11 rows (220px) into a
    # 216px content area and overflow:hidden ate the bottom of the last line.
    # A DOM measurement, because a screenshot of a terminal full of text is
    # exactly where four clipped pixels hide.
    page.locator('button[aria-label="Terminal"]').click()
    page.wait_for_selector(".xterm", timeout=15000)
    page.wait_for_timeout(3000)
    page.evaluate("() => document.querySelector('.xterm-helper-textarea').focus()")
    page.keyboard.type("for i in $(seq 1 60); do echo FIT-$i; done\n")
    page.wait_for_timeout(2500)
    fit = page.evaluate("""() => {
      const host = document.querySelector('.terminal-host');
      const rows = document.querySelector('.xterm-rows');
      if (!host || !rows) return null;
      const hs = getComputedStyle(host);
      const hb = host.getBoundingClientRect(), rb = rows.getBoundingClientRect();
      const padV = parseFloat(hs.paddingTop) + parseFloat(hs.paddingBottom);
      return { hostPadding: padV,
               contentHeight: +(hb.height - padV).toFixed(1),
               rowsHeight: +rb.height.toFixed(1),
               overhang: +(rb.bottom - hb.bottom).toFixed(1),
               rowCount: rows.children.length };
    }""")
    rec("TERM: the fitted element carries no vertical padding",
        bool(fit) and fit["hostPadding"] == 0,
        f"{fit['hostPadding']}px" if fit else "no terminal")
    rec("TERM: every row fits — the last line is not clipped",
        bool(fit) and fit["rowsHeight"] <= fit["contentHeight"] + 0.5 and fit["overhang"] <= 0.5,
        f"{fit['rowCount']} rows, {fit['rowsHeight']}px in {fit['contentHeight']}px, "
        f"overhang {fit['overhang']}px" if fit else "")
    page.screenshot(path=f"{OUT}/v14-terminal-fit.png")

    rec("CONSOLE: no page errors from our own code", not errs, "; ".join(errs[:3]))
    b.close()

passed = sum(1 for _, ok, _ in res if ok)
print(f"\n{passed}/{len(res)} checks passed")
sys.exit(0 if passed == len(res) else 1)
