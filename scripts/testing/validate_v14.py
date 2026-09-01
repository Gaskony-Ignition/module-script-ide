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
    page.wait_for_selector(".file-tree-item", timeout=20000)

    # ---------- 1. inheritance: read-only until overridden ----------
    page.select_option(".workspace-project select", INHERIT_PROJECT)
    page.wait_for_timeout(2500)

    inherited = page.locator(".file-tree-row:has(.badge-inherited) .file-tree-item").first
    have_fixture = inherited.count() > 0
    rec("FIXTURE: an inherited script exists to test against",
        have_fixture, f"project={INHERIT_PROJECT}")

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
    ta = page.locator(".xterm-helper-textarea")
    ta.click()
    page.keyboard.type("id -u && id -un\n")
    page.wait_for_timeout(2500)
    rows = page.locator(".xterm-rows").inner_text()
    tail = rows.strip()[-120:].replace("\n", " | ")
    rec("TERM: the shell is running as root", "root" in rows.split("id -un")[-1], tail)

    page.keyboard.type("git --version\n")
    page.wait_for_timeout(2500)
    rows = page.locator(".xterm-rows").inner_text()
    rec("TERM: git is on the command line",
        "git version" in rows, rows.strip()[-60:].replace("\n", " | "))

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

    rec("CONSOLE: no page errors from our own code", not errs, "; ".join(errs[:3]))
    b.close()

passed = sum(1 for _, ok, _ in res if ok)
print(f"\n{passed}/{len(res)} checks passed")
sys.exit(0 if passed == len(res) else 1)
