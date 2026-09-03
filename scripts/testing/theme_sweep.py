"""Measure contrast on the REAL painted elements, per theme, in the browser."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gateway_session import CONFIG, GATEWAY_URL, login
from playwright.sync_api import sync_playwright
SPA = CONFIG.get("spa_path", "/data/scriptide/")
OUT = os.environ.get("SI_SHOT_DIR", "/tmp")

MEASURE = """() => {
  const lum = (c) => {
    const [r,g,b] = c;
    const f = (v) => { v/=255; return v<=0.04045 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); };
    return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b);
  };
  const parse = (s) => { const m = s.match(/rgba?\\(([^)]+)\\)/); if(!m) return null;
    const p = m[1].split(',').map(Number); return p.length>=3 ? p.slice(0,3) : null; };
  const bgOf = (el) => {
    let n = el;
    while (n && n !== document.documentElement) {
      const c = getComputedStyle(n).backgroundColor;
      const p = parse(c);
      if (p && !/rgba\\(.*,\\s*0\\)/.test(c)) return p;
      n = n.parentElement;
    }
    return parse(getComputedStyle(document.body).backgroundColor) || [255,255,255];
  };
  const ratio = (a,b) => { const la=lum(a), lb=lum(b);
    return (Math.max(la,lb)+0.05)/(Math.min(la,lb)+0.05); };
  const out = [];
  const sel = '.file-tree-item, .file-tree-header, .file-tree-package, .panel-tab, ' +
    '.tab-strip button, .config-label, .workspace-toolbar button, .rail-title, ' +
    '.outline-item, .console-output, .muted, .badge, .status-footer, .app-version';
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) continue;
    const text = (el.textContent || '').trim();
    if (!text) continue;
    const fg = parse(getComputedStyle(el).color);
    if (!fg) continue;
    out.push({ text: text.slice(0,28), cls: el.className.toString().slice(0,40),
               ratio: Math.round(ratio(fg, bgOf(el))*100)/100 });
  }
  return out;
}"""

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
    page = b.new_context(viewport={"width":1600,"height":1000}).new_page()
    login(page)
    page.goto(GATEWAY_URL + SPA, wait_until="load", timeout=30000)
    page.wait_for_selector(".file-tree-header", timeout=20000)
    expand_tree(page)
    page.locator(".file-tree-item").first.click()
    page.wait_for_timeout(2500)
    page.locator('button[aria-label="Toggle panel"]').click()
    page.wait_for_timeout(600)
    ids = page.locator('select[aria-label="Theme"] option').evaluate_all("e=>e.map(x=>x.value)")
    worst_overall = []
    for tid in ids:
        page.select_option('select[aria-label="Theme"]', tid)
        page.wait_for_timeout(450)
        rows = page.evaluate(MEASURE)
        bad = [r for r in rows if r["ratio"] < 4.5]
        worst = min((r["ratio"] for r in rows), default=99)
        print(f"{tid:26} elements={len(rows):3}  worst={worst:5.2f}  below-4.5={len(bad)}")
        for r in sorted(bad, key=lambda x: x["ratio"])[:4]:
            print(f"      {r['ratio']:5.2f}  {r['cls'][:34]:34} {r['text']!r}")
        if bad:
            worst_overall.append(tid)
        page.screenshot(path=f"{OUT}/theme-{tid}.png")
    b.close()
print()
print("THEMES WITH ILLEGIBLE TEXT:", worst_overall or "none")
sys.exit(1 if worst_overall else 0)
