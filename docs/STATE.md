# State

**Read this first each session.** Single source of truth for where the module is.

**Version 1.4.1 · all phases complete · deployed, gate-green and live-validated on
`ignition-module-testing` (8.3.8) · 01/09/2026**

1.1.0–1.4.1 are post-1.0 feature work driven by Nigel's review, not new phases.
1.3.0 added a **Gateway terminal**, moved the console into a **bottom panel**, and
brought **Gateway Events** into line with the real Designer. 1.4.0 makes
**inherited scripts read-only until overridden**, names and explains **Script Hint
Scope**, and makes the terminal a **root shell** where the host allows it.

### 1.4.0, and how the Designer was measured

The Designer was DRIVEN, not recalled — `designer-drive` against
`Site_Redgum_Sewer > Template` on this gateway, 01/09/2026. What it showed:

| Action on an inherited Project Library script | The Designer |
| --- | --- |
| Double-click | **Nothing.** No editor opens |
| Right-click | Exactly `Override Resource` · `Copy Path` · `Open read-only` |
| `Open read-only` | Header `Chart  (Read-Only)`; caret places, text selects, **typing is discarded** |
| `Override Resource` | No dialog. Row goes bold+italic; double-click now opens it, header has no suffix |
| Right-click, overridden | The full local menu, with **no Delete** — `Discard Overrides` in its place |
| `Discard Overrides` | "…discard this resource and return to its inherited state? All local changes will be lost." |

Two things that change how this is built:

- **Overriding writes nothing.** After `Override Resource` the gateway's own
  `data/projects/Site_Redgum_Sewer/ignition/script-python/` still held no copy.
  The italic row is this Designer's mark for *unsaved*. So our override is a tab
  flag, and the resource appears through the existing save path.
- **Inheritance is not lost by overriding.** `Discard Overrides` returns to the
  parent's copy. Calling that button "Delete" — which this module did — describes
  a consequence that does not happen.

One deliberate deviation: an already-open read-only tab in the Designer does NOT
become editable when you override the resource, and we do not copy that. It reads
as an oversight rather than a decision, and the whole point of the bar is that the
remedy is one click from where you are.

`Script Hint Scope` is the Designer's own control, on Project Library scripts
only, top-right of the editor header. Its option order is **None · Designer ·
Gateway · All** — measured, and NOT the bitmask order this module used.

**1.4.1 put it where the Designer puts it and took the words away.** 1.4.0
renamed and explained it, and the explanation was a paragraph on the strip —
which made the rarest control in the module the loudest thing on the row (Nigel:
"I had never even noticed it was there and never needed to use it"). It is now
small, last on the strip, hard against the right edge, and silent. What the
paragraph said is kept in the `TRAILING_FIELDS` comment, where it costs a reader
nothing. The rule generalises: matching a Designer control means matching how
much room it takes up, not only what it is called.

## Where we are

| Phase | Status |
| --- | --- |
| Spike S1 — execution, parsing, hints | **Done.** 5 of 6 answered without a module; the sixth closed by P0 |
| P0 — skeleton, shell, auth, socket | **Done** |
| P1 — read/write script resources, byte-perfect | **Done.** Byte-identical on disk, verified with `cat -A` |
| P2 — execution | **Done.** 0 cross-user output leakage under concurrency |
| P3 — completions, signature help, hover | **Done.** Sourced from the running gateway |
| P4 — project navigation | **Done.** Definition, outline, symbol search |
| P5 — diagnostics | **Done.** Real Jython parser; valid Python 2 never flagged |
| P6 — cross-file search, polish | **Done** |
| P7 — hardening, docs, 1.0.0 | **Done.** Security review clean |

## What is proved on a real gateway

Six suites plus a per-theme contrast sweep, all green, all run against the
live gateway rather than mocks.

**`deploy_gate.py` — 6 checks.** Served bundle hash matches the build; Config ▸
Modules shows the built version ACTIVE; a real cookie session gets `authenticated:true` with a
CSRF token; every GET route parsed from the registrar at run time answers as
mounted; an authenticated WebSocket completes a ping/pong; and `print 1+1` over the
exec channel returns `2`, proving auth + socket + CSRF + pool + Jython + capture in
one assertion.

**`validate_p1_p2.py` — 8 checks.**
- **Byte fidelity.** A script saved through the IDE is byte-identical on the
  gateway's own filesystem, verified with `cat -A`: tabs are `^I`, and the file ends
  with **no** terminating newline, exactly as the Designer writes it.
- **No cross-user leakage.** Two concurrent executions, 500 tagged lines each:
  **500/500 own lines, 0 cross-talk both ways.** Spike S1 measured the original
  design leaking 22–25 lines each way, so this is the fix holding under the test
  that broke it.
- A saved script becomes importable with no project scan and no restart.
- Tracebacks carry frames with correct line numbers.

**`validate_lsp.py` — 10 checks.** Completions for `system.tag.` come back from the
running gateway with real signatures (`readBlocking(tagPaths, [timeout])`);
signature help resolves inside a call; the outline survives a half-typed line;
workspace symbol search and cross-file text search both find project symbols; valid
Python 2 produces **zero** diagnostics; a real syntax error is flagged on the right
line.

**`validate_v11.py` — 12 checks.** Create and delete round-trip through the tree;
delete without `If-Match` is 428 and with a stale one is 409; `enabled` round-trips
on Shutdown and Update; a cron expression round-trips and a malformed one is a 400.

**`validate_v14.py` — 19 checks, all in a real browser.** An inherited script
opens with a bar naming the project it came from; **typing into it changes
nothing** (2593 characters before, 2593 after — the same assertion that was made
against the real Designer); Save is disabled and Ctrl+S does not fork the parent;
the Override action unlocks that buffer and nothing else; `Script Hint Scope`
carries the Designer's name and option order, is the last thing on the strip and
sits against its right edge; and the terminal reports `uid=0 root` with `git version 2.43.0` on the
command line.

**`validate_v13.py` — 25 checks, all in a real browser.** Gateway Events in the
Designer's order with the three singletons as rows rather than folders; the three
layout toggles; the panel opening below the editor rather than beside it; a
console run inside the panel; a terminal that shows a prompt, runs a command,
starts in the data directory and reports a real window size; maximise hiding the
editor and restore bringing it back; the UI font not resolving to a serif and the
editor font resolving to a monospace; ten themes with no two sharing a palette;
and no failed request or console error attributable to this module.

A sixth script, `theme_sweep_v13.py`, measures contrast on the **painted**
elements per theme — foreground against the background actually behind it, walked
up the tree — because the 1.2.0 generator's own check measured the wrong pair and
certified five illegible themes. Worst element across all ten: 5.08:1.

Also verified by driving the real browser: the editor mounts with syntax
highlighting and a tab strip, `system.tag.` opens a completion popup with a
documentation panel, and a syntax error renders both an inline squiggle and a
gutter marker.

## Findings that cost real time (do not rediscover these)

1. **`ScriptManager.runCode` leaks output between concurrent users** — 22–25 lines
   of cross-talk, measured. Execution uses a private `PySystemState` per run, with
   the manager's module map COPIED and the copy's `sys` repointed at our own state.
   Both refinements are load-bearing; removing either breaks isolation silently.
2. **A hand-built `script-python` resource is silently unimportable.** Writing it as
   `putData("code.py", bytes)` gives perfect bytes on disk and a resource that reads
   back correctly — and the script library ignores it, failing with a bare
   `ImportError` that survives a scan AND a restart. The missing piece is
   `setApplicationScope(7)`. Use `ModuleLibrary.serializeScript(...)`, the
   platform's own writer.
3. **The library rebuild is asynchronous** — a freshly saved module is importable
   about 2–6 seconds later, not instantly. A test that checks immediately reports a
   false failure.
4. **The LSP and the workspace keyed documents differently** (`ignition://P/path`
   vs `P::path`). Subscribing to diagnostics with the workspace key meant every
   diagnostic was dropped and the editor looked clean however broken the code was.
   Caught by driving the real browser — every unit test still passed.
5. **Jython's syntax error is a `PyTuple`**, `(msg, (file, lineno, offset, text))`,
   not a `SyntaxError` with `.lineno`. The obvious Java translation silently reports
   every error on line 1.
6. **A Perspective theme pack is a SEMANTIC palette, not a lightness ramp.** Mapping
   `surface.sidebar` onto `--bg-secondary` made five of ten themes illegible, because
   a "sidebar" is branded chrome — dark navy in a light theme. Derive the neutrals
   from the page colour and take only the accents from the pack. And a pack names a
   FONT too: applying it renders the whole IDE in Georgia on `newsprint-night`.
7. **`[hidden]` loses to any `display:` rule in your own stylesheet** — same
   specificity, later rule wins. Three components here stay mounted-but-hidden to
   keep state, and all three were visible. Force it globally once.
8. **`script(1)` is how a JVM gets a pty with no native code.** Measured in the
   gateway container: the child gets `/dev/pts/N`, echoes, prompts, and honours
   `stty`. The command passed to `-c` is not echoed, so setup can be smuggled in
   front of the shell; capture the slave path there and later resizes can be done
   from outside with `stty -F` instead of typing into the user's session.
9. **git is not in the Ignition image and cannot be added from the terminal** — the
   Gateway runs as uid 2003 with no sudo. It has to go in the image; see
   `modules/dockers/ignition/Dockerfile.test`.

## Known gaps and deliberate omissions

- **No breakpoint debugging.** The only serious Ignition debugger needs a live
  Designer and blocks a gateway worker thread; neither fits a browser IDE.
- **No find-references.** Definition, outline and symbol search are in; a correct
  references implementation needs the type system the AST index does not build.
- **Diagnostics are syntax-only.** Undefined-name, unused-import and arity checks
  were designed but not shipped: the release bar was zero false positives, and one
  wrong squiggle on correct code costs more trust than ten missed problems.
- **Perspective/Vision event scripts** are not editable — their code lives inside
  view JSON, not as its own resource.
- **No git UI**, still. Nigel's decision (01/09/2026): this module is not becoming a git
  module — `Gaskony-Ignition/module-git` already exists. git is driven from the
  terminal's command line, and any UI added later is VS Code-shaped status and
  diffs on top of that, not a second implementation.
- **Tag Change attribute writes are still refused**, because that Designer
  workspace has never been measured. Its tag-path list is the missing piece, and
  guessing the key would write a value the Designer never reads.
- **Git**: own repo, private at `Gaskony-Ignition/module-script-ide`; `v1.0.0`
  through `v1.4.1` tagged 01/09/2026. The folder is gitignored by the workspace repo,
  like every sibling module. There is **no GitHub release artefact** — the signed
  `.modl` is built locally and has not been attached to the tag.

## Measured facts worth not rediscovering

- The Config ▸ Modules grid **paginates at 20 rows** (36 modules on this gateway),
  so reading the page text finds nothing and looks exactly like a failed install.
  Filter `#modules-data-grid-global-search` instead.
- **HTTP Basic auth creates no `WebUiSession`**, so the session probe must be
  checked through a real browser cookie — never `curl -u`.
- `logs/wrapper.log` is a symlink to `/dev/stdout`; `tail`/`grep` on it hangs.
  Use `docker logs --since <n>m`.
- The nav shell renders the page **key**, not the page title, as the sidebar link.
- A module install requires a gateway restart. That is inherent to installs, not
  the config-resource case the estate's no-restart rule refers to.
- **A CSS `max-width` on a flex item defeats `flex-basis: 100%`.** The item's
  hypothetical main size is clamped before the line-breaking step, so a help line
  meant to take its own row sat back on the control's row, wrapped into three
  short lines against the right edge. Every test passed; only the screenshot
  showed it. Put a measure limit on a child, never on the item doing the wrapping.
- **The test rig's image is now built, not pulled** —
  `modules/dockers/ignition/Dockerfile.test`, wired into `docker-compose.yml`
  01/09/2026. It adds git 2.43.0, less, openssh-client and a **passwordless
  sudoers rule for the `ignition` user**. That rule is what makes the browser
  terminal a root shell, and no module property could have: an Ignition module is
  Java in a JVM that is already uid 2003. The privilege is not confined to the
  terminal — Jython from the Script Console gets it too — which is why it lives in
  a file named `.test` and is written out at length there.
