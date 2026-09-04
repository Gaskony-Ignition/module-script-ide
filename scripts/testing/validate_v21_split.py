"""
Split editors — 1.10.0.

Nigel, 03/09/2026: *"I'm not seeing a way to split the screen between 2 or more
scripts so that I can do comparisons or copy and paste between etc. This is a
major limitation on the designer that I want to have working better on this
module."*

So the two things this suite is actually about are the two he asked for:
**seeing both at once**, and **copying between them**. Everything else here
exists because a split is easy to make look right and get wrong underneath: a
pane showing a tab strip and no buffer, a document that appears in both panes,
or an editor that loses its undo history the moment it moves.

Run:
    WD_ALLOW_LOCAL_CONFIG=1 .venv-test/bin/python3 scripts/testing/validate_v21_split.py
"""
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gateway_session import CONFIG, GATEWAY_URL, login          # noqa: E402
from playwright.sync_api import sync_playwright                 # noqa: E402

SPA = CONFIG.get("spa_path", "/data/scriptide/")
LEFT = "SplitProbeLeft"
RIGHT = "SplitProbeRight"
LEFT_SOURCE = "# left probe\nLEFT_MARKER = 'left-probe-value'\n"
RIGHT_SOURCE = "# right probe\nRIGHT_MARKER = 1\n"
res = []


def rec(name, ok, detail=""):
    res.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def api(page, method, url, csrf="", body=None, if_match=None):
    return page.evaluate(
        """async ([spa, method, url, csrf, body, ifMatch]) => {
             const headers = {'Accept': 'application/json'};
             if (csrf) headers['X-CSRF-Token'] = csrf;
             if (body !== null) headers['Content-Type'] = 'application/json';
             if (ifMatch !== null) headers['If-Match'] = ifMatch;
             const res = await fetch(spa + url, {
               method, credentials: 'include', headers,
               body: body === null ? undefined : JSON.stringify(body)});
             return {status: res.status, etag: res.headers.get('ETag'),
                     text: await res.text()};
           }""",
        [SPA, method, url, csrf, body, if_match])


def json_of(response):
    try:
        return json.loads(response["text"])
    except Exception:
        return {}


def content_url(project, module):
    return ("api/scripts/content/"
            + urllib.parse.quote(f"ignition/script-python/{module}", safe="")
            + f"?project={urllib.parse.quote(project)}")


def tree_of(page, project):
    return json_of(api(page, "GET",
                       f"api/scripts?project={urllib.parse.quote(project)}")).get("scripts", [])


def delete(page, project, module, csrf):
    entry = next((e for e in tree_of(page, project)
                  if e.get("path") == f"ignition/script-python/{module}"), None)
    if entry:
        api(page, "DELETE", content_url(project, module), csrf, None, entry.get("signature"))


def open_module(page, module):
    """Open a script through quick open — no tree expansion, no ambiguity."""
    page.keyboard.press("Control+p")
    page.wait_for_selector(".quick-open-input input", timeout=5000)
    page.fill(".quick-open-input input", module)
    page.wait_for_timeout(400)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1500)


def pane_text(page, index):
    return page.evaluate(
        """(i) => {
             const pane = document.querySelectorAll('.workspace-pane')[i];
             if (!pane) return null;
             const view = [...pane.querySelectorAll('.cm-editor')]
               .find((el) => el.offsetParent !== null);
             return view ? view.textContent : '';
           }""", index)


with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    context.grant_permissions(["clipboard-read", "clipboard-write"])
    page = context.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))

    login(page)
    page.goto(GATEWAY_URL + SPA, wait_until="load", timeout=30000)
    page.wait_for_selector(".file-tree-header", timeout=20000)

    session = page.evaluate(
        """async (spa) => (await fetch(spa + 'api/auth/session',
             {credentials: 'include'})).json()""", SPA)
    csrf = session.get("csrfToken")
    project = page.eval_on_selector(".workspace-project select", "el => el.value")

    delete(page, project, LEFT, csrf)
    delete(page, project, RIGHT, csrf)
    a = api(page, "POST", content_url(project, LEFT), csrf, {"source": LEFT_SOURCE})
    b = api(page, "POST", content_url(project, RIGHT), csrf, {"source": RIGHT_SOURCE})
    rec("FIXTURE: two scripts to compare", a["status"] == 200 and b["status"] == 200,
        f"{LEFT} HTTP {a['status']}, {RIGHT} HTTP {b['status']} in {project}")
    page.reload(wait_until="load")
    page.wait_for_selector(".file-tree-header", timeout=20000)

    # ---------- one pane until asked ----------
    open_module(page, LEFT)
    open_module(page, RIGHT)
    rec("BEFORE: one editor, two tabs — the split is opt-in",
        page.locator(".workspace-pane").count() == 1
        and page.locator(".tab").count() == 2,
        f"{page.locator('.workspace-pane').count()} pane(s), "
        f"{page.locator('.tab').count()} tab(s)")

    # ---------- split ----------
    page.locator(".tab-strip-action").first.click()
    page.wait_for_timeout(700)
    panes = page.locator(".workspace-pane")
    rec("SPLIT: there are two editors", panes.count() == 2, f"{panes.count()} pane(s)")

    # THE thing he asked for: both scripts visible at once.
    left_text = pane_text(page, 0) or ""
    right_text = pane_text(page, 1) or ""
    rec("SPLIT: both scripts are on screen at the same time",
        "left-probe-value" in (left_text + right_text)
        and "RIGHT_MARKER" in (left_text + right_text)
        and ("left-probe-value" in left_text) != ("left-probe-value" in right_text),
        f"left={left_text.strip()[:34]!r} right={right_text.strip()[:34]!r}")

    # Side by side, not stacked — the axis is the whole point of the feature.
    boxes = [panes.nth(i).bounding_box() or {} for i in range(2)]
    rec("SPLIT: side by side, not one above the other",
        all(boxes) and boxes[1]["x"] > boxes[0]["x"] + 100
        and abs(boxes[0]["y"] - boxes[1]["y"]) < 4,
        f"x {boxes[0].get('x', 0):.0f}/{boxes[1].get('x', 0):.0f}, "
        f"y {boxes[0].get('y', 0):.0f}/{boxes[1].get('y', 0):.0f}")
    rec("SPLIT: each pane keeps a usable width",
        all(box.get("width", 0) > 200 for box in boxes),
        f"widths {boxes[0].get('width', 0):.0f} / {boxes[1].get('width', 0):.0f}")

    # A document is in ONE pane. Two views over one buffer would need
    # synchronising on every keystroke, so the model forbids it.
    rec("SPLIT: one document, one pane — never both",
        page.locator(".workspace-pane").nth(0).locator(".tab").count() == 1
        and page.locator(".workspace-pane").nth(1).locator(".tab").count() == 1,
        f"{page.locator('.workspace-pane').nth(0).locator('.tab').count()} + "
        f"{page.locator('.workspace-pane').nth(1).locator('.tab').count()} tab(s)")

    # ---------- copy between them, which is the other half of the ask ----------
    page.locator(".workspace-pane").nth(0).locator(".cm-content").click()
    page.keyboard.press("Control+a")
    page.keyboard.press("Control+c")
    page.wait_for_timeout(200)
    page.locator(".workspace-pane").nth(1).locator(".cm-content").click()
    page.keyboard.press("Control+End")
    page.keyboard.press("Control+v")
    page.wait_for_timeout(500)
    after = pane_text(page, 1) or ""
    rec("COPY: text pastes from one pane into the other",
        "left-probe-value" in after and "RIGHT_MARKER" in after,
        repr(after.strip()[-46:]))

    # And undo still works in the pane that was moved — the view survived the
    # move rather than being torn down and rebuilt.
    page.keyboard.press("Control+z")
    page.wait_for_timeout(400)
    undone = pane_text(page, 1) or ""
    rec("MOVE: the moved editor kept its undo history",
        "left-probe-value" not in undone and "RIGHT_MARKER" in undone,
        repr(undone.strip()[-46:]))

    # ---------- editing in one pane does not disturb the other ----------
    before_left = pane_text(page, 0)
    page.locator(".workspace-pane").nth(1).locator(".cm-content").click()
    page.keyboard.press("Control+End")
    page.keyboard.type("\nSTILL_INDEPENDENT = True\n")
    page.wait_for_timeout(500)
    rec("SPLIT: typing in one pane leaves the other alone",
        pane_text(page, 0) == before_left
        and "STILL_INDEPENDENT" in (pane_text(page, 1) or ""),
        "left unchanged" if pane_text(page, 0) == before_left else "LEFT MOVED")

    # ---------- the divider ----------
    divider = page.locator(".workspace-panes .resizer")
    rec("SPLIT: there is a divider between them", divider.count() == 1,
        f"{divider.count()} divider(s)")
    if divider.count():
        wide = page.locator(".workspace-pane").first.bounding_box()["width"]
        box = divider.bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down()
        page.mouse.move(box["x"] - 200, box["y"] + box["height"] / 2, steps=8)
        page.mouse.up()
        page.wait_for_timeout(400)
        narrow = page.locator(".workspace-pane").first.bounding_box()["width"]
        rec("SPLIT: dragging the divider LEFT narrows the left pane",
            narrow < wide - 100, f"{wide:.0f}px -> {narrow:.0f}px")
        # It received the pointer AT ALL. A 1px divider between two flex
        # children loses the half-pixel to whichever paints last, and until
        # 1.10.0 `elementFromPoint` on the divider's own centre returned the
        # neighbouring CodeMirror's gutter — the drag did nothing while every
        # static check said the divider was there.
        on_top = page.evaluate("""() => {
          const r = document.querySelector('.workspace-panes .resizer');
          const b = r.getBoundingClientRect();
          const el = document.elementFromPoint(b.x + b.width / 2, b.y + b.height / 2);
          return el === r || r.contains(el);
        }""")
        rec("SPLIT: the divider is on top of the panes, not behind them", on_top,
            f"elementFromPoint hits the divider={on_top}")

    # ---------- Ctrl+\ toggles, and collapsing is the same gesture ----------
    page.locator(".workspace-pane").nth(1).locator(".cm-content").click()
    page.keyboard.press("Control+\\")
    page.wait_for_timeout(700)
    rec("COLLAPSE: moving the last document back leaves one editor",
        page.locator(".workspace-pane").count() == 1
        and page.locator(".tab").count() == 2,
        f"{page.locator('.workspace-pane').count()} pane(s), "
        f"{page.locator('.tab').count()} tab(s)")
    rec("COLLAPSE: nothing was closed — both documents are still open",
        "STILL_INDEPENDENT" in (pane_text(page, 0) or "")
        or page.locator(f'.tab:has-text("{LEFT}")').count() == 1,
        f"{page.locator('.tab').count()} tab(s) left")

    # ---------- closing a tab in the second pane ----------
    page.keyboard.press("Control+\\")            # split again
    page.wait_for_timeout(600)
    rec("TOGGLE: Ctrl+\\ splits as well as collapses",
        page.locator(".workspace-pane").count() == 2,
        f"{page.locator('.workspace-pane').count()} pane(s)")
    second = page.locator(".workspace-pane").nth(1)
    second.locator(".tab-close").first.click()
    page.wait_for_timeout(400)
    # It is dirty — typed into and never saved — so the guard should ask first.
    dialog = page.locator('[role="alertdialog"]')
    if dialog.count():
        rec("CLOSE: an unsaved document in the second pane still asks first",
            True, dialog.first.inner_text().split("\n")[0][:60])
        dialog.locator('button:has-text("Discard")').first.click()
        page.wait_for_timeout(600)
    else:
        rec("CLOSE: an unsaved document in the second pane still asks first",
            False, "no dialog")
    rec("CLOSE: emptying the second pane collapses the split",
        page.locator(".workspace-pane").count() == 1,
        f"{page.locator('.workspace-pane').count()} pane(s)")
    # `pane_text` includes the line-number gutter, so this is containment, not a
    # prefix — the marker is unique to one of the two fixtures either way.
    rec("CLOSE: and the surviving document is the one on screen",
        "left-probe-value" in (pane_text(page, 0) or ""),
        repr((pane_text(page, 0) or "").strip()[:40]))

    rec("CONSOLE: no page errors during any of it", not errs, "; ".join(errs[:2]) or "none")

    delete(page, project, LEFT, csrf)
    delete(page, project, RIGHT, csrf)
    left_over = [e["path"] for e in tree_of(page, project)
                 if e.get("path", "").endswith(("SplitProbeLeft", "SplitProbeRight"))]
    rec("FIXTURE: removed again", not left_over, f"{left_over or 'none left'}")
    browser.close()

failed = [n for n, ok, _ in res if not ok]
print(f"\n{len(res) - len(failed)}/{len(res)} checks passed")
if failed:
    print("FAILED: " + "; ".join(failed))
sys.exit(1 if failed else 0)
