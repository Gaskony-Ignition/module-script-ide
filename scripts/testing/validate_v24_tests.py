"""
R6 — a Jython test runner, on the real gateway.

Discovery, the three outcomes, per-test output and the panel that shows them,
all against the module-testing rig rather than a mock. The three findings that
made capturing a test's own output hard each fail SILENTLY — the run reports
success and the output is simply gone — so the assertions here are what stop
them coming back:

* every import happens before any output;
* the private interpreter state is re-asserted after those imports; and
* the harness flushes its own streams, because a batch run has no pump.

Everything this suite creates it removes: three fixture library modules and the
package folder they sit in.

Run:
    SI_GATEWAY_CONFIG=$PWD/config.local.json \\
      .venv-test/bin/python scripts/testing/validate_v24_tests.py
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

# Fixture modules. The names carry the convention they are testing: the probe is
# `_si_v24.test_probe`, whose LAST segment starts with `test`, and the decoy is
# `_si_v24.plain`, whose does not. The first version of this suite named them
# `_si_v24_test_probe` and `_si_v24_plain` and discovered nothing — the leaf of
# the first is `_si_v24_test_probe`, which does not start with `test`. That was
# the convention working, not failing, and it is why the names are shaped so.
TEST_MODULE = "ignition/script-python/_si_v24/test_probe"
ORDINARY_MODULE = "ignition/script-python/_si_v24/plain"
# The PACKAGE is a resource in its own right, and deleting the three scripts
# inside it leaves it behind — an empty folder that accumulates one per run and
# shows up in the next release's README screenshot. It is removed LAST, because
# the platform will not delete a folder that still has children.
FIXTURE_FOLDER = "ignition/script-python/_si_v24"
FIXTURES = (TEST_MODULE, ORDINARY_MODULE, FIXTURE_FOLDER)

# One of each outcome, plus a setUp that a passing test can observe. Tabs, per
# the estate's Jython standard.
TEST_SOURCE = "\n".join([
    "_si_v24_setup_ran = False",
    "",
    "def setUp():",
    "\tglobal _si_v24_setup_ran",
    "\t_si_v24_setup_ran = True",
    "",
    "def test_passes():",
    "\tprint 'hello from the passing test'",
    "\tassert _si_v24_setup_ran",
    "",
    "def test_fails():",
    "\tassert 1 == 2, 'one is not two'",
    "",
    "def test_errors():",
    "\timport _si_v24_definitely_not_a_module",
    "",
    "def helper():",
    "\treturn 'not a test'",
    "",
    "class TestGroup:",
    "\tdef test_method(self):",
    "\t\tassert True",
    "",
])

# The same function name, in a module the convention says is NOT a test module.
# If this one is ever discovered, the narrowing has been lost.
ORDINARY_SOURCE = "def test_connection():\n\traise Exception('this must never run')\n"

res = []


def rec(name, ok, detail=""):
    res.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def api(page, method, url, csrf="", body=None):
    return page.evaluate(
        """async ([spa, method, url, csrf, body]) => {
             const headers = {'Accept': 'application/json'};
             if (csrf) headers['X-CSRF-Token'] = csrf;
             if (body !== null) headers['Content-Type'] = 'application/json';
             const res = await fetch(spa + url, {
               method, credentials: 'include', headers,
               body: body === null ? undefined : JSON.stringify(body)});
             return {status: res.status, text: await res.text()};
           }""",
        [SPA, method, url, csrf, body])


def json_of(response):
    try:
        return json.loads(response["text"])
    except Exception:
        return {}


def q(value):
    return urllib.parse.quote(str(value))


def tree(page, project=PROJECT):
    return json_of(api(page, "GET", f"api/scripts?project={q(project)}")).get("scripts", [])


def entry_for(page, path, project=PROJECT):
    return next((e for e in tree(page, project) if e.get("path") == path), None)


def write(page, csrf, path, source):
    found = entry_for(page, path)
    signature = found.get("signature") if found else None
    return page.evaluate(
        """async ([spa, url, csrf, source, ifMatch]) => {
             const headers = {'Accept': 'application/json',
                              'Content-Type': 'application/json',
                              'X-CSRF-Token': csrf};
             if (ifMatch) headers['If-Match'] = ifMatch;
             const res = await fetch(spa + url, {
               method: 'POST', credentials: 'include', headers,
               body: JSON.stringify({source})});
             return {status: res.status, text: await res.text()};
           }""",
        [SPA, f"api/scripts/content/{urllib.parse.quote(path, safe='')}?project={q(PROJECT)}",
         csrf, source, signature])


def remove_fixtures(page, csrf):
    for path in FIXTURES:
        found = entry_for(page, path)
        if not found:
            continue
        page.evaluate(
            """async ([spa, url, csrf, ifMatch]) => {
                 await fetch(spa + url, {method: 'DELETE', credentials: 'include',
                   headers: {'X-CSRF-Token': csrf, 'If-Match': ifMatch}});
               }""",
            [SPA, f"api/scripts/content/{urllib.parse.quote(path, safe='')}?project={q(PROJECT)}",
             csrf, found.get("signature") or ""])


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

    # =================== discovery ===================
    made = write(page, csrf, TEST_MODULE, TEST_SOURCE)
    rec("FIXTURE: the test module was created", made["status"] == 200,
        f"HTTP {made['status']} {made['text'][:70]}")
    plain = write(page, csrf, ORDINARY_MODULE, ORDINARY_SOURCE)
    rec("FIXTURE: the ordinary module was created", plain["status"] == 200,
        f"HTTP {plain['status']} {plain['text'][:70]}")

    listing = {}
    for attempt in range(8):
        # The project index rebuilds a moment after a resource write, so the
        # first listing for a brand-new file legitimately finds nothing.
        page.wait_for_timeout(2000 + 1000 * attempt)
        listing = json_of(api(page, "GET", f"api/tests?project={q(PROJECT)}"))
        if listing.get("total", 0) > 0:
            break

    ids = [t["id"] for m in listing.get("modules", []) for t in m.get("tests", [])]
    rec("RUNNER: the four tests in the fixture are discovered",
        sum(1 for i in ids if "_si_v24.test_probe" in i) == 4,
        f"{len(ids)} discovered: {[i.split('.')[-1] for i in ids][:6]}")

    # The narrowing that keeps `test_connection` off a Run All button. This is
    # the assertion the whole discovery convention exists for.
    rec("RUNNER: a test-named function in an ORDINARY module is NOT discovered",
        not any("_si_v24.plain" in i for i in ids),
        "the module rule holds")

    rec("RUNNER: a helper beside the tests is not mistaken for one",
        not any(i.endswith(".helper") for i in ids), "helper() was skipped")
    rec("RUNNER: a test method on a Test-named class is found, and named fully",
        any(i.endswith("TestGroup.test_method") for i in ids),
        next((i for i in ids if "TestGroup" in i), "not found"))
    rec("RUNNER: the module reports that it brackets its tests with setUp",
        any(m.get("hasSetUp") for m in listing.get("modules", [])
            if "_si_v24.test_probe" in m.get("module", "")),
        "hasSetUp is true")
    rec("RUNNER: the response states the discovery convention",
        "test_" in listing.get("convention", ""), listing.get("convention", "")[:80])

    # =================== the run ===================
    mine = [i for i in ids if "_si_v24.test_probe" in i]
    run = json_of(api(page, "POST", f"api/tests/run?project={q(PROJECT)}", csrf, {"ids": mine}))
    by_id = {r["id"]: r for r in run.get("results", [])}

    rec("RUNNER: every requested test ran", len(by_id) == len(mine),
        f"{len(by_id)} of {len(mine)}")
    rec("RUNNER: the tally counts one of each outcome",
        run.get("passed") == 2 and run.get("failed") == 1 and run.get("errored") == 1,
        f"passed={run.get('passed')} failed={run.get('failed')} errored={run.get('errored')}")

    passing = next((r for r in by_id.values() if r["id"].endswith("test_passes")), {})
    rec("RUNNER: setUp ran before the test — the passing test asserts it did",
        passing.get("status") == "pass", passing.get("message", "") or "passed")
    rec("RUNNER: what a test PRINTED is captured with it",
        "hello from the passing test" in passing.get("output", ""),
        passing.get("output", "")[:60].strip())

    failing = next((r for r in by_id.values() if r["id"].endswith("test_fails")), {})
    rec("RUNNER: a false assertion is a FAIL, and its message survives",
        failing.get("status") == "fail" and "one is not two" in failing.get("message", ""),
        f"{failing.get('status')}: {failing.get('message', '')[:50]}")

    erroring = next((r for r in by_id.values() if r["id"].endswith("test_errors")), {})
    # The distinction that sends a reader to the right half of the file: an
    # error never got far enough to have an opinion about anything.
    rec("RUNNER: anything other than an assertion is an ERROR, not a failure",
        erroring.get("status") == "error", f"{erroring.get('status')}: "
        f"{erroring.get('message', '')[:60]}")
    rec("RUNNER: an error carries a traceback",
        bool(erroring.get("traceback")), erroring.get("traceback", "")[:60].replace("\n", " "))

    # An id the client invented must not become a call to an arbitrary function.
    invented = api(page, "POST", f"api/tests/run?project={q(PROJECT)}", csrf,
                   {"ids": ["_si_v24.plain.test_connection"]})
    rec("RUNNER: an id the server did not discover is refused",
        invented["status"] == 400, f"HTTP {invented['status']} "
        f"{json_of(invented).get('error', '')[:60]}")

    # =================== the panel ===================
    page.locator('.activity-item[aria-label="Tests"]').click()
    page.wait_for_selector(".tests-panel", timeout=20000)
    page.wait_for_timeout(2000)
    rec("UI: the Tests panel lists the fixture module",
        "_si_v24.test_probe" in page.locator(".tests-panel").inner_text(),
        page.locator(".tests-panel-count").inner_text())

    page.locator(".tests-panel-run").click()
    page.wait_for_selector(".tests-panel-tally", timeout=120000)
    tally = page.locator(".tests-panel-tally").inner_text().replace("\n", " ")
    rec("UI: running from the panel reports passes and failures separately",
        "passed" in tally and "failed" in tally, tally[:80])

    why = page.locator(".tests-row-toggle").first
    if why.count():
        why.click()
        page.wait_for_timeout(600)
        detail = page.locator(".tests-row-detail").first.inner_text()
        rec("UI: a failure explains itself on demand",
            "failed" in detail or "errored" in detail, detail[:80].replace("\n", " "))
    else:
        rec("UI: a failure explains itself on demand", False, "no toggle rendered")

    # 1.21.0 changed what the caveat SAYS, because it changed what is true:
    # module state no longer carries between runs, but the tests within one run
    # still share the namespace. The assertion follows the fact.
    rec("UI: the panel says what the tests in one run share",
        "share one interpreter" in page.locator(".tests-panel").inner_text(),
        "the caveat is on screen")

    # =================== clean up ===================
    remove_fixtures(page, csrf)
    left = [p for p in FIXTURES if entry_for(page, p)]
    rec("CLEANUP: every fixture script was removed", not left, ", ".join(left) or "none left")

    browser.close()

passed = sum(1 for _, ok, _ in res if ok)
print(f"\n{passed}/{len(res)} checks passed")
sys.exit(0 if passed == len(res) else 1)
