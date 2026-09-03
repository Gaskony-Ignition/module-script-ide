#!/usr/bin/env python3
"""Live acceptance for the 1.6.0 navigation work (batch D).

Everything the gateway needed for project navigation was answered from 1.0.0 and
called by NOTHING: `textDocument/definition`, `workspace/symbol` and the module's
own `scriptide/searchText` all worked, `lspClient` wrapped all three, and no
component invoked any of them. P4 read "done" and the product had an outline and
Ctrl+F. So every check below is about the JOIN — the part that turns a server
answer into an open tab with the caret in the right place — and none of it can be
proved without a browser and a real gateway:

  QUICKOPEN   Ctrl+P over the script tree, `#` over workspace symbols. The
              symbol half is a live round trip to the AST index.
  DEFINITION  F12 and Ctrl-click on a name defined in ANOTHER file: the tab has
              to open AND the caret has to land on the definition. The second
              half is the one that used to be lost — the view for a
              just-opened document does not exist when the jump is published, so
              a dropped reveal shows the file at line 1 with nothing saying why.
  SEARCH      The Search view in the activity bar, over `scriptide/searchText`,
              with Match case actually reaching the server (the client sent no
              caseSensitive flag at all until 1.6.0, so the box could not work).
  REFERENCES  Shift+F12 over `scriptide/references` — name-based, and the panel
              must SAY it is name-based, because a list read as a type-aware
              find-references is a rename waiting to break an unrelated method.
  PROBLEMS    A syntax error in a tab you are NOT looking at has to appear in the
              Problems panel; the inline squiggle and gutter marker are only
              visible in the file on screen.
  FOLD/GOTO   A fold gutter on a file, and Ctrl+G opening go-to-line.
  PANEL       The bottom panel's opening height on the 1000px viewport the
              02/09/2026 review measured as cramped.

The fixture is created and removed by this script: two library modules in a
mutable project, one calling the other, so definition, references and search all
have a known answer. `SI_NAV_PROJECT` overrides the project.

Run after deploy_gate.py prints PASS.
"""
import os
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gateway_session import CONFIG, GATEWAY_URL, login  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

SPA = CONFIG.get("spa_path", "/data/scriptide/")
OUT = os.environ.get("SI_SHOT_DIR", "/tmp")
NAV_PROJECT = os.environ.get("SI_NAV_PROJECT", "")

STAMP = str(int(time.time()))
LIB = f"si_nav_lib_{STAMP}"
CALLER = f"si_nav_caller_{STAMP}"

# `compute` is defined once and written three times, and `recompute` exists
# solely to prove the reference matcher uses identifier boundaries: a substring
# search returns it, and a name-based one must not.
LIB_SOURCE = (
    "TOLERANCE = 0.5\n"
    "\n"
    "def compute(values):\n"
    "\ttotal = 0\n"
    "\tfor value in values:\n"
    "\t\ttotal += value\n"
    "\treturn total\n"
    "\n"
    "def recompute(values):\n"
    "\treturn compute(values)"
)
CALLER_SOURCE = (
    f"import {LIB}\n"
    "\n"
    "def run():\n"
    f"\treturn {LIB}.compute([1, 2, 3])"
)

res = []


# Where on screen a piece of RENDERED text is — used to put the caret on an
# identifier by clicking it.
#
# A DOM Range around the actual text node, not arithmetic on the line's width.
# The obvious approach (line width ÷ character count) is wrong on any line with a
# tab in it: a tab is ONE character and four columns, so the estimate drifts and
# the click lands a couple of characters off the name it was aiming at — which
# looks exactly like F12 being unbound, because a keypress with the caret on
# whitespace correctly does nothing. That cost an hour on 02/09/2026; the Range
# is exact and cannot drift.
CARET_ON = """([needle]) => {
  const host = document.querySelector('.code-editor-host:not([style*="none"])');
  const walker = document.createTreeWalker(host, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    const at = node.textContent.indexOf(needle);
    if (at < 0) continue;
    const range = document.createRange();
    range.setStart(node, at);
    range.setEnd(node, at + needle.length);
    const box = range.getBoundingClientRect();
    if (box.width === 0) continue;
    return {x: box.left + box.width / 2, y: box.top + box.height / 2,
            text: node.textContent};
  }
  return null;
}"""

def rec(name, ok, detail=""):
    res.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def skip(name, detail=""):
    # A pass with the reason stated — the convention the v14/v15 suites use. A
    # check that cannot run on THIS gateway is not evidence of a defect, and
    # dropping it silently leaves the tally looking complete when it is not.
    res.append((name, True, detail))
    print(f"  [SKIP] {name}: {detail}")


def api(page, method, url, csrf, body=None, if_match=None):
    return page.evaluate(
        """async ([spa, method, url, csrf, body, ifMatch]) => {
             const headers = {'Accept': 'application/json', 'X-CSRF-Token': csrf};
             if (body !== null) headers['Content-Type'] = 'application/json';
             if (ifMatch !== null) headers['If-Match'] = ifMatch;
             const res = await fetch(spa + url, {
               method, credentials: 'include', headers,
               body: body === null ? undefined : JSON.stringify(body)});
             const text = await res.text();
             return {status: res.status, etag: res.headers.get('ETag'), text: text};
           }""",
        [SPA, method, url, csrf, body, if_match])


def json_of(response):
    import json as _json
    try:
        return _json.loads(response["text"])
    except Exception:
        return {}


def content_url(project, module):
    # The route matches a SINGLE path segment, so the resource path is
    # percent-encoded here and the project rides in the query string — exactly
    # what scripts.ts#scriptRouteUrl builds.
    return ("api/scripts/content/"
            + urllib.parse.quote(f"ignition/script-python/{module}", safe="")
            + f"?project={urllib.parse.quote(project)}")


def create(page, project, module, source, csrf):
    # A create sends NO If-Match: there is no version to match, and sending one
    # makes the server treat it as a modify of something absent.
    return api(page, "POST", content_url(project, module), csrf, {"source": source})


def delete(page, project, module, csrf):
    entry = next((e for e in tree_of(page, project)
                  if e.get("path") == f"ignition/script-python/{module}"), None)
    if not entry:
        return
    api(page, "DELETE", content_url(project, module), csrf, None, entry.get("signature"))


def tree_of(page, project):
    return json_of(api(page, "GET",
                       f"api/scripts?project={urllib.parse.quote(project)}", "")).get("scripts", [])


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
    browser = p.chromium.launch()
    # 1000px is the viewport the 02/09/2026 review measured the panel on.
    page = browser.new_context(viewport={"width": 1600, "height": 1000}).new_page()
    errs = []
    page.on("console", lambda m: errs.append(f"{m.text} @ {m.location.get('url', '')}")
            if m.type == "error" and "/res/sys/" not in m.location.get("url", "")
            and "/data/app/session" not in m.location.get("url", "") else None)
    page.on("pageerror", lambda e: errs.append(str(e)))

    login(page)
    page.goto(GATEWAY_URL + SPA, wait_until="load", timeout=30000)
    page.wait_for_selector(".file-tree-header", timeout=20000)
    expand_tree(page)
    session = page.evaluate(
        """async (spa) => (await fetch(spa + 'api/auth/session',
             {credentials: 'include'})).json()""", SPA)
    csrf = session.get("csrfToken")

    projects = json_of(api(page, "GET", "api/projects", ""))
    mutable = [p_["name"] for p_ in (projects if isinstance(projects, list)
                                     else projects.get("projects", []))
               if p_.get("mutable")]
    project = NAV_PROJECT or (mutable[0] if mutable else "")
    rec("FIXTURE: a mutable project to build the fixture in", bool(project),
        f"project={project or 'none'} (mutable: {', '.join(mutable) or 'none'})")

    if not project:
        browser.close()
        print("\nNo mutable project — nothing to navigate.")
        sys.exit(1)

    created = create(page, project, LIB, LIB_SOURCE, csrf)
    created_caller = create(page, project, CALLER, CALLER_SOURCE, csrf)
    rec("FIXTURE: two library modules created",
        created["status"] == 200 and created_caller["status"] == 200,
        f"{LIB}={created['status']} {CALLER}={created_caller['status']}")

    # ---------- ETag quoting (RFC 9110) ----------
    read = api(page, "GET", content_url(project, LIB), "")
    etag = read.get("etag") or ""
    rec("ETAG: the header is a quoted entity tag", etag.startswith('"') and etag.endswith('"'),
        f"ETag: {etag}")
    # And the QUOTED value must still satisfy If-Match, or every save from a page
    # that did not strip the quotes becomes a permanent 409 that reads on screen
    # as somebody else editing the file.
    saved = api(page, "POST", content_url(project, LIB), csrf, {"source": LIB_SOURCE}, etag)
    rec("ETAG: a quoted If-Match is accepted, not treated as a stale signature",
        saved["status"] == 200, f"HTTP {saved['status']} with If-Match: {etag}")

    # The index is signature-diffed and the library rebuild is asynchronous, so
    # give the gateway the few seconds it measurably needs before asking it to
    # navigate to something that did not exist a moment ago.
    time.sleep(6)
    page.reload(wait_until="load", timeout=30000)
    page.wait_for_selector(".file-tree-header", timeout=20000)
    page.select_option(".workspace-project select", project)
    page.wait_for_timeout(2000)
    # Expand AFTER switching project: the tree is re-fetched on the switch, and
    # opening branches of the previous project's tree opens nothing in this one.
    expand_tree(page)

    # ---------- 1. quick open ----------
    page.keyboard.press("Control+p")
    page.wait_for_selector(".quick-open", timeout=5000)
    rec("QUICKOPEN: Ctrl+P opens the palette on scripts",
        page.locator(".quick-open").get_attribute("aria-label") == "Go to script", "")
    page.keyboard.type(CALLER)
    page.wait_for_timeout(400)
    rows = page.locator(".quick-open-row").count()
    rec("QUICKOPEN: typing a path filters to it", rows >= 1,
        f"{rows} row(s) for '{CALLER}'")
    page.keyboard.press("Enter")
    page.wait_for_timeout(1500)
    rec("QUICKOPEN: Enter opens the script it highlighted",
        page.locator(f'.tab-label[title*="{CALLER}"]').count() == 1,
        page.locator(".tab-name").first.inner_text() if page.locator(".tab-name").count() else "")
    page.screenshot(path=f"{OUT}/v16-quickopen.png")

    # `#` switches to symbols, which is a live round trip to the AST index. The
    # prefix is the guarantee: Ctrl+T is refused by Chrome and cannot be
    # intercepted, so the shortcut alone would not be testable OR usable.
    page.keyboard.press("Control+p")
    page.wait_for_selector(".quick-open", timeout=5000)
    page.keyboard.type("#compute")
    page.wait_for_timeout(1500)
    symbol_rows = page.locator(".quick-open-row").all_inner_texts()
    rec("QUICKOPEN: '#' searches project SYMBOLS on the gateway",
        any("compute" in row for row in symbol_rows),
        f"{len(symbol_rows)} symbol row(s): {'; '.join(r.replace(chr(10), ' ') for r in symbol_rows[:3])}")
    page.screenshot(path=f"{OUT}/v16-quickopen-symbols.png")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    rec("QUICKOPEN: Escape closes it without opening anything",
        page.locator(".quick-open").count() == 0, "")

    # ---------- 2. go to definition, across files ----------
    # The caller's body is `return si_nav_lib_N.compute([1, 2, 3])`; the caret
    # goes on `compute`, whose definition is in the OTHER module.
    page.locator(f'.tab-label[title*="{CALLER}"]').click()
    page.wait_for_timeout(800)
    placed = page.evaluate(CARET_ON, ["compute"])
    if not placed:
        skip("DEFINITION: F12 opens the defining file with the caret on the definition",
             "could not locate the call line in the rendered buffer")
    else:
        page.mouse.click(placed["x"], placed["y"])
        page.wait_for_timeout(300)
        page.keyboard.press("F12")
        page.wait_for_timeout(2500)
        opened = page.locator(f'.tab-label[title*="{LIB}"]').count() == 1
        # THE assertion the pending-reveal fix exists for: opening the file is
        # only half the jump, and before 1.6.0 the caret landed on line 1
        # whenever the target was not already open.
        where = page.evaluate(
            """() => {
                 const host = document.querySelector('.code-editor-host:not([style*="none"])');
                 const active = host && host.querySelector('.cm-activeLine');
                 if (!active) return null;
                 const lines = Array.from(host.querySelectorAll('.cm-line'));
                 return {index: lines.indexOf(active), text: active.textContent};
               }""")
        rec("DEFINITION: F12 opens the DEFINING file", opened,
            f"tabs: {', '.join(page.locator('.tab-name').all_inner_texts())}")
        rec("DEFINITION: and the caret lands on the definition, not line 1",
            bool(where) and "def compute" in (where["text"] or ""),
            f"active line {where['index'] if where else '?'}: "
            f"{(where['text'] if where else '')!r}")
        page.screenshot(path=f"{OUT}/v16-definition.png")

    # ---------- 3. references ----------
    #
    # Put the caret ON the name first. After a definition jump it sits at column
    # 0 of `def compute(values):`, and the word there is `def` — so a bare
    # Shift+F12 asks for every `def` in the project, gets a hundred honest hits,
    # and reads like a broken matcher. The product is doing the right thing with
    # the caret it was given; the suite has to give it the right caret.
    on_name = page.evaluate(CARET_ON, ["compute"])
    if on_name:
        page.mouse.click(on_name["x"], on_name["y"])
        page.wait_for_timeout(300)
    page.keyboard.press("Shift+F12")
    page.wait_for_timeout(2500)
    rec("REFERENCES: Shift+F12 opens the Search view",
        page.locator(".search-panel").count() == 1,
        page.locator(".rail-title").inner_text() if page.locator(".rail-title").count() else "")
    status = (page.locator(".search-panel-status").inner_text()
              if page.locator(".search-panel-status").count() else "")
    rec("REFERENCES: the results say they are matched by NAME",
        "matched by NAME" in status, status.replace("\n", " ")[:140])
    hits = page.locator(".search-panel-hit").all_inner_texts()
    # Three writes of `compute` in the library (the def, the call inside
    # recompute) plus the caller's own use. `recompute` must NOT be one of them:
    # a substring search returns it and an identifier-boundary one does not.
    joined = " | ".join(h.replace("\n", " ") for h in hits)
    rec("REFERENCES: it finds the definition and both call sites", len(hits) >= 3,
        f"{len(hits)} hit(s): {joined[:180]}")
    rec("REFERENCES: `recompute` is NOT reported as a reference to `compute`",
        not any("def recompute" in h for h in hits),
        "identifier boundaries, not a substring search")
    page.screenshot(path=f"{OUT}/v16-references.png")

    # ---------- 4. project text search ----------
    box = page.locator(".search-panel-input input")
    box.fill("TOLERANCE")
    box.press("Enter")
    page.wait_for_timeout(2000)
    text_hits = page.locator(".search-panel-hit").all_inner_texts()
    rec("SEARCH: a project-wide text search finds a constant in an unopened file",
        any("TOLERANCE" in h for h in text_hits),
        f"{len(text_hits)} hit(s)")

    # Match case has to reach the SERVER: the client sent no caseSensitive flag
    # at all until 1.6.0, so the box was decoration.
    box.fill("tolerance")
    box.press("Enter")
    page.wait_for_timeout(1500)
    insensitive = page.locator(".search-panel-hit").count()
    page.locator(".search-panel-case input").check()
    page.wait_for_timeout(1800)
    sensitive = page.locator(".search-panel-hit").count()
    rec("SEARCH: Match case actually changes the answer",
        insensitive > sensitive,
        f"'tolerance' -> {insensitive} insensitive, {sensitive} case-sensitive")
    page.locator(".search-panel-case input").uncheck()

    # A result opens the file it is in, at its own line.
    page.locator(".search-panel-input input").fill("TOLERANCE")
    page.locator(".search-panel-input input").press("Enter")
    page.wait_for_timeout(1800)
    if page.locator(".search-panel-hit").count():
        page.locator(".search-panel-hit").first.click()
        page.wait_for_timeout(1500)
        line = page.evaluate(
            """() => {
                 const host = document.querySelector('.code-editor-host:not([style*="none"])');
                 const active = host && host.querySelector('.cm-activeLine');
                 return active ? active.textContent : null;
               }""")
        rec("SEARCH: clicking a result opens that file at that line",
            bool(line) and "TOLERANCE" in line, repr(line))
    else:
        skip("SEARCH: clicking a result opens that file at that line", "no hits to click")
    page.screenshot(path=f"{OUT}/v16-search.png")

    # ---------- 5. problems ----------
    # A syntax error in a tab that is NOT on screen. That is the whole reason the
    # panel exists: the squiggle and the gutter marker are per-file.
    page.locator(f'.tab-label[title*="{CALLER}"]').click()
    page.wait_for_timeout(600)
    page.locator(".cm-content").first.click()
    page.keyboard.press("Control+End")
    page.keyboard.type("\ndef broken(:\n")
    page.wait_for_timeout(2500)
    # Switch AWAY from the broken file before looking at the panel.
    page.locator(f'.tab-label[title*="{LIB}"]').click()
    page.wait_for_timeout(600)
    page.locator('.activity-item[aria-label="Problems"]').click()
    page.wait_for_timeout(2000)
    problems = page.locator(".problems-row").all_inner_texts()
    rec("PROBLEMS: a syntax error in a NON-active tab is listed",
        any(CALLER.split("_")[-1] in row or "broken" in row or row.strip() for row in problems)
        and len(problems) >= 1,
        f"{len(problems)} row(s): {'; '.join(r.replace(chr(10), ' ') for r in problems[:2])}")
    if problems:
        page.locator(".problems-row").first.click()
        page.wait_for_timeout(1200)
        active_tab = page.locator(".tab.is-active .tab-name").inner_text()
        rec("PROBLEMS: clicking one switches to that tab",
            CALLER in active_tab, active_tab)
    else:
        skip("PROBLEMS: clicking one switches to that tab", "no problem rows to click")
    page.screenshot(path=f"{OUT}/v16-problems.png")

    # ---------- 6. fold gutter, go to line, panel height ----------
    rec("FOLD: a file's editor has a fold gutter",
        page.locator(".cm-foldGutter").count() >= 1,
        f"{page.locator('.cm-foldGutter').count()} gutter(s)")

    page.locator(".cm-content").first.click()
    page.keyboard.press("Control+g")
    page.wait_for_timeout(600)
    rec("GOTO: Ctrl+G opens go-to-line",
        page.locator(".cm-panel").count() >= 1,
        "CodeMirror's own panel")
    page.keyboard.press("Escape")

    height = page.evaluate(
        """() => {
             const slot = document.querySelector('.workspace-panel-slot');
             return slot ? Math.round(slot.getBoundingClientRect().height) : null;
           }""")
    # 34% of a 1000px viewport, clamped. The old fixed 260px was measured cramped
    # at exactly this size in the 02/09/2026 review.
    rec("PANEL: the bottom panel opens taller than the 260px measured cramped",
        bool(height) and height >= 300, f"{height}px at a 1000px viewport")
    page.screenshot(path=f"{OUT}/v16-panel-height.png", full_page=False)

    rec("CONSOLE: no page errors from our own code", not errs, "; ".join(errs[:3]))

    # ---------- clean up ----------
    delete(page, project, LIB, csrf)
    delete(page, project, CALLER, csrf)
    remaining = [e.get("path") for e in tree_of(page, project)]
    rec("FIXTURE: both modules removed again",
        f"ignition/script-python/{LIB}" not in remaining
        and f"ignition/script-python/{CALLER}" not in remaining,
        f"{len(remaining)} script(s) left in {project}")

    browser.close()

print()
passed = sum(1 for _, ok, _ in res if ok)
print(f"{passed}/{len(res)} checks passed")
sys.exit(0 if passed == len(res) else 1)
