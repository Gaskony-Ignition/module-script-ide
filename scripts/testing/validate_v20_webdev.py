"""
Web Dev's real shapes — 1.9.0.

Nigel, 03/09/2026: *"The webdev section seems to me missing the mark from what
is in the designer. the Machine_HMI-Demo is a good example as it has cell3D
which appears to be javascript or html code which I should be able to view/edit
like a script but instead all I am seeing is doGet, doPost etc for each
endpoint."*

Measured on the rig 04/09/2026, that is because a Web Dev resource comes in TWO
shapes and this module knew one:

    admin/    config.json {"resource-type":"python-resource"} + 8 do*.py
    lib/      config.json {"resource-type":"python-resource"} + doGet.py
                                                             + three.min.js
    cell3d/   config.json {"resource-type":"text-resource",
                           "content-type":"text/html",
                           "text":"<!doctype html>…"}   files: [config.json] ONLY

So this suite is written around the DIFFERENCE between them: every check that
says a text resource does something also says a python one does not, and the
other way about. A component that ignored the discriminant would pass either
half on its own — which is exactly how the verb-only model looked healthy for
three releases.

It also edits `cell3d` for real and puts it back byte for byte, because the
round trip is the whole feature and a save that quietly escaped the HTML would
be invisible to any check that only read the page.

Run:
    WD_ALLOW_LOCAL_CONFIG=1 .venv-test/bin/python3 scripts/testing/validate_v20_webdev.py
"""
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gateway_session import CONFIG, GATEWAY_URL, login          # noqa: E402
from playwright.sync_api import sync_playwright                 # noqa: E402

SPA = CONFIG.get("spa_path", "/data/scriptide/")
PROJECT = os.environ.get("SI_WEBDEV_PROJECT", "Machine_HMI_Demo")
TEXT_KEY = "config.json#text"
PROBE = "\n<!-- scriptide v20 probe -->"
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


def content_url(path, key=None):
    url = ("api/scripts/content/" + urllib.parse.quote(path, safe="")
           + f"?project={urllib.parse.quote(PROJECT)}")
    return url + f"&key={urllib.parse.quote(key)}" if key else url


def endpoints(page):
    listing = json_of(api(page, "GET",
                          f"api/scripts?project={urllib.parse.quote(PROJECT)}"))
    return [e for e in listing.get("scripts", []) if e.get("typeId") == "resources"]


def row_for(page, name):
    """The expanded endpoint row, and the <li> holding its children."""
    header = page.locator(f'.file-tree-package:has-text("{name}")').first
    if header.count() and header.get_attribute("aria-expanded") == "false":
        header.click()
        page.wait_for_timeout(200)
    return header.locator("xpath=ancestor::li[1]")


with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))

    login(page)
    page.goto(GATEWAY_URL + SPA, wait_until="load", timeout=30000)
    page.wait_for_selector(".file-tree-header", timeout=20000)

    # ---------- the project that has all three shapes ----------
    page.select_option(".workspace-project select", PROJECT)
    page.wait_for_timeout(1500)

    listed = endpoints(page)
    by_name = {e["name"]: e for e in listed}
    rec("FIXTURE: the demo project's three endpoints are listed",
        {"admin", "cell3d", "lib"} <= set(by_name),
        f"{sorted(by_name)} in {PROJECT}")
    if not {"admin", "cell3d", "lib"} <= set(by_name):
        browser.close()
        print("\nThe fixture endpoints are not on this gateway — nothing to check.")
        sys.exit(1)

    # ---------- the listing says WHICH shape each one is ----------
    rec("SHAPE: cell3d is reported as a text resource",
        by_name["cell3d"].get("webdevKind") == "text",
        f"webdevKind={by_name['cell3d'].get('webdevKind')!r} "
        f"contentType={by_name['cell3d'].get('contentType')!r}")
    rec("SHAPE: admin and lib are reported as python — the guard is not vacuous",
        by_name["admin"].get("webdevKind") == "python"
        and by_name["lib"].get("webdevKind") == "python",
        f"admin={by_name['admin'].get('webdevKind')!r} "
        f"lib={by_name['lib'].get('webdevKind')!r}")
    rec("SHAPE: cell3d's default key is its body, not a handler it does not have",
        by_name["cell3d"].get("scriptKey") == TEXT_KEY,
        f"scriptKey={by_name['cell3d'].get('scriptKey')!r}")
    rec("SHAPE: cell3d reports NO verbs, admin reports the ones it has",
        by_name["cell3d"].get("methods") == []
        and "doGet" in (by_name["admin"].get("methods") or []),
        f"cell3d={by_name['cell3d'].get('methods')} "
        f"admin={by_name['admin'].get('methods')}")

    # ---------- static files that used to appear nowhere ----------
    lib_files = {f["key"]: f for f in (by_name["lib"].get("files") or [])}
    rec("FILES: lib's three.min.js is listed at all",
        "three.min.js" in lib_files, f"{sorted(lib_files)}")
    rec("FILES: it is listed as too large to edit, with its real size",
        lib_files.get("three.min.js", {}).get("editable") is False
        and lib_files.get("three.min.js", {}).get("size", 0) > 500_000,
        f"{lib_files.get('three.min.js')}")
    rec("FILES: admin, which carries none, reports none",
        (by_name["admin"].get("files") or []) == [],
        f"{by_name['admin'].get('files')}")

    # ---------- the tree draws the difference ----------
    page.click('.activity-item[title="Web Dev"], .activity-item:has-text("Web Dev")')
    page.wait_for_timeout(800)
    rec("VIEW: the Web Dev view opened",
        page.locator('nav[aria-label="Web Dev"]').count() == 1,
        f"{page.locator('nav[aria-label=\"Web Dev\"]').count()} tree(s)")

    cell = row_for(page, "cell3d")
    admin = row_for(page, "admin")
    lib = row_for(page, "lib")

    # THE defect, in the words it was reported in. Under the verb-only model
    # cell3d drew eight "add doGet" buttons and no row for the file itself —
    # and pressing one would have put Python onto a static HTML resource.
    rec("TREE: cell3d offers NO add-a-verb button",
        cell.locator('[title^="Add do"]').count() == 0,
        f"{cell.locator('[title^=\"Add do\"]').count()} add button(s)")
    # `lib`, not `admin`: admin implements all eight verbs on this gateway, so
    # it has nothing left to add and would pass this check for the wrong reason.
    # lib implements doGet only, which is precisely the case the add buttons
    # exist for.
    rec("TREE: lib still does — the same tree, two shapes",
        lib.locator('[title^="Add do"]').count() == 7,
        f"{lib.locator('[title^=\"Add do\"]').count()} add button(s), "
        f"admin (all eight implemented) has "
        f"{admin.locator('[title^=\"Add do\"]').count()}")
    rec("TREE: cell3d offers the file it actually serves",
        cell.locator('.file-tree-name:has-text("cell3d.html")').count() == 1,
        cell.inner_text().replace("\n", " · ")[:90])
    rec("TREE: and says which content type that is",
        "text/html" in cell.inner_text(), cell.inner_text().replace("\n", " · ")[:90])
    rec("TREE: cell3d has no settings cog, which it has no settings for",
        cell.locator('[aria-label="Settings for cell3d"]').count() == 0
        and admin.locator('[aria-label="Settings for admin"]').count() == 1,
        "cell3d none, admin one")
    rec("TREE: lib shows three.min.js with its size",
        lib.locator('.file-tree-name:has-text("three.min.js")').count() == 1
        and "654 KB" in lib.inner_text(),
        lib.inner_text().replace("\n", " · ")[:90])

    # ---------- opening the file ----------
    cell.locator('.file-tree-name:has-text("cell3d.html")').click()
    page.wait_for_timeout(2500)
    text = page.evaluate(
        "() => document.querySelector('.code-editor .cm-content')?.textContent ?? ''")
    rec("OPEN: the HTML is in the editor, not eight empty verb slots",
        text.lstrip().lower().startswith("<!doctype html>"), repr(text[:60]))
    rec("OPEN: the tab is named for the file, not for the synthetic key",
        page.locator('.tab:has-text("cell3d.html")').count() == 1
        and page.locator('.tab:has-text("config.json")').count() == 0,
        page.locator(".tab").first.inner_text().replace("\n", " ")[:60])

    # A Jython parser pointed at HTML publishes an error on every line. The
    # ruler being absent is the visible half of the language gate.
    page.wait_for_timeout(2500)
    rec("OPEN: the Jython language server is NOT run over it",
        page.locator(".problem-ruler").count() == 0
        and page.locator(".cm-lintRange-error").count() == 0,
        f"{page.locator('.problem-ruler').count()} ruler(s), "
        f"{page.locator('.cm-lintRange-error').count()} lint range(s)")
    # And it IS highlighted — CodeMirror's HTML grammar tags an element name,
    # which a plain-text surface would leave as an untagged run.
    rec("OPEN: it is highlighted as HTML",
        page.evaluate("""() => {
          const spans = document.querySelectorAll('.code-editor .cm-line span[class]');
          return spans.length > 20;
        }"""),
        f"{page.evaluate(chr(40) + ') => document.querySelectorAll'
                         + chr(40) + chr(39) + '.code-editor .cm-line span[class]'
                         + chr(39) + chr(41) + '.length')} highlighted spans")

    # ---------- the round trip ----------
    session = page.evaluate(
        """async (spa) => (await fetch(spa + 'api/auth/session',
             {credentials: 'include'})).json()""", SPA)
    csrf = session.get("csrfToken")
    path = by_name["cell3d"]["path"]

    original = api(page, "GET", content_url(path, TEXT_KEY))
    rec("READ: the body comes back through the content route",
        original["status"] == 200 and original["text"].lstrip().lower().startswith("<!doctype"),
        f"HTTP {original['status']}, {len(original['text'])} bytes")
    before = original["text"]
    etag = original["etag"]

    saved = api(page, "POST", content_url(path), csrf,
                {"source": before + PROBE, "key": TEXT_KEY}, etag)
    rec("WRITE: an edit to the body is accepted", saved["status"] == 200,
        f"HTTP {saved['status']} {saved['text'][:80]}")

    after = api(page, "GET", content_url(path, TEXT_KEY))
    rec("WRITE: and the gateway serves the edited body back",
        after["text"].endswith(PROBE), repr(after["text"][-40:]))

    # The two things a naive read-modify-write would have destroyed.
    cfg = json_of(api(page, "GET",
                      "api/webdev/config/" + urllib.parse.quote(path, safe="")
                      + f"?project={urllib.parse.quote(PROJECT)}"))
    rec("WRITE: the content type survived the save",
        cfg.get("contentType") == "text/html" and cfg.get("kind") == "text",
        f"kind={cfg.get('kind')!r} contentType={cfg.get('contentType')!r}")

    # Gson escapes <, > and & by default. That is still valid JSON serving the
    # same page, so nothing downstream would report it — and the file would be
    # unreadable in the editor and in every diff from then on.
    on_disk = api(page, "GET", content_url(path, "config.json"))
    rec("WRITE: the HTML is stored readable, not escaped tag by tag",
        "<!doctype html>" in on_disk["text"].lower()
        and "\\u003c" not in on_disk["text"],
        f"escapes={on_disk['text'].count(chr(92) + 'u003c')}, "
        f"{len(on_disk['text'])} bytes of config.json")

    # ---------- put it back, and prove it went back ----------
    restore = api(page, "POST", content_url(path), csrf,
                  {"source": before, "key": TEXT_KEY}, after["etag"])
    final = api(page, "GET", content_url(path, TEXT_KEY))
    rec("RESTORE: cell3d is byte for byte what it was",
        restore["status"] == 200 and final["text"] == before,
        f"HTTP {restore['status']}, {len(final['text'])} bytes "
        f"({'identical' if final['text'] == before else 'DIFFERENT'})")

    # ---------- the settings route refuses a shape it does not fit ----------
    refused = api(page, "POST",
                  "api/webdev/config/" + urllib.parse.quote(path, safe="")
                  + f"?project={urllib.parse.quote(PROJECT)}", csrf,
                  {"method": "doGet", "settings": {"enabled": True}},
                  final["etag"])
    rec("GUARD: per-method settings are refused on a text resource",
        refused["status"] == 400 and "static" in refused["text"].lower(),
        f"HTTP {refused['status']} {refused['text'][:90]}")

    # And still accepted where they belong, so the guard is not simply off.
    admin_path = by_name["admin"]["path"]
    admin_cfg = json_of(api(page, "GET",
                            "api/webdev/config/" + urllib.parse.quote(admin_path, safe="")
                            + f"?project={urllib.parse.quote(PROJECT)}"))
    rec("GUARD: admin still reports its per-method settings",
        admin_cfg.get("kind") == "python" and "doGet" in (admin_cfg.get("config") or {}),
        f"kind={admin_cfg.get('kind')!r} methods={sorted((admin_cfg.get('config') or {}))}")

    # ---------- a python endpoint's handlers still open ----------
    admin.locator('.file-tree-method:has-text("doGet")').first.click()
    page.wait_for_timeout(2000)
    rec("PYTHON: a verb handler still opens as Python, with its ruler",
        page.locator(".problem-ruler").count() == 1,
        f"{page.locator('.problem-ruler').count()} ruler(s)")

    rec("CONSOLE: no page errors during any of it", not errs, "; ".join(errs[:2]) or "none")
    browser.close()

failed = [n for n, ok, _ in res if not ok]
print(f"\n{len(res) - len(failed)}/{len(res)} checks passed")
if failed:
    print("FAILED: " + "; ".join(failed))
sys.exit(1 if failed else 0)
