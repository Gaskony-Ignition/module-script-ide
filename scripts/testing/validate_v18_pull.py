"""
Staleness and pull — 1.8.5.

The defect this exists for (Nigel, 03/09/2026): *"I made an edit on the designer
to one of the scripts. I had the script open in my ide module. The change did not
show up."*

Nothing here was ever at risk of silently overwriting the Designer — every save
carries `If-Match` and the gateway answers 409 — but the ONLY way to find out
was to attempt a save. Until 1.8.5 the IDE never re-read anything: the listing
was refetched after this app's own mutations and at no other time, and reopening
the script from the tree just refocused the existing tab.

A Designer edit is simulated by writing the resource through the REST API while
the tab sits open. That is the same thing from the app's point of view — the
React state has no idea it happened, which is precisely the condition under test.

Run:
    WD_ALLOW_LOCAL_CONFIG=1 .venv-test/bin/python3 scripts/testing/validate_v18_pull.py
"""
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gateway_session import CONFIG, GATEWAY_URL, login          # noqa: E402
from playwright.sync_api import sync_playwright                 # noqa: E402

SPA = CONFIG.get("spa_path", "/data/scriptide/")
PULL_PROJECT = os.environ.get("SI_PULL_PROJECT", "")
MODULE = "si_pull_fixture"
ORIGINAL = "def value():\n    return 1\n"
# What the "Designer" writes underneath the open tab.
EDITED = "def value():\n    return 999\n"

res = []


def rec(name, ok, detail=""):
    res.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def api(page, method, url, csrf, body=None, if_match=None):
    return page.evaluate(
        """async ([spa, method, url, csrf, body, ifMatch]) => {
             const headers = {'Accept': 'application/json', 'X-CSRF-Token': csrf};
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
    import json as _json
    try:
        return _json.loads(response["text"])
    except Exception:
        return {}


def content_url(project, module):
    return ("api/scripts/content/"
            + urllib.parse.quote(f"ignition/script-python/{module}", safe="")
            + f"?project={urllib.parse.quote(project)}")


def tree_of(page, project):
    return json_of(api(page, "GET",
                       f"api/scripts?project={urllib.parse.quote(project)}",
                       "")).get("scripts", [])


def signature_of(page, project, module):
    entry = next((e for e in tree_of(page, project)
                  if e.get("path") == f"ignition/script-python/{module}"), None)
    return entry.get("signature") if entry else None


def expand_tree(page, passes=6):
    for _ in range(passes):
        shut = page.locator('.file-tree [aria-expanded="false"]')
        if shut.count() == 0:
            return
        for index in range(shut.count()):
            try:
                shut.nth(index).click()
            except Exception:
                pass
        page.wait_for_timeout(120)


def editor_text(page):
    return page.evaluate("() => document.querySelector('.cm-content')?.innerText ?? ''")


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_context(viewport={"width": 1600, "height": 1000}).new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))

    login(page)
    page.goto(GATEWAY_URL + SPA, wait_until="load", timeout=30000)
    page.wait_for_selector(".file-tree-header", timeout=20000)
    session = page.evaluate(
        """async (spa) => (await fetch(spa + 'api/auth/session',
             {credentials: 'include'})).json()""", SPA)
    csrf = session.get("csrfToken")

    projects = json_of(api(page, "GET", "api/projects", ""))
    mutable = [q["name"] for q in (projects if isinstance(projects, list)
                                   else projects.get("projects", []))
               if q.get("mutable")]
    project = PULL_PROJECT or (mutable[0] if mutable else "")
    rec("FIXTURE: a mutable project", bool(project), f"project={project or 'none'}")
    if not project:
        browser.close()
        sys.exit(1)

    api(page, "POST", content_url(project, MODULE), csrf, {"source": ORIGINAL})
    page.reload(wait_until="load")
    page.wait_for_selector(".file-tree-header", timeout=20000)
    expand_tree(page)

    # ---------- open the fixture ----------
    row = page.locator(f'.file-tree-item:has-text("{MODULE}")').first
    row.click()
    page.wait_for_timeout(2000)
    rec("OPEN: the fixture is in the editor", "return 1" in editor_text(page),
        repr(editor_text(page)[:48]))

    # ---------- nothing is stale yet ----------
    rec("CLEAN: no stale marker on an untouched tab",
        page.locator(".tab-stale").count() == 0
        and page.locator(".workspace-stale").count() == 0,
        f"tab={page.locator('.tab-stale').count()} "
        f"toolbar={page.locator('.workspace-stale').count()}")

    # ---------- the Designer edits it underneath ----------
    signature = signature_of(page, project, MODULE)
    wrote = api(page, "POST", content_url(project, MODULE), csrf,
                {"source": EDITED, "baseSignature": signature}, signature)
    rec("EXTERNAL: the resource was changed outside this app's state",
        wrote["status"] == 200, f"POST -> {wrote['status']}")

    # The window regaining focus is the realistic trigger — you alt-tab back
    # from the Designer — and it must not wait for the 20 s timer.
    page.evaluate("() => window.dispatchEvent(new Event('focus'))")
    page.wait_for_timeout(2500)

    rec("DETECT: the tab shows a stale marker without being asked",
        page.locator(".tab-stale").count() == 1,
        f"{page.locator('.tab-stale').count()} marker(s)")
    toolbar = page.locator(".workspace-stale")
    # The bar over the buffer. The tab marker and the toolbar count were both
    # missable (Nigel, 04/09/2026: "a bit to easy to miss"), so the document
    # itself carries the notice.
    bar = page.locator(".workspace-stale-bar")
    rec("DETECT: a bar on the document says so in words",
        bar.count() == 1 and MODULE in bar.first.inner_text(),
        repr(bar.first.inner_text()[:90]) if bar.count() else "absent")

    rec("DETECT: the toolbar offers a counted pull",
        toolbar.count() == 1 and "1" in (toolbar.first.inner_text() if toolbar.count() else ""),
        toolbar.first.inner_text() if toolbar.count() else "absent")

    # The editor must still show the OLD text: detection is not a silent
    # replacement. Overwriting a buffer someone may be reading is the one thing
    # a background poll must never do.
    rec("SAFETY: the buffer is NOT replaced behind the user",
        "return 1" in editor_text(page), repr(editor_text(page)[:48]))

    # ---------- pull it ----------
    page.locator(".tab-stale").first.click()
    page.wait_for_timeout(2000)
    rec("PULL: the tab now holds the gateway's copy",
        "return 999" in editor_text(page), repr(editor_text(page)[:48]))
    rec("PULL: the stale marker clears once pulled",
        page.locator(".tab-stale").count() == 0
        and page.locator(".workspace-stale").count() == 0,
        f"tab={page.locator('.tab-stale').count()} "
        f"toolbar={page.locator('.workspace-stale').count()}")

    # ---------- dirty + stale must NOT be silently resolved ----------
    page.locator(".cm-content").click()
    page.keyboard.press("Control+End")
    page.keyboard.type("\n# local edit\n")
    page.wait_for_timeout(600)
    rec("DIRTY: the unsaved marker appears", page.locator(".tab-dirty").count() == 1,
        f"{page.locator('.tab-dirty').count()} marker(s)")

    signature = signature_of(page, project, MODULE)
    api(page, "POST", content_url(project, MODULE), csrf,
        {"source": "def value():\n    return 12345\n",
         "baseSignature": signature}, signature)
    page.evaluate("() => window.dispatchEvent(new Event('focus'))")
    page.wait_for_timeout(2500)
    rec("DIRTY+STALE: both markers show at once",
        page.locator(".tab-dirty").count() == 1 and page.locator(".tab-stale").count() == 1,
        f"dirty={page.locator('.tab-dirty').count()} "
        f"stale={page.locator('.tab-stale').count()}")

    page.locator(".tab-stale").first.click()
    page.wait_for_timeout(2000)
    dialog = page.locator(".conflict-dialog")
    rec("DIRTY+STALE: pulling raises the conflict dialog rather than discarding",
        dialog.count() == 1, f"{dialog.count()} dialog(s)")
    if dialog.count():
        body = dialog.first.inner_text()
        rec("CONFLICT: the dialog shows BOTH copies",
            "12345" in body and "local edit" in body,
            f"theirs={'12345' in body} mine={'local edit' in body}")
        # Cancel, explicitly. Escape works too (1.8.9) but clicking the button
        # is what proves the dialog can be dismissed WITHOUT choosing a side —
        # and it leaves no backdrop to intercept the next step's clicks.
        dialog.first.locator('button:has-text("Cancel")').click()
        page.wait_for_timeout(500)
    else:
        rec("CONFLICT: the dialog shows BOTH copies", False, "no dialog to inspect")

    # ---------- closing a dirty tab must ask ----------
    # Nigel, 04/09/2026: "I can close a tab that has unsaved changes without any
    # notice or anything." The close button sits a few pixels from the tab you
    # meant to click, so this is the easiest way in the app to lose work.
    page.locator(".code-editor .cm-content").click()
    page.keyboard.press("Control+End")
    page.keyboard.type("\n# unsaved\n")
    page.wait_for_timeout(600)
    page.locator(f'.tab-close[aria-label*="{MODULE}"]').first.click()
    page.wait_for_timeout(800)
    asked = page.locator('[role="alertdialog"]')
    rec("CLOSE: closing a dirty tab asks before discarding",
        asked.count() == 1, f"{asked.count()} dialog(s)")
    rec("CLOSE: the tab is still open while the question stands",
        page.locator(".tab-strip button").count() > 0,
        f"{page.locator('.tab-strip button').count()} tab button(s)")
    if asked.count():
        rec("CLOSE: it offers save-and-close, not just discard-or-cancel",
            asked.first.locator('button:has-text("Save and close")').count() == 1,
            "; ".join(asked.first.locator("button").all_inner_texts()))
        asked.first.locator('button:has-text("Cancel")').click()
        page.wait_for_timeout(400)
        rec("CLOSE: cancelling keeps the buffer",
            page.locator(".tab-dirty").count() == 1,
            f"dirty={page.locator('.tab-dirty').count()}")
        # Now discard it deliberately, so the fixture can be deleted.
        page.locator(f'.tab-close[aria-label*="{MODULE}"]').first.click()
        page.wait_for_timeout(600)
        page.locator('[role="alertdialog"] button:has-text("Discard")').click()
        page.wait_for_timeout(600)
    else:
        rec("CLOSE: it offers save-and-close, not just discard-or-cancel", False, "no dialog")
        rec("CLOSE: cancelling keeps the buffer", False, "no dialog")

    # ---------- our OWN save is not somebody else's change ----------
    # Nigel, 07/09/2026: *"when I click save while it is saving to the gateway a
    # pull request pops up on the script which could be confusing for people.
    # They might think that there is a conflict."*
    #
    # The write lands on the gateway before its new signature comes back, so for
    # the length of that round trip the listing and the open document disagree —
    # and every check that asks "has this moved on?" answered yes about the
    # user's own keystroke. Sampled DURING the save rather than after it: a check
    # that only looks at the end would pass against the bug, because the state
    # resolves itself a moment later.
    page.reload(wait_until="load", timeout=30000)
    page.wait_for_selector(".file-tree-header", timeout=20000)
    page.select_option(".workspace-project select", project)
    page.wait_for_timeout(1500)
    expand_tree(page)
    page.locator(f'.file-tree .file-tree-item:has-text("{MODULE.split("/")[-1]}")').first.click()
    page.wait_for_timeout(2000)
    page.locator(".cm-content").click()
    page.keyboard.press("Control+End")
    page.keyboard.type("\n# save race\n")
    page.wait_for_timeout(500)

    # Poll fast, from the click until the save has settled, and keep the WORST
    # thing seen at any point rather than the state at the end.
    #
    # Proved able to FAIL, 07/09/2026: with the two halves of the fix reverted
    # and redeployed, this reports peak {'tab': 1, 'bar': 1, 'toolbar': 1} — the
    # marker, the bar and the counted pull button, all three during a save
    # nobody else touched. A timing check that has never been seen red is a
    # check that passes because the window is too narrow to sample.
    seen_stale = page.evaluate(r"""async () => {
      const btn = [...document.querySelectorAll('.workspace-actions button, button')]
        .find(b => /^Save (script|query)$/.test(b.textContent.trim()));
      if (!btn) return {error: 'no save button'};
      let worst = {tab: 0, bar: 0, toolbar: 0};
      const sample = () => {
        worst.tab = Math.max(worst.tab, document.querySelectorAll('.tab-stale').length);
        worst.bar = Math.max(worst.bar, document.querySelectorAll('.workspace-stale').length);
        worst.toolbar = Math.max(worst.toolbar,
          [...document.querySelectorAll('button')]
            .filter(b => /^Pull \d+ change/.test(b.textContent.trim())).length);
      };
      btn.click();
      const started = Date.now();
      while (Date.now() - started < 6000) {
        sample();
        await new Promise(r => setTimeout(r, 25));
      }
      return worst;
    }""")
    rec("SAVE RACE: no stale marker on the tab at any point during our own save",
        seen_stale.get("tab") == 0, f"peak {seen_stale}")
    rec("SAVE RACE: and no bar or pull button offering to overwrite it",
        seen_stale.get("bar") == 0 and seen_stale.get("toolbar") == 0,
        f"peak {seen_stale}")
    rec("SAVE RACE: the save itself still went through",
        "# save race" in editor_text(page)
        and page.locator(".tab-dirty").count() == 0,
        f"dirty={page.locator('.tab-dirty').count()}")

    # ---------- clean up ----------
    signature = signature_of(page, project, MODULE)
    api(page, "DELETE", content_url(project, MODULE), csrf, None, signature)
    remaining = [e.get("path") for e in tree_of(page, project)]
    rec("FIXTURE: removed again",
        f"ignition/script-python/{MODULE}" not in remaining,
        f"{len(remaining)} script(s) left in {project}")

    rec("CONSOLE: no page errors from our own code", not errs, "; ".join(errs[:2]))
    browser.close()

print()
passed = sum(1 for _, ok, _ in res if ok)
print(f"{passed}/{len(res)} checks passed")
sys.exit(0 if passed == len(res) else 1)
