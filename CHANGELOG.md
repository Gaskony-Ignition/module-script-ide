# Changelog

All notable changes to this module. Format follows [Keep a Changelog](https://keepachangelog.com/).

## [1.25.0] — 2026-09-07

feat: git status in the tree — which resources differ from the last commit.

- Read-only: shows changes since the last commit, never stages, commits or touches remotes.
- Reads `.git` with JGit in pure Java, since the rig has no `git` binary.
- A deleted resource's mark rolls up to the nearest surviving tree node; folders carry the worst mark below them.
- An unresolvable HEAD is reported rather than rendering every tracked file as untracked.
- Polls only for projects an IDE client has open, at a 10s interval.

## [1.24.0] — 2026-09-07

feat: templates, autosave and crash recovery, console export and timestamps.

- Autosave keeps every unsaved buffer in the browser and offers it back after a reload; restore loads over the gateway's current copy and never writes on its own.
- Six "New from…" templates for a new library script, each compiled against the live gateway's Jython before shipping.
- Console Export saves the output as a timestamped, ANSI-stripped text file.
- Console Times toggle, remembered per viewer, rendered outside the `<pre>` so copying the output never includes it.
- Fixed: a stale `web-<version>.jar` left in `build/moduleContent` failed `zipModule` with a multi-version library error; a clean build clears it.

## [1.23.0] — 2026-09-07

feat: presence — who else has this file open, and where they are working from.

- Other open IDE tabs are reported over the socket; a registry pushes changes to every client.
- Designer sessions are read from the platform's internal event bus (not SDK-stable; falls back to session-level presence if it stops matching).
- A warning, never a lock — `If-Match` is what prevents a lost update.
- Shown as a bar above the editor, a badge on the tab, and `GET /api/presence`.
- Run history is now searchable over source and output, and records duration.
- Fixed: two redundant null checks SpotBugs flagged on non-null SDK return values.

## [1.22.0] — 2026-09-07

feat: snippets, organise imports, live tag and schema completion, style lints, and colour in the console.

- Eighteen snippets with tab-stops in the completion popup.
- Organise imports: sorts, de-duplicates, removes unused; loaded as an ordinary undoable edit.
- Suggested imports for an undefined name, from the project's own modules first.
- Live tag-path completion inside a string literal, and table/column completion inside SQL-like strings.
- Seven AST-based style checks as warnings, built to zero false positives.
- `cprint`/`jsonPrint` and ANSI colour rendering in the console.
- Fixed: a `# -*- coding: utf-8 -*-` header broke the parse, the outline, go-to-definition and test discovery; the declaration is now neutralised without shifting any line or column.
- Fixed: the `tagchange` snippet named a non-existent `event.getTagPath()`.
- Fixed: a console ANSI reset left bold text coloured.

## [1.21.0] — 2026-09-07

feat: a Jython test framework — decorators, assertions, mocks, and a namespace per run.

- `@test`, `@skip`, `@cases`, `@beforeAll`/`@afterAll`/`@beforeEach`/`@afterEach`, `@timeout` (a budget, not an interrupt).
- Twelve assertions, each naming what it wanted and what it got.
- `mockTags`/`mockQuery` answer from a dict and record writes/calls; an unmocked read or query raises rather than returning `None`.
- A `skip` outcome, and re-run-failed-only.
- Each selected test module's source runs in a namespace private to the run, because importing returns the gateway's shared module object — a mock there would leak to every other user's scripts.
- `scriptide` (the test helper module) exists only during a run and is not importable outside one.

## [1.20.0] — 2026-09-07

feat: export and import code, in the Designer's own format.

- Right-click a script or package → Export, producing a Designer-compatible resource zip.
- Import lists the archive's contents, flags which resources already exist, and writes one push per resource.
- Every limit (traversal, per-entry/per-archive/total size, entry count, resource-type allowlist) is checked against the decompressed stream.
- Fixed: the first implementation built entry paths from `ResourcePath.getPath()`, which drops the module and type and makes the zip unimportable anywhere.
- `lastModification` is never carried across from the exporting gateway.

## [1.19.0] — 2026-09-07

fix: output written after an import was going to the gateway's console, not yours — plus a resizable, orientable console.

- Fixed: importing a project-library module moves the thread onto the platform's `PySystemState` and never restores it, so `print` and `sys.stdout.write` leaked to the gateway's own console from the first such import onward. Fixed with a private builtins table per run, restored in a `finally`.
- Console editor/output split is now a draggable divider, rows or columns, remembered as a proportional share.
- Fixed: the popped-out console showed a teal corner from the page glow leaking through unpadded chrome.
- Fixed: a document's own save briefly looked like somebody else's edit on the stale/pull UI; fixed by tracking in-flight saves and re-reading the tree before clearing that state.

## [1.18.0] — 2026-09-07

refactor: the compare-two-gateways feature is removed, and the split button is one you can see.

- Removed: the Compare view, `RemotePanel`, `RemoteGateways`, `RemoteClient`, `RemoteRouteHandler`, the `/api/remote/*` and `/api/scripts/digest` routes, the peer-or-session auth path, and the disposable second-gateway test rig.
- The test runner is unaffected.
- Split button now carries a label (`Split` / `Move left` / `Move right`) instead of a glyph alone.

## [1.17.0] — 2026-09-06

feat: two gateways side by side, and a Jython test runner.

- Compare view: pick a configured peer, see which bodies differ, open a differing one read-only beside your own. Read-only by construction — the client has no write path to a peer.
- Peers are named in `policy.properties`, never a client-supplied URL, to avoid a server-side request forgery primitive.
- A shared-secret token (`X-ScriptIDE-Remote-Token`) gates the peer-read surface; off unless configured, read-only, rejected under 24 characters.
- Test runner: discovers and runs Jython tests on the gateway, reporting pass/fail/error/elapsed/traceback/output; discovery is narrow by module-name convention.
- The decision to stay internal-only is recorded rather than assumed.
- Fixed: the peer gate originally covered the digest route only, leaving body reads open; a remote buffer could offer to overwrite the peer's file; the compare gesture could park the wrong pane.
- `scripts/testing/capture_readme_shots.py` retakes the README screenshots against whatever is deployed.
- A disposable second gateway (`dockers/peer.sh`) proves the Compare feature across two real machines and is destroyed after each run.

## [1.16.1] — 2026-09-06

feat: search that covers what the IDE actually edits, guards on the way out, and outstanding review items.

- Search, references and replace now cover gateway event scripts, Web Dev handlers/pages and named-query SQL, not just library scripts.
- A save that fails to parse asks once before writing.
- Rename a script, with call sites offered as a confirmed project-wide replace.
- Compare an override against its inherited parent chain, read-only.
- An "unused" report for top-level functions and classes nothing else names.
- Impact-before-save: a save removing or re-declaring a function lists its call sites first.
- Run history now survives a gateway restart, storing source and output per user.
- Tag change event scripts are fully editable (`paths`, `changeTypes`, `enabled`).
- The Administrator-role name is a policy key, not a hardcoded literal.
- Gateway event scripts show which are failing in the Problems panel (the SDK exposes no last-run/next-run data to build more on).
- Not done: two gateways side by side and a Jython test runner (shipped next release); internal/public status and a second-gateway proof are decisions, not code.

## [1.15.3] — 2026-09-05

feat: local save history, deprecation diagnostics, scope-aware checks, project-wide replace, and runtime errors in Problems.

- Local history: every save kept per user, including the pre-edit version, bounded and pruned; restore loads the buffer and never writes directly.
- Deprecated API calls now surface as a diagnostic, not just a hover note.
- Scope-aware checks flag `system.gui`/`system.nav` calls in contexts where the platform does not support them.
- Project-wide literal replace, written through the ordinary per-file save route.
- Problems panel gains a second list: runtime errors the gateway has actually logged, grouped by message.
- Fixed: local history was filed under the wrong data key; three new routes shipped with a hardcoded `/api/...` path instead of going through `apiUrl`; two new CSS classes collided with selectors the live suites count on.

## [1.14.4] — 2026-09-05

feat: diagnostics for every language the IDE opens, and the terminal keystroke bug root-caused.

- CSS, JavaScript, JSON, SQL and HTML documents now get error signalling, not just Python.
- Gateway write access is granted on the platform's `SESSION_WRITE` or the Administrator role, as a union.
- `terminal.docker` stays on by default.
- Terminal keyboard input, earlier marked "not root-caused" and removed from the suite, is confirmed working and restored — the earlier investigation never checked the socket itself.

## [1.13.0] — 2026-09-04

feat: undefined-name detection, ruler-to-line alignment, solid tooltips, a dedicated auth-error bar, stale-signature verification, and a collapsed Web Dev tree by default.

- `UnknownNames` reports a name bound nowhere in the module, excluding builtins and platform-injected names; tuned against the estate's own scripts to avoid false positives on script-library roots.
- The error ruler mark is now drawn on the line number itself rather than proportionally down the ruler.
- The hover tooltip uses a solid composited background instead of a glass film.
- A 401 on save now shows a dedicated bar saying the buffer is untouched, with sign-in and retry actions.
- A stale signature is verified once against the real bytes before the pull bar is raised, so a restart-only signature change does not trigger a false "pull" prompt.
- The Web Dev tree ships collapsed and remembers what you expand.

## [1.12.0] — 2026-09-04

fix: the status colours — three themes, not one.

- Three themes painted error/warning/success as a single hex or two near-identical greys.
- `pick_legible` now skips a candidate below a minimum chroma; `border.danger` is preferred over an amber "alarm-high" token for `--error`; status colours that resolved to one another by weight alone are now separated by hue.

## [1.11.0] — 2026-09-04

feat: the themes pass — colour in the grounds, the packs' own rails, and a syntax palette that distinguishes.

- Light theme grounds were nearly achromatic; raised to a visible chroma along each pack's own hue.
- The activity bar now takes a pack's own dark accent colour where the pack has one, instead of discarding it.
- Syntax highlighting separation is now scored on hue, weight and saturation together.
- The Run button's label no longer hardcodes white, which was unreadable on light-accent themes.

## [1.10.0] — 2026-09-04

feat: split editors — two scripts side by side.

- A second editor pane, toggled by a tab-strip button or Ctrl+\; a document moves between panes rather than duplicating.
- Draggable, remembered divider.
- Fixed: a 1px divider between flex children received no pointer events; widened to a 3px grab area, which also fixed the side-bar and panel dividers.

## [1.9.0] — 2026-09-04

feat: Web Dev's static resources — HTML, JavaScript and CSS, edited properly.

- Static (`text-resource`) Web Dev resources now open and save, with content-type-aware highlighting.
- Non-text data-key files (binary, oversized) are listed greyed rather than hidden.
- HTML, JavaScript, CSS and JSON editing surfaces alongside Python and SQL.
- Fixed: a static resource offered to add Python handlers to itself; the Jython language server ran over non-Python documents; only one tab per resource (not per file) tracked staleness.

## [1.8.10] — 2026-09-04

fix: the ruler marks the wrong line, closing a tab throws work away, and pull is missable.

- Ruler marks are now placed from CodeMirror's own layout rather than a line-count arithmetic approximation.
- Closing a dirty tab now asks, with Cancel / Discard / Save-and-close.
- A bar between the tab strip and the buffer now surfaces a pending pull for the active document.
- Escape now dismisses the conflict and close-confirmation dialogs.

## [1.8.7] — 2026-09-03

feat: the Designer's error ruler, with copy-to-clipboard on the mark and on every Problems row.

- An overview ruler beside the editor marks every problem line proportionally to the document, merging co-located problems and distinguishing severity by colour and width.
- Hover shows the parser's message with a Copy button; clicking jumps the caret and opens the Problems panel.
- Fixed: both Copy buttons silently did nothing over HTTP, because the async Clipboard API requires a secure context; replaced with an `execCommand('copy')` fallback that reports whether it actually worked.

## [1.8.5] — 2026-09-03

feat: a favicon, sidebar state that survives a view switch, and pull-from-gateway.

- A favicon, inlined as a data URI so the module works air-gapped.
- Pull from the gateway, per tab and for all at once, with a stale marker and a counted button; detection runs on focus, visibility and a 20s timer, and never replaces a buffer silently.
- Fixed: sidebar trees reset to default on every activity-bar view switch; each tree now keeps its open branches in `sessionStorage`.

## [1.8.4] — 2026-09-03

feat: the themes carry a material, not just a palette.

- Themes are now tiered (glass / soft / hard) by reading translucent-surface tokens from the pack itself, with translucent films, a lit ground gradient, and material-appropriate edge contrast.
- Fixed: native checkboxes and radios rendered in the browser default blue across all ten themes; the contrast sweep could not see alpha-composited surfaces and misjudged the glass pair as illegible.

## [1.7.2] — 2026-09-03

fix: the themes pass shipped geometry nobody could see.

- Radius and spacing clamp ceilings were set below where the packs actually live, collapsing most themes onto identical values; raised to span the packs' real range.
- Chrome bar heights now derive from `--control-height` instead of a hardcoded value in three files.
- `--row-height` now binds tree, palette, problems and outline rows consistently.
- Added a test asserting the ten themes yield enough distinct geometry signatures to catch this class of regression.

## [1.7.1] — 2026-09-03

Superseded within the hour by 1.7.2 — the clamp fix landed, then the row-padding half of the same defect was found.

## [1.7.0] — 2026-09-03

feat: named queries — the SQL and the Python that calls it, in one workspace.

- A Named Queries activity-bar view: folders, create, rename, delete, inherited/override badges.
- A SQL editor sharing the script editor's theme, gutters and byte-fidelity facets.
- Settings, Authoring and Testing tabs matching the Designer's own three concerns.
- Test run executes the draft (not the saved copy) through the prepared-statement route.
- Named queries appear in quick open, ranked with scripts.
- Fixed: a version-1 named query is unreadable by the platform itself; settings saves now repair it to version 2 without erasing the SQL.
- Theme geometry tokens (control/panel/row radius, marker width, row/control height, popup shadow, border colour, activity-bar background) are now taken from the packs, not just colour.

## [1.6.1] — 2026-09-02

fix: the console could not run a function or a class — every script with one raised NameError.

- `PrivateStateRunner` ran locals and globals as two separate dicts, so a function or class body could not see names the module itself had just defined. Fixed by running both in one dict.

## [1.6.0] — 2026-09-02

feat: the IDE navigates a project — go-to-definition, quick open, search, references and problems.

- Go to definition (F12/Ctrl-click) across files, silent on platform calls with no local source.
- Quick open (Ctrl+P), with `#` for project symbols.
- A Search view over project text search.
- Name-based references (Shift+F12), explicitly not type-aware, and labelled as such.
- A Problems panel over every open document's diagnostics.
- Fold gutter on files, go-to-line on Ctrl+G.
- The script tree ships collapsed and no longer lists Web Dev endpoints separately.
- `ETag` is now a quoted entity tag per RFC 9110; `If-Match` parsing is tolerant of `W/` and quoting.
- Fixed: a cross-file jump landed the caret on line 1 because the target CodeMirror view did not exist yet; fixed with a pending-reveal mechanism.

## [1.5.4] — 2026-09-02

feat: the project listing says where inherited scripts come from.

- `GET /api/projects` now carries `parent` and `inheritable` per project.

## [1.5.3] — 2026-09-02

fix: typed input never reached the terminal's shell, and closing it leaked a root shell.

- The hijacked Docker exec socket was wrapped in JDK stream adapters that share a lock between read and write, deadlocking input against the pump thread. Replaced with direct `SocketChannel` reads/writes using separate locks.

## [1.5.2] — 2026-09-02

fix: a terminal opened before its socket did, on a tab nothing else had used.

- `TermClient.open()` now defers its open frame to the transport's next connect event instead of sending on an unopened socket.

## [1.5.1] — 2026-09-02

fix: a stopped script poisoned its executor thread, and the next run on it was cancelled at once.

- `ScriptManager.interrupt` leaves the thread's frame/trace state pointing at a dead frame; `PrivateStateRunner` now snapshots and restores it around every run.

## [1.5.0] — 2026-09-02

fix: a socket that keeps listening, and a shell that actually dies.

- The exec frame handler no longer blocks the socket thread for the duration of a run; `started`/`output`/`finished` now arrive via callbacks, so Stop and every other frame are read promptly.
- Tracebacks are now unpacked from the structured payload instead of relying on client-invented field names.
- Docker exec resize now happens after attach, not before — the earlier order always timed out and silently skipped the resize.
- Closing a terminal now actively ends the shell: ETX/EOT/`exit`, then a root sweep that kills anything tagged with the terminal id, because the Docker Engine API has no "kill this exec".
- Policy switches (execution, terminal) are now read live from file/property/default instead of once at JVM start.
- An empty Project Library package no longer renders as an openable script; clicking an absent singleton event script opens a draft instead of writing a resource on click.
- `HintIndex` completion docs render the type name, not a raw data-class dump.

## [1.4.3] — 2026-09-02

fix: the Docker elevation route was never reachable, and the last terminal line was clipped.

- `SocketChannel.socket()` threw on a Unix-domain channel, making the Docker route report itself absent even when the socket was usable; timeouts now come from a watchdog that closes the channel instead.
- `FitAddon` did not subtract the fitted element's own padding, clipping the last terminal row; padding moved to the wrapper.
- The test rig is back on the stock Ignition image; the custom image and its Dockerfile are removed.

## [1.4.2] — 2026-09-02

feat: chrome sizing, one chrome row, and a Docker route to root.

- `--control-height` token applied across the toolbar's controls, fixing inconsistent heights and a Save button running into the border.
- The inheritance notice moved into the settings strip instead of its own row.
- A Docker-daemon exec route to root, with its own switch (`terminal.docker`) separate from sudo elevation.

## [1.4.1] — 2026-09-01

fix: Script Hint Scope is small, last on the strip, and silent.

- The control is now a small, unlabelled field at the trailing end of the editor header, matching the real Designer's footprint.

## [1.4.0] — 2026-09-01

feat: inherited scripts are read-only, and a root terminal.

- Inherited Project Library scripts are read-only until explicitly overridden, matching the real Designer's behaviour exactly (measured against it).
- The terminal elevates to root via `sudo -n` where the host already allows it; elevation happens inside the pty so the shell stays a process this JVM can signal.
- Script Hint Scope reordered to the Designer's own measured ordering (None · Designer · Gateway · All).

## [1.3.1] — 2026-09-01

Font rendering, measured side by side against VS Code.

- Removed `-webkit-font-smoothing: antialiased`, which is macOS advice and forces greyscale on Linux against the platform default.
- `ui-monospace` moved off the front of the mono font stack; alone it is not monospaced in Chrome on Linux.
- Code is now 14px at 1.4 line height, matching VS Code's split.

## [1.3.0] — 2026-09-01

feat: a terminal on the Gateway, a bottom panel, and Gateway Events measured against the real Designer.

- Terminal: a real shell on a real pseudo-terminal via `script(1)`, gated by Administrator + CSRF + same-origin with its own kill switch.
- A bottom dock panel holding Script Console and Terminal, plus the four VS Code layout glyphs.
- Startup/Shutdown/Update singleton scripts can now be created from the tree.
- Fixed: the two Glass Aurora theme variants were indistinguishable because the resolver fell through to a shared fallback token instead of lifting the pack's own accent.
- Fixed: `[hidden]` did not actually hide elements, because the user-agent rule lost to same-specificity app rules; forced globally.
- Fixed: Gateway Events tree order and singleton rendering did not match the real Designer; corrected against a measured reference.
- Typography: the UI font no longer comes from the theme pack.

## [1.2.0] — 2026-09-01

A VS Code-shaped shell, and Web Dev as a first-class view.

- Fixed: five of ten themes were illegible because neutrals were mapped from Perspective's semantic surface tokens rather than derived from the page colour; all ten now pass at 4.5:1.
- Fixed: a Web Dev endpoint's several tabs shared one language-server document, keyed only by path instead of by data key.
- Activity bar (Scripting / Web Dev / Search / Console), resizable and hideable panels.
- Web Dev as a full view: endpoints, methods, settings dialog, create/delete.
- Find and replace (Ctrl+F/Ctrl+H) in editor and console.
- Gateway event scripts can be created and deleted like the Designer's.

## [1.1.0] — 2026-09-01

Wiring the backend 1.0 had already built: Script Console, split panes and pop-out, an outline panel, create/delete scripts, a Designer-shaped tree, themes, gateway event settings.

- Fixed: an event-script folder resource was editable as if it were a script.
- Fixed: the first Run of a session always failed because the socket connects lazily.
- Fixed: themes did not apply, because `:root` and `[data-theme]` have identical specificity.
- Known limit: Tag Change settings are still refused; console output is not streamed.

## [1.0.0] — 2026-09-01

First complete release. Built and validated against Ignition 8.3.8.

- Editor: browser IDE served from the Gateway, file tree by script type, tabbed multi-file editing, CodeMirror 6, conflict dialog on concurrent edits.
- Resource editing: Project Library and Gateway event scripts, written through `ProjectManager.push()`, byte-identical to the Designer.
- Execution: run a buffer or selection with streamed output, structured traceback, best-effort Stop, per-user REPL console, per-execution audit.
- Language server: completions, signature help and hover over one authenticated WebSocket, sourced from the running gateway's own script registry.
- Navigation: go-to-definition through import bindings, outline, project-wide symbol search and text search.
- Diagnostics: syntax errors from the gateway's real Jython parser.
- Security: Administrator + session + CSRF + same-origin required for execution; no actor-string fallback; write routes type-gated to known script resources.
- Known limitations: no breakpoint debugging, no find-references, diagnostics are syntax-only, Perspective/Vision event scripts are not editable.
