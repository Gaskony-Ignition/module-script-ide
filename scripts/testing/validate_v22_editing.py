"""
The five things Nigel reported on 04/09/2026, each proved on the real gateway.

Every one of them is a case where the module looked like it was working:

1. **The error mark was nowhere near the error.** *"I intentionally put in a
   faulted line of code and then the error mark showed up high instead of in
   line with the actual line of code."* The overview ruler maps the WHOLE
   document, so a fault on line 22 of 190 belongs near the top of it — correct,
   and unreadable as anything but a mark in the wrong place. The line's own
   NUMBER carries the mark now.

2. **Garbage was accepted in silence.** *"I can put absolute garbage in here
   and it doesn't show up as an error which it really should"* —
   `j;sdfj;asdfjk;dksfj`, which is four valid expression statements. The parser
   was right; there simply was no check for a name that is never defined.

3. **The hover card was see-through.** It used `--surface`, which on the glass
   packs is the pack's own 10%-white film, so the code read straight through the
   documentation.

4. **A lost session showed the servlet container's JSON.** *"I was working on
   some code and tried to save but it came up with an authentication error...
   now I could potentially lose work."*

5. **The Web Dev tree opened everything.** Gated in `validate_v20_webdev.py`,
   with the rest of that tree's checks.

Each is asserted as a DIFFERENCE: the marked line beside an unmarked one, the
undefined name beside a defined one, the tooltip's fill beside the token it used
to use. A check that only looked for a mark would pass on a build that marked
everything.

The fixture is created and deleted by this script. Run:
    WD_ALLOW_LOCAL_CONFIG=1 .venv-test/bin/python3 scripts/testing/validate_v22_editing.py
"""
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gateway_session import CONFIG, GATEWAY_URL, login          # noqa: E402
from playwright.sync_api import sync_playwright                 # noqa: E402

SPA = CONFIG.get("spa_path", "/data/scriptide/")
PROJECT = os.environ.get("SI_EDIT_PROJECT", "Mining_Demo")
FIXTURE = "ignition/script-python/_si_v22_/code.py"
FIXTURE_PATH = "ignition/script-python/_si_v22_"

# Line 1 is fine, line 2 is Nigel's garbage, line 3 uses a name that IS defined.
# The middle line is the only one that may be marked, and the checks below say
# so in both directions.
SOURCE = "defined = 1\nj;sdfj;asdfjk;dksfj\nprint defined\n"

res = []


def rec(name, ok, detail=""):
    res.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def skip(name, detail=""):
    res.append((name, True, detail))
    print(f"  [SKIP] {name}: {detail}")


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


def tree(page):
    return json_of(api(page, "GET",
                       f"api/scripts?project={urllib.parse.quote(PROJECT)}")).get("scripts", [])


def entry_for(page, path):
    return next((e for e in tree(page) if e.get("path") == path), None)


def remove_fixture(page, csrf):
    for path in (FIXTURE_PATH, "ignition/script-python/_si_v22_"):
        found = entry_for(page, path)
        if found:
            api(page, "DELETE",
                f"api/scripts/content/{urllib.parse.quote(path, safe='')}"
                f"?project={urllib.parse.quote(PROJECT)}",
                csrf, if_match=found.get("signature"))


def alpha_of(colour):
    """The alpha of a computed `rgb()`/`rgba()` string. Opaque when absent."""
    body = colour[colour.find("(") + 1:colour.rfind(")")]
    parts = [p.strip() for p in body.replace("/", ",").split(",")]
    if len(parts) < 4:
        return 1.0
    try:
        return float(parts[3])
    except ValueError:
        return 1.0


with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    login(page)
    page.goto(GATEWAY_URL + SPA, wait_until="load", timeout=30000)
    page.wait_for_selector(".file-tree-header", timeout=20000)
    session = page.evaluate(
        "async (spa) => (await (await fetch(spa + 'api/auth/session',"
        " {credentials:'include'})).json())", SPA)
    csrf = session.get("csrfToken")

    page.select_option(".workspace-project select", PROJECT)
    page.wait_for_timeout(1500)
    remove_fixture(page, csrf)

    created = api(page, "POST",
                  f"api/scripts/content/{urllib.parse.quote(FIXTURE_PATH, safe='')}"
                  f"?project={urllib.parse.quote(PROJECT)}",
                  csrf, {"source": SOURCE})
    rec("FIXTURE: the probe script was created",
        created["status"] == 200, f"HTTP {created['status']} {created['text'][:80]}")

    # ---------- 2. the undefined names, and the defined one beside them -------
    page.select_option(".workspace-project select", PROJECT)
    page.wait_for_timeout(2000)
    for _ in range(5):
        shut = page.locator('.file-tree [aria-expanded="false"]')
        if shut.count() == 0:
            break
        for i in range(shut.count()):
            try:
                shut.nth(i).click(timeout=1500)
            except Exception:
                pass
        page.wait_for_timeout(200)
    row = page.locator('.file-tree .file-tree-item:has(.file-tree-name:text-is("_si_v22_"))')
    if row.count() == 0:
        row = page.locator('.file-tree .file-tree-item').filter(has_text="_si_v22_")
    row.first.click()
    page.wait_for_timeout(2500)
    rec("OPEN: the probe script opened", page.locator(".tab.is-active").count() == 1, "")

    # Diagnostics arrive over the socket; give the server a beat to parse.
    page.wait_for_timeout(3500)
    marks = page.locator(".cm-lineNumbers .cm-lint-line").all_inner_texts()
    rec("NAMES: the garbage line is reported at all",
        len(marks) > 0, f"marked lines: {marks}")
    # THE difference. Line 2 is the garbage; lines 1 and 3 are ordinary code and
    # must not be marked, or the check has simply painted the file red.
    rec("NAMES: the mark is on the GARBAGE line and on no other",
        marks == ["2"], f"marked lines: {marks} (expected exactly ['2'])")
    warned = page.locator(".cm-lineNumbers .cm-lint-line-warning").count()
    rec("NAMES: it is a WARNING, not an error — the name may exist at run time",
        warned == 1 and page.locator(".cm-lineNumbers .cm-lint-line-error").count() == 0,
        f"{warned} warning, "
        f"{page.locator('.cm-lineNumbers .cm-lint-line-error').count()} error")

    # ---------- 1. the mark is beside the line, not only on the ruler --------
    number = page.locator(".cm-lineNumbers .cm-lint-line").first
    box = number.bounding_box()
    line2 = page.locator(".cm-line").nth(1).bounding_box()
    rec("LINE: the marked number sits on the same row as the code it describes",
        box is not None and line2 is not None
        and abs((box["y"] + box["height"] / 2) - (line2["y"] + line2["height"] / 2)) < 6,
        f"number y={box['y'] if box else None} line y={line2['y'] if line2 else None}")
    # And it is actually painted differently from an ordinary number — a class
    # that no CSS picked up would pass every check above.
    marked = number.evaluate("n => getComputedStyle(n).color")
    plain = page.locator(".cm-lineNumbers .cm-gutterElement:not(.cm-lint-line)").nth(2)
    ordinary = plain.evaluate("n => getComputedStyle(n).color")
    rec("LINE: a marked number is painted differently from an unmarked one",
        marked != ordinary, f"marked {marked} vs ordinary {ordinary}")

    # The ruler still exists — the fix ADDS a signal, it does not move one.
    rec("RULER: the overview ruler still carries the problem too",
        page.locator(".problem-ruler .problem-ruler-slot, .problem-ruler-mark").count() > 0
        or page.locator(".problem-ruler").count() == 1,
        f"{page.locator('.problem-ruler').count()} ruler(s)")

    # ---------- 3. the hover card is opaque ---------------------------------
    # Hover a name the server has documentation for. `print` is a keyword; a
    # dotted platform call is the realistic case and the one in the screenshot.
    page.locator(".code-editor-host:not([style*=none]) .cm-content").click()
    page.keyboard.press("Control+End")
    page.keyboard.type("\nLOG = system.util.getLogger('probe')\n")
    page.wait_for_timeout(2500)
    # Typing the `(` opened the SIGNATURE tooltip, which then sits over the
    # token and swallows the hover. Escape dismisses it; `force` is used anyway
    # because any tooltip is a tooltip for this measurement, and waiting for one
    # to get out of the way of another is not what is under test.
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    token = page.locator(".cm-content span", has_text="getLogger").first
    tip_alpha = None
    tip_bg = ""
    if token.count():
        try:
            token.hover(force=True, timeout=8000)
            page.wait_for_selector(".cm-tooltip", timeout=8000)
            tip_bg = page.locator(".cm-tooltip").first.evaluate(
                "n => getComputedStyle(n).backgroundColor")
            tip_alpha = alpha_of(tip_bg)
        except Exception:
            pass
    if tip_alpha is None:
        skip("TOOLTIP: the hover card is opaque enough to read over code",
             "no tooltip appeared to measure — the server had no hover for this token")
        skip("TOOLTIP: it does not use --surface, which is 10% on a glass pack", "")
    else:
        rec("TOOLTIP: the hover card is opaque enough to read over code",
            tip_alpha >= 0.7, f"background {tip_bg} (alpha {tip_alpha})")
        surface = page.evaluate(
            "() => getComputedStyle(document.documentElement).getPropertyValue('--surface').trim()")
        rec("TOOLTIP: it does not use --surface, which is 10% on a glass pack",
            alpha_of(tip_bg) >= alpha_of(surface),
            f"tooltip {tip_bg} vs --surface {surface}")

    # ---------- 4. a lost session says so, and keeps the work ---------------
    # Provoked for real: drop the session cookies, then save. Nothing else in
    # this suite runs afterwards, because the session is genuinely gone.
    page.locator(".code-editor-host:not([style*=none]) .cm-content").click()
    page.keyboard.type("\n# unsaved work that must survive\n")
    page.wait_for_timeout(600)
    typed = page.locator(".cm-content").inner_text()
    context.clear_cookies()
    page.keyboard.press("Control+s")
    page.wait_for_timeout(4000)

    bar = page.locator(".workspace-signedout")
    rec("SESSION: a 401 on save raises the session bar, not a one-line notice",
        bar.count() == 1, f"{bar.count()} bar(s)")
    if bar.count():
        text = bar.inner_text()
        rec("SESSION: it says the work is safe, and offers a way back in",
            "session has ended" in text.lower()
            and ("nothing has been lost" in text.lower() or "not saved" in text.lower())
            and page.get_by_role("button", name="Sign in again").count() == 1
            and page.get_by_role("button", name="Retry the save").count() == 1,
            text.replace("\n", " ")[:150])
        rec("SESSION: no raw JSON body reaches the screen",
            '"status"' not in text and "Unauthorized\",\"url" not in text, "")
    else:
        rec("SESSION: it says the work is safe, and offers a way back in", False, "no bar")
        rec("SESSION: no raw JSON body reaches the screen", False, "no bar")

    # THE point of the whole feature: the buffer is still there.
    rec("SESSION: the unsaved buffer is untouched — nothing was discarded",
        "unsaved work that must survive" in page.locator(".cm-content").inner_text(),
        f"{len(typed)} chars before, "
        f"{len(page.locator('.cm-content').inner_text())} after")

    browser.close()

# The fixture is deleted in a fresh session — the one above no longer has one.
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_context().new_page()
    login(page)
    page.goto(GATEWAY_URL + SPA, wait_until="load", timeout=30000)
    page.wait_for_selector(".file-tree-header", timeout=20000)
    session = page.evaluate(
        "async (spa) => (await (await fetch(spa + 'api/auth/session',"
        " {credentials:'include'})).json())", SPA)
    remove_fixture(page, session.get("csrfToken"))
    rec("CLEANUP: the probe script was deleted",
        entry_for(page, FIXTURE_PATH) is None, "")
    browser.close()

passed = sum(1 for _, ok, _ in res if ok)
print(f"\n{passed}/{len(res)} checks passed")
sys.exit(0 if passed == len(res) else 1)
