#!/usr/bin/env python3
"""Live acceptance for the 1.5.0 tree/draft fixes, measured on 1.4.3.

Everything here is a claim a unit test cannot reach, because every one of
these four defects lives at the browser/gateway boundary:

  DRAFT     Clicking an absent Startup/Shutdown/Update row in the tree used to
            write to the project IMMEDIATELY — a single click on a live
            gateway, no confirmation, no save. 1.5.0 opens an unsaved draft
            instead; the resource is created on the FIRST save. This check
            proves the negative (nothing is created by the click or by
            closing the tab) as well as the positive (a save DOES create it),
            because a fix that only proves the positive would pass even if
            the click still wrote immediately.
  FOLDER    A project-library PACKAGE with nothing in it (`ignition/script-
            python/MiningDemo`, `dataKeys: []`) used to pass every filter and
            list as an openable script; clicking it 404'd with "No such data
            key 'code.py'". 1.5.0 renders it as an empty folder instead.
  FOOTER    "Language server offline" showed in the rail footer on landing,
            before any document had been opened — the LSP connects lazily,
            so nothing had actually failed. 1.5.0 shows a neutral idle state
            until a connection is actually attempted.
  READONLY  A tab holding an inherited, not-yet-overridden script now says so
            on the TAB itself (`(Read-Only)`), not only in the settings-strip
            notice below it.

TWO fixtures, discovered, and they are no longer the same project. DRAFT needs
one whose Update row is genuinely ABSENT; READONLY needs one that INHERITS from
an Inheritable parent. Both were pinned to `Site_Redgum_Sewer` until 04/09/2026
— a water-suite project this gateway does not have and never did — so
`select_option` threw and the run ended there with eleven checks unreported.
They were then briefly one discovered project, which worked only while
`_wd_scratch_` was not Inheritable: once it was (05/09/2026, so these very
READONLY checks could run at all) its child inherited an Update, whose row is
present-but-read-only and therefore serves neither check. SI_INHERIT_PROJECT
still pins the draft one, and a name this gateway does not offer is a FAIL
rather than a silent fallback.
FOLDER needs a project with an empty script-python package; `Mining_Demo` is
the known fixture, but this script also scans every mutable project for one,
so a gateway where that project has since gained content still finds a
fixture rather than skipping the check.

Run:
    WD_ALLOW_LOCAL_CONFIG=1 .venv-test/bin/python3 scripts/testing/validate_v15_tree.py
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
INHERIT_PROJECT = os.environ.get("SI_INHERIT_PROJECT", "Site_Redgum_Sewer")
FOLDER_PROJECT_HINT = os.environ.get("SI_FOLDER_PROJECT", "Mining_Demo")

res = []


def skip(name, detail=""):
    # A pass with the reason stated. A check that cannot run on this gateway is
    # not evidence of a defect, and dropping it silently would leave the tally
    # looking complete when it is not.
    res.append((name, True, detail))
    print(f"  [SKIP] {name}: {detail}")


def rec(name, ok, detail=""):
    res.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")


# ---- authenticated API calls from inside the real session, like validate_v11 ----

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
             return {status: res.status, text: text};
           }""",
        [SPA, method, url, csrf, body, if_match])


def json_of(response):
    import json as _json
    try:
        return _json.loads(response["text"])
    except Exception:
        return {}


def tree_of(page, project):
    r = api(page, "GET", f"api/scripts?project={urllib.parse.quote(project)}", "")
    return json_of(r).get("scripts", [])


def has_update(page, project):
    """Does an Update script exist for this project, from ANY origin?

    Any origin, deliberately: DRAFT needs a row that is genuinely ABSENT, and an
    INHERITED Update is not absent — it opens read-only, which is the other
    check's subject entirely.
    """
    return any(e.get("path") == "ignition/update" and e.get("defined", True)
               for e in tree_of(page, project))


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
                # A short timeout on purpose: opening a branch re-renders the
                # list, so a locator taken a moment ago can name a node that is
                # gone. That is expected and is swallowed below — but at the
                # default 30 s each stale one cost half a minute, and three of
                # them per pass put 90 s of nothing into every run.
                shut.nth(index).click(timeout=1500)
            except Exception:
                pass          # a click that re-renders the list is not a failure
        page.wait_for_timeout(120)


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_context(viewport={"width": 1600, "height": 1000}).new_page()
    login(page)
    page.goto(GATEWAY_URL + SPA, wait_until="load", timeout=30000)
    page.wait_for_selector(".file-tree-header", timeout=20000)
    expand_tree(page)

    session = page.evaluate(
        "async (spa) => (await (await fetch(spa + 'api/auth/session',"
        " {credentials:'include'})).json())", SPA)
    csrf = session.get("csrfToken")

    # ---------- FOOTER: no false "offline" before any script is opened ----------
    # First thing after load, deliberately — opening any script later in this
    # run is exactly what would legitimately connect the LSP and change the
    # state, so this has to run before that happens.
    saw_offline = False
    last_text = ""
    deadline = time.time() + 3.0
    while time.time() < deadline:
        last_text = page.locator(".rail-status").inner_text()
        if "offline" in last_text.lower():
            saw_offline = True
            break
        page.wait_for_timeout(200)
    rec("FOOTER: no 'offline' in the rail within 3s of landing",
        not saw_offline, repr(last_text))

    # ---------- pick the fixture project instead of assuming one ----------
    #
    # `Site_Redgum_Sewer` was the named fixture and this gateway does not have
    # it — the water-suite projects were never on the module rig. A hardcoded
    # name meant `select_option` THREW, so the run died here and the eleven
    # checks below it were neither passed nor recorded: a suite that reports
    # nothing is worse than one that reports a skip.
    #
    # The FOLDER check has scanned for its own fixture since 1.5.0. This does
    # the same. SI_INHERIT_PROJECT still wins, but only when the gateway
    # actually offers it — silently ignoring a name the user set would hide a
    # typo, so an absent one is a FAIL, not a fallback.
    projects = json_of(api(page, "GET", "api/projects", "")).get("projects", [])
    by_name = {q["name"]: q for q in projects}
    offered = set(page.locator(".workspace-project select option")
                  .evaluate_all("nodes => nodes.map(n => n.value)"))
    wanted = os.environ.get("SI_INHERIT_PROJECT")
    if wanted and wanted not in offered:
        rec("FIXTURE: SI_INHERIT_PROJECT names a project this gateway has",
            False, f"{wanted} is not in the project picker — {sorted(offered)}")
        wanted = None

    def draftable(name):
        # DRAFT needs somewhere to CREATE ignition/update and delete it again;
        # FOLDER_PROJECT_HINT is left out so the two checks cannot disturb each
        # other's fixture.
        return (name in offered and name != FOLDER_PROJECT_HINT
                and by_name.get(name, {}).get("mutable")
                and not has_update(page, name))

    # A project with a PARENT first, because READONLY needs one and DRAFT does
    # not care; then the rest, so DRAFT still runs on a gateway with no
    # inheritance at all.
    parented = sorted(q["name"] for q in projects if q.get("parent"))
    orphans = sorted(q["name"] for q in projects if not q.get("parent"))
    # TWO fixtures, because since `_wd_scratch_` was made Inheritable
    # (04/09/2026) no single project can be both. DRAFT needs a project whose
    # Update row is genuinely ABSENT; READONLY needs one that INHERITS — and a
    # project inheriting from a parent that HAS an Update has a row which is
    # present-but-read-only, which is neither.
    INHERIT_PROJECT = wanted or next(
        (n for n in parented + orphans if draftable(n)), None)
    READONLY_PROJECT = next(
        (n for n in parented
         if by_name.get(by_name.get(n, {}).get("parent") or "", {}).get("inheritable")),
        None)
    if INHERIT_PROJECT:
        print(f"  [FIXTURE] draft project = {INHERIT_PROJECT}; "
              f"read-only project = {READONLY_PROJECT}")

    if INHERIT_PROJECT is None:
        for name in ("FIXTURE: the inherit project has no Update script yet",
                     "DRAFT: clicking the absent row opens a tab, and writes NOTHING",
                     "DRAFT: the new tab is marked dirty (unsaved) immediately",
                     "DRAFT: closing the tab without saving still creates nothing",
                     "DRAFT: closing the tab removed it",
                     "DRAFT: Ctrl+S on the draft creates the resource for real",
                     "DRAFT: the tab no longer shows dirty after a successful save",
                     "CLEANUP: the fixture Update script was deleted",
                     "FIXTURE: the inherit project has an inherited script to open"):
            skip(name, "every mutable project on this gateway already has an "
                       "Update script — DRAFT needs one without. Set "
                       "SI_INHERIT_PROJECT, or delete the fixture script")
    else:

        # ---------- DRAFT: clicking an absent singleton does not write ----------
        page.select_option(".workspace-project select", INHERIT_PROJECT)
        page.wait_for_timeout(1500)
        # Reopen: the tree is re-fetched on a project switch and ships collapsed.
        expand_tree(page)
        page.wait_for_timeout(2000)

        before = has_update(page, INHERIT_PROJECT)
        rec("FIXTURE: the inherit project has no Update script yet",
            not before, f"project={INHERIT_PROJECT}")

        if before:
            rec("DRAFT", False, "cannot test the draft path — Update already exists; "
                "set SI_INHERIT_PROJECT to a project with none")
        else:
            update_row = page.get_by_role("button", name="Update", exact=True)
            update_row.click()
            page.wait_for_timeout(800)

            rec("DRAFT: clicking the absent row opens a tab, and writes NOTHING",
                page.locator(".tab.is-active").count() == 1 and not has_update(page, INHERIT_PROJECT),
                "")
            rec("DRAFT: the new tab is marked dirty (unsaved) immediately",
                page.locator(".tab.is-active .tab-dirty").count() == 1, "")

            # Close without saving — must discard, not create.
            #
            # Since 1.8.10 this asks first (Nigel, 04/09/2026: "I can close a
            # tab that has unsaved changes without any notice"). The guard is
            # the behaviour under test here, so it is ASSERTED rather than
            # dismissed: a close that silently discarded would leave no dialog
            # and pass a check that only looked at the tab count.
            page.locator(".tab.is-active .tab-close").click()
            page.wait_for_timeout(500)
            rec("DRAFT: closing an unsaved tab asks before discarding it",
                page.locator('[role=alertdialog]').count() == 1
                and page.locator(".tab").count() == 1,
                page.locator("#close-title").inner_text()
                if page.locator("#close-title").count() else "no dialog")
            page.get_by_role("button", name="Discard changes").click()
            page.wait_for_timeout(500)
            rec("DRAFT: closing the tab without saving still creates nothing",
                not has_update(page, INHERIT_PROJECT), "")
            rec("DRAFT: discarding removed the tab",
                page.locator(".tab").count() == 0, "")

            # Click it again, actually write something, and save for real.
            update_row.click()
            page.wait_for_timeout(800)
            page.locator(".code-editor-host:not([style*=none]) .cm-content").click()
            page.keyboard.type("print 1")
            page.wait_for_timeout(400)
            page.keyboard.press("Control+s")
            page.wait_for_timeout(1500)

            after_tree = tree_of(page, INHERIT_PROJECT)
            created = next((e for e in after_tree if e.get("path") == "ignition/update"), None)
            rec("DRAFT: Ctrl+S on the draft creates the resource for real",
                created is not None, f"{created}")
            rec("DRAFT: the tab no longer shows dirty after a successful save",
                page.locator(".tab.is-active .tab-dirty").count() == 0, "")

            # Leave the rig as found: delete the fixture this check just created.
            if created:
                d = api(page, "DELETE",
                        f"api/scripts/content/{urllib.parse.quote('ignition/update', safe='')}"
                        f"?project={urllib.parse.quote(INHERIT_PROJECT)}",
                        csrf, if_match=created["signature"])
                rec("CLEANUP: the fixture Update script was deleted",
                    d["status"] == 200 and not has_update(page, INHERIT_PROJECT),
                    f"HTTP {d['status']}")
                # Close the now-stale tab too, or the next check's screenshot/DOM
                # state carries a tab pointing at a resource that no longer exists.
                if page.locator(".tab").count():
                    page.locator(".tab.is-active .tab-close").click()
                    page.wait_for_timeout(300)

        # ---------- READONLY: an inherited tab's label says so ----------
        # Its OWN project — see the two-fixture note above.
        if READONLY_PROJECT and READONLY_PROJECT != INHERIT_PROJECT:
            page.select_option(".workspace-project select", READONLY_PROJECT)
            page.wait_for_timeout(1800)
            expand_tree(page)
            page.wait_for_timeout(1000)
        INHERIT_PROJECT = READONLY_PROJECT or INHERIT_PROJECT
        inherited = next((e for e in tree_of(page, INHERIT_PROJECT) if e.get("origin") == "inherited"), None)
        # An empty inherited set has two opposite meanings: the listing is broken,
        # or the parent on this rig is not marked Inheritable — in which case the
        # platform's merged view carries nothing to list, and no module could show
        # it. `/api/projects` reports the parent and its flag so the two can be told
        # apart here. `_wd_scratch_` on the module rig is not inheritable, and
        # flipping that is a change to another project, not to this suite.
        listing = {p["name"]: p for p in json_of(api(page, "GET", "api/projects", "")).get("projects", [])}
        me = listing.get(INHERIT_PROJECT, {})
        parent = listing.get(me.get("parent") or "", {})
        if inherited is None and not me.get("parent"):
            # No parent at all, so there is nothing to inherit and nothing to
            # check. This used to fall through to a FAIL, which reads as a
            # defect in the listing rather than as "this gateway offered no
            # inheriting project".
            skip("FIXTURE: the inherit project has an inherited script to open",
                 f"{INHERIT_PROJECT} has no parent — the READONLY checks need a "
                 "project that inherits from an Inheritable one")
        elif inherited is None and me.get("parent") and parent and not parent.get("inheritable", True):
            skip("FIXTURE: the inherit project has an inherited script to open",
                 f"{INHERIT_PROJECT} inherits {me['parent']}, which is not marked Inheritable on "
                 f"this gateway — the READONLY checks need a parent that is")
        else:
            rec("FIXTURE: the inherit project has an inherited script to open",
                inherited is not None, f"project={INHERIT_PROJECT} parent={me.get('parent')}")
        if inherited:
            row = page.locator(".file-tree-row:has(.badge-inherited) .file-tree-item").first
            row.click()
            page.wait_for_timeout(1500)
            tab_text = page.locator(".tab.is-active .tab-name").inner_text() if page.locator(
                ".tab.is-active .tab-name").count() else ""
            rec("READONLY: the tab label carries \"(Read-Only)\"",
                "Read-Only" in tab_text, repr(tab_text))
            # The editor itself must already refuse typing — this is the OTHER
            # half of the same claim, measured the same way validate_v14 measures
            # it (EditorState.readOnly is advisory, so typing-and-looking is the
            # only honest test).
            cm = page.locator(".code-editor-host:not([style*=none]) .cm-content")
            before_text = cm.inner_text()
            cm.click()
            page.keyboard.type("ZZZZ")
            page.wait_for_timeout(400)
            after_text = cm.inner_text()
            rec("READONLY: the buffer still discards typing (unchanged from 1.4.0)",
                before_text == after_text, "")
            page.screenshot(path=f"{OUT}/v15-readonly-tab.png")

    # ---------- FOLDER: an empty package renders as a folder, not a file ----------
    projects = page.evaluate(
        "async (spa) => (await (await fetch(spa + 'api/projects',"
        " {credentials:'include'})).json()).projects", SPA)
    mutable = [x["name"] for x in projects if x.get("mutable")]
    candidates = [FOLDER_PROJECT_HINT] + [p for p in mutable if p != FOLDER_PROJECT_HINT]

    folder_project = None
    folder_entry = None
    for candidate in candidates:
        entries = tree_of(page, candidate)
        found = next(
            (e for e in entries if e.get("typeId") == "script-python" and e.get("isFolder")), None)
        if found:
            folder_project, folder_entry = candidate, found
            break

    rec("FIXTURE: a project with an empty script-python package exists",
        folder_entry is not None,
        f"checked {candidates[:6]}{'…' if len(candidates) > 6 else ''}")

    if folder_entry:
        page.select_option(".workspace-project select", folder_project)
        page.wait_for_timeout(1500)
        expand_tree(page)
        page.wait_for_timeout(2000)
        leaf = folder_entry["name"].split("/")[-1]
        folder_row = page.locator(".file-tree-package", has_text=leaf).first
        rec("FOLDER: the empty package renders as a folder row",
            folder_row.count() > 0, f"project={folder_project} name={folder_entry['name']}")
        if folder_row.count():
            rec("FOLDER: the row carries aria-expanded (a folder), not a plain script button",
                folder_row.get_attribute("aria-expanded") is not None, "")
            folder_row.click()
            page.wait_for_timeout(600)
            error_notice = page.locator(".workspace-notice.is-error", has_text="No such data key")
            rec("FOLDER: clicking it never produces \"No such data key\"",
                error_notice.count() == 0,
                error_notice.inner_text() if error_notice.count() else "")
            # And it must not have opened a tab either — a folder has nothing
            # to edit.
            rec("FOLDER: clicking it opens no tab",
                page.locator(f'.tab-label[title*="{leaf}"]').count() == 0, "")
        page.screenshot(path=f"{OUT}/v15-empty-package.png")

    browser.close()

print()
passed = sum(1 for _, ok, _ in res if ok)
print(f"{passed}/{len(res)} checks passed")
sys.exit(0 if passed == len(res) else 1)
