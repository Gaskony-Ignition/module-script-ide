"""
R5 (two gateways side by side) and R6 (a Jython test runner), on the real gateway.

**The peer here is this gateway itself, and that is stated rather than hidden.**
The rig has exactly one gateway running this module, and the other containers on
this workstation belong to a different project that test modules must never be
installed on. So the suite configures `policy.properties` with a peer whose URL
is this gateway's own, which exercises every part of the path — the config
parsing, the name-not-URL lookup, the inbound token check, the outbound HTTP
client, the digest route and the drift comparison. The one property it cannot
prove is that the two ends are different machines. That is F2's question, not
this one's, and it is the reason `docs/STATE.md` still says so.

Two consequences that make the loopback peer a GOOD test rather than a weak one:

* comparing a project with itself must report zero drift — an off-by-one in the
  digest keying, or a hash taken over the wrong bytes, shows up immediately as
  phantom differences; and
* comparing two DIFFERENT projects across the same link must report real drift,
  so "zero" cannot be passing by accident.

Everything this suite creates it removes: four fixture library modules, and the
policy file itself, which did not exist on this rig before.

Run:
    SI_GATEWAY_CONFIG=$PWD/config.local.json \\
      .venv-test/bin/python scripts/testing/validate_v24_gateways_tests.py
"""
import json
import os
import subprocess
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gateway_session import CONFIG, GATEWAY_URL, login          # noqa: E402
from playwright.sync_api import sync_playwright                 # noqa: E402

SPA = CONFIG.get("spa_path", "/data/scriptide/")
PROJECT = os.environ.get("SI_EDIT_PROJECT", "Mining_Demo")
OTHER_PROJECT = os.environ.get("SI_OTHER_PROJECT", "Machine_HMI_Demo")

CONTAINER = os.environ.get("SI_CONTAINER", "ignition-module-testing")
POLICY_DIR = "/usr/local/bin/ignition/data/modules/scriptide"
POLICY_FILE = POLICY_DIR + "/policy.properties"

PEER_NAME = "selfloop"
PEER_LABEL = "This gateway (loopback)"
# 32 characters, comfortably over RemoteGateways.MIN_TOKEN_CHARS. Not a secret:
# it lives for the length of this run on a lab gateway and is deleted after.
TOKEN = "siV24LoopbackTokenForTestingOnly"

# Fixture modules. The names carry the convention they are testing: the probe is
# `_si_v24.test_probe`, whose LAST segment starts with `test`, and the decoy is
# `_si_v24.plain`, whose does not. The first version of this suite named them
# `_si_v24_test_probe` and `_si_v24_plain` and discovered nothing — the leaf of
# the first is `_si_v24_test_probe`, which does not start with `test`. That was
# the convention working, not failing, and it is why the names are shaped so.
TEST_MODULE = "ignition/script-python/_si_v24/test_probe"
ORDINARY_MODULE = "ignition/script-python/_si_v24/plain"
DRIFT_MODULE = "ignition/script-python/_si_v24/drift"
FIXTURES = (TEST_MODULE, ORDINARY_MODULE, DRIFT_MODULE)

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

DRIFT_SOURCE = "value = 'v24'\n"

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


# ==================== the policy file ====================

def docker(*args):
    return subprocess.run(["docker", "exec", CONTAINER, *args],
                          capture_output=True, text=True, timeout=60)


def write_policy():
    """Create the peer configuration, pointed at this gateway.

    Written through the container's own shell rather than a bind mount: the
    module reads it from the gateway's data directory, and that directory is
    inside a named volume this workstation does not mount anywhere.
    """
    body = "\n".join([
        f"com.gaskony.scriptide.remote.inboundToken={TOKEN}",
        f"com.gaskony.scriptide.remote.{PEER_NAME}.url={GATEWAY_URL}",
        f"com.gaskony.scriptide.remote.{PEER_NAME}.label={PEER_LABEL}",
        f"com.gaskony.scriptide.remote.{PEER_NAME}.token={TOKEN}",
        "",
    ])
    docker("mkdir", "-p", POLICY_DIR)
    # Staged then renamed, the same rule every config write in this estate
    # follows: a half-written properties file read mid-save is a configuration
    # the module would apply.
    docker("sh", "-c", f"cat > {POLICY_FILE}.tmp <<'SIV24EOF'\n{body}SIV24EOF")
    docker("sh", "-c", f"mv {POLICY_FILE}.tmp {POLICY_FILE}")
    return docker("cat", POLICY_FILE).stdout


def remove_policy():
    docker("rm", "-f", POLICY_FILE)
    return docker("sh", "-c", f"test -f {POLICY_FILE} && echo present || echo gone").stdout.strip()


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

    # A previous run that was interrupted between writing the policy file and
    # deleting it would leave the gateway configured, and the OFF checks below
    # would then fail for a reason that has nothing to do with this run.
    remove_policy()
    page.wait_for_timeout(4000)

    # =================== the OFF state, before anything is configured ===============
    off = json_of(api(page, "GET", "api/remote/gateways"))
    rec("OFF: with no policy file, no peer is reachable and none may read this one",
        off.get("gateways") == [] and off.get("acceptsInbound") is False,
        f"gateways={off.get('gateways')} acceptsInbound={off.get('acceptsInbound')}")

    denied = json_of(api(page, "GET", f"api/remote/drift?gateway={PEER_NAME}&project={q(PROJECT)}"))
    rec("OFF: a drift request for an unconfigured peer is refused",
        "error" in denied, denied.get("error", "")[:80])

    # =================== turn it on ===================
    written = write_policy()
    rec("CONFIG: the policy file was written into the gateway's data directory",
        f"remote.{PEER_NAME}.url" in written and "inboundToken" in written,
        f"{len(written.splitlines())} line(s)")
    # PolicySource re-stats at most once every 2s. No restart, by design.
    page.wait_for_timeout(4000)

    listed = json_of(api(page, "GET", "api/remote/gateways"))
    peers = listed.get("gateways", [])
    rec("R5: the peer is listed, by the name and label the operator chose",
        len(peers) == 1 and peers[0].get("name") == PEER_NAME
        and peers[0].get("label") == PEER_LABEL,
        json.dumps(peers)[:120])
    rec("R5: this gateway now says it will answer a peer",
        listed.get("acceptsInbound") is True, str(listed.get("acceptsInbound")))
    # The tokens exist to be SENT, not read back. No route returns one.
    rec("R5: no token is ever emitted to the browser",
        TOKEN not in json.dumps(listed) and all("token" not in g for g in peers),
        "no token field, and the value does not appear in the response")

    # =================== the digest, which is the local half ===================
    digest = json_of(api(page, "GET", f"api/scripts/digest?project={q(PROJECT)}"))
    bodies = digest.get("bodies", [])
    rec("R5: the digest route answers with a hash per openable body",
        len(bodies) > 0 and all(len(b.get("sha256", "")) == 64 for b in bodies),
        f"{len(bodies)} bodies, first={bodies[0].get('path') if bodies else '-'}")
    # The corpus is "everything this IDE can open", not just the library — the
    # same definition search uses. A digest that stopped at script-python would
    # report every timer script as absent from the other gateway.
    kinds = {b.get("path", "").split("/")[1] for b in bodies}
    rec("R5: the digest covers more than the project library",
        len(kinds) > 1 or any("timer" in b.get("path", "") for b in bodies),
        f"resource types seen: {sorted(kinds)}")

    # =================== drift against ourselves ===================
    same = json_of(api(page, "GET",
                       f"api/remote/drift?gateway={PEER_NAME}&project={q(PROJECT)}"))
    rec("R5: a project compared with ITSELF reports zero differences",
        same.get("total", 0) > 0 and same.get("differing") == 0,
        f"{same.get('differing')} of {same.get('total')} differ")
    rec("R5: and every row is marked 'same'",
        bool(same.get("rows")) and all(r.get("status") == "same" for r in same.get("rows", [])),
        f"{len(same.get('rows', []))} rows")

    # =================== drift against a different project ===================
    other = json_of(api(page, "GET", f"api/remote/drift?gateway={PEER_NAME}"
                        f"&project={q(PROJECT)}&remoteProject={q(OTHER_PROJECT)}"))
    # Asserted as a DIFFERENCE, not as a presence: zero above only means
    # something if a real comparison can produce a non-zero.
    rec("R5: a DIFFERENT project over the same link reports real drift",
        other.get("differing", 0) > 0,
        f"{other.get('differing')} of {other.get('total')} differ from {OTHER_PROJECT}")
    statuses = {r.get("status") for r in other.get("rows", [])}
    rec("R5: it distinguishes 'only here' from 'differs'",
        "only-here" in statuses or "only-there" in statuses,
        f"statuses seen: {sorted(s for s in statuses if s)}")

    # =================== a peer's body comes back byte for byte ===================
    probe = bodies[0] if bodies else None
    if probe:
        local = page.evaluate(
            """async ([spa, url]) => (await fetch(spa + url,
                 {credentials:'include', headers:{'Accept':'text/plain'}})).text()""",
            [SPA, f"api/scripts/content/{urllib.parse.quote(probe['path'], safe='')}"
                  f"?project={q(PROJECT)}&key={q(probe['key'])}"])
        remote = page.evaluate(
            """async ([spa, url]) => (await fetch(spa + url,
                 {credentials:'include', headers:{'Accept':'text/plain'}})).text()""",
            [SPA, f"api/remote/content?gateway={PEER_NAME}&project={q(PROJECT)}"
                  f"&path={q(probe['path'])}&key={q(probe['key'])}"])
        rec("R5: a peer's copy of a body arrives byte for byte",
            local == remote and len(local) > 0,
            f"{len(local)} chars local, {len(remote)} chars remote")
    else:
        rec("R5: a peer's copy of a body arrives byte for byte", False, "no body to probe")

    # =================== the SSRF question, asked directly ===================
    for hostile, label in (
        ("http://169.254.169.254/latest/meta-data/", "a cloud metadata URL"),
        ("file:///etc/passwd", "a file URL"),
        ("nosuchgateway", "an unconfigured name"),
    ):
        answer = api(page, "GET",
                     f"api/remote/drift?gateway={q(hostile)}&project={q(PROJECT)}")
        rec(f"R5: {label} sent as a gateway name is refused",
            answer["status"] == 404, f"HTTP {answer['status']}")

    # =================== the inbound token, from OUTSIDE a session ===================
    # A fresh context with no cookies: this is a peer gateway, not a browser.
    anon = browser.new_context()
    anon_page = anon.new_page()

    def as_peer(token):
        return anon_page.evaluate(
            """async ([url, token]) => {
                 const headers = {'Accept': 'application/json'};
                 if (token !== null) headers['X-ScriptIDE-Remote-Token'] = token;
                 const res = await fetch(url, {headers});
                 return {status: res.status, text: (await res.text()).slice(0, 120)};
               }""",
            [f"{GATEWAY_URL}{SPA}api/scripts/digest?project={q(PROJECT)}", token])

    anon_page.goto(GATEWAY_URL + SPA, wait_until="load", timeout=30000)
    rec("R5: a peer presenting the right token may READ the digest",
        as_peer(TOKEN)["status"] == 200, f"HTTP {as_peer(TOKEN)['status']}")
    rec("R5: a peer presenting the wrong token may not",
        as_peer(TOKEN[:-1] + "x")["status"] == 401,
        f"HTTP {as_peer(TOKEN[:-1] + 'x')['status']}")
    rec("R5: no token at all is refused",
        as_peer(None)["status"] == 401, f"HTTP {as_peer(None)['status']}")

    # The token buys a READ and nothing else. This is the assertion that keeps
    # the shared secret proportionate to what it protects.
    poked = anon_page.evaluate(
        """async ([url, token]) => {
             const res = await fetch(url, {method: 'POST',
               headers: {'X-ScriptIDE-Remote-Token': token,
                         'Content-Type': 'application/json'},
               body: JSON.stringify({source: 'x = 1'})});
             return res.status;
           }""",
        [f"{GATEWAY_URL}{SPA}api/scripts/content/"
         f"{urllib.parse.quote(DRIFT_MODULE, safe='')}?project={q(PROJECT)}", TOKEN])
    rec("R5: the same token cannot WRITE — the gate is mounted on reads only",
        poked in (401, 403), f"HTTP {poked}")
    anon.close()

    # =================== the Compare view ===================
    page.reload(wait_until="load", timeout=30000)
    page.wait_for_selector(".file-tree-header", timeout=20000)
    page.select_option(".workspace-project select", PROJECT)
    page.wait_for_timeout(1500)
    page.locator('.activity-item[aria-label="Compare Gateways"]').click()
    page.wait_for_timeout(1200)
    rec("R5 UI: the Compare view opens and lists the configured gateway",
        page.locator(".remote-panel").count() == 1
        and PEER_LABEL in page.locator(".remote-panel").inner_text(),
        page.locator(".remote-panel").inner_text()[:90].replace("\n", " ")
        if page.locator(".remote-panel").count() else "absent")

    page.locator(".remote-panel-go").click()
    page.wait_for_selector(".remote-panel-row", timeout=30000)
    rows = page.locator(".remote-panel-row").count()
    rec("R5 UI: comparing produces a row per body, matches included",
        rows > 0, f"{rows} row(s)")
    rec("R5 UI: it says plainly that everything matches",
        "match" in page.locator(".remote-panel-status").inner_text().lower(),
        page.locator(".remote-panel-status").inner_text()[:90])

    # A remote row must not reuse a class another suite counts. The Search
    # view's `.search-panel-hit` and the Problems panel's `.problems-row` are
    # both load-bearing selectors elsewhere.
    rec("R5 UI: its rows carry their own class, not another view's",
        page.locator(".remote-panel-row.problems-row").count() == 0
        and page.locator(".remote-panel-row.search-panel-hit").count() == 0,
        "no borrowed class names")

    # =================== R6: discovery ===================
    made = write(page, csrf, TEST_MODULE, TEST_SOURCE)
    rec("FIXTURE: the test module was created", made["status"] == 200,
        f"HTTP {made['status']} {made['text'][:70]}")
    plain = write(page, csrf, ORDINARY_MODULE, ORDINARY_SOURCE)
    rec("FIXTURE: the ordinary module was created", plain["status"] == 200,
        f"HTTP {plain['status']} {plain['text'][:70]}")
    write(page, csrf, DRIFT_MODULE, DRIFT_SOURCE)

    listing = {}
    for attempt in range(8):
        # The project index rebuilds a moment after a resource write, so the
        # first listing for a brand-new file legitimately finds nothing.
        page.wait_for_timeout(2000 + 1000 * attempt)
        listing = json_of(api(page, "GET", f"api/tests?project={q(PROJECT)}"))
        if listing.get("total", 0) > 0:
            break

    ids = [t["id"] for m in listing.get("modules", []) for t in m.get("tests", [])]
    rec("R6: the four tests in the fixture are discovered",
        sum(1 for i in ids if "_si_v24.test_probe" in i) == 4,
        f"{len(ids)} discovered: {[i.split('.')[-1] for i in ids][:6]}")

    # The narrowing that keeps `test_connection` off a Run All button. This is
    # the assertion the whole discovery convention exists for.
    rec("R6: a test-named function in an ORDINARY module is NOT discovered",
        not any("_si_v24.plain" in i for i in ids),
        "the module rule holds")

    rec("R6: a helper beside the tests is not mistaken for one",
        not any(i.endswith(".helper") for i in ids), "helper() was skipped")
    rec("R6: a test method on a Test-named class is found, and named fully",
        any(i.endswith("TestGroup.test_method") for i in ids),
        next((i for i in ids if "TestGroup" in i), "not found"))
    rec("R6: the module reports that it brackets its tests with setUp",
        any(m.get("hasSetUp") for m in listing.get("modules", [])
            if "_si_v24.test_probe" in m.get("module", "")),
        "hasSetUp is true")
    rec("R6: the response states the discovery convention",
        "test_" in listing.get("convention", ""), listing.get("convention", "")[:80])

    # =================== R6: the run ===================
    mine = [i for i in ids if "_si_v24.test_probe" in i]
    run = json_of(api(page, "POST", f"api/tests/run?project={q(PROJECT)}", csrf, {"ids": mine}))
    by_id = {r["id"]: r for r in run.get("results", [])}

    rec("R6: every requested test ran", len(by_id) == len(mine),
        f"{len(by_id)} of {len(mine)}")
    rec("R6: the tally counts one of each outcome",
        run.get("passed") == 2 and run.get("failed") == 1 and run.get("errored") == 1,
        f"passed={run.get('passed')} failed={run.get('failed')} errored={run.get('errored')}")

    passing = next((r for r in by_id.values() if r["id"].endswith("test_passes")), {})
    rec("R6: setUp ran before the test — the passing test asserts it did",
        passing.get("status") == "pass", passing.get("message", "") or "passed")
    rec("R6: what a test PRINTED is captured with it",
        "hello from the passing test" in passing.get("output", ""),
        passing.get("output", "")[:60].strip())

    failing = next((r for r in by_id.values() if r["id"].endswith("test_fails")), {})
    rec("R6: a false assertion is a FAIL, and its message survives",
        failing.get("status") == "fail" and "one is not two" in failing.get("message", ""),
        f"{failing.get('status')}: {failing.get('message', '')[:50]}")

    erroring = next((r for r in by_id.values() if r["id"].endswith("test_errors")), {})
    # The distinction that sends a reader to the right half of the file: an
    # error never got far enough to have an opinion about anything.
    rec("R6: anything other than an assertion is an ERROR, not a failure",
        erroring.get("status") == "error", f"{erroring.get('status')}: "
        f"{erroring.get('message', '')[:60]}")
    rec("R6: an error carries a traceback",
        bool(erroring.get("traceback")), erroring.get("traceback", "")[:60].replace("\n", " "))

    # An id the client invented must not become a call to an arbitrary function.
    invented = api(page, "POST", f"api/tests/run?project={q(PROJECT)}", csrf,
                   {"ids": ["_si_v24.plain.test_connection"]})
    rec("R6: an id the server did not discover is refused",
        invented["status"] == 400, f"HTTP {invented['status']} "
        f"{json_of(invented).get('error', '')[:60]}")

    # =================== R6 UI ===================
    page.locator('.activity-item[aria-label="Tests"]').click()
    page.wait_for_selector(".tests-panel", timeout=20000)
    page.wait_for_timeout(2000)
    rec("R6 UI: the Tests panel lists the fixture module",
        "_si_v24.test_probe" in page.locator(".tests-panel").inner_text(),
        page.locator(".tests-panel-count").inner_text())

    page.locator(".tests-panel-run").click()
    page.wait_for_selector(".tests-panel-tally", timeout=120000)
    tally = page.locator(".tests-panel-tally").inner_text().replace("\n", " ")
    rec("R6 UI: running from the panel reports passes and failures separately",
        "passed" in tally and "failed" in tally, tally[:80])

    why = page.locator(".tests-row-toggle").first
    if why.count():
        why.click()
        page.wait_for_timeout(600)
        detail = page.locator(".tests-row-detail").first.inner_text()
        rec("R6 UI: a failure explains itself on demand",
            "failed" in detail or "errored" in detail, detail[:80].replace("\n", " "))
    else:
        rec("R6 UI: a failure explains itself on demand", False, "no toggle rendered")

    rec("R6 UI: the panel says a run shares one interpreter",
        "share an interpreter" in page.locator(".tests-panel").inner_text(),
        "the caveat is on screen")

    # =================== clean up ===================
    remove_fixtures(page, csrf)
    left = [p for p in FIXTURES if entry_for(page, p)]
    rec("CLEANUP: every fixture script was removed", not left, ", ".join(left) or "none left")

    state = remove_policy()
    rec("CLEANUP: the policy file this suite wrote was deleted",
        state == "gone", state)
    page.wait_for_timeout(4000)
    after = json_of(api(page, "GET", "api/remote/gateways"))
    rec("CLEANUP: and the gateway is back to answering no peer",
        after.get("gateways") == [] and after.get("acceptsInbound") is False,
        f"acceptsInbound={after.get('acceptsInbound')}")

    browser.close()

passed = sum(1 for _, ok, _ in res if ok)
print(f"\n{passed}/{len(res)} checks passed")
sys.exit(0 if passed == len(res) else 1)
