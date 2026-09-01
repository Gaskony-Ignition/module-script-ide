"""Live checks for 1.3.0: bottom panel, layout controls, terminal, tree parity."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gateway_session import CONFIG, GATEWAY_URL, login
from playwright.sync_api import sync_playwright

SPA = CONFIG.get("spa_path", "/data/scriptide/")
OUT = os.environ.get("SI_SHOT_DIR", "/tmp")
res = []
def rec(n, ok, d=""):
    res.append((n, ok, d)); print(f"  [{'PASS' if ok else 'FAIL'}] {n}: {d}")

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_context(viewport={"width": 1600, "height": 1000}).new_page()
    errs, reqfail = [], []
    # Attribute by SOURCE, not by message: the gateway's own login page logs a
    # 401 and a URL TypeError from ia-gateway.js before our SPA is even loaded,
    # and counting those as ours means the check can never pass.
    page.on("console", lambda m: errs.append(f"{m.text} @ {m.location.get('url','')}")
            if m.type == "error" and "/res/sys/" not in m.location.get("url", "")
            and "/data/app/session" not in m.location.get("url", "") else None)
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.on("response", lambda r: reqfail.append(f"{r.status} {r.url}")
            if r.status >= 400 and "scriptide" in r.url else None)
    login(page)
    page.goto(GATEWAY_URL + SPA, wait_until="load", timeout=30000)
    page.wait_for_selector(".file-tree-item", timeout=20000)

    # ---------- 1. tree parity ----------
    rec("TREE: no Script Console row",
        page.locator(".file-tree button", has_text="Script Console").count() == 0, "")
    labels = page.locator(".file-tree button").all_inner_texts()
    labels = [l.strip().split("\n")[0] for l in labels]
    want = ["Message Handler", "Scheduled", "Tag Change", "Timer", "Shutdown", "Startup", "Update"]
    idx = [next((i for i, l in enumerate(labels) if l.startswith(w)), -1) for w in want]
    rec("TREE: folders then singletons, Designer order",
        all(i >= 0 for i in idx) and idx == sorted(idx), f"{list(zip(want, idx))}")
    for name in ("Startup", "Shutdown", "Update"):
        row = page.locator(f".file-tree button:has-text('{name}')").first
        rec(f"TREE: {name} is a row, not a folder",
            row.get_attribute("aria-expanded") is None, "")

    # ---------- 2. layout controls ----------
    for label, selector in (("primary side bar", ".workspace-rail"),
                            ("secondary side bar", ".outline")):
        btn = page.locator(f'button[aria-label="Toggle {label}"]')
        before = page.locator(selector).count()
        btn.click(); page.wait_for_timeout(350)
        after = page.locator(selector).count()
        btn.click(); page.wait_for_timeout(350)
        rec(f"LAYOUT: {label} toggles", before != after, f"{before} -> {after}")

    panel_btn = page.locator('button[aria-label="Toggle panel"]')
    panel_btn.click(); page.wait_for_timeout(500)
    rec("LAYOUT: panel opens at the BOTTOM", page.locator(".panel").count() == 1, "")
    if page.locator(".panel").count():
        box_p = page.locator(".panel").bounding_box()
        box_e = page.locator(".workspace-editor").bounding_box()
        rec("LAYOUT: panel is below the editor, not beside it",
            box_p["y"] > box_e["y"] and abs(box_p["x"] - box_e["x"]) < 4,
            f"panel y={box_p['y']:.0f} editor y={box_e['y']:.0f}")
    # customise-layout menu
    page.locator('button[aria-label="Customise layout"]').click()
    page.wait_for_timeout(300)
    rec("LAYOUT: customise menu lists the three areas",
        page.locator('[role="menuitemcheckbox"]').count() == 3, "")
    page.keyboard.press("Escape")

    # ---------- 3. console tab still works ----------
    page.locator('.panel-tab:has-text("Script Console")').click()
    page.wait_for_timeout(800)
    cm = page.locator(".console-editor .cm-content")
    if cm.count():
        cm.click(); page.keyboard.press("Control+A")
        page.keyboard.type("print 'panel console alive'")
        page.locator(".console-toolbar button:has-text('Run')").first.click()
        page.wait_for_timeout(4000)
        out = page.locator(".console-output").inner_text()
        rec("PANEL: console runs in the bottom panel",
            "panel console alive" in out, out[:70].replace("\n", " "))

    # ---------- 4. terminal ----------
    page.locator('button[aria-label="Terminal"]').click()
    page.wait_for_timeout(1000)
    page.wait_for_selector(".xterm", timeout=15000)
    page.wait_for_timeout(3000)
    rows = page.locator(".xterm-rows").inner_text()
    rec("TERM: a shell prompt appeared", "$" in rows or "#" in rows, rows.strip()[-70:].replace("\n", " | "))

    ta = page.locator(".xterm-helper-textarea")
    ta.click()
    page.keyboard.type("echo SCRIPTIDE-TERM-OK && pwd\n")
    page.wait_for_timeout(3000)
    rows = page.locator(".xterm-rows").inner_text()
    rec("TERM: a command runs and its output comes back",
        "SCRIPTIDE-TERM-OK" in rows, rows.strip()[-90:].replace("\n", " | "))
    rec("TERM: starts in the Gateway data directory",
        "/usr/local/bin/ignition/data" in rows, "")
    page.keyboard.type("stty size\n")
    page.wait_for_timeout(1500)
    rows = page.locator(".xterm-rows").inner_text()
    rec("TERM: the shell was told a real window size",
        "0 0" not in rows.split("stty size")[-1][:40], rows.strip()[-50:].replace("\n", " | "))
    page.keyboard.type("git --version\n")
    page.wait_for_timeout(2000)
    rows = page.locator(".xterm-rows").inner_text()
    rec("TERM: git status on this gateway recorded",
        True, "git present" if "git version" in rows else "git NOT installed in the container")
    page.screenshot(path=f"{OUT}/v13-terminal.png")

    # maximise / restore
    page.locator('button[aria-label="Maximise panel"]').click()
    page.wait_for_timeout(400)
    editor_hidden = page.locator(".workspace-editor").is_hidden()
    page.locator('button[aria-label="Restore panel size"]').click()
    page.wait_for_timeout(400)
    rec("PANEL: maximise hides the editor and restore brings it back",
        editor_hidden and page.locator(".workspace-editor").is_visible(), "")

    # ---------- 5. fonts ----------
    fam = page.evaluate("getComputedStyle(document.body).fontFamily")
    rec("FONT: UI stack is not a serif", "serif" not in fam.lower().replace("sans-serif", ""), fam[:60])

    # Measure the ADVANCE WIDTH, not the family string. `ui-monospace` is
    # unrecognised by Chrome on Linux and falls through to a PROPORTIONAL face
    # when it is the only entry — 'iiiiiiiiii' 36.1px against 'WWWWWWWWWW'
    # 122.7px, measured 01/09/2026. A stack whose name contains "mono" proves
    # nothing about what the browser actually drew.
    widths = page.evaluate("""() => {
      const el = document.querySelector('.cm-content') || document.body;
      const s = getComputedStyle(el);
      const c = document.createElement('canvas').getContext('2d');
      c.font = s.fontSize + ' ' + s.fontFamily;
      return { i: c.measureText('iiiiiiiiii').width,
               W: c.measureText('WWWWWWWWWW').width,
               size: s.fontSize, family: s.fontFamily };
    }""")
    rec("FONT: the editor actually renders monospaced",
        abs(widths["i"] - widths["W"]) < 0.5,
        f'i={widths["i"]:.1f} W={widths["W"]:.1f} at {widths["size"]}')

    # -webkit-font-smoothing: antialiased forces GREYSCALE antialiasing, which on
    # Linux is thinner and softer than the platform default's subpixel RGB. It
    # was set in 1.3.0 and is the reason this looked washed out beside VS Code.
    rec("FONT: platform antialiasing, not forced greyscale",
        page.evaluate("getComputedStyle(document.body).webkitFontSmoothing") in ("auto", "", None),
        page.evaluate("getComputedStyle(document.body).webkitFontSmoothing"))

    # ---------- 6. themes ----------
    opts = page.locator('select[aria-label="Theme"] option')
    ids = opts.evaluate_all("els => els.map(e => e.value)")
    rec("THEMES: ten offered", len(ids) == 10, f"{len(ids)}")
    seen = {}
    dupes = []
    for tid in ids:
        page.select_option('select[aria-label="Theme"]', tid)
        page.wait_for_timeout(350)
        tokens = page.evaluate("""() => {
          const s = getComputedStyle(document.documentElement);
          return ['--bg-primary','--bg-secondary','--text-primary','--accent-primary',
                  '--syntax-keyword','--syntax-type','--error','--success','--warning']
            .map(n => s.getPropertyValue(n).trim()).join('|');
        }""")
        if tokens in seen:
            dupes.append(f"{seen[tokens]} == {tid}")
        seen[tokens] = tid
    rec("THEMES: no two themes share a palette", not dupes, "; ".join(dupes))

    page.select_option('select[aria-label="Theme"]', "aurora-teal")
    page.wait_for_timeout(400)
    teal = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--bg-primary').trim()")
    page.screenshot(path=f"{OUT}/v13-aurora-teal.png")
    page.select_option('select[aria-label="Theme"]', "aurora-violet")
    page.wait_for_timeout(400)
    violet = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--bg-primary').trim()")
    page.screenshot(path=f"{OUT}/v13-aurora-violet.png")
    rec("THEMES: Glass Aurora Teal is not violet", teal != violet, f"teal={teal} violet={violet}")

    page.select_option('select[aria-label="Theme"]', "nord-dark-frost")
    page.wait_for_timeout(400)
    page.screenshot(path=f"{OUT}/v13-full.png")

    rec("NO FAILED REQUESTS", not reqfail, "; ".join(reqfail[:3])[:200] or "none")
    rec("NO CONSOLE ERRORS", not errs, "; ".join(errs[:3])[:250] or "none")
    b.close()

print()
bad = [n for n, ok, _ in res if not ok]
print(f"{'FAIL' if bad else 'PASS'}: {len(res)-len(bad)}/{len(res)}")
sys.exit(1 if bad else 0)
