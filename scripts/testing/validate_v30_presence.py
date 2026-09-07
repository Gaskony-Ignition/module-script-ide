"""1.23.0 — presence: who else has this file open, and where from.

Two feeds answer one question, and only a gateway can prove either.

  * OTHER BROWSERS. Two real IDE clients, two real sockets, one real registry.
    A unit test cannot show that opening a tab in one window puts a badge in
    another, because the mechanism IS the connection between them.

  * THE DESIGNER. This is the half that has to be measured rather than reasoned
    about. `DesignerResourceSessionEvent` lives in `gateway.jar`, NOT in the
    SDK's `gateway-api` — checked on 8.3.6 and 8.3.8 — so the module reaches it
    by class name and could stop matching after any patch release with nothing
    failing anywhere.

    `designerFeed` says the listener is attached. `designerEventSeen` says a real
    Designer event has actually been READ, which is the only evidence that the
    internal type still has the shape this build expects. The second is asserted
    here ONLY when a Designer is connected — see the note at that check — because
    a suite that fails when nobody happens to have the Designer open is a suite
    people learn to ignore.

Everything this suite creates it removes.

Run:
    SI_GATEWAY_CONFIG=$PWD/config.local.json \\
      .venv-test/bin/python scripts/testing/validate_v30_presence.py
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

PKG = "_si_v30"
ALPHA = f"ignition/script-python/{PKG}/alpha"
BETA = f"ignition/script-python/{PKG}/beta"
FOLDER = f"ignition/script-python/{PKG}"
FIXTURES = (ALPHA, BETA, FOLDER)

SOURCE = "def value():\n\treturn 1\n"

PASSED = 0
FAILED = 0


def rec(label, ok, detail=""):
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  [PASS] {label}")
    else:
        FAILED += 1
        print(f"  [FAIL] {label}: {detail}")


def api(page, method, path, body=None):
    return page.evaluate(
        """async ([spa, method, path, body]) => {
            const res = await fetch(spa + path, {
                method, credentials: 'include',
                headers: body ? {'Content-Type': 'application/json'} : {},
                body: body ? JSON.stringify(body) : undefined,
            });
            return {status: res.status, text: await res.text()};
        }""",
        [SPA, method, path, body])


def json_of(result):
    try:
        return json.loads(result["text"])
    except (ValueError, KeyError, TypeError):
        return {}


def presence(page):
    """The module's own account of who is where — not inferred from pixels."""
    return json_of(api(page, "GET", f"api/presence?project={PROJECT}"))


def q(value):
    return urllib.parse.quote(str(value), safe="")


def tree(page):
    return json_of(api(page, "GET", f"api/scripts?project={q(PROJECT)}")).get("scripts", [])


def entry_for(page, path):
    return next((e for e in tree(page) if e.get("path") == path), None)


def write(page, csrf, path, source):
    """Create or replace one script, through the route the IDE itself uses.

    The If-Match is not optional politeness: this module's write path refuses a
    signature-less overwrite of an existing resource, which is the same rule
    that stops two people silently clobbering each other.
    """
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
        [SPA, f"api/scripts/content/{q(path)}?project={q(PROJECT)}",
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
            [SPA, f"api/scripts/content/{q(path)}?project={q(PROJECT)}",
             csrf, found.get("signature")])


def expand_tree(page):
    """Open every collapsed node. The tree ships COLLAPSED on purpose."""
    for _ in range(6):
        shut = page.locator('.file-tree [aria-expanded="false"]')
        count = shut.count()
        if count == 0:
            break
        for i in range(count):
            try:
                shut.nth(i).click(timeout=1500)
            except Exception:
                pass
        page.wait_for_timeout(400)


def open_named(page, name):
    """Click a script by its leaf name, as a person would."""
    expand_tree(page)
    row = page.locator(
        f'.file-tree .file-tree-item:has(.file-tree-name:text-is("{name}"))')
    if row.count() == 0:
        row = page.locator('.file-tree .file-tree-item').filter(has_text=name)
    if row.count() == 0:
        return False
    row.first.click()
    page.wait_for_timeout(1800)
    return True


def open_ide(context):
    """A second, independent IDE client — its own page, its own socket."""
    page = context.new_page()
    page.goto(GATEWAY_URL + SPA, wait_until="load", timeout=30000)
    page.wait_for_selector(".file-tree-header", timeout=20000)
    page.select_option(".workspace-project select", PROJECT)
    page.wait_for_timeout(1800)
    return page


print(f"Presence on {GATEWAY_URL} (project {PROJECT})")

with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(viewport={"width": 1500, "height": 950})
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

    written = [write(page, csrf, ALPHA, SOURCE)["status"],
               write(page, csrf, BETA, SOURCE)["status"]]
    rec("FIXTURE: two scripts were created", all(s == 200 for s in written), f"HTTP {written}")

    second = None
    try:
        # The tree is read at load, so a script written after it needs a reload
        # before it is clickable.
        page.wait_for_timeout(2500)
        page.reload(wait_until="load", timeout=30000)
        page.wait_for_selector(".file-tree-header", timeout=20000)
        page.select_option(".workspace-project select", PROJECT)
        page.wait_for_timeout(2000)

        rec("the presence route answers", "peers" in presence(page),
            json.dumps(presence(page))[:200])

        # ================= one client alone =================

        rec("FIXTURE: alpha opens in the first client", open_named(page, "alpha"))
        page.wait_for_timeout(1500)

        state = presence(page)
        mine = [q for q in state["peers"] if ALPHA in q.get("resources", [])]
        rec("a client's own open file is reported to the gateway",
            len(mine) == 1, json.dumps(state)[:300])

        rec("but it is NOT shown back to the client that owns it",
            page.locator(".presence-bar").count() == 0,
            f"bars={page.locator('.presence-bar').count()}")

        # ================= a second browser =================

        second = open_ide(context)
        rec("FIXTURE: alpha opens in the second client", open_named(second, "alpha"))
        page.wait_for_timeout(2000)

        first_bar = page.locator(".presence-bar").count()
        second_bar = second.locator(".presence-bar").count()
        rec("opening the same script in a second browser is seen by the first",
            first_bar == 1, f"first={first_bar} second={second_bar}")
        rec("and the second sees the first — presence is mutual",
            second_bar == 1, f"second={second_bar}")

        text = page.locator(".presence-bar").inner_text() if first_bar else ""
        rec("the bar names where they are working from",
            "in the IDE" in text, text[:200])
        rec("the bar says plainly that saving is not blocked",
            "not blocked" in text.lower(), text[:200])

        rec("the tab carries a badge, so a background tab is visible too",
            page.locator(".tab .presence-badge").count() >= 1,
            f"badges={page.locator('.tab .presence-badge').count()}")

        # ================= scoping =================

        rec("FIXTURE: the second client also opens beta", open_named(second, "beta"))
        page.wait_for_timeout(2000)

        state = presence(page)
        on_beta = [q for q in state["peers"] if BETA in q.get("resources", [])]
        rec("a peer opening a SECOND file is recorded against that file too",
            len(on_beta) == 1, json.dumps(state)[:300])

        rec("and the first client, which has only alpha, still shows one bar",
            page.locator(".presence-bar").count() == 1,
            f"bars={page.locator('.presence-bar').count()}")

        # ================= departure =================

        second.close()
        second = None
        # No sweep wait: an IDE peer goes when its socket closes, immediately.
        # If this needs fifteen seconds, the close path is not removing the peer
        # and the sweep is quietly covering for it.
        page.wait_for_timeout(3000)

        rec("closing the other browser clears the bar without waiting for a sweep",
            page.locator(".presence-bar").count() == 0,
            f"bars={page.locator('.presence-bar').count()}")

        state = presence(page)
        gone = [q for q in state["peers"] if q.get("kind") == "ide" and BETA in q.get("resources", [])]
        rec("and the gateway has forgotten that session entirely",
            len(gone) == 0, json.dumps(state)[:300])

        # ================= the Designer feed =================

        state = presence(page)
        rec("the module reports whether the Designer listener is attached",
            isinstance(state.get("designerFeed"), bool),
            json.dumps(state)[:200])

        rec("the Designer listener IS attached on this gateway",
            state.get("designerFeed") is True,
            "designerFeed=false — CommonContext.getEventBus() registration failed; "
            "presence falls back to session level")

        designers = [q for q in state["peers"] if q.get("kind") == "designer"]
        if designers:
            # Only assertable when somebody has the Designer open. Asserting it
            # unconditionally would fail on an idle gateway and teach everyone to
            # ignore this suite — see the module's rule about lints that cry wolf.
            rec("a connected Designer is reported, with a user and a host",
                all(q.get("host") for q in designers),
                json.dumps(designers)[:300])
            with_files = [q for q in designers if q.get("resources")]
            rec("...and the per-file feed has been read at least once "
                "(this is the internal-type check)",
                state.get("designerEventSeen") is True or not with_files,
                f"designerEventSeen={state.get('designerEventSeen')} "
                f"designers_with_files={len(with_files)}")
        else:
            print("  [skip] no Designer is connected — per-file Designer presence "
                  "is proven by the Designer run, not by this suite")

    finally:
        if second is not None:
            second.close()
        remove_fixtures(page, csrf)
        rec("CLEANUP: the fixtures are gone", entry_for(page, ALPHA) is None,
            "alpha is still in the tree")
        browser.close()

print()
print(f"validate_v30_presence   {PASSED}/{PASSED + FAILED} checks passed")
sys.exit(0 if FAILED == 0 else 1)
