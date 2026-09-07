"""The console at 1.19.0: output that survives an import, and a split you can move.

Two things, both of which can only be answered on a real gateway.

**Output after an import.** Nigel, 07/09/2026: a script ran for 6.5 s, succeeded,
and printed nothing — while the same script in the Designer's console printed
what he expected. Importing a project library module runs that module through
`ScriptManager.runCode`, which moves the calling thread onto the manager's
`PySystemState` and never moves it back, so everything written after the import
went to the gateway's own console instead of the capture.

Two properties of that make it hard to see and easy to reintroduce, and both are
asserted here rather than described:

  * it only happens when the import EXECUTES code. A standard-library module
    uses Jython's own importer, and a module already in the manager's registry is
    copied across and never imported at all — so the SAME script prints on its
    second run, which is the most confusing part of the symptom. Every fixture
    below is therefore a fresh module with a name nothing has imported before.
  * an explicit `sys.stdout.write` is lost too, not just `print`. Asserting only
    on `print` would pass against a fix that repaired half of it.

**And the JVM-wide builtins table.** The fix gives each run a private builtins
table whose `__import__` restores the state. Jython hands every `PySystemState`
the same default table, so doing that in place — which is what the first attempt
did, on this rig — replaces `__import__` for the whole gateway with a closure
belonging to one console session. That is invisible from inside a run, so it is
asserted from outside one.

**The split.** The editor and the output were fixed at 45/55 and could not be put
side by side (Nigel, same day). Both the divider and the orientation are geometry,
so they are measured off the real DOM: two panes, an actual drag, and the axis
they lie on.

Run:
    SI_GATEWAY_CONFIG=$PWD/config.local.json \\
      .venv-test/bin/python scripts/testing/validate_v26_console.py
"""
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gateway_session import CONFIG, GATEWAY_URL, login          # noqa: E402
from playwright.sync_api import sync_playwright                 # noqa: E402

SPA = CONFIG.get("spa_path", "/data/scriptide/")
PROJECT = os.environ.get("SI_EDIT_PROJECT", "Mining_Demo")

# A fresh package per RUN of this suite, so every import below is a first import
# even when the suite is run twice in a row against the same gateway.
TAG = uuid.uuid4().hex[:6]
PKG = f"_si_v26_{TAG}"
LIB = "VALUE = 'library-value'\n\ndef hello():\n\treturn 'from-the-library'\n"
MODULES = ("a", "b", "c", "d", "e")
FIXTURES = tuple(f"ignition/script-python/{PKG}/{m}" for m in MODULES) \
    + (f"ignition/script-python/{PKG}",)

res = []


def rec(name, ok, detail=""):
    res.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")


# ==================== the gateway ====================

def api_write(page, csrf, path, source):
    return page.evaluate("""async ([spa, path, project, src, csrf]) => {
      const url = spa+'api/scripts/content/'+encodeURIComponent(path)
                  +'?project='+encodeURIComponent(project);
      const cur = await fetch(url, {credentials:'include', headers:{'Accept':'text/plain'}});
      const h = {'Content-Type':'application/json','X-CSRF-Token':csrf};
      if (cur.ok) h['If-Match'] = (cur.headers.get('ETag')||'').replace(/^W\\//,'').replace(/^"|"$/g,'');
      const r = await fetch(url, {method:'POST', credentials:'include', headers:h,
        body: JSON.stringify({source: src})});
      return r.status;
    }""", [SPA, path, PROJECT, source, csrf])


def api_delete(page, csrf, path):
    page.evaluate("""async ([spa, path, project, csrf]) => {
      const url = spa+'api/scripts/content/'+encodeURIComponent(path)
                  +'?project='+encodeURIComponent(project);
      const cur = await fetch(url, {credentials:'include', headers:{'Accept':'text/plain'}});
      if (!cur.ok) return;
      const tag = (cur.headers.get('ETag')||'').replace(/^W\\//,'').replace(/^"|"$/g,'');
      await fetch(url, {method:'DELETE', credentials:'include',
        headers:{'X-CSRF-Token':csrf, 'If-Match':tag}});
    }""", [SPA, path, PROJECT, csrf])


def exists(page, path):
    return page.evaluate("""async ([spa, path, project]) => {
      const url = spa+'api/scripts/content/'+encodeURIComponent(path)
                  +'?project='+encodeURIComponent(project);
      const r = await fetch(url, {credentials:'include', headers:{'Accept':'text/plain'}});
      return r.ok;
    }""", [SPA, path, PROJECT])


# ==================== the console ====================

def console_text(page):
    return page.evaluate("() => document.querySelector('.console-output')?.innerText ?? ''")


def clear_output(page):
    button = page.locator(".console-toolbar").get_by_role(
        "button", name="Clear output", exact=True)
    if button.is_enabled():
        button.click()
        page.wait_for_timeout(250)


def run_and_wait(page, source, timeout=45):
    """Run `source` on its own, and return only what THIS run produced."""
    clear_output(page)
    page.locator(".console-editor .cm-content").click()
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")
    # insert_text, never typing: CodeMirror's auto-indent would add leading
    # spaces after every colon and change the program.
    page.keyboard.insert_text(source)
    page.wait_for_timeout(250)
    page.locator(".console-toolbar").get_by_role("button", name="Run", exact=True).click()
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.locator(".console-output-head .console-running").count() == 0:
            break
        page.wait_for_timeout(150)
    page.wait_for_timeout(400)
    return console_text(page)


with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    login(page)
    page.goto(GATEWAY_URL + SPA, wait_until="load", timeout=30000)
    page.wait_for_selector(".file-tree-header", timeout=20000)
    csrf = page.evaluate(
        "async (spa) => (await (await fetch(spa+'api/auth/session',"
        "{credentials:'include'})).json()).csrfToken", SPA)
    page.select_option(".workspace-project select", PROJECT)
    page.wait_for_timeout(1500)

    made = [api_write(page, csrf, f"ignition/script-python/{PKG}/{m}", LIB) for m in MODULES]
    rec("FIXTURE: five fresh library modules were created",
        all(s == 200 for s in made), f"HTTP {made}")
    # The project index rebuilds a moment after a resource write, and an import
    # of a module the manager has not seen is the whole point of the suite.
    page.wait_for_timeout(12000)

    page.reload(wait_until="load", timeout=30000)
    page.wait_for_selector(".file-tree-header", timeout=20000)
    page.select_option(".workspace-project select", PROJECT)
    page.wait_for_timeout(1500)
    page.locator('button[aria-label="Script Console"]').click()
    page.wait_for_timeout(1000)
    page.wait_for_selector(".console-editor .cm-content", timeout=20000)

    # =================== output survives an import ===================

    out = run_and_wait(page, "print 'V26-PLAIN'\n")
    rec("BASELINE: print with no import at all reaches the output",
        "V26-PLAIN" in out, out.strip()[:70].replace("\n", " | "))

    out = run_and_wait(page, f"import {PKG}.a\nprint 'V26-AFTER-IMPORT'\n")
    rec("THE DEFECT: print after a FIRST project-library import reaches the output",
        "V26-AFTER-IMPORT" in out, out.strip()[:70].replace("\n", " | "))

    out = run_and_wait(page, f"import sys\nimport {PKG}.b\nsys.stdout.write('V26-WRITE\\n')\n")
    rec("THE DEFECT: an explicit sys.stdout.write after one does too",
        "V26-WRITE" in out, out.strip()[:70].replace("\n", " | "))

    out = run_and_wait(page, f"print 'V26-BEFORE'\nimport {PKG}.c\nprint 'V26-AFTER'\n")
    rec("BOTH SIDES: output written before AND after the import survives",
        "V26-BEFORE" in out and "V26-AFTER" in out,
        out.strip()[:80].replace("\n", " | "))

    out = run_and_wait(page, f"from {PKG}.d import hello\nprint 'V26-FROM', hello()\n")
    rec("`from X import Y` is the same path, and keeps its output",
        "V26-FROM" in out and "from-the-library" in out,
        out.strip()[:80].replace("\n", " | "))

    out = run_and_wait(page, "import json\nprint 'V26-STDLIB', json.dumps({'a': 1})\n")
    rec("a standard-library import never had the problem, and still does not",
        "V26-STDLIB" in out, out.strip()[:70].replace("\n", " | "))

    # The second run of the same code is the case that made the bug read as
    # intermittent: by then the module is in the manager's registry and the
    # import executes nothing at all.
    same = f"import {PKG}.e\nprint 'V26-REPEAT'\n"
    first = run_and_wait(page, same)
    second = run_and_wait(page, same)
    rec("the SAME script prints on the first run and the second alike",
        "V26-REPEAT" in first and "V26-REPEAT" in second,
        f"first={'V26-REPEAT' in first} second={'V26-REPEAT' in second}")

    # =================== and nothing global was mutated ===================
    # Read through PySystemState.getDefaultBuiltins() rather than the frame's own
    # __builtins__: the frame's is SUPPOSED to hold the hook, and asserting on it
    # would pass whether or not the shared table had been replaced too.
    out = run_and_wait(page, "\n".join([
        "from org.python.core import PySystemState",
        "_shared = PySystemState.getDefaultBuiltins()['__import__']",
        "print 'V26-SHARED', repr(_shared)",
        "",
    ]))
    rec("ISOLATION: the gateway's JVM-wide __import__ is still the built-in",
        "V26-SHARED" in out and "built-in function __import__" in out,
        out.strip()[:110].replace("\n", " | "))

    out = run_and_wait(page, "\n".join([
        "from org.python.core import Py, PySystemState",
        "print 'V26-PRIVATE', Py.getSystemState().getBuiltins() is "
        "PySystemState.getDefaultBuiltins()",
        "",
    ]))
    rec("ISOLATION: and this run's own table is a copy, not the shared one",
        "V26-PRIVATE False" in out, out.strip()[:90].replace("\n", " | "))

    # =================== the split ===================

    def panes():
        return page.evaluate("""() => {
          const e = document.querySelector('.console-editor');
          const o = document.querySelector('.console-output-panel');
          const r = document.querySelector('.console-body .resizer');
          const box = (n) => n ? n.getBoundingClientRect().toJSON() : null;
          return {editor: box(e), output: box(o), divider: box(r),
                  orientation: document.querySelector('.console').className};
        }""")

    before = panes()
    rec("SPLIT: the divider is there, between the editor and the output",
        before["divider"] is not None, "present" if before["divider"] else "ABSENT")
    rec("SPLIT: rows means the output is BELOW the editor",
        before["editor"] and before["output"]
        and before["output"]["y"] > before["editor"]["y"] + 40,
        f"editor y={before['editor']['y']:.0f} output y={before['output']['y']:.0f}")

    # An actual drag, not a click on the handle: the defect a divider has is that
    # it looks right and moves nothing.
    box = before["divider"]
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2 + 120, steps=12)
    page.mouse.up()
    page.wait_for_timeout(600)
    after = panes()
    grew = after["editor"]["height"] - before["editor"]["height"]
    rec("SPLIT: dragging the divider DOWN makes the editor taller",
        grew > 60, f"editor {before['editor']['height']:.0f} -> "
                   f"{after['editor']['height']:.0f} px")
    rec("SPLIT: and the output gives up what the editor gained",
        after["output"]["height"] < before["output"]["height"] - 60,
        f"output {before['output']['height']:.0f} -> {after['output']['height']:.0f} px")

    # =================== the orientation ===================

    page.locator('.console-layout-toggle button[title="Output beside the editor"]').click()
    page.wait_for_timeout(700)
    side = panes()
    rec("COLUMNS: the output moves BESIDE the editor, not below it",
        side["output"]["x"] > side["editor"]["x"] + 200
        and abs(side["output"]["y"] - side["editor"]["y"]) < 6,
        f"editor x={side['editor']['x']:.0f} output x={side['output']['x']:.0f}, "
        f"y {side['editor']['y']:.0f}/{side['output']['y']:.0f}")
    rec("COLUMNS: both panes keep a usable width",
        side["editor"]["width"] > 150 and side["output"]["width"] > 150,
        f"{side['editor']['width']:.0f} / {side['output']['width']:.0f} px")

    box = side["divider"]
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] / 2 + 140, box["y"] + box["height"] / 2, steps=12)
    page.mouse.up()
    page.wait_for_timeout(600)
    wider = panes()
    rec("COLUMNS: dragging the divider RIGHT makes the editor wider",
        wider["editor"]["width"] - side["editor"]["width"] > 70,
        f"editor {side['editor']['width']:.0f} -> {wider['editor']['width']:.0f} px")

    # The console is remounted every time the panel closes, and popping it out is
    # a whole new document — a setting that does not survive that is not a
    # setting, it is a gesture.
    page.reload(wait_until="load", timeout=30000)
    page.wait_for_selector(".file-tree-header", timeout=20000)
    page.locator('button[aria-label="Script Console"]').click()
    page.wait_for_timeout(1200)
    page.wait_for_selector(".console-editor .cm-content", timeout=20000)
    kept = panes()
    rec("REMEMBERED: the console comes back side by side after a reload",
        "console-columns" in kept["orientation"]
        and kept["output"]["x"] > kept["editor"]["x"] + 200,
        kept["orientation"])
    rec("REMEMBERED: and at the width it was dragged to",
        abs(kept["editor"]["width"] - wider["editor"]["width"]) < 40,
        f"{wider['editor']['width']:.0f} -> {kept['editor']['width']:.0f} px")

    page.locator('.console-layout-toggle button[title="Output below the editor"]').click()
    page.wait_for_timeout(700)
    back = panes()
    rec("BACK: rows restores its own remembered split, not the columns one",
        back["output"]["y"] > back["editor"]["y"] + 40,
        f"editor y={back['editor']['y']:.0f} output y={back['output']['y']:.0f}")

    # =================== the popped-out console ===================
    # The tab where the console IS the page. It used to sit inside .app-main's
    # padding, which framed it in a strip of the app's lit ground — teal at the
    # top-left on the glass packs, while the console itself painted flat.
    popped = context.new_page()
    popped.goto(f"{GATEWAY_URL}{SPA}?view=console&project={PROJECT}",
                wait_until="load", timeout=30000)
    popped.wait_for_selector(".console", timeout=20000)
    popped.wait_for_timeout(1200)
    frame = popped.evaluate("""() => {
      const main = document.querySelector('.app-main-console');
      const con = document.querySelector('.console');
      const cs = getComputedStyle(con);
      const m = main.getBoundingClientRect(), c = con.getBoundingClientRect();
      return {padding: getComputedStyle(main).padding,
              inset: [c.x - m.x, c.y - m.y, (m.x + m.width) - (c.x + c.width)],
              glow: cs.backgroundImage.slice(0, 30),
              rootGlow: getComputedStyle(document.documentElement)
                          .getPropertyValue('--page-glow').trim().slice(0, 30)};
    }""")
    rec("POP-OUT: the console fills its tab instead of sitting in a padded frame",
        max(abs(v) for v in frame["inset"]) < 1.5,
        f"inset {[round(v, 1) for v in frame['inset']]}, padding {frame['padding']}")
    rec("POP-OUT: and it carries the theme's own ground rather than painting over it",
        frame["glow"].startswith(frame["rootGlow"][:12]) or frame["rootGlow"] == "none",
        f"console {frame['glow']!r} vs root {frame['rootGlow']!r}")
    popped.close()

    # =================== clean up ===================
    for path in FIXTURES:
        api_delete(page, csrf, path)
        page.wait_for_timeout(700)
    left = [f for f in FIXTURES if exists(page, f)]
    rec("CLEANUP: every fixture this suite created was removed",
        not left, ", ".join(left) or "none left")

    browser.close()

passed = sum(1 for _, ok, _ in res if ok)
print(f"\n{passed}/{len(res)} checks passed")
sys.exit(0 if passed == len(res) else 1)
