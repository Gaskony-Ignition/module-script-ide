"""1.25.0 — git status in the tree.

Only a gateway can answer this. The module reads a repository on the GATEWAY's
disk with JGit, and every interesting case is about what is actually on that
disk: whether two files fold into one script, whether a deletion still finds a
node to mark, whether an unreadable repository is distinguishable from a clean
one. A unit test supplies its own answer to all of that.

The rig's image has NO `git` binary — it is the stock Ignition image, and
building a custom one is a decision already taken the other way. So the fixture
repository is built here on the host and copied in, which is also the only way a
person could do it on that gateway.

Everything this suite creates it removes, including the repository.

Run:
    SI_GATEWAY_CONFIG=$PWD/scripts/testing/config.local.json \\
      .venv-test/bin/python scripts/testing/validate_v32_git.py
"""
import json
import os
import subprocess
import sys
import tempfile
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gateway_session import CONFIG, GATEWAY_URL, login          # noqa: E402
from playwright.sync_api import sync_playwright                 # noqa: E402

SPA = CONFIG.get("spa_path", "/data/scriptide/")
CONTAINER = os.environ.get("SI_CONTAINER", "ignition-module-testing")
PROJECTS = "/usr/local/bin/ignition/data/projects"

# The scratch project, not a demo. This suite writes a .git directory into a
# project directory on a SHARED gateway, so it goes where this module already
# keeps its probes.
PROJECT = os.environ.get("SI_GIT_PROJECT", "_wd_scratch_")
# A project that is deliberately NOT a repo, to prove the feature stays hidden.
PLAIN_PROJECT = os.environ.get("SI_EDIT_PROJECT", "Mining_Demo")

PKG = "_si_v32"
# Created BEFORE the baseline commit, so it is tracked and can be modified and
# deleted. The suite owns it and removes it at the end.
TRACKED_SCRIPT = f"ignition/script-python/{PKG}/v32_tracked"
# Created AFTER the baseline, so it reads as a new file.
NEW_SCRIPT = f"ignition/script-python/{PKG}/v32_added"

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


def docker(*args, check=True):
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check)


def sh(script, root=False):
    args = ["exec"] + (["-u", "0"] if root else []) + [CONTAINER, "sh", "-c", script]
    return docker(*args, check=False)


def make_repo():
    """Build a real repository from the project's own files and install it.

    Built on the host because the container has no git. The index records paths
    and stat data; the files it names are identical either side of the copy, so
    JGit re-hashes what it cannot match on stat and reports the truth.
    """
    remove_repo()
    tmp = tempfile.mkdtemp(prefix="si-v32-")
    work = os.path.join(tmp, "project")
    docker("cp", f"{CONTAINER}:{PROJECTS}/{PROJECT}", work)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
    subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=work, check=True, env=env)
    subprocess.run(["git", "add", "-A"], cwd=work, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", "v32 fixture baseline"],
                   cwd=work, check=True, env=env)
    docker("cp", os.path.join(work, ".git"), f"{CONTAINER}:{PROJECTS}/{PROJECT}/.git")
    # The gateway runs as `ignition`, and a root-owned .git is unreadable to it.
    # Only the .git subtree — never the project directory, where a wrong owner
    # silently stops every resource scan.
    sh(f"chown -R ignition:ignition {PROJECTS}/{PROJECT}/.git", root=True)
    return tmp


def remove_repo():
    sh(f"rm -rf {PROJECTS}/{PROJECT}/.git", root=True)


def api(page, path):
    raw = page.evaluate(
        """async ([spa, path]) => {
             const r = await fetch(spa + path, {credentials: 'include'});
             return {status: r.status, text: await r.text()};
           }""", [SPA, path])
    try:
        return json.loads(raw["text"])
    except (ValueError, TypeError):
        return {"_status": raw["status"], "_text": raw["text"][:200]}


def status(page, project=PROJECT):
    return api(page, f"api/git/status?project={q(project)}")


def tree(page, project=PROJECT):
    return api(page, f"api/scripts?project={q(project)}").get("scripts", [])


def write(page, csrf, path, source, project=PROJECT):
    found = next((e for e in tree(page, project) if e.get("path") == path), None)
    return page.evaluate(
        """async ([spa, url, csrf, src, etag]) => {
             const h = {'Content-Type': 'application/json', 'X-CSRF-Token': csrf};
             if (etag) h['If-Match'] = etag;
             const r = await fetch(spa + url, {method: 'POST', credentials: 'include',
               headers: h, body: JSON.stringify({source: src})});
             return r.status;
           }""",
        [SPA, f"api/scripts/content/{q(path)}?project={q(project)}",
         csrf, source, found.get("signature") if found else None])


def remove(page, csrf, path, project=PROJECT):
    found = next((e for e in tree(page, project) if e.get("path") == path), None)
    if not found:
        return 404
    return page.evaluate(
        """async ([spa, url, csrf, etag]) => {
             const h = {'X-CSRF-Token': csrf};
             if (etag) h['If-Match'] = etag;
             return (await fetch(spa + url, {method: 'DELETE', credentials: 'include',
               headers: h})).status;
           }""",
        [SPA, f"api/scripts/content/{q(path)}?project={q(project)}", csrf,
         found.get("signature")])


print(f"Git status on {GATEWAY_URL} (project {PROJECT})")
scratch = None

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_context(viewport={"width": 1500, "height": 950}).new_page()
    login(page)
    page.goto(GATEWAY_URL + SPA, wait_until="load", timeout=30000)
    page.wait_for_selector(".file-tree-header", timeout=20000)
    csrf = page.evaluate(
        "async (spa) => (await (await fetch(spa + 'api/auth/session',"
        " {credentials:'include'})).json()).csrfToken", SPA)

    try:
        # ---------- a project that is not a repository ----------
        plain = status(page, PLAIN_PROJECT)
        rec("a project with no .git reports repo=false",
            plain.get("repo") is False, json.dumps(plain)[:200])
        rec("...and carries no error, because that is the ordinary case",
            plain.get("error") is None, json.dumps(plain)[:200])

        # Remove the fixtures BEFORE the baseline is committed. A leftover
        # v32_added from an interrupted run would be committed INTO the baseline,
        # and re-creating it would then read as "modified" rather than "added" —
        # which is exactly how this suite first failed, on litter left by its own
        # earlier run.
        remove(page, csrf, NEW_SCRIPT)
        remove(page, csrf, TRACKED_SCRIPT)
        remove(page, csrf, f"ignition/script-python/{PKG}")

        # The one the baseline will track.
        write(page, csrf, TRACKED_SCRIPT, "TRACKED = True\n")
        scratch = make_repo()

        # ---------- a clean repository ----------
        clean = status(page)
        rec("a fresh repository reads as clean", clean.get("clean") is True,
            json.dumps(clean)[:300])
        rec("...on the branch it was created on", clean.get("branch") == "main",
            str(clean.get("branch")))
        rec("...with a HEAD commit", bool(clean.get("head")), str(clean.get("head")))
        rec("...and no marks", clean.get("marks") == {}, str(clean.get("marks")))

        # ---------- one script, two files, ONE mark ----------
        # This suite's OWN script, committed into the baseline above, never one
        # that was already in the project. An earlier version edited and then
        # DELETED whichever library script happened to be first, and three runs
        # permanently removed two real probe scripts from a shared gateway. A
        # test that destroys the fixtures of other tests is a worse defect than
        # anything it can catch.
        target = TRACKED_SCRIPT
        rec("FIXTURE: this suite's own script is in the baseline commit",
            any(e.get("path") == target for e in tree(page)))
        code = write(page, csrf, target, "# v32\nVALUE = 1\n")
        rec("a save through the IDE's own route succeeds", code == 200, str(code))

        edited = status(page)
        rec("the edited script is marked modified",
            edited.get("marks", {}).get(target) == "modified",
            json.dumps(edited.get("marks"))[:300])
        rec("a save that rewrote code.py AND resource.json is ONE mark",
            len(edited.get("marks", {})) == 1, json.dumps(edited.get("marks"))[:300])
        rec("...and the summary counts it", edited.get("dirty") == 1,
            str(edited.get("dirty")))

        # ---------- a new script ----------
        write(page, csrf, NEW_SCRIPT, "NEW = True\n")
        added = status(page)
        rec("a new script is marked added",
            added.get("marks", {}).get(NEW_SCRIPT) == "added",
            json.dumps(added.get("marks"))[:300])

        # ---------- a deletion ----------
        gone = remove(page, csrf, target)
        rec("the tracked script was deleted", gone in (200, 204), str(gone))
        deleted = status(page)
        rec("a deleted resource is marked deleted, and keeps its own path so the "
            "client can roll it up",
            deleted.get("marks", {}).get(target) == "deleted",
            json.dumps(deleted.get("marks"))[:300])

        # ---------- the UI ----------
        page.reload(wait_until="load")
        page.wait_for_selector(".file-tree-header", timeout=20000)
        page.select_option(".workspace-project select", PROJECT)
        page.wait_for_timeout(2500)

        summary = page.locator(".git-summary")
        rec("the side bar shows a git summary line", summary.count() == 1,
            f"found {summary.count()}")
        if summary.count() == 1:
            text = summary.inner_text()
            rec("...naming the branch", "main" in text, text)
            rec("...and how much has changed", "changed" in text, text)

        # Open the library group, then the fixture package by NAME. A sweep over
        # every collapsed node was not enough: each click re-renders the list, so
        # the indices behind the remaining handles go stale and those clicks are
        # silently dropped. Opening the two nodes this suite cares about is both
        # reliable and what a person actually does.
        page.locator('.file-tree-header:has-text("Project Library")').click()
        page.wait_for_timeout(500)
        package = page.locator(f'.file-tree-package:has-text("{PKG}")')
        rec("the fixture package is in the tree", package.count() == 1,
            f"found {package.count()}")

        marks = page.locator(".git-mark")
        rec("marks are rendered in the tree", marks.count() > 0,
            f"found {marks.count()}")
        # The package holds an ADDED script and a DELETED one. A collapsed
        # folder shows the WORST of what is inside it, so this is a `D`: a
        # package that reported the milder of two states would let a deletion
        # hide behind an addition.
        rec("a COLLAPSED package carries the WORST mark of what is inside it",
            package.locator(".git-mark-deleted").count() == 1
            and package.locator(".git-mark-added").count() == 0,
            "collapsed package did not show the worse of its two marks")

        package.click()
        page.wait_for_timeout(500)
        rec("the new script's own row carries an 'A' once the package is open",
            page.locator(".file-tree-item:has-text('v32_added') .git-mark-added").count() == 1,
            "no added badge on v32_added")

        # The deleted resource has no row of its own, so its mark had to travel
        # up. Asserted after the package is OPEN, which is the case the roll-up
        # is really for: the parent keeps the mark even when the children are
        # all visible and none of them is the one that went.
        rec("the deleted script's mark stays on the open package",
            package.locator(".git-mark-deleted").count() == 1,
            "the deleted badge vanished once the package was expanded")

        # ---------- an unreadable repository ----------
        # The failure the whole feature is shaped around: this must never render
        # the same as a clean tree.
        sh(f"cp {PROJECTS}/{PROJECT}/.git/HEAD /tmp/v32-head", root=True)
        sh(f"sh -c 'echo not-a-ref > {PROJECTS}/{PROJECT}/.git/HEAD'", root=True)
        broken = status(page)
        rec("an unreadable HEAD is an error, not a clean tree",
            bool(broken.get("error")), json.dumps(broken)[:300])
        rec("...and does NOT mark every resource as newly added",
            broken.get("marks") == {}, json.dumps(broken.get("marks"))[:300])
        sh(f"cp /tmp/v32-head {PROJECTS}/{PROJECT}/.git/HEAD", root=True)
        sh(f"chown ignition:ignition {PROJECTS}/{PROJECT}/.git/HEAD", root=True)

    finally:
        # Put the project back: remove the fixtures, then the repository itself.
        try:
            remove(page, csrf, NEW_SCRIPT)
            remove(page, csrf, TRACKED_SCRIPT)
            remove(page, csrf, f"ignition/script-python/{PKG}")
        except Exception as e:
            print(f"  [warn] fixture cleanup: {e}")
        remove_repo()
        left = sh(f"test -d {PROJECTS}/{PROJECT}/.git && echo LEFT || echo GONE")
        rec("the fixture repository was removed", "GONE" in left.stdout, left.stdout.strip())
        if scratch:
            subprocess.run(["rm", "-rf", scratch], check=False)
        browser.close()

print(f"validate_v32_git   {PASSED}/{PASSED + FAILED} checks passed")
sys.exit(1 if FAILED else 0)
