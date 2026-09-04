"""
The overview ruler — 1.8.6.

Nigel, 03/09/2026: *"in the designer on the right hand side between the outline
and the code editor is a narrow rectangle, if there is an error a mark appears
in the right hand side in line with the line or lines that have a problem. This
mark can then be hovered over and it shows up what that error is. Ideally i
would like to take this one step further and if i click on it I can copy the
error text."*

And the report that led to it: *"i wrote a clearly broken line of code to try
and get it to give me an error notice but it said no problems in the open
script."* The diagnostics worked — this suite types the same kind of line and
checks what a person can actually SEE without going looking.

Run:
    WD_ALLOW_LOCAL_CONFIG=1 .venv-test/bin/python3 scripts/testing/validate_v19_ruler.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gateway_session import CONFIG, GATEWAY_URL, login          # noqa: E402
from playwright.sync_api import sync_playwright                 # noqa: E402

SPA = CONFIG.get("spa_path", "/data/scriptide/")
res = []


def rec(name, ok, detail=""):
    res.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def clipboard_text(page):
    """Read the clipboard by PASTING into a scratch field.

    `navigator.clipboard.readText` is as unavailable over HTTP as writeText is —
    the whole reason the product needed an execCommand fallback — so a suite
    that verified the copy with it was testing the same missing API from the
    other side. A real paste is also closer to what the user does with it.
    """
    page.evaluate("""() => {
      let el = document.getElementById('si-clip-probe');
      if (!el) {
        el = document.createElement('textarea');
        el.id = 'si-clip-probe';
        el.style.position = 'fixed';
        el.style.bottom = '0';
        el.style.opacity = '0';
        document.body.appendChild(el);
      }
      el.value = '';
      el.focus();
    }""")
    page.keyboard.press("Control+V")
    page.wait_for_timeout(250)
    return page.evaluate(
        "() => document.getElementById('si-clip-probe')?.value ?? ''")


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


with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    # The copy button writes to the clipboard, which headless Chromium refuses
    # without the permission — and refuses SILENTLY, which is exactly the kind of
    # thing this suite exists to notice.
    context.grant_permissions(["clipboard-read", "clipboard-write"])
    page = context.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))

    login(page)
    page.goto(GATEWAY_URL + SPA, wait_until="load", timeout=30000)
    page.wait_for_selector(".file-tree-header", timeout=20000)
    expand_tree(page)
    page.locator(".file-tree-item").first.click()
    page.wait_for_timeout(2500)

    # ---------- a clean script has a ruler and no marks ----------
    ruler = page.locator(".problem-ruler")
    rec("RULER: present beside the editor", ruler.count() == 1, f"{ruler.count()} ruler(s)")
    rec("RULER: no marks on a script with no problems",
        page.locator(".problem-ruler-mark").count() == 0,
        f"{page.locator('.problem-ruler-mark').count()} mark(s)")
    box = ruler.first.bounding_box() or {}
    editor = page.locator(".code-editor").first.bounding_box() or {}
    rec("RULER: sits at the right edge of the editor, full height",
        bool(box) and bool(editor)
        and abs((box["x"] + box["width"]) - (editor["x"] + editor["width"])) < 2
        and abs(box["height"] - editor["height"]) < 2,
        f"ruler right={box.get('x', 0) + box.get('width', 0):.0f} "
        f"editor right={editor.get('x', 0) + editor.get('width', 0):.0f}; "
        f"heights {box.get('height', 0):.0f}/{editor.get('height', 0):.0f}")

    # ---------- a broken line, far down, gets a mark ----------
    page.locator(".code-editor .cm-content").click()
    page.keyboard.press("Control+End")
    page.keyboard.type("\n\n\n\n\n\n\n\n\n\nthis is = = not python(\n")
    page.wait_for_timeout(3000)

    marks = page.locator(".problem-ruler-mark")
    rec("MARK: one mark for one broken line", marks.count() == 1, f"{marks.count()} mark(s)")
    if marks.count() == 0:
        browser.close()
        print("\nNo mark — nothing further to check.")
        sys.exit(1)
    mark = marks.first
    rec("MARK: it is an error, not a hint",
        "is-error" in (mark.get_attribute("class") or ""), mark.get_attribute("class"))

    # THE check, and the one Nigel's complaint was about: the mark must be level
    # with the line it describes, not merely somewhere on the ruler.
    #
    # 1.8.7 spread the line count evenly over the ruler's height, which is only
    # right when the document fills the pane. A 28-line script fills about two
    # thirds of an 819px editor, so the last line's mark was drawn at the bottom
    # while its code sat at 62% — "it seems to just appear randomly". Measured
    # against the real DOM position of the line, not against a formula.
    mark_box = mark.bounding_box() or {}
    line_box = page.evaluate("""() => {
      for (const el of document.querySelectorAll('.code-editor .cm-line')) {
        if (el.textContent && el.textContent.includes('not python')) {
          const r = el.getBoundingClientRect();
          return {y: r.y, height: r.height};
        }
      }
      return null;
    }""")
    if mark_box and line_box:
        mark_mid = mark_box["y"] + mark_box["height"] / 2
        line_mid = line_box["y"] + line_box["height"] / 2
        drift = abs(mark_mid - line_mid)
    else:
        drift = 9999
    # Half a line height: close enough that the eye reads them as level.
    rec("MARK: sits level with the line it describes",
        drift <= max(10, (line_box or {}).get("height", 0) / 2 + 4),
        f"mark centre {mark_mid:.0f}px vs line centre {line_mid:.0f}px, drift {drift:.0f}px"
        if mark_box and line_box else "could not measure")

    # ---------- hover shows the message ----------
    card = page.locator(".problem-ruler-card").first
    rec("HOVER: the card is hidden until hovered", not card.is_visible(),
        f"visible={card.is_visible()}")
    mark.hover()
    page.wait_for_timeout(300)
    rec("HOVER: the card appears with the parser's message",
        card.is_visible() and "no viable alternative" in card.inner_text(),
        repr(card.inner_text()[:80]) if card.is_visible() else "not visible")

    # ---------- the card's copy button puts the message on the clipboard ----------
    copy = card.locator(".problem-ruler-copy")
    copy.hover()
    copy.click()
    page.wait_for_timeout(300)
    clip = clipboard_text(page)
    rec("COPY: the message is on the clipboard", "no viable alternative" in clip, repr(clip[:80]))
    rec("COPY: the button says so", "Copied" in copy.inner_text(), copy.inner_text())

    # ---------- click reveals it in the Problems panel ----------
    page.mouse.move(400, 400)          # leave the card so the click is on the mark
    page.wait_for_timeout(200)
    mark.click()
    page.wait_for_timeout(1200)
    panel_rows = page.locator(".problems-row")
    rec("CLICK: the Problems panel opens on the problem",
        page.locator('.panel-tab:has-text("Problems")').count() == 1 and panel_rows.count() == 1,
        f"{panel_rows.count()} problem row(s)")
    line_no = page.evaluate(
        "() => { const v = document.querySelector('.cm-editor')?.querySelector('.cm-activeLine');"
        " return v ? v.textContent : null; }")
    rec("CLICK: the caret is on the broken line",
        bool(line_no) and "not python" in line_no, repr(line_no))

    # ---------- the Problems row has its own copy ----------
    if panel_rows.count():
        panel_rows.first.hover()
        page.wait_for_timeout(200)
        pcopy = page.locator(".problems-copy").first
        pcopy.click()
        page.wait_for_timeout(300)
        clip2 = clipboard_text(page)
        rec("PANEL: its copy carries file, line and message",
            "no viable alternative" in clip2 and ":" in clip2, repr(clip2[:80]))
    else:
        rec("PANEL: its copy carries file, line and message", False, "no row")

    # ---------- fixing the line removes the mark ----------
    # Delete the whole broken line. The earlier sequence left "this is = = not
    # python" behind — still broken — so the mark correctly stayed and the CHECK
    # was what was wrong.
    page.locator(".code-editor .cm-content").click()
    page.keyboard.press("Control+End")
    for _ in range(len("this is = = not python(") + 2):
        page.keyboard.press("Backspace")
    page.wait_for_timeout(3500)
    rec("FIX: the mark goes when the line does",
        page.locator(".problem-ruler-mark").count() == 0,
        f"{page.locator('.problem-ruler-mark').count()} mark(s) left")

    # Nothing was saved. The buffer was edited and the tab must still say so —
    # a suite that typed into a real project's script and left it clean would
    # mean something WROTE it.
    dirty = page.locator(".tab-dirty").count()
    rec("SAFETY: the edits are unsaved, so the gateway copy is untouched", dirty == 1,
        f"dirty marker={dirty}")

    rec("CONSOLE: no page errors from our own code", not errs, "; ".join(errs[:2]))
    browser.close()

print()
passed = sum(1 for _, ok, _ in res if ok)
print(f"{passed}/{len(res)} checks passed")
sys.exit(0 if passed == len(res) else 1)
