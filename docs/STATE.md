# State

**Read this first each session.** Single source of truth for where the module is.

**Version 1.3.1 · all phases complete · deployed, gate-green and live-validated on
`ignition-module-testing` (8.3.8) · 01/09/2026**

1.1.0–1.3.0 are post-1.0 feature work driven by Nigel's review, not new phases.
1.3.0 adds a **Gateway terminal**, moves the console into a **bottom panel**, and
brings **Gateway Events** into line with the real Designer.

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

Five suites, all green, all run against the live gateway rather than mocks.

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

**`validate_v13.py` — 24 checks, all in a real browser.** Gateway Events in the
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
- **No git UI.** Nigel's decision (01/09/2026): this module is not becoming a git
  module — `Gaskony-Ignition/module-git` already exists. git is driven from the
  terminal's command line, and any UI added later is VS Code-shaped status and
  diffs on top of that, not a second implementation.
- **Tag Change attribute writes are still refused**, because that Designer
  workspace has never been measured. Its tag-path list is the missing piece, and
  guessing the key would write a value the Designer never reads.
- **Git**: own repo, private at `Gaskony-Ignition/module-script-ide`; `v1.0.0`,
  `v1.1.0`, `v1.2.0` and `v1.3.0` tagged 01/09/2026. The folder is gitignored by the workspace repo,
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
