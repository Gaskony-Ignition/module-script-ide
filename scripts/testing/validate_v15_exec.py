"""Live checks for 1.5.0: the execution channel — stop, streaming, tracebacks, reset.

Run against the real gateway after deploy_gate.py passes. Every one of these six
is invisible below the UI and four of them were MEASURED as broken on 1.4.3:

  a. Stop actually stops. `handleExec` used to block the socket thread inside
     `execute()`, so a stop frame sent 1.5 s into a 20 s loop was not READ until
     the loop had finished. The button could not have worked.
  b. The socket keeps serving during a run. Same defect, other symptom: pings,
     LSP requests and terminal keystrokes all queued behind the script. Typing in
     the Terminal DURING a run is the cheapest proof, because terminal frames
     share the one socket — if they echo, nothing is blocked.
  c. Output is streamed. One `finished` frame used to carry the lot, so a
     twenty-second script showed nothing for twenty seconds.
  d. A traceback names its exception type and its functions. The client read
     field names the server does not send, so every frame read "<console>,
     line N" with no function and no type.
  e. A syntax error reads as a syntax error, not as a raw PyTuple carrying our
     internal `<script-ide:…>` token.
  f. Reset drops the console's locals, as the Designer's does.

Any project will do — nothing here writes a resource — so SI_EXEC_PROJECT
overrides, and the default is simply the first project the SPA offers.

    cd scripts/testing
    SI_GATEWAY_CONFIG=$PWD/config.local.json \
      PLAYWRIGHT_BROWSERS_PATH=$HOME/.cache/ms-playwright \
      /home/nigel/Ignition-Work/ignition-toolbox/backend/.venv/bin/python \
      validate_v15_exec.py
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gateway_session import CONFIG, GATEWAY_URL, login
from playwright.sync_api import sync_playwright

SPA = CONFIG.get("spa_path", "/data/scriptide/")
OUT = os.environ.get(
    "SI_SHOT_DIR",
    "/tmp/claude-1000/-home-nigel-Ignition-Work/662a0682-b950-4be1-b8b2-453d08f040fa/scratchpad")
PROJECT = os.environ.get("SI_EXEC_PROJECT")

# The 20 s loop in (a) has to be longer than the stop takes and shorter than the
# gateway's own execution timeout (60 s by default), or a PASS would prove only
# that the timeout fired.
BUSY_LOOP = "import time\nt=time.time()\nwhile time.time()-t<20: pass\n"

res = []


def rec(n, ok, d=""):
    res.append((n, ok, d))
    print(f"  [{'PASS' if ok else 'FAIL'}] {n}: {d}")
    return ok


def shot(page, name):
    try:
        page.screenshot(path=f"{OUT}/v15-{name}.png")
    except Exception as e:                                   # noqa: BLE001
        print(f"  (screenshot {name} failed: {e})")


def console_text(page):
    """Everything currently in the output pane."""
    return page.evaluate(
        "() => document.querySelector('.console-output')?.innerText ?? ''")


def set_source(page, text):
    """Replace the console buffer.

    `el.cmView` is not exposed, so there is no way to dispatch a transaction from
    outside — the buffer is set by selecting all and typing, exactly as a person
    would. insert_text pastes the whole string in one input event, which matters:
    typing it key by key would let CodeMirror's auto-indent add leading spaces
    after every colon and change the program.
    """
    page.locator(".console-editor .cm-content").click()
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")
    page.keyboard.insert_text(text)
    page.wait_for_timeout(250)


def toolbar(page, label):
    """One console toolbar button, by its exact label.

    Exact, because "Run" is a prefix of "Run selection" and "Run file" and a
    substring match would click whichever came first in the DOM.
    """
    return page.locator(".console-toolbar").get_by_role("button", name=label, exact=True)


def closed(tail):
    """Every run closes with exactly one of these three quiet lines."""
    return "— finished in" in tail or "— stopped —" in tail or "— failed —" in tail


def wait_idle(page, timeout=30):
    """Wait until no run is in flight.

    The header's `running…` marker is the honest signal — it is set the instant
    Run is clicked, before the server has answered, so there is no window where
    a run has begun and the page still looks idle.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.locator(".console-output-head .console-running").count() == 0:
            return True
        page.wait_for_timeout(150)
    return False


def run_and_wait(page, source, timeout_ms=25000):
    """Run `source` and wait for THIS run to close. Returns only its own output.

    Two rules, both learned from the first live run (02/09/2026), where every
    traceback check failed against the text `— finished in 2.6 s —` — which was
    the PREVIOUS run's closing line, 2.6 s being the streaming check's own
    duration:

      1. Snapshot the pane only once the console is IDLE. A run still in flight
         drops its closing line into what we are about to call our own tail.
      2. Wait for our own `▸ run N` divider as well as a closing line, so a tail
         can never be satisfied by anything that was already on its way.
    """
    wait_idle(page)
    before = len(console_text(page))
    set_source(page, source)
    toolbar(page, "Run").click()
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        tail = console_text(page)[before:]
        if "▸ run" in tail and closed(tail):
            return tail
        page.wait_for_timeout(200)
    return console_text(page)[before:]


def terminal_ready(page, timeout=25):
    """Wait for a shell PROMPT, not merely for the canvas to exist.

    The canvas appears as soon as the component mounts; the shell behind it is a
    Docker exec that has still to start. Typing into that gap loses the
    keystrokes silently, which on the first live run looked exactly like a
    blocked socket — 0 occurrences of a marker that had simply never been typed
    anywhere.
    """
    page.wait_for_selector(".xterm", timeout=timeout * 1000)
    deadline = time.time() + timeout
    while time.time() < deadline:
        rows = page.locator(".xterm-rows").inner_text()
        if "#" in rows or "$" in rows:
            return rows
        page.wait_for_timeout(250)
    return page.locator(".xterm-rows").inner_text()


def term_type(page, text):
    """Type into the terminal.

    A JS .focus(), not a click: xterm's helper textarea is positioned off-screen
    and Playwright refuses to click it as "not visible". Re-focused on every
    call, because switching panel tabs hides the terminal and takes the focus
    with it.
    """
    page.wait_for_selector(".xterm-helper-textarea", state="attached", timeout=10000)
    page.evaluate("() => document.querySelector('.xterm-helper-textarea').focus()")
    page.keyboard.type(text)


def term_wait_for(page, marker, timeout=12):
    """Poll the terminal for a marker. Returns (found, rows)."""
    deadline = time.time() + timeout
    rows = ""
    while time.time() < deadline:
        rows = page.locator(".xterm-rows").inner_text()
        if marker in rows:
            return True, rows
        page.wait_for_timeout(250)
    return False, rows


def panel(page, label):
    page.locator(f'button[aria-label="{label}"]').click()
    page.wait_for_timeout(600)


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
                shut.nth(index).click()
            except Exception:
                pass          # a click that re-renders the list is not a failure
        page.wait_for_timeout(120)


with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_context(viewport={"width": 1600, "height": 1000}).new_page()
    errs = []
    page.on("console", lambda m: errs.append(f"{m.text} @ {m.location.get('url','')}")
            if m.type == "error" and "/res/sys/" not in m.location.get("url", "")
            and "/data/app/session" not in m.location.get("url", "") else None)
    page.on("pageerror", lambda e: errs.append(str(e)))
    login(page)
    page.goto(GATEWAY_URL + SPA, wait_until="load", timeout=30000)
    page.wait_for_selector(".file-tree-header", timeout=20000)
    expand_tree(page)

    if PROJECT:
        page.select_option(".workspace-project select", PROJECT)
        page.wait_for_timeout(2000)
    chosen = page.evaluate(
        "() => document.querySelector('.workspace-project select')?.value ?? ''")
    rec("FIXTURE: a project is selected to run against", bool(chosen), chosen)

    # The terminal is opened FIRST, while nothing is running, so check (b) tests
    # the socket under load rather than testing whether a pty can be created.
    panel(page, "Terminal")
    terminal_ready(page)
    # A baseline echo while NOTHING is running. Without it, a silent terminal
    # during a run is ambiguous — a blocked socket and an unfocused textarea
    # look identical, and on the first live run it was the latter.
    #
    # The marker is typed as SOCK''ALIVE and comes back as SOCKALIVE, so a match
    # can only be the shell's OUTPUT: the echoed command line spells it
    # differently, and xterm does no local echo of its own.
    term_type(page, "echo SOCK''ALIVE-IDLE\n")
    idle_echo, rows = term_wait_for(page, "SOCKALIVE-IDLE")
    rec("FIXTURE: the terminal echoes when nothing is running", idle_echo,
        rows.strip()[-60:].replace("\n", " | "))
    if not idle_echo:
        shot(page, "terminal-dead")
    panel(page, "Script Console")
    page.wait_for_selector(".console-editor .cm-content", timeout=20000)
    rec("FIXTURE: the console and the terminal are both open",
        page.locator(".console-toolbar").count() == 1, "")

    # ---------- (a) + (b) Stop works, and the socket stays awake ----------
    wait_idle(page)
    set_source(page, BUSY_LOOP)
    busy_from = len(console_text(page))
    toolbar(page, "Run").click()
    run_began = time.time()
    page.wait_for_timeout(2000)

    # (b) The terminal shares the ONE socket. If a frame gets through and echoes
    # while the script is still spinning, nothing is blocked. On 1.4.3 the
    # keystrokes sat in the queue until the loop ended.
    panel(page, "Terminal")
    term_type(page, "echo SOCK''ALIVE-BUSY\n")
    alive, rows = term_wait_for(page, "SOCKALIVE-BUSY")
    rec("SOCKET: the terminal still answers while a script is running", alive,
        f"round trip {'completed' if alive else 'NEVER arrived'} "
        f"{time.time() - run_began:.1f}s into a 20s loop")
    if not alive:
        shot(page, "socket-blocked")

    # (a) Stop, and time it. The Jython interrupt fires at the next trace point,
    # which for a busy loop is within about three seconds.
    panel(page, "Script Console")
    stop = toolbar(page, "Stop")
    rec("STOP: the Stop button is live while a script runs", stop.is_enabled(), "")
    stop.click()
    stop_sent = time.time()
    stopped = False
    while time.time() - stop_sent < 8:
        if "— stopped —" in console_text(page)[busy_from:]:
            stopped = True
            break
        page.wait_for_timeout(200)
    took = time.time() - stop_sent
    total = time.time() - run_began
    rec("STOP: the script stops within 5s of the button, well short of its 20s",
        stopped and took < 5 and total < 20,
        f"stopped after {took:.1f}s; the loop had run {total:.1f}s of 20s")
    shot(page, "stopped")

    # ---------- (c) output arrives while the run is still going ----------
    # Single-line bodies on purpose: a pasted block is inserted verbatim, but
    # keeping the program free of indentation removes the whole question.
    wait_idle(page)
    set_source(page, "import time\nfor i in range(5): print i; time.sleep(0.5)\n")
    toolbar(page, "Run").click()
    saw_partial = False
    deadline = time.time() + 15
    while time.time() < deadline:
        block = page.evaluate(
            "() => [...document.querySelectorAll('.console-output .console-stdout')]"
            ".pop()?.innerText ?? ''")
        # THE assertion: at some moment the first line is on screen and the last
        # is not. With one `finished` frame carrying everything, that moment
        # cannot exist — 0 and 4 arrive together or not at all.
        if "0" in block and "4" not in block:
            saw_partial = True
        if "4" in block:
            break
        page.wait_for_timeout(200)
    final = page.evaluate(
        "() => [...document.querySelectorAll('.console-output .console-stdout')]"
        ".pop()?.innerText ?? ''")
    rec("STREAM: the first line appears before the last",
        saw_partial and "4" in final,
        f"partial seen={saw_partial}; final block={final.strip()[:40]!r}")
    if not saw_partial:
        shot(page, "not-streamed")
    # The loop above breaks on the last line, which is BEFORE the run closes.
    # Leaving it in flight is what poisoned every traceback check on the first
    # live run.
    wait_idle(page)

    # ---------- (d) a traceback reads like a traceback ----------
    text = run_and_wait(page, "def f(): return 1/0\nf()\n")
    rec("TRACEBACK: the exception type is the headline",
        "ZeroDivisionError" in text, text.strip().splitlines()[-4:][0][:70] if text else "")
    rec("TRACEBACK: the failing function is named",
        "in f" in text, text.strip().replace("\n", " | ")[:90])
    rec("TRACEBACK: the submitted source is called <console>",
        '<console>' in text, "")
    rec("TRACEBACK: frames are clickable where they resolve",
        page.locator(".console-frame-link").count() >= 1,
        f"{page.locator('.console-frame-link').count()} link(s)")
    shot(page, "traceback")

    # ---------- (e) a syntax error, without the internal token ----------
    text = run_and_wait(page, "if True\n  pass\n")
    rec("SYNTAX: it says SyntaxError", "SyntaxError" in text,
        text.strip().replace("\n", " | ")[:90])
    rec("SYNTAX: it names the line", "line 1" in text or "(line 1)" in text,
        [l for l in text.splitlines() if "Syntax" in l][:1])
    # The token is ours. It meant nothing to Nigel and it must never be shown.
    rec("SYNTAX: the internal <script-ide:…> token does not leak",
        "script-ide" not in text, "")
    rec("SYNTAX: no raw PyTuple", "', ('" not in text and not text.count("(\"mismatched"), "")
    shot(page, "syntax-error")

    # ---------- (f) Reset drops the locals ----------
    text = run_and_wait(page, "y = 42\nprint y\n")
    rec("REPL: locals survive a run", "42" in text,
        text.strip().replace("\n", " | ")[:90])

    wait_idle(page)
    reset_from = len(console_text(page))
    toolbar(page, "Reset").click()
    got_reset = False
    deadline = time.time() + 6
    while time.time() < deadline:
        if "— reset —" in console_text(page)[reset_from:]:
            got_reset = True
            break
        page.wait_for_timeout(200)
    rec("RESET: the gateway acknowledges the reset", got_reset, "")

    fresh = run_and_wait(page, "print y\n")
    rec("RESET: the binding is gone afterwards",
        "NameError" in fresh, fresh.strip().replace("\n", " ")[:80])
    shot(page, "reset")

    # ---------- (g) a function sees the script's own module-level names ----------
    # Regression guard for 1.6.1: `PrivateStateRunner` used to call
    # `Py.runCode(code, locals, scriptManager.getGlobals())` — locals and globals
    # were two different dicts, so `x = 41` landed in locals while `f`'s closure
    # read an empty globals, and EVERY script with a function or class raised
    # `NameError: global name 'x' is not defined`. Every check above this one is a
    # bare one-liner, so none of them could have caught it — that is the actual
    # lesson, not just the bug. Fixed by running `Py.runCode(code, locals, locals)`.
    namespace_text = run_and_wait(page, "x = 41\ndef f():\n\treturn x + 1\nprint f()\n")
    rec("NAMESPACE: a function sees the script's own names",
        "42" in namespace_text, namespace_text.strip().replace("\n", " | ")[:90])

    rec("CONSOLE: no page errors from our own code", not errs, "; ".join(errs[:3]))
    b.close()

passed = sum(1 for _, ok, _ in res if ok)
print(f"\n{passed}/{len(res)} checks passed")
sys.exit(0 if passed == len(res) else 1)
