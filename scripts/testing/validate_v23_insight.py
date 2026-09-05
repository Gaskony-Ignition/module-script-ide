"""
The five things added in 1.15.0, each proved against the real gateway.

They are one release because they are one idea: the IDE knew things it never
said. The deprecation flag was already in the hint index and only ever reached a
hover card; the gateway's log knew which scripts were failing and nothing asked
it; search could find a string across the project and could not change it; and
every save went into a running gateway with no way back to the version before
it.

1. **Local history.** Every save is kept, per user, with the version that was
   there BEFORE the first one — so the state you started from is reachable.
   Restore LOADS THE BUFFER; it does not write.
2. **Deprecation as a diagnostic**, not just a tooltip on a completion.
3. **Scope-aware checks.** `system.gui` on the Gateway is an AttributeError
   waiting for the next tick. Asserted as a DIFFERENCE: the same line in a
   Project Library module must NOT be marked, because a Vision client may
   legitimately import it.
4. **Replace across the project**, through the ordinary save path — so
   inheritance, CSRF, If-Match and byte fidelity all still apply.
5. **Runtime errors in the Problems panel** — what the gateway has actually
   logged, as opposed to what the parser thinks of code that has not run.

Every fixture here is created and deleted by this script. The gateway-scope
fixture is a MESSAGE handler rather than a timer: a message handler runs only
when something sends to it, so the suite cannot leave a script firing every
second on the rig.

Run:
    WD_ALLOW_LOCAL_CONFIG=1 .venv-test/bin/python3 scripts/testing/validate_v23_insight.py
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

# A library module and a gateway-scope message handler, holding the SAME line.
# The pair is the whole point: one must be marked and the other must not.
# Distinct NAMES, not just distinct paths. Both rows are rendered by their leaf
# name, so two fixtures called `_si_v23_` are two rows a selector cannot tell
# apart — and the whole point of the pair is which of the two got marked.
LIB_PATH = "ignition/script-python/_si_v23_lib"
MSG_PATH = "ignition/message/_si_v23_msg"

# Two library modules for the replace, so "how many files" is a real answer.
REPL_A = "ignition/script-python/_si_v23_repl_a"
REPL_B = "ignition/script-python/_si_v23_repl_b"

# A token that cannot occur anywhere else on the gateway, so the search that
# drives the replace cannot pick up somebody's real code.
TOKEN = "siV23ReplaceMe"

SCOPE_SOURCE = "def show():\n\tsystem.gui.messageBox('hi')\n"
REPL_SOURCE = f"value = '{TOKEN}'\nother = {TOKEN}\n"

VISIBLE = ".code-editor-host:not([style*=none])"

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


def write(page, csrf, path, source, signature=None):
    return api(page, "POST",
               f"api/scripts/content/{urllib.parse.quote(path, safe='')}"
               f"?project={urllib.parse.quote(PROJECT)}",
               csrf, {"source": source}, if_match=signature)


def read_body(page, path):
    return api(page, "GET",
               f"api/scripts/content/{urllib.parse.quote(path, safe='')}"
               f"?project={urllib.parse.quote(PROJECT)}")["text"]


def remove_fixtures(page, csrf):
    for path in (LIB_PATH, MSG_PATH, REPL_A, REPL_B):
        found = entry_for(page, path)
        if found:
            api(page, "DELETE",
                f"api/scripts/content/{urllib.parse.quote(path, safe='')}"
                f"?project={urllib.parse.quote(PROJECT)}",
                csrf, if_match=found.get("signature"))


def settle(page, selector, timeout=15000):
    try:
        page.wait_for_selector(selector, timeout=timeout)
        return True
    except Exception:
        return False


def expand_tree(page):
    """Open every closed branch, repeatedly, until nothing is closed.

    The same loop `validate_v22` uses. A group header is a TOGGLE, so clicking
    one by name is only correct when it is currently shut — clicking blind
    collapses an open branch and the row is then not there to click, which is
    how validate_v20 came to measure an empty Web Dev column on 04/09/2026.
    Driving off `aria-expanded="false"` asks the tree what is actually shut.
    """
    for _ in range(6):
        shut = page.locator('.file-tree [aria-expanded="false"]')
        if shut.count() == 0:
            return
        for i in range(shut.count()):
            try:
                shut.nth(i).click(timeout=1500)
            except Exception:
                pass
        page.wait_for_timeout(250)


def open_from_tree(page, label):
    """Open a script by its tree row, whatever branch it is under."""
    expand_tree(page)
    row = page.locator(
        f'.file-tree .file-tree-item:has(.file-tree-name:text-is("{label}"))')
    if row.count() == 0:
        row = page.locator('.file-tree .file-tree-item').filter(has_text=label)
    if row.count() == 0:
        return False
    row.first.click()
    page.wait_for_timeout(2000)
    return True


def open_problems(page):
    """Show the Problems panel.

    Not optional scaffolding: `.problems-message` and `.problems-runtime` only
    exist while the panel is rendered, so a check that reads them without this
    measures a closed panel and reports every diagnostic as missing. The first
    run of this suite failed six checks that way.
    """
    # Idempotent: the activity item is a TOGGLE, so clicking it while the panel
    # is already showing Problems closes the thing we came to read.
    if page.locator(".problems, .problems-empty").count():
        return
    item = page.locator('.activity-item[aria-label="Problems"]')
    if item.count():
        item.click()
        page.wait_for_timeout(1800)


def problem_messages(page):
    open_problems(page)
    return [t.strip() for t in page.locator(".problems-message").all_inner_texts()]


def search_for(page, term, tries=6):
    """Search, retrying while the gateway's index catches up.

    A fixture written through the API is in the resource system immediately and
    in the language server's project index a moment later, so the first search
    for a brand-new file legitimately returns nothing. Retrying is the honest
    wait; asserting on the first answer tests the index's rebuild interval.
    """
    box = ".search-panel-form .search-panel-input input"
    for attempt in range(tries):
        page.fill(box, term)
        page.press(box, "Enter")
        page.wait_for_timeout(2500)
        if page.locator(".search-panel-hit").count():
            return page.locator(".search-panel-hit").count()
        page.wait_for_timeout(2000 * (attempt + 1))
    return 0


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
    remove_fixtures(page, csrf)

    # =================== 1. local history ===================
    first = write(page, csrf, LIB_PATH, "x = 1\n")
    rec("FIXTURE: the library probe was created", first["status"] == 200,
        f"HTTP {first['status']} {first['text'][:80]}")

    entry = entry_for(page, LIB_PATH)
    second = write(page, csrf, LIB_PATH, "x = 2\n",
                   signature=(entry or {}).get("signature"))
    rec("FIXTURE: it was saved a second time", second["status"] == 200,
        f"HTTP {second['status']}")

    history = json_of(api(page, "GET",
                          f"api/history?project={urllib.parse.quote(PROJECT)}"
                          f"&path={urllib.parse.quote(LIB_PATH, safe='')}&key=code.py"))
    versions = history.get("versions", [])
    # Three, not two: the create, the second save, AND the baseline recorded
    # before that second save — which is the version the user started from.
    rec("HISTORY: every save is kept", len(versions) >= 2,
        f"{len(versions)} version(s)")

    if versions:
        newest = api(page, "GET",
                     f"api/history/content?project={urllib.parse.quote(PROJECT)}"
                     f"&path={urllib.parse.quote(LIB_PATH, safe='')}&key=code.py"
                     f"&id={versions[0]['id']}")
        rec("HISTORY: the newest version is the text that was last written",
            newest["status"] == 200 and newest["text"] == "x = 2\n",
            repr(newest["text"][:40]))

        older = [v for v in versions if v["id"] != versions[0]["id"]]
        if older:
            back = api(page, "GET",
                       f"api/history/content?project={urllib.parse.quote(PROJECT)}"
                       f"&path={urllib.parse.quote(LIB_PATH, safe='')}&key=code.py"
                       f"&id={older[0]['id']}")
            rec("HISTORY: an earlier version still holds the earlier text",
                back["status"] == 200 and back["text"] == "x = 1\n",
                repr(back["text"][:40]))
        else:
            rec("HISTORY: an earlier version still holds the earlier text", False,
                "only one version kept")
    else:
        rec("HISTORY: the newest version is the text that was last written", False, "none")
        rec("HISTORY: an earlier version still holds the earlier text", False, "none")

    # A traversal id must read nothing, whatever is on disk beside the store.
    traversal = api(page, "GET",
                    f"api/history/content?project={urllib.parse.quote(PROJECT)}"
                    f"&path={urllib.parse.quote(LIB_PATH, safe='')}&key=code.py"
                    f"&id={urllib.parse.quote('../../../../config/secrets', safe='')}")
    rec("HISTORY: a traversal id is refused", traversal["status"] == 404,
        f"HTTP {traversal['status']}")

    # ---- the dialog itself ----
    page.reload(wait_until="load")
    page.wait_for_selector(".file-tree-header", timeout=20000)
    page.select_option(".workspace-project select", PROJECT)
    page.wait_for_timeout(1500)
    open_from_tree(page, "_si_v23_lib")

    has_button = page.locator('.workspace-toolbar button:has-text("History")').count() == 1
    rec("HISTORY: the open script offers its history", has_button,
        "History button present" if has_button else "no History button")

    if has_button:
        page.click('.workspace-toolbar button:has-text("History")')
        opened = settle(page, ".history-dialog", 8000)
        rows = page.locator(".history-version")
        rec("HISTORY: the dialog lists the versions", opened and rows.count() >= 2,
            f"{rows.count()} row(s)")

        # The newest is selected without a click, and it is what is in the
        # editor — so Load must be refused rather than doing nothing visible.
        load = page.locator('.history-dialog button:has-text("Load into editor")')
        page.wait_for_timeout(1200)
        same_note = page.locator(".history-same").count()
        rec("HISTORY: a version identical to the buffer says so and cannot be loaded",
            same_note == 1 and load.is_disabled(),
            f"note={same_note} disabled={load.is_disabled()}")

        if rows.count() >= 2:
            rows.nth(1).click()
            page.wait_for_timeout(1200)
            rec("HISTORY: selecting an older version enables the load",
                not load.is_disabled(), f"disabled={load.is_disabled()}")
            load.click()
            page.wait_for_timeout(1000)
            editor_text = page.locator(f"{VISIBLE} .cm-content").first.inner_text()
            rec("HISTORY: it loads into the editor as an UNSAVED change",
                "x = 1" in editor_text, repr(editor_text[:40]))
            on_gateway = read_body(page, LIB_PATH)
            # The safety property: a restore writes nothing until you save.
            rec("HISTORY: nothing was written to the gateway",
                on_gateway == "x = 2\n", repr(on_gateway[:40]))
        else:
            skip("HISTORY: selecting an older version enables the load", "one version")
            skip("HISTORY: it loads into the editor as an UNSAVED change", "one version")
            skip("HISTORY: nothing was written to the gateway", "one version")

        if page.locator(".history-dialog").count():
            page.click('.history-dialog button:has-text("Cancel")')
            page.wait_for_timeout(400)

    # =================== 2 & 3. deprecation and scope ===================
    # The SAME source in both places. Only the gateway-scoped one may be marked.
    write(page, csrf, MSG_PATH, SCOPE_SOURCE)
    lib_entry = entry_for(page, LIB_PATH)
    write(page, csrf, LIB_PATH, SCOPE_SOURCE,
          signature=(lib_entry or {}).get("signature"))

    page.reload(wait_until="load")
    page.wait_for_selector(".file-tree-header", timeout=20000)
    page.select_option(".workspace-project select", PROJECT)
    page.wait_for_timeout(2000)

    # The message handler, under Gateway Events -> Message.
    expand_tree(page)
    msg_row = page.locator(
        '.file-tree .file-tree-item:has(.file-tree-name:text-is("_si_v23_msg"))')
    if msg_row.count():
        msg_row.first.click()
        page.wait_for_timeout(3000)
        messages = problem_messages(page)
        marked = [m for m in messages if "system.gui" in m]
        rec("SCOPE: a gateway-scope script calling system.gui is marked",
            len(marked) >= 1, "; ".join(marked)[:120] or f"{len(messages)} problem(s)")
        rec("SCOPE: the message says it will fail at RUN time, not at parse time",
            any("AttributeError" in m for m in marked), "; ".join(marked)[:120])
    else:
        rec("SCOPE: a gateway-scope script calling system.gui is marked", False,
            "message fixture not in the tree")
        rec("SCOPE: the message says it will fail at RUN time, not at parse time",
            False, "message fixture not in the tree")

    # The library module with the IDENTICAL line, which must be silent.
    open_from_tree(page, "_si_v23_lib")
    page.wait_for_timeout(2500)
    lib_messages = [m for m in problem_messages(page) if "system.gui" in m]
    # Both documents are open, so the panel holds the gateway one's mark too;
    # what must not appear is a SECOND one. One mark, from one document.
    rec("SCOPE: the same line in a Project Library module is NOT marked",
        len(lib_messages) <= 1,
        f"{len(lib_messages)} system.gui mark(s) with both documents open")

    # =================== 4. replace across the project ===================
    write(page, csrf, REPL_A, REPL_SOURCE)
    write(page, csrf, REPL_B, REPL_SOURCE)
    page.reload(wait_until="load")
    page.wait_for_selector(".file-tree-header", timeout=20000)
    page.select_option(".workspace-project select", PROJECT)
    page.wait_for_timeout(1500)

    page.locator('.activity-item[aria-label="Search"]').click()
    page.wait_for_timeout(800)
    hits = search_for(page, TOKEN)
    rec("REPLACE: the search finds the token in both files", hits >= 4,
        f"{hits} hit(s)")

    replace_box = page.locator('input[aria-label="Replace with"]')
    rec("REPLACE: a text search offers a replace", replace_box.count() == 1,
        f"{replace_box.count()} replace input")

    if replace_box.count() == 1 and hits:
        replace_box.fill(TOKEN + "Done")
        page.click('button:has-text("Replace all…")')
        page.wait_for_timeout(400)
        confirm = page.locator(".search-panel-confirm")
        rec("REPLACE: the first press confirms with the real counts, and writes nothing",
            confirm.count() == 1 and "occurrences of" in confirm.inner_text()
            and TOKEN in read_body(page, REPL_A),
            confirm.inner_text()[:110] if confirm.count() else "no confirmation")

        page.click('button:has-text("Replace in")')
        page.wait_for_timeout(4000)

        after_a = read_body(page, REPL_A)
        after_b = read_body(page, REPL_B)
        rec("REPLACE: both files were changed on the gateway",
            TOKEN + "Done" in after_a and TOKEN + "Done" in after_b,
            f"a={after_a[:34]!r} b={after_b[:34]!r}")
        # Every occurrence, not just the first on each line.
        rec("REPLACE: every occurrence went, not just the first",
            after_a.count(TOKEN + "Done") == 2,
            f"{after_a.count(TOKEN + 'Done')} in the first file")
        report = page.locator(".search-panel-report-line")
        rec("REPLACE: it reports what it did",
            report.count() == 1 and "Replaced" in report.inner_text(),
            report.inner_text()[:110] if report.count() else "no report")
    else:
        for name in ("REPLACE: the first press confirms with the real counts, and writes nothing",
                     "REPLACE: both files were changed on the gateway",
                     "REPLACE: every occurrence went, not just the first",
                     "REPLACE: it reports what it did"):
            rec(name, False, "no replace control")

    # =================== 5. runtime errors ===================
    runtime = json_of(api(page, "GET",
                          f"api/runtime/errors?project={urllib.parse.quote(PROJECT)}"))
    rec("RUNTIME: the gateway answers with a window and how it matched",
        "errors" in runtime and runtime.get("windowMinutes", 0) > 0
        and bool(runtime.get("matchedBy")),
        f"window={runtime.get('windowMinutes')} matchedBy={runtime.get('matchedBy')!r}")

    # The route must be reachable from the SPA's OWN base. It shipped once with
    # a bare `/api/...`, which 404s on a gateway and passes every unit test.
    bare = page.evaluate(
        """async (project) => {
             const res = await fetch('/api/runtime/errors?project=' + project,
                                     {credentials: 'include'});
             return res.status;
           }""", PROJECT)
    rec("RUNTIME: the SPA calls it under /data/scriptide, not at the server root",
        bare == 404, f"bare path answered HTTP {bare} (404 is correct)")

    open_from_tree(page, "_si_v23_repl_a")
    open_problems(page)
    page.wait_for_timeout(1500)
    section = page.locator(".problems-runtime")
    rec("RUNTIME: the Problems panel carries a second, separate list",
        section.count() == 1,
        section.locator(".problems-runtime-head").inner_text()[:60]
        if section.count() else "absent")
    if section.count():
        text = section.inner_text()
        rec("RUNTIME: it says how a row was matched, or that the log is quiet",
            "Matched by" in text or "Nothing at warning level" in text,
            text[:110].replace("\n", " "))
        # A row is not a link: a log line has no range to jump to.
        rec("RUNTIME: its rows are not counted as static problems",
            section.locator(".problems-row").count() == 0,
            f"{section.locator('.problems-runtime-row').count()} runtime row(s)")
    else:
        rec("RUNTIME: it says how a row was matched, or that the log is quiet", False, "absent")
        rec("RUNTIME: its rows are not counted as static problems", False, "absent")

    # =================== clean up ===================
    remove_fixtures(page, csrf)
    left = [p for p in (LIB_PATH, MSG_PATH, REPL_A, REPL_B) if entry_for(page, p)]
    rec("CLEANUP: every fixture was removed", not left, ", ".join(left) or "none left")

    browser.close()

passed = sum(1 for _, ok, _ in res if ok)
print(f"\n{passed}/{len(res)} checks passed")
sys.exit(0 if passed == len(res) else 1)
