"""1.22.0 — snippets, organise imports, style lints, and colour in the console.

Groups 2 and part of 4 of the borrowed-ideas brief, on the real gateway.

The one in here that is not a new feature is the most important. **A PEP 263
coding declaration made the whole file a syntax error** — measured 07/09/2026.
Everything in this module parses from a `StringReader`, which is Unicode text,
and Jython refuses a coding declaration in one: `encoding declaration in Unicode
string`. So an ordinary `# -*- coding: utf-8 -*-` header put a red mark on line 1
about nothing in the file's own code, and the file then contributed nothing to
the outline, was skipped entirely by test discovery, and could not be organised.
On 1.21.0 a test module with that header was invisible. Both halves are asserted
below: it is discovered, and it runs.

Everything this suite creates it removes.

Run:
    SI_GATEWAY_CONFIG=$PWD/config.local.json \\
      .venv-test/bin/python scripts/testing/validate_v29_authoring.py
"""
import json
import os
import sys
import time
import urllib.parse
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gateway_session import CONFIG, GATEWAY_URL, login          # noqa: E402
from playwright.sync_api import sync_playwright                 # noqa: E402

SPA = CONFIG.get("spa_path", "/data/scriptide/")
PROJECT = os.environ.get("SI_EDIT_PROJECT", "Mining_Demo")

TAG = uuid.uuid4().hex[:6]
PKG = f"_si_v29_{TAG}"
MESSY = f"ignition/script-python/{PKG}/messy"
HELPER = f"ignition/script-python/{PKG}/helper"
CODING = f"ignition/script-python/{PKG}/test_coding"
LINTS = f"ignition/script-python/{PKG}/lints"
FOLDER = f"ignition/script-python/{PKG}"
FIXTURES = (MESSY, HELPER, CODING, LINTS, FOLDER)

# A docstring FIRST, because that is the case the first implementation got wrong
# and it is the shape almost every well-written module in this estate has: the
# docstring was read as code, so the imports counted as "below code" and the
# whole feature was a silent no-op on exactly those files.
MESSY_SOURCE = "\n".join([
    '"""A module whose imports need sorting."""',
    "import sys",
    "import json",
    "import sys",          # an exact duplicate
    "import re",           # genuinely unused
    "from os import path",
    "",
    "def use():",
    "\treturn json.dumps({'p': path.sep, 's': sys.platform})",
    "",
])

HELPER_SOURCE = "def computeTotal(rows):\n\treturn len(rows)\n"

# The coding declaration, with a real test under it.
CODING_SOURCE = "\n".join([
    "# -*- coding: utf-8 -*-",
    '"""A module with a coding header, which is ordinary in any file that has '
    'ever held a non-ASCII character."""',
    "",
    "def test_it_runs():",
    "\tassert 1 + 1 == 2",
    "",
    "def helperName():",
    "\treturn 'outline'",
    "",
])

# One of each style finding, and — the point of doing this over the AST rather
# than over the text — the same words inside a string and a comment, which must
# NOT be reported.
LINTS_SOURCE = "\n".join([
    '"""Style checks. This docstring mentions == None and except: on purpose."""',
    "",
    "# never write except: in real code",
    "ADVICE = 'do not write x == None'",
    "",
    "def collect(items=[]):",
    "\ttry:",
    "\t\tif items == None:",
    "\t\t\treturn {}",
    "\texcept:",
    "\t\tpass",
    "\treturn items",
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


def read(page, path):
    return page.evaluate(
        """async ([spa, url]) => {
             const r = await fetch(spa + url, {credentials: 'include',
               headers: {'Accept': 'text/plain'}});
             return r.ok ? await r.text() : null;
           }""",
        [SPA, f"api/scripts/content/{urllib.parse.quote(path, safe='')}?project={q(PROJECT)}"])


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


def run_console(page, source, timeout=40):
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
    page.locator(".console-toolbar").get_by_role("button", name="Run", exact=True).click()
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.locator(".console-output-head .console-running").count() == 0:
            break
        page.wait_for_timeout(150)
    page.wait_for_timeout(400)
    return page


with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(viewport={"width": 1700, "height": 1050})
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
        write(page, csrf, MESSY, MESSY_SOURCE)["status"],
        write(page, csrf, HELPER, HELPER_SOURCE)["status"],
        write(page, csrf, CODING, CODING_SOURCE)["status"],
        write(page, csrf, LINTS, LINTS_SOURCE)["status"],
    ]
    rec("FIXTURE: four modules were created", all(s == 200 for s in written), f"HTTP {written}")
    page.wait_for_timeout(14000)

    try:
        # =================== the coding declaration ===================

        listing = {}
        for attempt in range(6):
            listing = json_of(api(page, "GET", f"api/tests?project={q(PROJECT)}"))
            if any(m["module"].endswith("test_coding") for m in listing.get("modules", [])):
                break
            page.wait_for_timeout(2000 + 1000 * attempt)

        codingIds = [t["id"] for m in listing.get("modules", [])
                     if m["module"].startswith(PKG) for t in m["tests"]]
        rec("A CODING DECLARATION NO LONGER HIDES THE FILE: its test is discovered",
            len(codingIds) == 1, ", ".join(codingIds) or "nothing discovered")

        if codingIds:
            run = json_of(api(page, "POST", f"api/tests/run?project={q(PROJECT)}",
                              csrf, {"ids": codingIds}))
            result = (run.get("results") or [{}])[0]
            # The second half, and it is a different question: the parser refuses
            # a coding declaration in a UNICODE string but not in a byte str, and
            # the runner compiles the module's source itself.
            rec("...and it RUNS — the runner compiles that source too",
                result.get("status") == "pass",
                f"{result.get('status')}: {(result.get('message') or '')[:90]}")

        # =================== organise imports ===================

        before = read(page, MESSY)
        organised = json_of(api(page, "POST",
                                f"api/scripts/organise-imports?project={q(PROJECT)}",
                                csrf, {"source": MESSY_SOURCE}))
        newSource = organised.get("source", "")

        rec("THE DOCSTRING IS NOT CODE: a module that opens with one is still organised",
            newSource != MESSY_SOURCE and newSource.startswith('"""A module whose imports'),
            newSource.split("\n\n")[0][:90].replace("\n", " | "))
        rec("the duplicate import is gone and the rest is sorted",
            newSource.count("import sys") == 1
            and newSource.index("import json") < newSource.index("import sys"),
            " | ".join(newSource.split("\n")[1:5]))
        rec("the unused import is removed and named, and a USED one is not",
            "import re" not in newSource
            and any("re" in r for r in organised.get("removed", []))
            and "from os import path" in newSource and "import sys" in newSource,
            f"removed={organised.get('removed')}")
        rec("the body below the imports is untouched",
            "return json.dumps({'p': path.sep, 's': sys.platform})" in newSource,
            "the function survived")
        rec("ORGANISING WRITES NOTHING TO THE GATEWAY",
            read(page, MESSY) == before, "the stored resource is unchanged")

        unparseable = json_of(api(page, "POST",
                                  f"api/scripts/organise-imports?project={q(PROJECT)}",
                                  csrf, {"source": "import os\ndef f(:\n"}))
        rec("a file that does not parse comes back byte-identical, with a reason",
            unparseable.get("source") == "import os\ndef f(:\n"
            and bool(unparseable.get("notes")),
            "; ".join(unparseable.get("notes", []))[:90])

        guarded = json_of(api(page, "POST",
                              f"api/scripts/organise-imports?project={q(PROJECT)}",
                              csrf, {"source": "import os\nimport sys\n\nexec 'x = 1'\n"}))
        rec("a module using exec keeps its unused imports, and says why",
            "import os" in guarded.get("source", "")
            and any("exec" in n for n in guarded.get("notes", [])),
            "; ".join(guarded.get("notes", []))[:100])

        suggested = json_of(api(page, "POST",
                                f"api/scripts/organise-imports?project={q(PROJECT)}",
                                csrf, {"source": "def run():\n\treturn computeTotal([1, 2])\n"}))
        names = [s.get("statement", "") for s in suggested.get("suggestions", [])]
        rec("an unknown name defined in another project module is suggested",
            any(f"{PKG}.helper" in s and "computeTotal" in s for s in names),
            "; ".join(names)[:110] or "no suggestions")

        stdlib = json_of(api(page, "POST",
                             f"api/scripts/organise-imports?project={q(PROJECT)}",
                             csrf, {"source": "def run():\n\treturn json.dumps({})\n"}))
        rec("a standard-library name is suggested from the built-in table",
            any(s.get("statement") == "import json"
                for s in stdlib.get("suggestions", [])),
            "; ".join(s.get("statement", "") for s in stdlib.get("suggestions", []))[:90])

        # =================== the console helpers ===================

        page.locator('button[aria-label="Script Console"]').click()
        page.wait_for_timeout(800)
        page.wait_for_selector(".console-editor .cm-content", timeout=20000)

        run_console(page, "cprint('V29-GREEN', 'green')\n")
        coloured = page.locator(".console-output .console-ansi")
        rec("cprint reaches the console as a coloured span, not as escape bytes",
            coloured.count() >= 1
            and "V29-GREEN" in page.locator(".console-output").inner_text(),
            f"{coloured.count()} span(s)")
        rec("...and the escape itself is never shown",
            "[32m" not in page.locator(".console-output").inner_text(),
            page.locator(".console-output").inner_text().strip()[:80].replace("\n", " | "))
        if coloured.count():
            colour = coloured.first.evaluate("el => getComputedStyle(el).color")
            rec("the span is actually painted, so the theme variable resolved",
                colour not in ("", "rgba(0, 0, 0, 0)"), colour)

        run_console(page, "cprint('V29-HEX', '#ff8800', bold=True)\n")
        rec("a 24-bit colour is honoured",
            "V29-HEX" in page.locator(".console-output").inner_text()
            and page.locator(".console-output .console-ansi").count() >= 1,
            page.locator(".console-output").inner_text().strip()[:70].replace("\n", " | "))

        run_console(page, "jsonPrint({'b': 2, 'a': [1, 'two', None]})\n")
        text = page.locator(".console-output").inner_text()
        rec("jsonPrint pretty-prints, sorted, and in colour",
            '"a"' in text and text.index('"a"') < text.index('"b"')
            and page.locator(".console-output .console-ansi").count() >= 3,
            text.strip()[:90].replace("\n", " | "))

        run_console(page, "jsonPrint(system.db)\n")
        rec("something JSON cannot encode falls back to repr rather than failing",
            "Traceback" not in page.locator(".console-output").inner_text(),
            page.locator(".console-output").inner_text().strip()[:80].replace("\n", " | "))

        run_console(page, "print 'V29-PLAIN', [1, 2][0]\n")
        rec("ordinary output with a bracket in it is untouched",
            "V29-PLAIN 1" in page.locator(".console-output").inner_text(),
            page.locator(".console-output").inner_text().strip()[:70].replace("\n", " | "))

        # The CONSOLE never had the coding-declaration problem, and this says so
        # rather than leaving it to be assumed. The two paths differ for a real
        # reason: the console hands Jython a Java String, which compiles as a byte
        # str, while the test runner seeds its sources through Py.java2py and gets
        # unicode -- and Python 2 refuses the declaration only in the second.
        # Asserted so nobody "fixes" a path that was never broken.
        run_console(page, "# -*- coding: utf-8 -*-\nprint 'V29-CONSOLE-CODING'\n")
        rec("a coding declaration in the CONSOLE was never a problem, and still is not",
            "V29-CONSOLE-CODING" in page.locator(".console-output").inner_text(),
            page.locator(".console-output").inner_text().strip()[:80].replace("\n", " | "))
    finally:
        remove_fixtures(page, csrf)
        browser.close()

passed = sum(1 for _, ok, _ in res if ok)
print(f"\nvalidate_v29_authoring   {passed}/{len(res)} checks passed")
sys.exit(0 if passed == len(res) else 1)
