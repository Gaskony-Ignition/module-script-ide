"""
Named queries, driven in a real browser against the real gateway — batch E.

Batch E shipped in 1.7.0 with 127 Java tests and 134 Vitest tests and NOTHING
that ran it end to end. It is the only batch without a live gate, and the three
defects unit tests have missed on this module — the batch-D caret, the batch-D
`finished.stdout` staleness, the 1.6.1 namespace bug — were all of the kind a
mock cannot see: a contract that both sides agree on and the platform does not.

So every check here is written against a DIFFERENCE rather than a presence,
because a named query has three ways of looking right while being wrong:

  * a settings key the platform never reads (`dataType`, `Date`) makes a
    resource that inspects perfectly and does not run;
  * a version-1 resource is not merely mis-keyed, it is DEAD — `fromResource`
    returns a blank query and `runNamedQuery` raises a NullPointerException —
    and a read that quietly showed the platform's defaults instead would look
    identical to a healthy read;
  * the test tab claims to run the DRAFT. Running the saved copy instead gives
    the right answer for every query nobody has edited, which is most of them.

Each of those is asserted BOTH ways: the thing that must work, beside the thing
that must be refused.

The legacy repair is the one check that leaves the gateway changed, deliberately
and in one direction only: it takes a query in `Whiteboard` that the gateway
cannot run, saves it, and proves the platform then runs it. There is no way to
write a version-1 resource back, and no way to test the repair without doing it.
`Whiteboard` had 29 dead queries when this was written; the suite picks one that
is still dead and skips with a reason when none is left.

Run:
    WD_ALLOW_LOCAL_CONFIG=1 .venv-test/bin/python3 scripts/testing/validate_v17_nq.py
"""
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gateway_session import CONFIG, GATEWAY_URL, login          # noqa: E402
from playwright.sync_api import sync_playwright                 # noqa: E402

SPA = CONFIG.get("spa_path", "/data/scriptide/")

# Where the fixture is built. A project with no named queries of its own, so a
# stray row from an earlier run is visible rather than lost in a real tree.
PROJECT = os.environ.get("SI_NQ_PROJECT", "Mining_Demo")
# Where the dead version-1 queries are. Whiteboard's were written by a script.
LEGACY_PROJECT = os.environ.get("SI_NQ_LEGACY_PROJECT", "Whiteboard")
DB = os.environ.get("SI_NQ_DB", "Postgres_Test")

FOLDER = "_si_nq_"
QUERY = f"{FOLDER}/Fixture"
MOVED = f"{FOLDER}/Renamed"
FOLDER2 = "_si_nq2_"

res = []


def rec(name, ok, detail=""):
    res.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def skip(name, detail=""):
    # A pass with its reason stated. A check that cannot run on this gateway is
    # not evidence of a defect; dropping it silently leaves the tally looking
    # complete when it is not.
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


def seg(path):
    """A query path as ONE route segment — slashes percent-encoded."""
    return urllib.parse.quote(path, safe="")


def listing(page, project):
    return json_of(api(page, "GET", f"api/named-queries?project={urllib.parse.quote(project)}"))


def rows(page, project):
    return {q["path"]: q for q in listing(page, project).get("queries", [])}


def settings_of(page, project, path):
    return json_of(api(page, "GET",
                       f"api/named-queries/settings/{seg(path)}"
                       f"?project={urllib.parse.quote(project)}"))


def content_of(page, project, path):
    return api(page, "GET", f"api/named-queries/content/{seg(path)}"
                            f"?project={urllib.parse.quote(project)}")


def write(page, csrf, project, path, body, if_match=None):
    return api(page, "POST", f"api/named-queries/content/{seg(path)}"
                             f"?project={urllib.parse.quote(project)}",
               csrf, body, if_match)


def test_run(page, csrf, project, body):
    return api(page, "POST", f"api/named-queries/test?project={urllib.parse.quote(project)}",
               csrf, body)


def remove(page, csrf, project, path, if_match):
    return api(page, "DELETE", f"api/named-queries/content/{seg(path)}"
                               f"?project={urllib.parse.quote(project)}",
               csrf, if_match=if_match)


def settle(page, selector, timeout=15000):
    """Wait for a selector and say whether it arrived, instead of throwing.

    The tab, its settings and the parameter table each land on their own round
    trip, so a fixed sleep here is a race that fails on a slow gateway and
    passes on a fast one. A check that waits for its own precondition and then
    asserts is still an assertion — a missing element times out and is
    RECORDED, rather than ending the run with a traceback and no tally.
    """
    try:
        page.wait_for_selector(selector, timeout=timeout)
        return True
    except Exception:
        return False


def cleanup(page, csrf, project):
    """Delete every fixture row this suite could have left, deepest first."""
    for path, row in sorted(rows(page, project).items(), reverse=True):
        if path.split("/")[0] in (FOLDER, FOLDER2):
            remove(page, csrf, project, path, row.get("signature"))


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_context(viewport={"width": 1600, "height": 1000}).new_page()
    login(page)
    page.goto(GATEWAY_URL + SPA, wait_until="load", timeout=30000)
    page.wait_for_selector(".file-tree-header", timeout=20000)
    session = page.evaluate(
        "async (spa) => (await (await fetch(spa + 'api/auth/session',"
        " {credentials:'include'})).json())", SPA)
    csrf = session.get("csrfToken")

    cleanup(page, csrf, PROJECT)          # a previous run that died mid-way

    # ================= A. the view, and what the listing says =================
    page.locator('.activity-item[title*="Named Queries"], '
                 '.activity-item[aria-label*="Named Queries"]').first.click()
    page.wait_for_timeout(800)
    rec("VIEW: the activity bar opens a Named Queries tree",
        page.locator('.file-tree[aria-label="Named Queries"]').count() == 1, "")

    page.select_option(".workspace-project select", LEGACY_PROJECT)
    page.wait_for_timeout(1500)
    legacy_rows = rows(page, LEGACY_PROJECT)
    queries = {k: v for k, v in legacy_rows.items() if not v.get("isFolder")}
    folders = {k: v for k, v in legacy_rows.items() if v.get("isFolder")}
    rec("LISTING: the legacy project lists queries", len(queries) > 0,
        f"{len(queries)} queries, {len(folders)} folder resources")

    # The difference, not the presence: a folder must NOT carry query fields,
    # or a client cannot tell a folder from a query with defaults.
    rec("LISTING: a folder row carries none of the query fields",
        all("type" not in f and "database" not in f for f in folders.values())
        if folders else True,
        "no folder RESOURCES on this gateway" if not folders else f"{len(folders)} checked")

    dead = sorted(k for k, v in queries.items() if v.get("legacy"))
    alive = sorted(k for k, v in queries.items() if not v.get("legacy"))
    rec("LISTING: the dead version-1 queries are found, and marked",
        len(dead) > 0 and all(queries[k].get("version") == 1 for k in dead),
        f"{len(dead)} legacy, {len(alive)} version-2 in {LEGACY_PROJECT}")
    # The counterpart — a row that must NOT be marked — is the fixture created
    # below. `Whiteboard` is entirely version-1 on this gateway, so asserting
    # both here would be asserting the fixture rather than the code.

    # ===================== B. create, on the pinned defaults ==================
    page.select_option(".workspace-project select", PROJECT)
    page.wait_for_timeout(1500)
    before = rows(page, PROJECT)
    page.locator('.file-tree[aria-label="Named Queries"] '
                 '[aria-label="New named query"]').click()
    page.wait_for_timeout(400)
    page.fill("#namedquery-name", QUERY)
    page.locator(".newscript-dialog button[type=submit]").click()
    page.wait_for_timeout(2000)

    after = rows(page, PROJECT)
    rec("CREATE: the dialog creates the query at the path it was given",
        QUERY in after and QUERY not in before, f"{sorted(set(after) - set(before))}")

    fresh = settings_of(page, PROJECT, QUERY).get("settings", {})
    pinned = {
        "type": "Query", "enabled": True, "database": "",
        "cacheEnabled": False, "cacheAmount": 1, "cacheUnit": "SEC",
        "fallbackEnabled": False, "fallbackValue": "",
        "useMaxReturnSize": False, "maxReturnSize": 100,
        "autoBatchEnabled": False, "parameters": [],
    }
    wrong = {k: (fresh.get(k), v) for k, v in pinned.items() if fresh.get(k) != v}
    rec("CREATE: it lands on the defaults the contract pins, every one",
        not wrong, f"{wrong}" if wrong else f"{len(pinned)} fields")
    made = settings_of(page, PROJECT, QUERY)
    rec("CREATE: the new query is NOT legacy",
        made.get("legacy") is False and made.get("version") == 2,
        f"version={made.get('version')} legacy={made.get('legacy')}")
    # The difference the listing has to carry, now that both kinds exist on
    # this gateway: same field, opposite value, read the same way.
    rec("LISTING: a healthy row and a dead one differ on `legacy` and `version`",
        after[QUERY].get("legacy") is False and after[QUERY].get("version") == 2
        and legacy_rows[dead[0]].get("legacy") is True
        and legacy_rows[dead[0]].get("version") == 1,
        f"{QUERY}=v2, {dead[0]}=v1")

    # ============ C. the settings round trip, and what it refuses ============
    signature = after[QUERY]["signature"]
    full = {
        "type": "Query", "enabled": True, "database": DB,
        "description": "scriptide v17 fixture — safe to delete",
        "cacheEnabled": True, "cacheAmount": 30, "cacheUnit": "MIN",
        "fallbackEnabled": True, "fallbackValue": "0",
        "useMaxReturnSize": True, "maxReturnSize": 1000,
        "autoBatchEnabled": True,
        "permissions": [{"zone": "", "role": ""}],
        "parameters": [
            {"type": "Parameter", "identifier": "v", "sqlType": "String"},
            {"type": "Parameter", "identifier": "n", "sqlType": "Int4"},
        ],
    }
    SQL = "SELECT :v AS echoed, :n AS counted"
    saved = write(page, csrf, PROJECT, QUERY, {"sql": SQL, "settings": full}, signature)
    rec("SAVE: SQL and settings go up together against one signature",
        saved["status"] == 200 and json_of(saved).get("signature"), f"HTTP {saved['status']}")
    signature = json_of(saved).get("signature", signature)

    back = settings_of(page, PROJECT, QUERY).get("settings", {})
    differs = {k: (back.get(k), v) for k, v in full.items() if back.get(k) != v}
    rec("SAVE: every settings field reads back exactly as it was written",
        not differs, f"{differs}" if differs else f"{len(full)} fields")

    body = content_of(page, PROJECT, QUERY)
    rec("SAVE: the SQL comes back byte for byte, nothing added or stripped",
        body["text"] == SQL, repr(body["text"]))

    # The refusals. A key the platform never reads is how a resource comes to
    # look right and behave wrongly, so each is a 400 rather than a drop —
    # and each is asserted to NAME what it refused, because a bare 400 sends
    # the reader to the wrong place.
    for label, patch in (
        ("an unknown settings key", {"nosuchkey": 1}),
        ("the guessed sqlType 'Date'",
         {"parameters": [{"type": "Parameter", "identifier": "d", "sqlType": "Date"}]}),
        ("the guessed key 'dataType'",
         {"parameters": [{"identifier": "d", "dataType": "String"}]}),
        ("an unknown cacheUnit", {"cacheUnit": "FORTNIGHT"}),
        ("an unknown query type", {"type": "SelectQuery"}),
    ):
        r = api(page, "POST",
                f"api/named-queries/settings/{seg(QUERY)}?project={urllib.parse.quote(PROJECT)}",
                csrf, {"settings": patch}, signature)
        offender = str(list(patch.values())[0])
        rec(f"REFUSE: {label} is a 400 that names it",
            r["status"] == 400 and any(w in r["text"] for w in
                                       (list(patch.keys())[0], "Date", "dataType",
                                        "FORTNIGHT", "SelectQuery")),
            f"HTTP {r['status']} {r['text'][:110]}")

    # ...and the settings are untouched by a refused write. A 400 that half
    # applied would be worse than one that applied nothing.
    rec("REFUSE: a refused settings write changed nothing",
        settings_of(page, PROJECT, QUERY).get("settings", {}).get("cacheUnit") == "MIN", "")

    # ============ D. the tab that was open while all that happened ===========
    #
    # Creating a query OPENS it, so the settings written above went onto the
    # gateway underneath a tab already showing the version this suite created.
    # That is the stale case, and it has never been gated for a named query:
    # `staleUris` was keyed by DOCUMENT until 1.9.0 and a query tab's own
    # staleness had no test at all. The watch polls every 20 s.
    rec("OPEN: the create opened the query it made",
        page.locator('[aria-label="Named query"]').count() == 1
        and page.locator(".tab.is-active").count() == 1, "")
    saw_stale = settle(page, ".workspace-stale-bar", timeout=40000)
    rec("STALE: a query changed on the gateway is reported on its open tab",
        saw_stale,
        page.locator(".workspace-stale-bar").inner_text().replace("\n", " ")
        if saw_stale else "no stale bar within 40 s")
    if saw_stale:
        page.get_by_role("button", name="Pull the current copy").click()
        page.wait_for_timeout(1500)
        rec("STALE: pulling replaces the bar with the gateway's own copy",
            page.locator(".workspace-stale-bar").count() == 0, "")
    else:
        # Fall back to a fresh open, so the checks below still run and say why.
        skip("STALE: pulling replaces the bar with the gateway's own copy",
             "no stale bar to pull")
        page.select_option(".workspace-project select", LEGACY_PROJECT)
        page.wait_for_timeout(800)
        page.select_option(".workspace-project select", PROJECT)
        page.wait_for_timeout(1500)
        for _ in range(4):
            shut = page.locator('.file-tree[aria-label="Named Queries"] '
                                '[aria-expanded="false"]')
            if shut.count() == 0:
                break
            for i in range(shut.count()):
                try:
                    shut.nth(i).click(timeout=1500)
                except Exception:
                    pass      # opening a branch re-renders the list
            page.wait_for_timeout(200)
        page.locator('.file-tree[aria-label="Named Queries"] '
                     '.file-tree-item:has(.file-tree-name:text-is("Fixture"))').first.click()
        settle(page, '[aria-label="Named query"]')

    page.locator("#nq-tab-testing").click()
    arrived = settle(page, "#nq-panel-testing .nq-test-controls input")
    inputs = page.locator("#nq-panel-testing .nq-test-controls input")
    rec("TESTING: one input per declared parameter",
        arrived and inputs.count() == 2,
        f"{inputs.count()} inputs for {len(full['parameters'])} parameters")
    # Typed BY the declared sqlType, not all text — an Int4 that offers a free
    # text box is the shape that lets a fractional value reach the database.
    rec("TESTING: the Int4 parameter gets a number input, the String does not",
        page.locator('#nq-panel-testing input[aria-label="n"]')
            .get_attribute("type") == "number"
        and page.locator('#nq-panel-testing input[aria-label="v"]')
            .get_attribute("type") == "text", "")

    page.fill('#nq-panel-testing input[aria-label="v"]', "hello")
    page.fill('#nq-panel-testing input[aria-label="n"]', "7")
    page.locator(".nq-run").click()
    page.wait_for_selector(".nq-result", timeout=20000)
    grid = page.locator(".nq-result .nq-table")
    text = page.locator(".nq-result").inner_text()
    rec("TESTING: Run returns a grid with the bound values in it",
        grid.count() == 1 and "hello" in text and "7" in text, text[:120].replace("\n", " | "))

    # THE DRAFT, NOT THE SAVED COPY. This is the check the whole tab rests on
    # and the one a wrong implementation passes silently: running the saved
    # query gives the right answer for every query nobody has edited.
    page.locator("#nq-tab-authoring").click()
    settle(page, ".code-editor-host:not([style*=none]) .cm-content")
    page.locator(".code-editor-host:not([style*=none]) .cm-content").click()
    page.keyboard.press("Control+a")
    page.keyboard.type("SELECT 'draft-only' AS marker")
    page.wait_for_timeout(400)
    page.locator("#nq-tab-testing").click()
    settle(page, ".nq-run")
    page.locator(".nq-run").click()
    page.wait_for_selector(".nq-result", timeout=20000)
    drafted = page.locator(".nq-result").inner_text()
    rec("DRAFT: the run uses the SQL on screen, not the last saved version",
        "draft-only" in drafted, drafted[:120].replace("\n", " | "))
    rec("DRAFT: and the saved copy is still the old SQL — nothing was written",
        content_of(page, PROJECT, QUERY)["text"] == SQL, "")

    # The same two paths at the API, where the saved side can be exercised.
    r = test_run(page, csrf, PROJECT, {"path": QUERY, "parameters": {"v": "x", "n": 1}})
    saved_run = json_of(r)
    rec("SAVED RUN: with no sql the platform's own runNamedQuery path runs",
        r["status"] == 200 and saved_run.get("ok") and saved_run.get("type") == "Query",
        f"HTTP {r['status']} {str(saved_run)[:100]}")
    rec("SAVED RUN: it returns the SAVED SQL's columns, not the draft's",
        [c["name"].lower() for c in saved_run.get("columns", [])] == ["echoed", "counted"],
        f"{[c.get('name') for c in saved_run.get('columns', [])]}")

    # A value that does not fit its declared type is refused rather than
    # rounded — the refusal has to name the identifier, the type and the value.
    r = test_run(page, csrf, PROJECT,
                 {"path": QUERY, "parameters": {"v": "x", "n": 1.5}})
    rec("TYPES: a fractional value against Int4 is a 400 naming the parameter",
        r["status"] == 400 and "n" in r["text"] and "Int4" in r["text"],
        f"HTTP {r['status']} {r['text'][:110]}")
    r = test_run(page, csrf, PROJECT,
                 {"path": QUERY, "parameters": {"v": "x", "n": "12"}})
    rec("TYPES: a numeric STRING against Int4 is accepted — the contract says so",
        r["status"] == 200 and json_of(r).get("ok"), f"HTTP {r['status']}")

    # Scalar and Update are different response SHAPES, not a Query with one
    # cell: without the type, a null scalar and an empty grid are one answer.
    r = test_run(page, csrf, PROJECT,
                 {"path": QUERY, "parameters": {}, "sql": "SELECT 42",
                  "settings": {"type": "ScalarQuery", "database": DB, "parameters": []}})
    scalar = json_of(r)
    rec("SHAPES: a ScalarQuery answers with a value and says which type it was",
        r["status"] == 200 and scalar.get("type") == "ScalarQuery"
        and scalar.get("value") == 42 and "rows" not in scalar,
        f"{str(scalar)[:100]}")

    # ==================== E. the legacy repair ===============================
    still_dead = [k for k in dead if rows(page, LEGACY_PROJECT).get(k, {}).get("legacy")]
    if not still_dead:
        for name in ("LEGACY: the tree badges a version-1 query",
                     "LEGACY: the editor says it will not run",
                     "LEGACY: a SAVED run is refused with a 409 that names the fix",
                     "LEGACY: a DRAFT run is NOT refused — testing a fix is the point",
                     "LEGACY: saving the settings unedited stamps version 2",
                     "LEGACY: the SQL survived the repair byte for byte",
                     "LEGACY: the platform now runs what it could not run before"):
            skip(name, f"no version-1 queries left in {LEGACY_PROJECT} — this check "
                       "repairs one per run and there are none to repair")
    else:
        target = still_dead[0]
        row = rows(page, LEGACY_PROJECT)[target]
        original_sql = content_of(page, LEGACY_PROJECT, target)["text"]

        page.select_option(".workspace-project select", LEGACY_PROJECT)
        page.wait_for_timeout(2000)
        # The tree ships COLLAPSED (1.6.0, Nigel 02/09) and a badge only exists
        # on a rendered row, so this has to open the branches before counting —
        # the first version of this check read 0 badges beside 29 legacy rows
        # and that was the suite, not the tree.
        for _ in range(5):
            shut = page.locator('.file-tree[aria-label="Named Queries"] '
                                '[aria-expanded="false"]')
            if shut.count() == 0:
                break
            for i in range(shut.count()):
                try:
                    shut.nth(i).click(timeout=1500)
                except Exception:
                    pass
            page.wait_for_timeout(250)
        rec("LEGACY: the tree badges a version-1 query",
            page.locator(".file-tree .badge-legacy").count() > 0,
            f"{page.locator('.file-tree .badge-legacy').count()} badged, "
            f"{len(still_dead)} legacy in the listing")

        # Refused BEFORE, allowed AFTER — the pair is the check. Either half
        # alone passes on an implementation that always refuses, or never does.
        r = test_run(page, csrf, LEGACY_PROJECT, {"path": target, "parameters": {}})
        rec("LEGACY: a SAVED run is refused with a 409 that names the fix",
            r["status"] == 409 and ("sav" in r["text"].lower() or "legacy" in r["text"].lower()),
            f"HTTP {r['status']} {r['text'][:110]}")

        r = test_run(page, csrf, LEGACY_PROJECT,
                     {"path": target, "parameters": {}, "sql": "SELECT 1 AS probe",
                      "settings": {"type": "Query", "database": DB, "parameters": []}})
        rec("LEGACY: a DRAFT run is NOT refused — testing a fix is the point",
            r["status"] == 200 and json_of(r).get("ok"), f"HTTP {r['status']} {r['text'][:110]}")

        current = settings_of(page, LEGACY_PROJECT, target)
        repair = api(page, "POST",
                     f"api/named-queries/settings/{seg(target)}"
                     f"?project={urllib.parse.quote(LEGACY_PROJECT)}",
                     csrf, {"settings": current.get("settings", {})},
                     current.get("signature") or row.get("signature"))
        page.wait_for_timeout(1500)
        repaired = settings_of(page, LEGACY_PROJECT, target)
        rec("LEGACY: saving the settings unedited stamps version 2",
            repair["status"] == 200 and repaired.get("version") == 2
            and repaired.get("legacy") is False,
            f"HTTP {repair['status']} version={repaired.get('version')} "
            f"legacy={repaired.get('legacy')}")
        rec("LEGACY: the SQL survived the repair byte for byte",
            content_of(page, LEGACY_PROJECT, target)["text"] == original_sql,
            f"{len(original_sql)} bytes")

        # The one only a live gate can make: the PLATFORM runs it now.
        r = test_run(page, csrf, LEGACY_PROJECT, {"path": target, "parameters": {}})
        ran = json_of(r)
        # A repaired query may still fail on its own SQL (a missing table is
        # not this module's problem). What must have changed is the REFUSAL.
        rec("LEGACY: the platform now runs what it could not run before",
            r["status"] != 409,
            f"was 409, now HTTP {r['status']} ok={ran.get('ok')} "
            f"{str(ran.get('error', {}).get('type', ''))[:40]} — repaired {target}")

    # ======================= F. quick open ===================================
    # Before the renames, deliberately. Quick open ranks the listing the CLIENT
    # holds, and the renames below go through the API — the client would not
    # learn of them until the 20 s watch, so searching for the new name here
    # would be testing the poll interval rather than the palette.
    page.select_option(".workspace-project select", PROJECT)
    page.wait_for_timeout(1500)
    page.keyboard.press("Control+p")
    settle(page, ".quick-open-input input", timeout=5000)
    page.fill(".quick-open-input input", "Fixture")
    page.wait_for_timeout(900)
    hits = page.locator(".quick-open-list .quick-open-row").all_inner_texts()
    rec("QUICK OPEN: a named query is offered, and says it is one",
        any("Fixture" in h and "Named Query" in h for h in hits),
        f"{[h.replace(chr(10), ' / ') for h in hits[:3]]}")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # ========================== G. renaming ==================================
    live = rows(page, PROJECT)[QUERY]

    r = api(page, "POST", f"api/named-queries/rename?project={urllib.parse.quote(PROJECT)}",
            csrf, {"path": QUERY, "newPath": MOVED})
    rec("RENAME: a query without If-Match is a 428, as a delete is",
        r["status"] == 428, f"HTTP {r['status']}")

    r = api(page, "POST", f"api/named-queries/rename?project={urllib.parse.quote(PROJECT)}",
            csrf, {"path": QUERY, "newPath": MOVED, "baseSignature": live["signature"]})
    page.wait_for_timeout(1200)
    moved_rows = rows(page, PROJECT)
    rec("RENAME: a query moves, and does not stay behind",
        r["status"] == 200 and MOVED in moved_rows and QUERY not in moved_rows,
        f"HTTP {r['status']} {sorted(k for k in moved_rows if k.startswith(FOLDER))}")
    rec("RENAME: the moved query kept its SQL",
        content_of(page, PROJECT, MOVED)["text"] == SQL, "")

    # A FOLDER rename takes no If-Match — most named-query folders are implied
    # by a path and have no resource, so there is no signature to demand.
    r = api(page, "POST", f"api/named-queries/rename?project={urllib.parse.quote(PROJECT)}",
            csrf, {"path": FOLDER, "newPath": FOLDER2})
    page.wait_for_timeout(1200)
    folder_rows = rows(page, PROJECT)
    moved_list = json_of(r).get("moved", [])
    rec("RENAME: an implied folder moves with NO If-Match, taking its children",
        r["status"] == 200 and f"{FOLDER2}/Renamed" in folder_rows
        and not any(k.startswith(FOLDER + "/") for k in folder_rows),
        f"HTTP {r['status']} moved={len(moved_list)} rows")
    rec("RENAME: the answer lists every resource that moved, so tabs can retarget",
        len(moved_list) >= 1 and all("from" in m and "to" in m for m in moved_list),
        f"{moved_list}")

    # And what it must refuse.
    r = api(page, "POST", f"api/named-queries/rename?project={urllib.parse.quote(PROJECT)}",
            csrf, {"path": FOLDER2, "newPath": f"{FOLDER2}/Inner"})
    rec("RENAME: moving a folder into itself is a 400",
        r["status"] == 400, f"HTTP {r['status']} {r['text'][:90]}")

    second = write(page, csrf, PROJECT, f"{FOLDER2}/Second", {"sql": "SELECT 1"})
    page.wait_for_timeout(800)
    clash = rows(page, PROJECT).get(f"{FOLDER2}/Second", {})
    r = api(page, "POST", f"api/named-queries/rename?project={urllib.parse.quote(PROJECT)}",
            csrf, {"path": f"{FOLDER2}/Second", "newPath": f"{FOLDER2}/Renamed",
                   "baseSignature": clash.get("signature")})
    rec("RENAME: a destination that already exists is a 409, not an overwrite",
        r["status"] == 409 and f"{FOLDER2}/Second" in rows(page, PROJECT),
        f"HTTP {r['status']}")

    # ========================== H. cleanup ===================================
    cleanup(page, csrf, PROJECT)
    page.wait_for_timeout(800)
    left = [k for k in rows(page, PROJECT) if k.split("/")[0] in (FOLDER, FOLDER2)]
    rec("CLEANUP: every fixture row this suite created is gone",
        not left, f"{left}" if left else "")

    browser.close()

passed = sum(1 for _, ok, _ in res if ok)
print(f"\n{passed}/{len(res)} checks passed")
sys.exit(0 if passed == len(res) else 1)
