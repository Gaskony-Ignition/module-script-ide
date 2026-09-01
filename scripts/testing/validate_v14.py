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

        rec("EDIT: opening an inherited script says so, in a bar",
            page.locator(".inherited-bar").count() == 1,
            page.locator(".inherited-bar").inner_text().replace("\n", " ")[:90]
            if page.locator(".inherited-bar").count() else "no bar")

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
        override = page.locator(".inherited-bar-action").first
        rec("OVERRIDE: the bar carries the action that unlocks it",
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
            rec("OVERRIDE: the bar now explains the save, not the lock",
                page.locator(".inherited-bar.is-override").count() == 1,
                page.locator(".inherited-bar").inner_text().replace("\n", " ")[:90]
                if page.locator(".inherited-bar").count() else "")
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
        rec("HINTS: the control explains itself",
            page.locator(".config-help").count() >= 1,
            page.locator(".config-help").first.inner_text()[:70]
            if page.locator(".config-help").count() else "no help line")
        # A help line that pushes the controls onto separate rows is a
        # regression: it is a whole flex row of its own or it is wrong.
        if page.locator(".config-help").count():
            help_box = page.locator(".config-help").first.bounding_box()
            field_box = page.locator(".config-field").first.bounding_box()
            rec("HINTS: the help sits BELOW the control, not beside it",
                help_box["y"] >= field_box["y"] + field_box["height"] - 2,
                f"help y={help_box['y']:.0f} field bottom={field_box['y'] + field_box['height']:.0f}")
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

    rec("CONSOLE: no page errors from our own code", not errs, "; ".join(errs[:3]))
    b.close()

passed = sum(1 for _, ok, _ in res if ok)
print(f"\n{passed}/{len(res)} checks passed")
sys.exit(0 if passed == len(res) else 1)
