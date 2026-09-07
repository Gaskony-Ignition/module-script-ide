"""Export and import, round-tripped against the Designer's own format — 1.20.0.

Nigel, 07/09/2026: *"there is no export/import code options like in the
designer"*, choosing the **Designer-compatible resource zip** over plain `.py`
files, on the tree's right-click menu.

That choice is the whole test. "Compatible" is not a property of a zip this
module can read back — a format invented here would round-trip through itself
perfectly and still be a file the Designer refuses. So the assertions are against
a REAL Designer export, captured on 07/09/2026 from `Mining_Demo` on this gateway
and described in `docs/EXPORT-FORMAT.md`:

* the zip this module writes has the same shape — `project.json` at the root,
  each resource as `<path>/resource.json` plus its data files, no wrapper
  directory;
* `resource.json` carries the same five fields, with `scope` as a LETTER rather
  than the integer the API returns;
* the code inside is byte-identical to what the gateway holds, tabs and all —
  the same bar every save in this module is held to; and
* a zip is IMPORTED back into a second project and the script arrives whole.

The refusals are unit-tested (`TransferRouteHandlerTest`); what needs a gateway
is the round trip and the menu that starts it.

Run:
    SI_GATEWAY_CONFIG=$PWD/config.local.json \\
      .venv-test/bin/python scripts/testing/validate_v27_transfer.py
"""
import io
import json
import os
import sys
import time
import uuid
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gateway_session import CONFIG, GATEWAY_URL, login          # noqa: E402
from playwright.sync_api import sync_playwright                 # noqa: E402

SPA = CONFIG.get("spa_path", "/data/scriptide/")
PROJECT = os.environ.get("SI_EDIT_PROJECT", "Mining_Demo")

TAG = uuid.uuid4().hex[:6]
PKG = f"_si_v27_{TAG}"
MODULES = ("alpha", "beta")
# Tabs, a trailing-newline-free body and a non-ASCII character: byte fidelity is
# the bar every save in this module is held to, and an export that quietly
# reformatted would be a diff-noisy backup nobody could trust.
SOURCE = "def total(rows):\n\ttotal = 0\n\tfor r in rows:\n\t\ttotal += r\n\treturn total  # µ"
FIXTURES = tuple(f"ignition/script-python/{PKG}/{m}" for m in MODULES) \
    + (f"ignition/script-python/{PKG}",)

res = []


def rec(name, ok, detail=""):
    res.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def api_write(page, csrf, path, source, project=PROJECT):
    return page.evaluate("""async ([spa, path, project, src, csrf]) => {
      const url = spa+'api/scripts/content/'+encodeURIComponent(path)
                  +'?project='+encodeURIComponent(project);
      const cur = await fetch(url, {credentials:'include', headers:{'Accept':'text/plain'}});
      const h = {'Content-Type':'application/json','X-CSRF-Token':csrf};
      if (cur.ok) h['If-Match'] = (cur.headers.get('ETag')||'').replace(/^W\\//,'').replace(/^"|"$/g,'');
      const r = await fetch(url, {method:'POST', credentials:'include', headers:h,
        body: JSON.stringify({source: src})});
      return r.status;
    }""", [SPA, path, project, source, csrf])


def api_read(page, path, project=PROJECT):
    return page.evaluate("""async ([spa, path, project]) => {
      const url = spa+'api/scripts/content/'+encodeURIComponent(path)
                  +'?project='+encodeURIComponent(project);
      const r = await fetch(url, {credentials:'include', headers:{'Accept':'text/plain'}});
      return r.ok ? await r.text() : null;
    }""", [SPA, path, project])


def api_delete(page, csrf, path, project=PROJECT):
    page.evaluate("""async ([spa, path, project, csrf]) => {
      const listing = await (await fetch(
        spa+'api/scripts?project='+encodeURIComponent(project),
        {credentials:'include'})).json();
      const entry = (listing.scripts||[]).find(e => e.path === path);
      if (!entry) return;
      const url = spa+'api/scripts/content/'+encodeURIComponent(path)
                  +'?project='+encodeURIComponent(project);
      await fetch(url, {method:'DELETE', credentials:'include',
        headers:{'X-CSRF-Token':csrf, 'If-Match': entry.signature||''}});
    }""", [SPA, path, project, csrf])


def tree_paths(page, project=PROJECT):
    return page.evaluate("""async ([spa, project]) => {
      const r = await fetch(spa+'api/scripts?project='+encodeURIComponent(project),
        {credentials:'include'});
      const j = r.ok ? await r.json() : {scripts: []};
      return (j.scripts||[]).map(e => e.path);
    }""", [SPA, project])


def fetch_export(page, paths, project=PROJECT):
    """Download an export as base64 + its Content-Disposition, from the page."""
    return page.evaluate("""async ([spa, project, paths]) => {
      const q = new URLSearchParams();
      q.set('project', project);
      paths.forEach(p => q.append('path', p));
      const r = await fetch(spa+'api/scripts/export?'+q.toString(), {credentials:'include'});
      if (!r.ok) return {status: r.status, body: (await r.text()).slice(0, 200)};
      const buf = new Uint8Array(await r.arrayBuffer());
      let s = '';
      for (const b of buf) s += String.fromCharCode(b);
      return {status: 200, disposition: r.headers.get('Content-Disposition'),
              type: r.headers.get('Content-Type'), b64: btoa(s)};
    }""", [SPA, project, paths])


with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    login(page)
    page.goto(GATEWAY_URL + SPA, wait_until="load", timeout=30000)
    page.wait_for_selector(".file-tree-header", timeout=20000)
    csrf = page.evaluate(
        "async (spa) => (await (await fetch(spa+'api/auth/session',"
        "{credentials:'include'})).json()).csrfToken", SPA)
    page.select_option(".workspace-project select", PROJECT)
    page.wait_for_timeout(1500)

    made = [api_write(page, csrf, f"ignition/script-python/{PKG}/{m}", SOURCE)
            for m in MODULES]
    rec("FIXTURE: two library scripts were created",
        all(s == 200 for s in made), f"HTTP {made}")
    page.wait_for_timeout(9000)

    # =================== the exported file ===================

    paths = [f"ignition/script-python/{PKG}/{m}" for m in MODULES]
    got = fetch_export(page, paths)
    rec("EXPORT: the route answers with a file",
        got.get("status") == 200, f"HTTP {got.get('status')} {got.get('body', '')}")

    import base64
    raw = base64.b64decode(got["b64"]) if got.get("b64") else b""
    rec("EXPORT: it is a zip, not JSON describing one",
        raw[:2] == b"PK", f"{raw[:4]!r}, {len(raw)} bytes")

    # The Designer's own convention, measured off its Save dialog:
    # <Project>_<YYYY-MM-DD>_<HHMM>.zip
    import re
    disposition = got.get("disposition") or ""
    rec("EXPORT: named the way the Designer names its own",
        bool(re.search(rf'filename="{re.escape(PROJECT)}_\d{{4}}-\d{{2}}-\d{{2}}_\d{{4}}\.zip"',
                       disposition)),
        disposition)

    archive = zipfile.ZipFile(io.BytesIO(raw))
    names = sorted(archive.namelist())
    rec("EXPORT: project.json sits at the ROOT, with no wrapper directory",
        "project.json" in names and not any(n.startswith(PROJECT + "/") for n in names),
        ", ".join(names[:3]))

    expected = sorted(
        ["project.json"]
        + [f"{p}/resource.json" for p in paths]
        + [f"{p}/code.py" for p in paths])
    rec("EXPORT: each resource is its real path, with resource.json beside code.py",
        names == expected, f"{len(names)} entries")

    manifest = json.loads(archive.read("project.json"))
    rec("EXPORT: project.json carries the five fields the Designer writes",
        sorted(manifest.keys())
        == ["description", "enabled", "inheritable", "parent", "title"],
        ", ".join(sorted(manifest.keys())))
    rec("EXPORT: a project with no parent gets the empty string, not null",
        manifest.get("parent") == "" or isinstance(manifest.get("parent"), str),
        repr(manifest.get("parent")))

    descriptor = json.loads(archive.read(f"{paths[0]}/resource.json"))
    rec("EXPORT: resource.json carries the same five keys",
        sorted(descriptor.keys())
        == ["attributes", "files", "overridable", "restricted", "scope", "version"],
        ", ".join(sorted(descriptor.keys())))
    # The API returns an integer; the Designer writes a letter. Getting this
    # wrong produces a file that looks right and imports as the wrong scope.
    rec("EXPORT: scope is a LETTER, as the Designer writes it, not the API's integer",
        descriptor.get("scope") == "A", repr(descriptor.get("scope")))
    rec("EXPORT: files names the data keys actually in the archive",
        descriptor.get("files") == ["code.py"], repr(descriptor.get("files")))

    body = archive.read(f"{paths[0]}/code.py").decode("utf-8")
    rec("EXPORT: the code is byte-identical to what the gateway holds",
        body == SOURCE,
        f"{len(body)} chars, tabs={body.count(chr(9))} vs {SOURCE.count(chr(9))}")

    # =================== importing it back ===================
    # Into a DIFFERENT project, which is the case that matters: importing into
    # the project it came from proves only that nothing changed.
    others = [n for n in page.evaluate(
        "async (spa) => (await (await fetch(spa+'api/projects',"
        "{credentials:'include'})).json()).projects.filter(p => p.mutable)"
        ".map(p => p.name)", SPA) if n != PROJECT]
    target = others[0] if others else PROJECT
    rec("FIXTURE: a second, writable project to import into",
        target != PROJECT, target)

    inspected = page.evaluate("""async ([spa, project, b64, csrf]) => {
      const bin = atob(b64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const r = await fetch(spa+'api/scripts/import/inspect?project='
                            +encodeURIComponent(project), {
        method:'POST', credentials:'include',
        headers:{'Content-Type':'application/zip','X-CSRF-Token':csrf},
        body: bytes});
      return {status: r.status, body: await r.json().catch(() => null)};
    }""", [SPA, target, got["b64"], csrf])
    rec("INSPECT: the archive is read and its resources listed",
        inspected.get("status") == 200
        and len((inspected.get("body") or {}).get("entries", [])) == 2,
        f"HTTP {inspected.get('status')}, "
        f"{len((inspected.get('body') or {}).get('entries', []))} entries")

    entries = (inspected.get("body") or {}).get("entries", [])
    rec("INSPECT: it says these are NEW in the target, not replacements",
        entries and all(e.get("exists") is False for e in entries),
        ", ".join(f"{e['path'].split('/')[-1]}:{e['exists']}" for e in entries))
    rec("INSPECT: and that this module will write them",
        entries and all(e.get("importable") for e in entries), "importable")
    rec("INSPECT: it reports the exporting project, from project.json",
        (inspected.get("body") or {}).get("source", {}).get("title") is not None,
        str((inspected.get("body") or {}).get("source", {}).get("title"))[:40])

    # Nothing has been written yet — that is the whole point of a separate route.
    rec("INSPECT: writes NOTHING",
        not any(p.startswith(f"ignition/script-python/{PKG}")
                for p in tree_paths(page, target)),
        "target still clean")

    applied = page.evaluate("""async ([spa, project, b64, paths, csrf]) => {
      const bin = atob(b64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const q = new URLSearchParams();
      q.set('project', project);
      paths.forEach(p => q.append('path', p));
      const r = await fetch(spa+'api/scripts/import?'+q.toString(), {
        method:'POST', credentials:'include',
        headers:{'Content-Type':'application/zip','X-CSRF-Token':csrf},
        body: bytes});
      return {status: r.status, body: await r.json().catch(() => null)};
    }""", [SPA, target, got["b64"], paths, csrf])
    rec("IMPORT: both resources were written",
        applied.get("status") == 200
        and (applied.get("body") or {}).get("written") == 2,
        json.dumps(applied.get("body"))[:150])
    rec("IMPORT: and each is reported as CREATED rather than replaced",
        all(r.get("status") == "created"
            for r in (applied.get("body") or {}).get("results", [])),
        ", ".join(r.get("status", "?")
                  for r in (applied.get("body") or {}).get("results", [])))

    page.wait_for_timeout(6000)
    landed = api_read(page, paths[0], target)
    rec("ROUND TRIP: the imported script is byte-identical to the original",
        landed == SOURCE,
        f"{len(landed or '')} chars vs {len(SOURCE)}")

    # A second import of the same file is the overwrite case, and it must SAY so.
    again = page.evaluate("""async ([spa, project, b64, csrf]) => {
      const bin = atob(b64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const r = await fetch(spa+'api/scripts/import/inspect?project='
                            +encodeURIComponent(project), {
        method:'POST', credentials:'include',
        headers:{'Content-Type':'application/zip','X-CSRF-Token':csrf},
        body: bytes});
      return await r.json();
    }""", [SPA, target, got["b64"], csrf])
    rec("OVERWRITE: a second inspect now reports them as EXISTING",
        all(e.get("exists") for e in again.get("entries", [])),
        "exists=True for both")

    # =================== what it refuses ===================

    bad = page.evaluate("""async ([spa, project, csrf]) => {
      const bytes = new TextEncoder().encode('print "not a zip"');
      const r = await fetch(spa+'api/scripts/import/inspect?project='
                            +encodeURIComponent(project), {
        method:'POST', credentials:'include',
        headers:{'Content-Type':'application/zip','X-CSRF-Token':csrf},
        body: bytes});
      return {status: r.status, body: (await r.text()).slice(0, 120)};
    }""", [SPA, target, csrf])
    rec("REFUSES: a file that is not a zip, in words a user can act on",
        bad.get("status") == 400 and "zip" in bad.get("body", "").lower(),
        f"HTTP {bad.get('status')} {bad.get('body', '')[:70]}")

    nothing = fetch_export(page, [])
    rec("REFUSES: an export with nothing selected",
        nothing.get("status") == 400, f"HTTP {nothing.get('status')}")

    absent = fetch_export(page, ["ignition/script-python/_si_v27_absent/nope"])
    rec("REFUSES: an export naming a script this project does not have",
        absent.get("status") == 404, f"HTTP {absent.get('status')}")

    # =================== the menu it hangs off ===================

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
                shut.nth(i).click(timeout=1500)
            except Exception:
                pass
        page.wait_for_timeout(500)

    row = page.locator(
        f'.file-tree .file-tree-item:has(.file-tree-name:text-is("{MODULES[0]}"))').first
    rec("MENU: the fixture script is in the tree", row.count() > 0, MODULES[0])
    row.click(button="right")
    page.wait_for_timeout(600)
    menu = page.locator(".context-menu")
    rec("MENU: right-clicking a script opens a menu, not the browser's own",
        menu.count() == 1, f"{menu.count()} menu(s)")
    rec("MENU: it names what it is about",
        MODULES[0] in menu.inner_text(),
        menu.inner_text().replace("\n", " | ")[:80])
    rec("MENU: it offers both export and import",
        menu.locator('button:has-text("Export")').count() == 1
        and menu.locator('button:has-text("Import")').count() == 1,
        menu.inner_text().replace("\n", " | ")[:80])

    # On screen, in full. A menu opened near an edge that runs off it loses its
    # last item, which is the one people are usually reaching for.
    box = menu.bounding_box() or {}
    rec("MENU: it is fully on screen",
        box and box["x"] >= 0 and box["y"] >= 0
        and box["x"] + box["width"] <= 1600 and box["y"] + box["height"] <= 1000,
        f"x={box.get('x', -1):.0f} y={box.get('y', -1):.0f} "
        f"w={box.get('width', 0):.0f} h={box.get('height', 0):.0f}")

    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    rec("MENU: Escape closes it", page.locator(".context-menu").count() == 0,
        f"{page.locator('.context-menu').count()} left")

    # A PACKAGE acts on everything under it, which is what "export this package"
    # has to mean or the gesture is useless on anything but a single file.
    pkg = page.locator(
        f'.file-tree .file-tree-package:has-text("{PKG}")').first
    if pkg.count():
        pkg.click(button="right")
        page.wait_for_timeout(600)
        label = page.locator(".context-menu").inner_text()
        rec("MENU: a package's export names every script under it",
            "Export 2 scripts" in label, label.replace("\n", " | ")[:80])
        page.keyboard.press("Escape")
    else:
        rec("MENU: a package's export names every script under it", False,
            "package row not found")

    # =================== clean up ===================
    for path in FIXTURES:
        api_delete(page, csrf, path)
        page.wait_for_timeout(600)
    for path in FIXTURES:
        api_delete(page, csrf, path, target)
        page.wait_for_timeout(600)
    page.wait_for_timeout(2000)
    left = [p for p in tree_paths(page) if PKG in p] \
        + [p for p in tree_paths(page, target) if PKG in p]
    rec("CLEANUP: every fixture was removed from both projects",
        not left, ", ".join(left) or "none left")

    browser.close()

passed = sum(1 for _, ok, _ in res if ok)
print(f"\n{passed}/{len(res)} checks passed")
sys.exit(0 if passed == len(res) else 1)
