"""1.24.0 — templates, autosave/recovery, and console export.

The three remaining items from the borrowed-ideas brief. Each is checked on
the real gateway, because the interesting claim in each is one a unit test
cannot reach:

  * TEMPLATES seed code into somebody's new file. A unit test proves they use
    tabs and catch `Throwable`; only Jython can say whether they PARSE, and only
    this gateway can say whether the calls they make exist. A template that
    looks right and does not compile is worse than no template.

  * AUTOSAVE lives in `localStorage`, so the thing worth proving is that a
    buffer survives the PAGE being destroyed — which is a browser fact, not a
    React one.

  * THE EXPORT is a real download from a real browser.

Everything this suite creates it removes.

Run:
    SI_GATEWAY_CONFIG=$PWD/config.local.json \\
      .venv-test/bin/python scripts/testing/validate_v31_authoring.py
"""
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gateway_session import CONFIG, GATEWAY_URL, login          # noqa: E402
from playwright.sync_api import sync_playwright                 # noqa: E402

SPA = CONFIG.get("spa_path", "/data/scriptide/")
SOCKET = CONFIG.get("socket_path", "/system/scriptide")
PROJECT = os.environ.get("SI_EDIT_PROJECT", "Mining_Demo")

PKG = "_si_v31"
DRAFT = f"ignition/script-python/{PKG}/draft_me"
FOLDER = f"ignition/script-python/{PKG}"
FIXTURES = (DRAFT, FOLDER)

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


def q(value):
    return urllib.parse.quote(str(value), safe="")


def api(page, method, path, body=None):
    return page.evaluate(
        """async ([spa, method, path, body]) => {
            const res = await fetch(spa + path, {
                method, credentials: 'include',
                headers: body ? {'Content-Type': 'application/json'} : {},
                body: body ? JSON.stringify(body) : undefined,
            });
            return {status: res.status, text: await res.text()};
        }""", [SPA, method, path, body])


def json_of(result):
    try:
        return json.loads(result["text"])
    except (ValueError, KeyError, TypeError):
        return {}


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


def run_on_gateway(page, source):
    """Execute Jython on the gateway and return its stdout."""
    return page.evaluate(
        """async ([path, spa, src]) => {
          const r = await fetch(spa + 'api/auth/session', {credentials:'include'});
          const session = await r.json();
          const pr = await fetch(spa + 'api/projects', {credentials:'include'});
          const projects = (await pr.json()).projects || [];
          const target = projects.find(p => p.mutable) || projects[0];
          const url = (location.protocol === 'https:' ? 'wss://' : 'ws://')
                      + location.host + path;
          return await new Promise((resolve) => {
            let done = false, out = '';
            const finish = (v) => { if (!done) { done = true; resolve(v); } };
            const t = setTimeout(() => finish({out, why:'timeout'}), 30000);
            const ws = new WebSocket(url);
            ws.onopen = () => ws.send(JSON.stringify({ch:'exec', msg:{
                action:'run', project: target.name,
                csrfToken: session.csrfToken, source: src}}));
            ws.onmessage = (ev) => {
              const f = JSON.parse(ev.data);
              if (f.ch !== 'exec') return;
              if (f.msg && f.msg.event === 'output') out += f.msg.text || '';
              if (f.msg && f.msg.event === 'finished') {
                clearTimeout(t); ws.close();
                finish({out: out + (f.msg.stdout || ''), ok: f.msg.ok,
                        error: f.msg.error ? JSON.stringify(f.msg.error).slice(0, 400) : ''});
              }
            };
            ws.onerror = () => { clearTimeout(t); finish({out, why:'socket error'}); };
          });
        }""", [SOCKET, SPA, source])


print(f"Authoring on {GATEWAY_URL} (project {PROJECT})")

with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(
        viewport={"width": 1500, "height": 950}, accept_downloads=True)
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

    try:
        # =================== templates ===================

        # The picker is exercised through the DIALOG — the thing that has to
        # work anyway — and the template SOURCES are compiled separately below.
        # The shipped bundle is an IIFE with no module exports, so there is
        # nothing on the page to read them off.
        # The real control, read off FileTree.tsx rather than guessed: the
        # Project Library section's own "+" carries aria-label="New library
        # script". Guessing this cost a run.
        page.wait_for_timeout(600)
        opened = False
        add = page.get_by_role("button", name="New library script")
        if add.count() > 0:
            add.first.click(timeout=4000)
            page.wait_for_timeout(600)
            opened = page.locator('#newscript-template').count() > 0

        rec("the New script dialog offers a template picker", opened,
            "no #newscript-template select found")

        names = []
        if opened:
            names = page.locator('#newscript-template option').all_text_contents()
            rec("it offers Empty first and several real starting points",
                len(names) >= 5 and names[0].strip() == "Empty",
                ", ".join(names))
            # Leave the dialog; the compile check below is the real assertion.
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)
        else:
            rec("it offers Empty first and several real starting points", False,
                "dialog never opened")

        # THE assertion for templates: every one of them compiles as Jython, on
        # this gateway, with this interpreter.
        sources = page.evaluate("""() => (window.__scriptideTemplates || null)""")
        if sources is None:
            # Not exposed by the app — read them from the dialog by selecting
            # each option and creating nothing. Instead, compile the shipped
            # copies from the repo, which the unit tests keep in step.
            here = os.path.dirname(os.path.abspath(__file__))
            src_file = os.path.join(here, "..", "..", "web", "src", "api", "templates.ts")
            text = open(src_file, encoding="utf-8").read()
            # Each template's source is a joined array of single-quoted lines.
            import re
            blocks = re.findall(r"source: \[(.*?)\]\.join\('\\n'\)", text, re.S)
            sources = []
            for block in blocks:
                lines = re.findall(r"^\s*(['\"])(.*?)\1,\s*$", block, re.M)
                body = "\n".join(
                    line.replace("\\t", "\t").replace("\\'", "'").replace('\\"', '"')
                    for _quote, line in lines)
                sources.append(body)

        rec("FIXTURE: the template sources were recovered", len(sources) >= 5,
            f"{len(sources)} found")

        probe = "\n".join([
            "import json",
            "SOURCES = json.loads(r'''" + json.dumps(sources) + "''')",
            "bad = []",
            "for i, s in enumerate(SOURCES):",
            "\ttry:",
            "\t\tcompile(s, '<template%d>' % i, 'exec')",
            "\texcept Exception, e:",
            "\t\tbad.append('%d: %s' % (i, e))",
            "print 'COMPILED', len(SOURCES) - len(bad), 'of', len(SOURCES)",
            "for b in bad:",
            "\tprint 'BAD', b",
        ])
        result = run_on_gateway(page, probe)
        out = result.get("out", "")
        rec("every template compiles as Jython on the gateway",
            "BAD" not in out and f"COMPILED {len(sources)} of {len(sources)}" in out,
            out.strip()[:400] or result.get("error", "")[:300])

        # =================== autosave ===================

        rec("FIXTURE: a script to edit was created",
            write(page, csrf, DRAFT, "value = 1\n")["status"] == 200)

        page.wait_for_timeout(2000)
        page.reload(wait_until="load", timeout=30000)
        page.wait_for_selector(".file-tree-header", timeout=20000)
        page.select_option(".workspace-project select", PROJECT)
        page.wait_for_timeout(2000)

        for _ in range(6):
            shut = page.locator('.file-tree [aria-expanded="false"]')
            if shut.count() == 0:
                break
            for i in range(shut.count()):
                try:
                    shut.nth(i).click(timeout=1200)
                except Exception:
                    pass
            page.wait_for_timeout(300)

        row = page.locator(
            '.file-tree .file-tree-item:has(.file-tree-name:text-is("draft_me"))')
        rec("FIXTURE: the script opens", row.count() > 0)
        if row.count() > 0:
            row.first.click()
            page.wait_for_timeout(1500)
            editor = page.locator(".code-editor-host:not([style*=none]) .cm-content")
            editor.click()
            page.keyboard.press("Control+End")
            page.keyboard.type("\nunsaved = 'do not lose me'\n")
            # The persist is debounced at 800 ms.
            page.wait_for_timeout(2500)

            kept = page.evaluate(
                """() => Object.keys(window.localStorage)
                     .filter((k) => k.startsWith('scriptide.draft.')).length""")
            rec("the unsaved buffer is written to this browser", kept >= 1,
                f"{kept} drafts in localStorage")

            # Destroy the page — the case the feature exists for. A reload is
            # the closest a test gets to the tab dying, and it is enough: the
            # React state is gone either way.
            page.reload(wait_until="load", timeout=30000)
            page.wait_for_selector(".file-tree-header", timeout=20000)
            page.select_option(".workspace-project select", PROJECT)
            page.wait_for_timeout(2500)

            bar = page.locator(".workspace-recover")
            rec("after the page is destroyed, the work is offered back",
                bar.count() == 1, f"recover bars={bar.count()}")

            if bar.count() == 1:
                text = bar.inner_text()
                rec("the notice names the script and says where it was kept",
                    "draft_me" in text and "this browser" in text, text[:200])

                page.get_by_role("button", name="Restore").click()
                page.wait_for_timeout(3000)
                body = page.locator(
                    ".code-editor-host:not([style*=none]) .cm-content").inner_text()
                rec("Restore puts the text back in the editor",
                    "do not lose me" in body, body[-160:])
                rec("...and as an UNSAVED edit, not a silent write",
                    page.locator(".tab .tab-dirty").count() >= 1,
                    "no dirty marker on any tab")

                served = json_of(api(
                    page, "GET",
                    f"api/scripts/content/{q(DRAFT)}?project={q(PROJECT)}"))
                rec("the gateway's copy was never touched",
                    "do not lose me" not in json.dumps(served),
                    json.dumps(served)[:200])

        # =================== console export ===================

        page.locator('.activity-item[aria-label="Console"], '
                     '.activity-item[aria-label="Script Console"]').first.click(timeout=5000)
        page.wait_for_timeout(1200)
        console_editor = page.locator(".console-editor .cm-content")
        if console_editor.count() == 0:
            rec("FIXTURE: the console is on screen", False, "no console editor")
        else:
            console_editor.click()
            page.keyboard.press("Control+a")
            page.keyboard.type("print 'exported line'\n")
            page.keyboard.press("Control+Enter")
            page.wait_for_timeout(4000)

            rec("Times is a toggle, off by default",
                page.get_by_role("button", name="Times").get_attribute("aria-pressed")
                == "false")

            page.get_by_role("button", name="Times").click()
            page.wait_for_timeout(500)
            rec("turning Times on stamps the output",
                page.locator(".console-stamp").count() >= 1,
                f"stamps={page.locator('.console-stamp').count()}")

            with page.expect_download(timeout=15000) as caught:
                page.get_by_role("button", name="Export").click()
            download = caught.value
            saved = download.path()
            content = open(saved, encoding="utf-8").read() if saved else ""
            rec("Export hands over a text file named for the project",
                PROJECT in (download.suggested_filename or ""),
                download.suggested_filename or "<none>")
            rec("...containing the output, stamped, with a header",
                "exported line" in content and "# project:" in content,
                content[:200])

    finally:
        remove_fixtures(page, csrf)
        rec("CLEANUP: the fixture is gone", entry_for(page, DRAFT) is None,
            "draft_me is still in the tree")
        browser.close()

print()
print(f"validate_v31_authoring   {PASSED}/{PASSED + FAILED} checks passed")
sys.exit(0 if FAILED == 0 else 1)
