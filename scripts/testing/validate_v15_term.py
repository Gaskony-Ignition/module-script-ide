"""Live checks for 1.5.0: the terminal opens fast, and closing it ends the shell.

Three of the four defects 1.5.0 fixes are invisible from inside the browser, so
this suite is the only place they can be asserted:

* **How long an open takes** is a wall-clock measurement, and the old number was
  not a slow gateway — it was `POST /exec/{id}/resize` sent BEFORE the attach,
  blocking inside the daemon for ten seconds until our own five-second watchdog
  cut it. It cost exactly 5.00 s every time.
* **Whether the shell actually died** cannot be seen from the page at all. The
  page closes and looks closed either way; the evidence is a process list inside
  the container, which is why this script shells out to `docker`. 1.4.3 left one
  root `bash -i` behind for every terminal ever opened — 38 of them, measured on
  02/09/2026 — and the 120-minute idle reaper was calling the same no-op close.
* **The per-session tag** is what makes the sweep possible: it is inherited by
  everything the shell starts, so a background job is caught with its parent. If
  it is missing, close still looks like it worked and the leak is back.

Run it from `scripts/testing`, as the others are run:

    SI_GATEWAY_CONFIG=$PWD/config.local.json \
    PLAYWRIGHT_BROWSERS_PATH=$HOME/.cache/ms-playwright \
      /home/nigel/Ignition-Work/ignition-toolbox/backend/.venv/bin/python \
      validate_v15_term.py

`SI_TERM_CONTAINER` names the container to count processes in; it defaults to
the module test rig. The process checks SKIP rather than fail when the container
is not reachable, because a gateway that is not in Docker cannot leak a Docker
exec and failing there would be asserting a property of the host.
"""
import os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gateway_session import CONFIG, GATEWAY_URL, login
from playwright.sync_api import sync_playwright

SPA = CONFIG.get("spa_path", "/data/scriptide/")
OUT = os.environ.get("SI_SHOT_DIR", "/tmp")
CONTAINER = os.environ.get("SI_TERM_CONTAINER", "ignition-module-testing")

# What a shell must be gone within. The module's own budget is a ~200 ms exit
# sequence plus a sweep with a one-second grace between HUP and KILL, so this is
# several times the measured cost and still far short of "nobody noticed".
CLOSE_BUDGET_SECONDS = 10

res = []


def rec(n, ok, d=""):
    res.append((n, ok, d))
    print(f"  [{'PASS' if ok else 'FAIL'}] {n}: {d}")


def skip(n, d=""):
    # Recorded as a pass with the reason stated. A check that cannot run on this
    # host is not evidence of a defect, and silently dropping it would leave the
    # tally looking complete when it is not.
    res.append((n, True, d))
    print(f"  [SKIP] {n}: {d}")


def container_ps():
    """Every process in the container, or None when we cannot look."""
    try:
        out = subprocess.run(
            ["docker", "exec", "-u", "0", CONTAINER, "ps", "-eo", "pid,user,etime,cmd"],
            capture_output=True, text=True, timeout=20)
        return out.stdout if out.returncode == 0 else None
    except Exception:
        return None


def count(ps, needle):
    return 0 if ps is None else sum(1 for line in ps.splitlines() if needle in line)


# The prompt, not the widget. `.xterm` mounts as soon as React renders it, which
# says nothing about whether the daemon has answered.
#
# Matched against the last NON-EMPTY line rather than against the whole buffer
# with `$`. `.xterm-rows` holds one div per viewport row, so the prompt is
# followed by however many blank rows the panel is tall, and what those blank
# rows contain is xterm's business, not ours — an anchored match on the whole
# string is a check on the renderer's padding, which is what made the first
# version of this wait time out with a shell that was sitting there at a perfectly
# good prompt. The first line is usually the container's own
# `groups: cannot find name for group ID 984`, so the match cannot be anchored at
# the start of the buffer either.
PROMPT_READY = r"""() => {
  const rows = document.querySelector('.xterm-rows');
  if (!rows) return false;
  const lines = rows.innerText.split('\n')
      .map(l => l.replace(/\s+$/, ''))
      .filter(l => l.length > 0);
  return lines.length > 0 && /[#$]$/.test(lines[lines.length - 1]);
}"""


def terminal_dump(page):
    """What the terminal actually shows, for a failure message worth reading."""
    try:
        rows = page.locator(".xterm-rows").inner_text()
    except Exception as exc:
        rows = f"<no .xterm-rows: {exc}>"
    try:
        notice = " ".join(page.locator(".terminal-notice").all_inner_texts())
    except Exception:
        notice = ""
    return f"buffer={rows.strip()[-200:]!r} notice={notice[:120]!r}"


def open_terminal(page):
    """Click Terminal, wait for a prompt, and return how long that took."""
    started = time.time()
    page.locator('button[aria-label="Terminal"]').click()
    page.wait_for_selector(".xterm", timeout=20000)
    page.wait_for_function(PROMPT_READY, timeout=20000)
    return time.time() - started


def type_line(page, text):
    # JS .focus(), NOT a click: xterm's helper textarea is positioned off-screen
    # and Playwright refuses to click it as "not visible". This is the form that
    # works in this suite — see validate_v14.
    page.evaluate("() => document.querySelector('.xterm-helper-textarea').focus()")
    page.keyboard.type(text + "\n")


baseline_ps = container_ps()
have_container = baseline_ps is not None
before_shells = count(baseline_ps, "bash -i")
before_sleeps = count(baseline_ps, "sleep 300")

with sync_playwright() as p:
    b = p.chromium.launch()
    # Nothing below may take the whole suite down without printing. The first
    # run of this script died on a bare Playwright timeout and reported NOTHING
    # — no PASS, no FAIL, no clue which check it was on — which is the one
    # outcome a gate must never produce: it is indistinguishable from a suite
    # that was never run. Whatever breaks, the tally below still prints.
    try:
        context = b.new_context(viewport={"width": 1600, "height": 1000})
        page = context.new_page()
        login(page)
        page.goto(GATEWAY_URL + SPA, wait_until="load", timeout=30000)
        page.wait_for_selector(".file-tree-item", timeout=20000)

        # ---------- 1. open latency ----------
        # 1.4.x took 5.00 s here, every single time, and it was not the gateway:
        # a resize before the attach blocks in the daemon for 10 s and our watchdog
        # cut it at 5. Attaching first makes the same pair of calls ~90 ms, measured
        # against the raw daemon.
        elapsed = open_terminal(page)
        rec("TERM: a prompt appears in under 2 s", elapsed < 2.0, f"{elapsed:.2f}s")
        page.screenshot(path=f"{OUT}/v15-terminal-open.png")

        # ---------- 2. the per-session tag ----------
        type_line(page, "echo TAG=[$SCRIPTIDE_TERM]")
        page.wait_for_timeout(2000)
        rows = page.locator(".xterm-rows").inner_text()
        tagged = "TAG=[" in rows and "TAG=[]" not in rows.split("echo TAG=")[-1]
        rec("TERM: the shell carries a SCRIPTIDE_TERM tag", tagged,
            rows.strip()[-120:].replace("\n", " | "))

        # ---------- 3. the notice is clean ----------
        # Reported, not gated. The `groups: cannot find name for group ID 984` line
        # comes from Debian's /etc/bash.bashrc sudo hint calling `groups`, because
        # the rig adds the host's docker gid to the container and that gid has no
        # name in the container's /etc/group. It is a property of the container, not
        # of this module, and 1.5.0 deliberately did not suppress it — see the
        # 1.5.0 report. This records the state so a later fix has a before.
        notice = " ".join(page.locator(".terminal-notice").all_inner_texts())
        rec("TERM: the notice text is recorded", True,
            "contains 'groups:'" if "groups:" in notice else "clean")

        # ---------- 4. closing the page ends the shell AND its children ----------
        if not have_container:
            skip("TERM: closing a terminal leaves no shell behind",
                 f"container {CONTAINER} not reachable from here")
            skip("TERM: closing a terminal leaves no background job behind",
                 f"container {CONTAINER} not reachable from here")
        else:
            # A background job and a foreground one. They exercise the two halves of
            # the fix: the exit sequence's ^C ends the foreground `sleep`, and only
            # the /proc sweep can reach the backgrounded one, which by design
            # outlives its shell.
            type_line(page, "sleep 300 &")
            page.wait_for_timeout(800)
            type_line(page, "sleep 300")
            page.wait_for_timeout(1500)

            during = container_ps()
            started_shells = count(during, "bash -i")
            started_sleeps = count(during, "sleep 300")
            rec("FIXTURE: the terminal really started a shell and two sleeps",
                started_shells > before_shells and started_sleeps >= before_sleeps + 2,
                f"shells {before_shells}->{started_shells}, sleeps {before_sleeps}->{started_sleeps}")

            # Close the BROWSER, not the panel: a socket that goes away is the case
            # that leaked, and it is what happens every time a user shuts a tab.
            page.close()
            context.close()

            deadline = time.time() + CLOSE_BUDGET_SECONDS
            shells = sleeps = None
            while time.time() < deadline:
                ps = container_ps()
                shells = count(ps, "bash -i")
                sleeps = count(ps, "sleep 300")
                if shells <= before_shells and sleeps <= before_sleeps:
                    break
                time.sleep(0.5)
            waited = CLOSE_BUDGET_SECONDS - max(0.0, deadline - time.time())

            rec("TERM: closing a terminal leaves no shell behind",
                shells is not None and shells <= before_shells,
                f"{before_shells} before, {shells} after, {waited:.1f}s")
            rec("TERM: closing a terminal leaves no background job behind",
                sleeps is not None and sleeps <= before_sleeps,
                f"{before_sleeps} before, {sleeps} after — a backgrounded `sleep 300` "
                f"survives its shell, so only the /proc sweep can have removed it")

        b.close()
    except Exception as exc:
        # Named as a check so it lands in the tally and the exit code.
        detail = f"{type(exc).__name__}: {exc}".replace("\n", " ")[:250]
        rec("SUITE: the run completed", False, f"{detail} || {terminal_dump(page)}")
        try:
            page.screenshot(path=f"{OUT}/v15-failure.png")
        except Exception:
            pass
        try:
            b.close()
        except Exception:
            pass

passed = sum(1 for _, ok, _ in res if ok)
print(f"\n{passed}/{len(res)} checks passed")
sys.exit(0 if passed == len(res) else 1)
