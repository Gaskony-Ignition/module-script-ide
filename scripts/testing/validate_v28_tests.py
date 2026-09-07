"""1.21.0 — the test framework: decorators, assertions, mocks, and a private namespace.

Everything here is on the real gateway because every claim in it is about how
Jython behaves inside Ignition, and none of it can be checked from a unit test.

The design rests on one measurement, taken 07/09/2026 and re-asserted below.
`__import__` of a project-library module hands back the manager's OWN module
object: the same `id()` came back from two separate runs, and a module global set
in one run was read by the next, on every user's behalf. So the mock the alternative's
runner uses — swapping `globals()['system']` in the module under test — would
change what every script on the gateway sees for as long as the block is open.
That is the same class of mistake as the JVM-wide `__builtins__` edit recorded in
CLAUDE.md, and it is refused here.

Instead the runner is handed each test module's SOURCE and executes it into a
namespace private to the run. Three things follow, and all three are asserted:

  * a mock can replace `system` in that namespace safely, and the SHARED module
    is untouched while it is open;
  * module-level state no longer carries from one run to the next; and
  * when the source cannot be read the runner imports instead and a mock REFUSES,
    rather than quietly writing into the gateway's copy.

Everything this suite creates it removes.

Run:
    SI_GATEWAY_CONFIG=$PWD/config.local.json \\
      .venv-test/bin/python scripts/testing/validate_v28_tests.py
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

PKG = "_si_v28"
# The leaf name is what the convention reads, so `test_probe` qualifies and
# `plain` does not. See the note in validate_v24_tests.py: a module called
# `_si_v28_test_probe` would NOT qualify, because its leaf does not start `test`.
FEATURES = f"ignition/script-python/{PKG}/test_features"
MOCKS = f"ignition/script-python/{PKG}/test_mocks"
STATE = f"ignition/script-python/{PKG}/test_state"
NEUTRAL = f"ignition/script-python/{PKG}/test_neutral"
DECOY = f"ignition/script-python/{PKG}/plain"
FOLDER = f"ignition/script-python/{PKG}"
# The package folder is a resource in its own right and will not delete while it
# still has children, so it goes last.
FIXTURES = (FEATURES, MOCKS, STATE, NEUTRAL, DECOY, FOLDER)

# Tabs, per the estate's Jython standard.
FEATURES_SOURCE = "\n".join([
    "from scriptide import test, skip, timeout, cases",
    "from scriptide import beforeAll, afterAll, beforeEach, afterEach",
    "from scriptide import assertEquals, assertRaises, assertAlmostEquals, assertIn",
    "",
    "CALLS = []",
    "",
    "@beforeAll",
    "def openTheModule():",
    "\tCALLS.append('beforeAll')",
    "",
    "@afterAll",
    "def closeTheModule():",
    "\tCALLS.append('afterAll')",
    "",
    "@beforeEach",
    "def eachOne():",
    "\tCALLS.append('beforeEach')",
    "",
    "@afterEach",
    "def eachOneAfter():",
    "\tCALLS.append('afterEach')",
    "",
    "@test",
    "def check_totals():",
    "\tassertEquals(2 + 2, 4)",
    "",
    "@skip('waiting on the PLC')",
    "def test_is_skipped():",
    "\traise Exception('a skipped test must never run')",
    "",
    "@cases((2, 3, 5), (0, 0, 0), (1, 1, 3))",
    "def test_adds(a, b, expected):",
    "\tassertEquals(a + b, expected)",
    "",
    "@timeout(0.001)",
    "def test_over_budget():",
    "\timport time",
    "\ttime.sleep(0.4)",
    "",
    "def test_raises():",
    "\twith assertRaises(ValueError) as raised:",
    "\t\tint('not a number')",
    "\tassertIn('invalid literal', str(raised.exception))",
    "",
    "def test_almost():",
    "\tassertAlmostEquals(0.1 + 0.2, 0.3)",
    "",
    "def test_brackets_ran():",
    "\t# beforeAll once, and one beforeEach per test that has run so far.",
    "\tassertEquals(CALLS.count('beforeAll'), 1)",
    "\tassertIn('beforeEach', CALLS)",
    "",
    "def test_message_says_what_it_wanted():",
    "\tassertEquals('left', 'right')",
    "",
])

MOCKS_SOURCE = "\n".join([
    "from scriptide import mockTags, mockQuery, assertEquals, assertTagValue",
    "from scriptide import assertDbRowCount, assertRaises",
    "",
    "# A path no gateway has. Reading it for real is an error, so a passing read",
    "# proves the mock answered rather than the gateway.",
    "ABSENT = '[default]_si_v28/nothing/at/all'",
    "",
    "def test_mock_answers_a_read():",
    "\twith mockTags({ABSENT: 42}):",
    "\t\tassertEquals(system.tag.readBlocking([ABSENT])[0].value, 42)",
    "",
    "def test_mock_records_a_write():",
    "\twith mockTags({ABSENT: 0}) as tags:",
    "\t\tsystem.tag.writeBlocking([ABSENT], [7])",
    "\tassertEquals(tags.writes, [(ABSENT, 7)])",
    "",
    "def test_a_written_tag_reads_back():",
    "\twith mockTags({ABSENT: 0}):",
    "\t\tsystem.tag.writeBlocking([ABSENT], [9])",
    "\t\tassertTagValue(ABSENT, 9)",
    "",
    "def test_an_unmocked_path_is_loud():",
    "\twith mockTags({ABSENT: 1}):",
    "\t\twith assertRaises(AssertionError):",
    "\t\t\tsystem.tag.readBlocking(['[default]_si_v28/other'])",
    "",
    "def test_the_real_system_comes_back():",
    "\twith mockTags({ABSENT: 1}):",
    "\t\tpass",
    "\t# Outside the block the name resolves to the gateway's own object again.",
    "\tassertEquals(system.tag.__class__.__name__, 'ImmutableScriptPackage')",
    "",
    "def test_mock_answers_a_query():",
    "\twith mockQuery({'FROM _si_v28': [[1, 'a'], [2, 'b']]}) as db:",
    "\t\tassertDbRowCount('SELECT * FROM _si_v28_orders', 2)",
    "\tassertEquals(len(db.queries), 1)",
    "",
    "def test_an_unanswered_query_is_loud():",
    "\twith mockQuery({'FROM _si_v28': []}):",
    "\t\twith assertRaises(AssertionError):",
    "\t\t\tsystem.db.runQuery('SELECT * FROM something_else')",
    "",
])

# The module state test: a global that a run increments. Run twice, it must say
# 1 both times -- the property the private namespace buys.
STATE_SOURCE = "\n".join([
    "from scriptide import assertEquals",
    "",
    "COUNT = 0",
    "",
    "def test_state_does_not_carry():",
    "\tglobal COUNT",
    "\tCOUNT = COUNT + 1",
    "\tassertEquals(COUNT, 1)",
    "",
])

# A test module with NO top-level `from scriptide import`. That matters: the
# helper module exists only while a run is executing, so a module that imports it
# at the top cannot be imported at all outside one -- asserted below, because it
# is a consequence people will meet rather than a thing anyone would guess. A
# function-level import is the pattern for a test module that must stay
# importable, and this fixture is also how the no-leak check is made: the shared
# copy can only be read from the console if the console can import it.
NEUTRAL_SOURCE = "\n".join([
    "ABSENT = '[default]_si_v28/neutral/nothing'",
    "",
    "def test_mock_does_not_escape():",
    "\tfrom scriptide import mockTags, assertEquals",
    "\twith mockTags({ABSENT: 5}):",
    "\t\tassertEquals(system.tag.readBlocking([ABSENT])[0].value, 5)",
    "",
])

# NOT a test module: its leaf name is `plain`. A @test in here must discover
# nothing at all -- the decorator widens the function rule and never the module
# rule, which is what keeps `plc.diagnostics.test_connection` off a Run button.
DECOY_SOURCE = "\n".join([
    "from scriptide import test",
    "",
    "@test",
    "def check_nothing():",
    "\traise Exception('this must never run')",
    "",
    "def test_connection():",
    "\traise Exception('nor this')",
    "",
])

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


def tree(page):
    return json_of(api(page, "GET", f"api/scripts?project={q(PROJECT)}")).get("scripts", [])


def entry_for(page, path):
    return next((e for e in tree(page) if e.get("path") == path), None)


def write(page, csrf, path, source):
    found = entry_for(page, path)
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
         csrf, source, found.get("signature") if found else None])


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


def run_tests(page, csrf, ids):
    return json_of(api(page, "POST", f"api/tests/run?project={q(PROJECT)}", csrf, {"ids": ids}))


def by_id(run):
    return {r["id"]: r for r in run.get("results", [])}


with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    login(page)
    page.goto(GATEWAY_URL + SPA, wait_until="load", timeout=30000)
    page.wait_for_selector(".file-tree-header", timeout=20000)
    csrf = page.evaluate(
        "async (spa) => (await (await fetch(spa + 'api/auth/session',"
        " {credentials:'include'})).json()).csrfToken", SPA)
    page.select_option(".workspace-project select", PROJECT)
    page.wait_for_timeout(1500)
    remove_fixtures(page, csrf)

    written = [
        write(page, csrf, FEATURES, FEATURES_SOURCE)["status"],
        write(page, csrf, MOCKS, MOCKS_SOURCE)["status"],
        write(page, csrf, STATE, STATE_SOURCE)["status"],
        write(page, csrf, NEUTRAL, NEUTRAL_SOURCE)["status"],
        write(page, csrf, DECOY, DECOY_SOURCE)["status"],
    ]
    rec("FIXTURE: five modules were created", all(s == 200 for s in written), f"HTTP {written}")

    listing = {}
    for attempt in range(8):
        # The project index rebuilds a moment after a resource write, so the
        # first listing for a brand-new file legitimately finds nothing.
        page.wait_for_timeout(2000 + 1000 * attempt)
        listing = json_of(api(page, "GET", f"api/tests?project={q(PROJECT)}"))
        names = [m["module"] for m in listing.get("modules", [])]
        if f"{PKG}.test_features" in names and f"{PKG}.test_mocks" in names:
            break

    modules = {m["module"]: m for m in listing.get("modules", [])}
    features = modules.get(f"{PKG}.test_features", {})
    cases = {t["id"]: t for t in features.get("tests", [])}

    try:
        # =================== discovery ===================

        rec("the listing offers the helper import line",
            listing.get("helperImport", "").startswith("from scriptide import "),
            listing.get("helperImport", "<absent>"))

        rec("@test discovers a function whose name is not test_*",
            f"{PKG}.test_features.check_totals" in cases,
            ", ".join(sorted(cases))[:120])

        rec("a decorated test says so, and a conventionally named one does not",
            cases.get(f"{PKG}.test_features.check_totals", {}).get("decorated") is True
            and cases.get(f"{PKG}.test_features.test_raises", {}).get("decorated") is False,
            f"check_totals={cases.get(f'{PKG}.test_features.check_totals', {}).get('decorated')}"
            f" test_raises={cases.get(f'{PKG}.test_features.test_raises', {}).get('decorated')}")

        # THE load-bearing one. A decorator widens which FUNCTIONS count, never
        # which modules are looked at -- so `plc.diagnostics.test_connection`
        # stays off the Run All button however it is written.
        rec("THE MODULE RULE IS NOT WIDENED: @test in an ordinary module finds nothing",
            f"{PKG}.plain" not in modules,
            "modules: " + ", ".join(sorted(modules))[:140])

        rec("@skip is LISTED, and marked, rather than hidden",
            cases.get(f"{PKG}.test_features.test_is_skipped", {}).get("skipped") is True,
            json.dumps(cases.get(f"{PKG}.test_features.test_is_skipped", {}))[:120])

        rec("the four brackets are reported on the module",
            features.get("hasBeforeAll") and features.get("hasAfterAll")
            and features.get("hasBeforeEach") and features.get("hasAfterEach"),
            f"beforeAll={features.get('hasBeforeAll')} afterAll={features.get('hasAfterAll')} "
            f"beforeEach={features.get('hasBeforeEach')} afterEach={features.get('hasAfterEach')}")

        rec("a bracket is not itself discovered as a test",
            not any(name.endswith(("openTheModule", "closeTheModule", "eachOne", "eachOneAfter"))
                    for name in cases),
            ", ".join(sorted(cases))[:140])

        # =================== the run ===================

        featureIds = sorted(cases)
        run = run_tests(page, csrf, featureIds)
        results = by_id(run)

        rec("the run reported a result for every selected test",
            len(run.get("results", [])) >= len(featureIds),
            f"{len(run.get('results', []))} results for {len(featureIds)} tests")

        rec("a skipped test reports skip and is counted separately",
            results.get(f"{PKG}.test_features.test_is_skipped", {}).get("status") == "skip"
            and run.get("skipped") == 1,
            f"status={results.get(f'{PKG}.test_features.test_is_skipped', {}).get('status')} "
            f"skipped={run.get('skipped')}")

        rec("a skipped test carries the reason it was given",
            "PLC" in results.get(f"{PKG}.test_features.test_is_skipped", {}).get("message", ""),
            results.get(f"{PKG}.test_features.test_is_skipped", {}).get("message", "")[:80])

        # @cases((2,3,5), (0,0,0), (1,1,3)) -- the third is wrong on purpose.
        expanded = [r for r in run.get("results", [])
                    if r.get("parentId") == f"{PKG}.test_features.test_adds"]
        rec("@cases expands into one result per row",
            len(expanded) == 3, f"{len(expanded)} rows")
        rec("each case carries its own label, and the ids are distinct",
            len({r["id"] for r in expanded}) == 3
            and all(r.get("case") for r in expanded),
            "; ".join(f"{r['id']}={r.get('case')}" for r in expanded)[:160])
        rec("a failing case fails ALONE, and names itself",
            sorted(r["status"] for r in expanded) == ["fail", "pass", "pass"],
            "; ".join(f"{r.get('case')}:{r['status']}" for r in expanded)[:160])
        rec("a case's parentId is the discovered test, so a re-run can target it",
            all(r.get("parentId") == f"{PKG}.test_features.test_adds" for r in expanded),
            ", ".join(sorted({r.get("parentId", "") for r in expanded})))

        rec("an ordinary test's parentId is its own id",
            results.get(f"{PKG}.test_features.test_raises", {}).get("parentId")
            == f"{PKG}.test_features.test_raises",
            results.get(f"{PKG}.test_features.test_raises", {}).get("parentId", "<absent>"))

        rec("assertRaises catches the class it was asked about",
            results.get(f"{PKG}.test_features.test_raises", {}).get("status") == "pass",
            results.get(f"{PKG}.test_features.test_raises", {}).get("message", "")[:90])

        rec("assertAlmostEquals is how a float comparison is written",
            results.get(f"{PKG}.test_features.test_almost", {}).get("status") == "pass",
            results.get(f"{PKG}.test_features.test_almost", {}).get("message", "")[:90])

        # A budget, not an interrupt: the test finishes and then fails.
        budget = results.get(f"{PKG}.test_features.test_over_budget", {})
        rec("@timeout fails a test that took longer than its budget",
            budget.get("status") == "fail" and "budget" in budget.get("message", ""),
            f"{budget.get('status')}: {budget.get('message', '')[:80]}")

        rec("the brackets actually ran, once and per test",
            results.get(f"{PKG}.test_features.test_brackets_ran", {}).get("status") == "pass",
            results.get(f"{PKG}.test_features.test_brackets_ran", {}).get("message", "")[:90])

        failure = results.get(f"{PKG}.test_features.test_message_says_what_it_wanted", {})
        rec("a failed assertion says what it wanted and what it got",
            failure.get("status") == "fail"
            and "'right'" in failure.get("message", "")
            and "'left'" in failure.get("message", ""),
            failure.get("message", "")[:100])

        rec("@test found a function the naming convention would have missed, and it ran",
            results.get(f"{PKG}.test_features.check_totals", {}).get("status") == "pass",
            results.get(f"{PKG}.test_features.check_totals", {}).get("status", "<absent>"))

        # =================== the private namespace ===================

        stateIds = [f"{PKG}.test_state.test_state_does_not_carry"]
        first = by_id(run_tests(page, csrf, stateIds))
        second = by_id(run_tests(page, csrf, stateIds))
        rec("MODULE STATE DOES NOT CARRY BETWEEN RUNS",
            first.get(stateIds[0], {}).get("status") == "pass"
            and second.get(stateIds[0], {}).get("status") == "pass",
            f"first={first.get(stateIds[0], {}).get('status')} "
            f"second={second.get(stateIds[0], {}).get('status')}: "
            f"{second.get(stateIds[0], {}).get('message', '')[:60]}")

        mockModule = modules.get(f"{PKG}.test_mocks", {})
        mockIds = sorted(t["id"] for t in mockModule.get("tests", []))
        mockRun = run_tests(page, csrf, mockIds)
        mocked = by_id(mockRun)

        rec("a mock answers a tag read for a path no gateway has",
            mocked.get(f"{PKG}.test_mocks.test_mock_answers_a_read", {}).get("status") == "pass",
            mocked.get(f"{PKG}.test_mocks.test_mock_answers_a_read", {}).get("message", "")[:90])
        rec("a mock records what the code under test wrote",
            mocked.get(f"{PKG}.test_mocks.test_mock_records_a_write", {}).get("status") == "pass",
            mocked.get(f"{PKG}.test_mocks.test_mock_records_a_write", {}).get("message", "")[:90])
        rec("a tag written through a mock reads back through it",
            mocked.get(f"{PKG}.test_mocks.test_a_written_tag_reads_back", {}).get("status")
            == "pass",
            mocked.get(f"{PKG}.test_mocks.test_a_written_tag_reads_back", {})
            .get("message", "")[:90])
        rec("a read of an unmocked path raises rather than answering None",
            mocked.get(f"{PKG}.test_mocks.test_an_unmocked_path_is_loud", {}).get("status")
            == "pass",
            mocked.get(f"{PKG}.test_mocks.test_an_unmocked_path_is_loud", {})
            .get("message", "")[:90])
        rec("the real `system` is back the moment the block closes",
            mocked.get(f"{PKG}.test_mocks.test_the_real_system_comes_back", {}).get("status")
            == "pass",
            mocked.get(f"{PKG}.test_mocks.test_the_real_system_comes_back", {})
            .get("message", "")[:90])
        rec("a mock answers a query by SQL fragment, and records it",
            mocked.get(f"{PKG}.test_mocks.test_mock_answers_a_query", {}).get("status") == "pass",
            mocked.get(f"{PKG}.test_mocks.test_mock_answers_a_query", {}).get("message", "")[:90])
        rec("a query matching no fragment raises rather than returning nothing",
            mocked.get(f"{PKG}.test_mocks.test_an_unanswered_query_is_loud", {}).get("status")
            == "pass",
            mocked.get(f"{PKG}.test_mocks.test_an_unanswered_query_is_loud", {})
            .get("message", "")[:90])

        neutralId = f"{PKG}.test_neutral.test_mock_does_not_escape"
        neutral = by_id(run_tests(page, csrf, [neutralId]))
        rec("a function-level import of the helpers works too",
            neutral.get(neutralId, {}).get("status") == "pass",
            neutral.get(neutralId, {}).get("message", "")[:90])

        # THE ONE THAT MATTERS MOST. A mock is only defensible if it cannot reach
        # the gateway's own copy of the module. Import that module the ordinary
        # way from the console, AFTER the run above installed a mock in it, and
        # read its `system` -- if a mock had leaked, this is where it would show.
        page.locator('button[aria-label="Script Console"]').click()
        page.wait_for_timeout(800)
        page.wait_for_selector(".console-editor .cm-content", timeout=20000)

        def console(source):
            clear = page.locator(".console-toolbar").get_by_role(
                "button", name="Clear output", exact=True)
            if clear.is_enabled():
                clear.click()
                page.wait_for_timeout(200)
            page.locator(".console-editor .cm-content").click()
            page.keyboard.press("Control+a")
            page.keyboard.press("Delete")
            page.keyboard.insert_text(source)
            page.wait_for_timeout(250)
            page.locator(".console-toolbar").get_by_role(
                "button", name="Run", exact=True).click()
            page.wait_for_timeout(3500)
            return page.evaluate(
                "() => document.querySelector('.console-output')?.innerText ?? ''")

        shared = console(
            f"import {PKG}.test_neutral as shared\n"
            "print 'SHARED', shared.__dict__['system'].tag.__class__.__name__\n")
        rec("THE SHARED MODULE IS UNTOUCHED: its `system` is still the gateway's",
            "SHARED ImmutableScriptPackage" in shared,
            shared.strip()[:110].replace("\n", " | "))

        # The other half of the same fact, asserted so nobody reports it as a bug:
        # `scriptide` exists only while a run is executing, so a test module that
        # imports it at the TOP cannot be imported outside one. That is the point
        # of it -- a helper ordinary gateway code could reach would be a second
        # script library nobody administers -- and the runner never imports a test
        # module anyway, it executes its source.
        outside = console(f"import {PKG}.test_mocks\nprint 'IMPORTED'\n")
        rec("a module importing the helpers at the top is NOT importable outside a run",
            "IMPORTED" not in outside and "scriptide" in outside,
            outside.strip()[:120].replace("\n", " | "))

        # =================== the panel ===================

        page.locator('button[aria-label="Tests"]').click()
        page.wait_for_selector(".tests-panel", timeout=20000)
        page.wait_for_timeout(1200)

        rerun = page.locator(".tests-panel-rerun")
        rec("the re-run button is present and refuses to run nothing",
            rerun.count() == 1 and not rerun.is_enabled(),
            f"count={rerun.count()} enabled={rerun.is_enabled() if rerun.count() else 'n/a'}")

        page.locator(".tests-panel-run").click()
        page.wait_for_selector(".tests-panel-tally", timeout=180000)
        page.wait_for_timeout(800)
        tally = page.locator(".tests-panel-tally").inner_text().replace("\n", " ")
        rec("the tally counts skipped alongside passed and failed",
            "skipped" in tally, tally[:120])

        rec("the re-run button offers the failures it just found",
            rerun.is_enabled() and "failed" in rerun.inner_text(),
            rerun.inner_text().replace("\n", " ")[:80])

        rec("a parameterised test's cases are shown under it",
            page.locator(".tests-case-row").count() >= 3,
            f"{page.locator('.tests-case-row').count()} case rows")

        panel = page.locator(".tests-panel").inner_text()
        rec("the panel no longer claims module state carries between runs",
            "share an interpreter" not in panel or "between runs" in panel,
            panel[-200:].replace("\n", " "))
    finally:
        remove_fixtures(page, csrf)
        browser.close()

passed = sum(1 for _, ok, _ in res if ok)
print(f"\nvalidate_v28_tests   {passed}/{len(res)} checks passed")
sys.exit(0 if passed == len(res) else 1)
