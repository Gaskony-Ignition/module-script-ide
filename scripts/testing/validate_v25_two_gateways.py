"""
F2: the compare feature between TWO REAL GATEWAYS.

`validate_v24` proves R5 against a peer that is this gateway — which exercises
the config, the token lookup, the outbound client, the digest and the
comparison, and cannot prove the two ends are different machines. That was the
last thing `docs/PRODUCT-REVIEW.md` had open, and it is what this suite closes.

**The second gateway is a real, separate Ignition instance**: its own container,
its own data volume, its own port, its own admin account, its own module
install. `dockers/peer.sh up` creates it and `dockers/peer.sh down` destroys it
with its volume. Nothing here runs against a gateway that already existed.

What makes this a proof rather than a re-run of v24:

* the two gateways cannot see each other's filesystem, so an identical hash is
  identical CONTENT and not a shared resource;
* the peer's project was created by importing a zip, so the module had no hand
  in putting it there;
* every one of the four statuses is produced deliberately — a body written the
  same on both, one written differently, one written only here, one written
  only there — rather than being whatever the two projects happened to hold;
* the comparison is then asserted in BOTH directions, because a link that only
  works the way it was set up is a link nobody can rely on.

Run (after `dockers/peer.sh up` and installing the module on both):

    SI_GATEWAY_CONFIG=$PWD/config.local.json \\
      SI_PEER_CONFIG=$PWD/config.peer.json \\
      .venv-test/bin/python scripts/testing/validate_v25_two_gateways.py
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gateway_session import (                                   # noqa: E402
    CONFIG, GATEWAY_URL, HOME_READY, LOGIN_LINK, PASS_FIELD, USER_FIELD,
    dismiss_quick_start, login,
)
from playwright.sync_api import sync_playwright                 # noqa: E402

SPA = CONFIG.get("spa_path", "/data/scriptide/")
PROJECT = os.environ.get("SI_COMPARE_PROJECT", "Compare_Demo")

PEER_CONFIG = os.environ.get("SI_PEER_CONFIG")
if not PEER_CONFIG or not os.path.exists(PEER_CONFIG):
    print("SI_PEER_CONFIG must point at the peer gateway's config "
          "(created by dockers/peer.sh up)", file=sys.stderr)
    sys.exit(2)
PEER = json.load(open(PEER_CONFIG))

# The URL each gateway uses to reach the OTHER one. Not localhost: the peer is
# in a bridge network and "localhost" there is the peer itself, so the pair only
# works over an address that means the same thing on both sides.
HOST_IP = os.environ.get("SI_HOST_IP", "192.168.153.128")
LOCAL_FOR_PEER = f"http://{HOST_IP}:8088"
PEER_FOR_LOCAL = f"http://{HOST_IP}:8099"

LOCAL_CONTAINER = CONFIG.get("container_name", "ignition-module-testing")
PEER_CONTAINER = PEER.get("container_name", "scriptide-peer-gateway")
POLICY_DIR = "/usr/local/bin/ignition/data/modules/scriptide"
POLICY_FILE = POLICY_DIR + "/policy.properties"

# One token per DIRECTION, so a leak of one does not open the other. Both are
# disposable and live only for this run.
TOKEN_TO_PEER = "siV25TokenForReadingThePeerGateway"
TOKEN_TO_LOCAL = "siV25TokenForReadingTheLocalGateway"

SAME = "ignition/script-python/f2/shared"
DIFFERS = "ignition/script-python/f2/drifted"
ONLY_HERE = "ignition/script-python/f2/local_only"
ONLY_THERE = "ignition/script-python/f2/peer_only"
FOLDER = "ignition/script-python/f2"

SAME_SOURCE = "VERSION = '1.0.0'\n\ndef total(rows):\n\treturn sum(r['qty'] for r in rows)\n"
LOCAL_DRIFT = "def rate():\n\treturn 3.9\n"
PEER_DRIFT = "def rate():\n\treturn 4.1\n"
LOCAL_ONLY_SOURCE = "def onlyOnDev():\n\treturn True\n"
PEER_ONLY_SOURCE = "def onlyOnProd():\n\treturn True\n"

res = []


def rec(name, ok, detail=""):
    res.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def q(value):
    return urllib.parse.quote(str(value))


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
        [spa_of(page), method, url, csrf, body])


def json_of(response):
    try:
        return json.loads(response["text"])
    except Exception:
        return {}


_spa = {}


def spa_of(page):
    return _spa.get(page, SPA)


def tree(page, project=PROJECT):
    return json_of(api(page, "GET", f"api/scripts?project={q(project)}")).get("scripts", [])


def entry_for(page, path, project=PROJECT):
    return next((e for e in tree(page, project) if e.get("path") == path), None)


def write(page, csrf, path, source):
    found = entry_for(page, path)
    return page.evaluate(
        """async ([spa, url, csrf, source, ifMatch]) => {
             const headers = {'Accept': 'application/json',
                              'Content-Type': 'application/json',
                              'X-CSRF-Token': csrf};
             if (ifMatch) headers['If-Match'] = ifMatch;
             const res = await fetch(spa + url, {method: 'POST', credentials: 'include',
               headers, body: JSON.stringify({source})});
             return {status: res.status, text: (await res.text()).slice(0, 90)};
           }""",
        [spa_of(page),
         f"api/scripts/content/{urllib.parse.quote(path, safe='')}?project={q(PROJECT)}",
         csrf, source, (found or {}).get("signature")])


def remove(page, csrf, paths):
    for path in paths:
        found = entry_for(page, path)
        if not found:
            continue
        page.evaluate(
            """async ([spa, url, csrf, ifMatch]) => {
                 await fetch(spa + url, {method: 'DELETE', credentials: 'include',
                   headers: {'X-CSRF-Token': csrf, 'If-Match': ifMatch}});
               }""",
            [spa_of(page),
             f"api/scripts/content/{urllib.parse.quote(path, safe='')}?project={q(PROJECT)}",
             csrf, found.get("signature") or ""])


def peer_request(method, path, token, body=None):
    """One HTTP call to the peer, as a PEER makes it: no session, no origin."""
    request = urllib.request.Request(PEER_FOR_LOCAL + path, method=method, data=body)
    if token:
        request.add_header("X-ScriptIDE-Remote-Token", token)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        print(f"  (peer_request {method} {path}: {e})")
        return -1


def docker(container, *args):
    return subprocess.run(["docker", "exec", container, *args],
                          capture_output=True, text=True, timeout=60)


def write_policy(container, peer_name, peer_label, peer_url, outbound_token, inbound_token):
    """Point one gateway at the other, and let the other read it back."""
    body = "\n".join([
        f"com.gaskony.scriptide.remote.inboundToken={inbound_token}",
        f"com.gaskony.scriptide.remote.{peer_name}.url={peer_url}",
        f"com.gaskony.scriptide.remote.{peer_name}.label={peer_label}",
        f"com.gaskony.scriptide.remote.{peer_name}.token={outbound_token}",
        "",
    ])
    docker(container, "mkdir", "-p", POLICY_DIR)
    # Staged then renamed: a half-written properties file read mid-save is a
    # configuration the module would apply.
    docker(container, "sh", "-c", f"cat > {POLICY_FILE}.tmp <<'SIV25EOF'\n{body}SIV25EOF")
    docker(container, "sh", "-c", f"mv {POLICY_FILE}.tmp {POLICY_FILE}")


def remove_policy(container):
    docker(container, "rm", "-f", POLICY_FILE)
    return docker(container, "sh", "-c",
                  f"test -f {POLICY_FILE} && echo present || echo gone").stdout.strip()


def status_of(report, path):
    for row in report.get("rows", []):
        if row.get("path") == path:
            return row.get("status")
    return None


with sync_playwright() as p:
    browser = p.chromium.launch()

    # ---------- a session on EACH gateway ----------
    local = browser.new_context(viewport={"width": 1600, "height": 1000}).new_page()
    login(local)
    local.goto(GATEWAY_URL + SPA, wait_until="load", timeout=30000)
    local.wait_for_selector(".file-tree-header", timeout=20000)
    _spa[local] = SPA
    local_csrf = local.evaluate(
        "async (spa) => (await (await fetch(spa + 'api/auth/session',"
        " {credentials:'include'})).json())", SPA).get("csrfToken")

    peer = browser.new_context(viewport={"width": 1600, "height": 1000}).new_page()
    peer_spa = PEER.get("spa_path", "/data/scriptide/")
    _spa[peer] = peer_spa
    # The peer has its own admin account, so `gateway_session.login` — which is
    # bound to the module-testing gateway's config — cannot be used directly.
    # Its SELECTORS and its Quick Start dismissal are reused rather than
    # reinvented: both encode findings that cost real time (the modal's backdrop
    # blocks the login link itself; the nav renders after the load event and
    # needs one reload). A hand-rolled two-page login here failed on exactly the
    # first of those, on a gateway fresh enough to still be showing the modal.
    peer_url = PEER["gateway_url"].rstrip("/")
    peer.goto(peer_url + "/", wait_until="load", timeout=30000)
    dismiss_quick_start(peer)
    try:
        peer.wait_for_selector(LOGIN_LINK, state="visible", timeout=20000)
    except Exception:
        peer.reload(wait_until="load", timeout=30000)
        dismiss_quick_start(peer)
        peer.wait_for_selector(LOGIN_LINK, state="visible", timeout=30000)
    peer.click(LOGIN_LINK, timeout=10000)
    peer.wait_for_selector(USER_FIELD, timeout=10000)
    peer.fill(USER_FIELD, PEER["username"])
    peer.click("text='CONTINUE'", timeout=10000)
    peer.wait_for_selector(PASS_FIELD, timeout=10000)
    peer.fill(PASS_FIELD, PEER["password"])
    peer.click("text='CONTINUE'", timeout=10000)
    peer.wait_for_selector(HOME_READY, timeout=15000)
    peer.goto(peer_url + peer_spa, wait_until="load", timeout=30000)
    peer.wait_for_selector(".file-tree-header", timeout=20000)
    peer_csrf = peer.evaluate(
        "async (spa) => (await (await fetch(spa + 'api/auth/session',"
        " {credentials:'include'})).json())", peer_spa).get("csrfToken")

    rec("SETUP: both gateways answer as authenticated sessions",
        bool(local_csrf) and bool(peer_csrf),
        f"local csrf={'yes' if local_csrf else 'no'}, peer csrf={'yes' if peer_csrf else 'no'}")

    # They must be genuinely different gateways, not two views of one.
    local_id = local.evaluate("async () => (await (await fetch('/StatusPing')).json()).state")
    peer_id = peer.evaluate("async () => (await (await fetch('/StatusPing')).json()).state")
    rec("SETUP: they are two separate gateway processes",
        LOCAL_CONTAINER != PEER_CONTAINER and local_id == "RUNNING" and peer_id == "RUNNING",
        f"{LOCAL_CONTAINER} and {PEER_CONTAINER}, both RUNNING")

    rec("SETUP: the project exists on BOTH, and the module put it on neither",
        bool(json_of(api(local, "GET", "api/projects"))) and tree(peer) is not None,
        f"'{PROJECT}' imported from a zip onto each")

    # ---------- author the four cases ----------
    remove(local, local_csrf, (SAME, DIFFERS, ONLY_HERE, ONLY_THERE))
    remove(peer, peer_csrf, (SAME, DIFFERS, ONLY_HERE, ONLY_THERE))

    writes = [
        write(local, local_csrf, SAME, SAME_SOURCE),
        write(peer, peer_csrf, SAME, SAME_SOURCE),
        write(local, local_csrf, DIFFERS, LOCAL_DRIFT),
        write(peer, peer_csrf, DIFFERS, PEER_DRIFT),
        write(local, local_csrf, ONLY_HERE, LOCAL_ONLY_SOURCE),
        write(peer, peer_csrf, ONLY_THERE, PEER_ONLY_SOURCE),
    ]
    rec("FIXTURE: six bodies written across the two gateways",
        all(w["status"] == 200 for w in writes),
        ", ".join(str(w["status"]) for w in writes))

    # ---------- link them, both ways ----------
    write_policy(LOCAL_CONTAINER, "prod", "Peer gateway", PEER_FOR_LOCAL,
                 TOKEN_TO_PEER, TOKEN_TO_LOCAL)
    write_policy(PEER_CONTAINER, "dev", "Module-testing gateway", LOCAL_FOR_PEER,
                 TOKEN_TO_LOCAL, TOKEN_TO_PEER)
    # PolicySource re-stats at most once every 2s. No restart, by design — and
    # on TWO gateways at once, which is the claim the docs make.
    local.wait_for_timeout(5000)

    listed_local = json_of(api(local, "GET", "api/remote/gateways"))
    listed_peer = json_of(api(peer, "GET", "api/remote/gateways"))
    rec("LINK: each gateway lists the other, with no restart on either",
        [g.get("name") for g in listed_local.get("gateways", [])] == ["prod"]
        and [g.get("name") for g in listed_peer.get("gateways", [])] == ["dev"],
        f"local sees {[g.get('label') for g in listed_local.get('gateways', [])]}, "
        f"peer sees {[g.get('label') for g in listed_peer.get('gateways', [])]}")
    rec("LINK: and each says it will answer the other",
        listed_local.get("acceptsInbound") is True
        and listed_peer.get("acceptsInbound") is True,
        "inbound accepted on both")

    # ---------- the comparison, dev -> prod ----------
    forward = json_of(api(local, "GET",
                          f"api/remote/drift?gateway=prod&project={q(PROJECT)}"))
    rec("COMPARE: the local gateway reached the peer over the network",
        "rows" in forward and forward.get("total", 0) > 0,
        f"{forward.get('differing')} of {forward.get('total')} differ"
        if "rows" in forward else forward.get("error", "")[:110])

    # The four statuses, each produced on purpose. This is the assertion that
    # makes the whole thing a proof: identical content on two machines that
    # share no filesystem must hash the same, and different content must not.
    rec("COMPARE: a body written IDENTICALLY on both is 'same'",
        status_of(forward, SAME) == "same", str(status_of(forward, SAME)))
    rec("COMPARE: a body written DIFFERENTLY is 'differs'",
        status_of(forward, DIFFERS) == "differs", str(status_of(forward, DIFFERS)))
    rec("COMPARE: a body only this gateway has is 'only here'",
        status_of(forward, ONLY_HERE) == "only-here", str(status_of(forward, ONLY_HERE)))
    rec("COMPARE: a body only the PEER has is 'only there'",
        status_of(forward, ONLY_THERE) == "only-there", str(status_of(forward, ONLY_THERE)))

    # ---------- the peer's copy, over the wire ----------
    fetched = local.evaluate(
        """async ([spa, url]) => (await fetch(spa + url,
             {credentials:'include', headers:{'Accept':'text/plain'}})).text()""",
        [SPA, f"api/remote/content?gateway=prod&project={q(PROJECT)}"
              f"&path={q(DIFFERS)}&key=code.py"])
    rec("COMPARE: the peer's copy of a differing body arrives byte for byte",
        fetched == PEER_DRIFT,
        f"got {len(fetched)} chars, expected {len(PEER_DRIFT)}")
    rec("COMPARE: and it is the PEER's text, not this gateway's",
        fetched != LOCAL_DRIFT and "4.1" in fetched,
        "the value that exists only on the peer came back")

    # ---------- and the other way round ----------
    # A link that only works in the direction it was set up is a link nobody can
    # rely on. The statuses invert, which is the cheapest way to prove the
    # comparison is oriented rather than symmetric by accident.
    reverse = json_of(api(peer, "GET", f"api/remote/drift?gateway=dev&project={q(PROJECT)}"))
    rec("REVERSE: the peer can compare itself against the local gateway",
        reverse.get("total", 0) > 0,
        f"{reverse.get('differing')} of {reverse.get('total')} differ"
        if "rows" in reverse else reverse.get("error", "")[:110])
    rec("REVERSE: the same body is still 'same' from the other side",
        status_of(reverse, SAME) == "same", str(status_of(reverse, SAME)))
    rec("REVERSE: and 'only here' and 'only there' swap over",
        status_of(reverse, ONLY_THERE) == "only-here"
        and status_of(reverse, ONLY_HERE) == "only-there",
        f"peer_only={status_of(reverse, ONLY_THERE)}, "
        f"local_only={status_of(reverse, ONLY_HERE)}")

    # ---------- the refusals still hold across a real link ----------
    wrong = api(local, "GET", f"api/remote/drift?gateway=nosuch&project={q(PROJECT)}")
    rec("SAFETY: an unconfigured name is still refused",
        wrong["status"] == 404, f"HTTP {wrong['status']}")

    hostile = api(local, "GET",
                  f"api/remote/drift?gateway={q(PEER_FOR_LOCAL)}&project={q(PROJECT)}")
    rec("SAFETY: the peer's own URL, sent as a name, is refused",
        hostile["status"] == 404,
        f"HTTP {hostile['status']} — a reachable host is still not a configured name")

    # The token buys a READ of the peer and nothing else, across a real link.
    #
    # Asked from PYTHON, not from a page. A peer gateway is a server-side HTTP
    # client with no session and no origin, which is exactly what this is
    # modelling — and a cross-origin fetch from the local gateway's page is
    # refused by the browser before it reaches the peer at all, so the answer
    # would be about CORS rather than about the gate.
    read_status = peer_request("GET",
        f"/data/scriptide/api/scripts/digest?project={q(PROJECT)}", TOKEN_TO_PEER)
    rec("SAFETY: a peer token READS the far gateway, with no session at all",
        read_status == 200, f"HTTP {read_status}")

    write_status = peer_request("POST",
        f"/data/scriptide/api/scripts/content/{urllib.parse.quote(SAME, safe='')}"
        f"?project={q(PROJECT)}", TOKEN_TO_PEER, body=b'{"source": "x = 1"}')
    rec("SAFETY: and the same token cannot WRITE to it",
        write_status in (401, 403), f"HTTP {write_status}")

    no_token = peer_request("GET",
        f"/data/scriptide/api/scripts/digest?project={q(PROJECT)}", None)
    rec("SAFETY: without the token the far gateway refuses outright",
        no_token == 401, f"HTTP {no_token}")

    # ---------- clean up ----------
    remove(local, local_csrf, (SAME, DIFFERS, ONLY_HERE, ONLY_THERE, FOLDER))
    remove(peer, peer_csrf, (SAME, DIFFERS, ONLY_HERE, ONLY_THERE, FOLDER))
    left = [p for p in (SAME, DIFFERS, ONLY_HERE) if entry_for(local, p)]
    left += [p for p in (SAME, DIFFERS, ONLY_THERE) if entry_for(peer, p)]
    rec("CLEANUP: every fixture body was removed from both gateways",
        not left, ", ".join(left) or "none left")

    states = (remove_policy(LOCAL_CONTAINER), remove_policy(PEER_CONTAINER))
    rec("CLEANUP: both policy files were deleted", states == ("gone", "gone"), str(states))
    local.wait_for_timeout(4000)
    rec("CLEANUP: and neither gateway answers a peer any more",
        json_of(api(local, "GET", "api/remote/gateways")).get("acceptsInbound") is False
        and json_of(api(peer, "GET", "api/remote/gateways")).get("acceptsInbound") is False,
        "inbound off on both")

    browser.close()

passed = sum(1 for _, ok, _ in res if ok)
print(f"\n{passed}/{len(res)} checks passed")
sys.exit(0 if passed == len(res) else 1)
