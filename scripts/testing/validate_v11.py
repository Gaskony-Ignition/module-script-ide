#!/usr/bin/env python3
"""Live acceptance for the 1.1.0 additions.

Everything here is a claim that a unit test cannot reach, checked against the
real gateway through a real browser session:

  CREATE   A new library script is created empty, appears in the tree, and comes
           back with a signature the client can save against.
  DELETE   Removes the resource, and REFUSES without a matching If-Match. The
           precondition is the whole reason a delete cannot silently discard an
           edit the user never saw, so both refusals are asserted, not just the
           happy path.
  ENABLED  `enabled` round-trips on Shutdown and Update. Those two were
           body-only until 1.1.0 and were opened up on the strength of the other
           four measured types; that is an inference, and this is what turns it
           into a measurement. If this check ever fails, the type table is wrong
           and should go back to refusing them.
  CRON     `cronExpression` round-trips on a Scheduled script, and a malformed
           one is refused rather than written.
"""
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from gateway_session import CONFIG, GATEWAY_URL, login  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

SPA = CONFIG.get("spa_path", "/data/scriptide/")

results = []


def record(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def api(page, method, url, csrf, body=None, if_match=None):
    """One authenticated API call, made from inside the real session."""
    return page.evaluate(
        """async ([spa, method, url, csrf, body, ifMatch]) => {
             const headers = {'Accept': 'application/json', 'X-CSRF-Token': csrf};
             if (body !== null) headers['Content-Type'] = 'application/json';
             if (ifMatch !== null) headers['If-Match'] = ifMatch;
             const res = await fetch(spa + url, {
               method, credentials: 'include', headers,
               body: body === null ? undefined : JSON.stringify(body)});
             const text = await res.text();
             return {status: res.status, text: text};
           }""",
        [SPA, method, url, csrf, body, if_match])


def json_of(response):
    import json as _json
    try:
        return _json.loads(response["text"])
    except Exception:
        return {}


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_context(viewport={"width": 1400, "height": 900}).new_page()
        login(page)
        page.goto(GATEWAY_URL + SPA, wait_until="load", timeout=30000)

        session = page.evaluate(
            "async (spa) => (await (await fetch(spa + 'api/auth/session',"
            " {credentials:'include'})).json())", SPA)
        csrf = session.get("csrfToken")
        projects = page.evaluate(
            "async (spa) => (await (await fetch(spa + 'api/projects',"
            " {credentials:'include'})).json()).projects", SPA)
        # Prefer a scratch project. These checks CREATE gateway event scripts to
        # exercise them, and doing that in a real project — even with cleanup —
        # means a transient shutdown script exists on something that matters.
        mutable = [x["name"] for x in projects if x["mutable"]]
        if not mutable:
            sys.exit("FAIL: no mutable project on this gateway to write into")
        project = next((n for n in mutable if "scratch" in n.lower()), mutable[0])
        print(f"Validating against project '{project}'\n")

        def tree():
            return page.evaluate(
                "async ([spa, project]) => (await (await fetch("
                " spa + 'api/scripts?project=' + encodeURIComponent(project),"
                " {credentials:'include'})).json()).scripts", [SPA, project])

        # ---------------- CREATE ----------------
        name = f"scriptide_v11_{int(time.time())}"
        path = f"ignition/script-python/{name}"
        enc = urllib.parse.quote(path, safe="")
        url = f"api/scripts/content/{enc}?project={urllib.parse.quote(project)}"

        # No If-Match: absence is what selects the server's create branch.
        r = api(page, "POST", url, csrf, {"source": ""})
        record("CREATE", r["status"] == 200, f"HTTP {r['status']} {r['text'][:100]}")

        entry = next((e for e in tree() if e["path"] == path), None)
        record("CREATE APPEARS IN TREE", entry is not None,
               f"scriptKey={entry['scriptKey'] if entry else None}")

        body = page.evaluate(
            "async ([spa, url]) => (await fetch(spa + url, {credentials:'include'})).text()",
            [SPA, url])
        record("CREATE IS EMPTY", body == "",
               f"body={body!r} (the Designer writes a zero-byte code.py)")

        # ---------------- DELETE PRECONDITIONS ----------------
        r = api(page, "DELETE", url, csrf)
        record("DELETE WITHOUT If-Match IS 428", r["status"] == 428, f"HTTP {r['status']}")

        r = api(page, "DELETE", url, csrf, if_match="a-signature-that-is-not-current")
        record("DELETE WITH STALE If-Match IS 409", r["status"] == 409, f"HTTP {r['status']}")

        # ---------------- ENABLED on the newly-opened types ----------------
        created_paths = []
        for type_id, label in (("shutdown", "Shutdown"), ("update", "Update")):
            rpath = f"ignition/{type_id}"
            apath = urllib.parse.quote(rpath, safe="")
            aurl = f"api/scripts/attributes/{apath}?project={urllib.parse.quote(project)}"
            read = json_of(api(page, "GET", aurl, csrf))
            if not read.get("signature"):
                # Create the singleton so the attribute can actually be exercised.
                # A check that skips itself when the fixture is missing proves
                # nothing, and this claim is load-bearing in the type table.
                curl = (f"api/scripts/content/{apath}"
                        f"?project={urllib.parse.quote(project)}")
                made = api(page, "POST", curl, csrf,
                           {"source": f"def on{label}():\n\tpass"})
                if made["status"] != 200:
                    record(f"ENABLED {label}", False,
                           f"could not create the fixture: HTTP {made['status']} "
                           f"{made['text'][:100]}")
                    continue
                created_paths.append((rpath, apath))
                read = json_of(api(page, "GET", aurl, csrf))
            if not read.get("signature"):
                record(f"ENABLED {label}", False, "resource still absent after create")
                continue
            before = read.get("attributes", {}).get("enabled")
            want = not bool(before)
            w = api(page, "POST", aurl, csrf,
                    {"attributes": {"enabled": want}, "baseSignature": read["signature"]})
            if w["status"] != 200:
                record(f"ENABLED {label}", False, f"write HTTP {w['status']} {w['text'][:120]}")
                continue
            back = json_of(api(page, "GET", aurl, csrf))
            got = back.get("attributes", {}).get("enabled")
            record(f"ENABLED {label} ROUND-TRIP", got == want,
                   f"editable={read.get('editable')} {before!r} -> {want!r} -> {got!r}")
            # Restore, so the check leaves the gateway as it found it.
            api(page, "POST", aurl, csrf,
                {"attributes": {"enabled": bool(before)}, "baseSignature": back["signature"]})

        # ---------------- CRON on a Scheduled script ----------------
        sched = next((e for e in tree() if e["typeId"] == "scheduled"), None)
        if not sched:
            sname = f"scriptide_sched_{int(time.time())}"
            spath_raw = f"ignition/scheduled/{sname}"
            senc = urllib.parse.quote(spath_raw, safe="")
            made = api(page, "POST",
                       f"api/scripts/content/{senc}?project={urllib.parse.quote(project)}",
                       csrf, {"source": "def handleScheduleEvent():\n\tpass"})
            if made["status"] == 200:
                created_paths.append((spath_raw, senc))
                sched = next((e for e in tree() if e["path"] == spath_raw), None)
        if sched:
            spath = urllib.parse.quote(sched["path"], safe="")
            surl = f"api/scripts/attributes/{spath}?project={urllib.parse.quote(project)}"
            read = json_of(api(page, "GET", surl, csrf))
            record("CRON IS EDITABLE", "cronExpression" in read.get("editable", []),
                   f"editable={read.get('editable')}")
            original = read.get("attributes", {}).get("cronExpression")
            w = api(page, "POST", surl, csrf,
                    {"attributes": {"cronExpression": "*/15 * * * *"},
                     "baseSignature": read["signature"]})
            back = json_of(api(page, "GET", surl, csrf))
            record("CRON ROUND-TRIP",
                   w["status"] == 200
                   and back.get("attributes", {}).get("cronExpression") == "*/15 * * * *",
                   f"HTTP {w['status']} -> {back.get('attributes', {}).get('cronExpression')!r}")
            bad = api(page, "POST", surl, csrf,
                      {"attributes": {"cronExpression": "not a cron"},
                       "baseSignature": back["signature"]})
            record("MALFORMED CRON IS REFUSED", bad["status"] == 400,
                   f"HTTP {bad['status']} {bad['text'][:90]}")
            if original is not None:
                cur = json_of(api(page, "GET", surl, csrf))
                api(page, "POST", surl, csrf,
                    {"attributes": {"cronExpression": original},
                     "baseSignature": cur["signature"]})
        else:
            record("CRON", False, f"no scheduled script in {project} — cannot verify here")

        # Tidy up every fixture this run created, so a second run starts clean.
        for rpath, enc_path in created_paths:
            cur = next((e for e in tree() if e["path"] == rpath), None)
            if cur:
                api(page, "DELETE",
                    f"api/scripts/content/{enc_path}?project={urllib.parse.quote(project)}",
                    csrf, if_match=cur["signature"])

        # ---------------- DELETE FOR REAL ----------------
        entry = next((e for e in tree() if e["path"] == path), None)
        if entry:
            r = api(page, "DELETE", url, csrf, if_match=entry["signature"])
            record("DELETE", r["status"] == 200, f"HTTP {r['status']} {r['text'][:100]}")
            record("DELETE REMOVES IT FROM THE TREE",
                   not any(e["path"] == path for e in tree()), "")
        else:
            record("DELETE", False, "the created script vanished before the delete")

        browser.close()

    print()
    failed = [n for n, ok, _ in results if not ok]
    print(f"{'FAIL' if failed else 'PASS'}: {len(results) - len(failed)}/{len(results)} checks")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
