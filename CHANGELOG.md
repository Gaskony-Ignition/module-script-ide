# Changelog

All notable changes to this module. Format follows [Keep a Changelog](https://keepachangelog.com/).

## [1.17.0] — 2026-09-06

feat: the two large items the product review left open — one gateway reading another, and a Jython test runner.

Nigel, 06/09/2026: *"Please finish the unfinished tasks"*, choosing **R5 and R6**
after being told R6 was the one the review recommended AGAINST. Both were
described in that review as days rather than hours, and neither is a small
feature. F1 was decided at the same time: the module **stays internal**, now by
decision rather than by inertia.

### Added — R5, two gateways side by side

- **A Compare view.** Choose a configured peer and every body this IDE can open
  is listed with whether it matches over there: `same`, `differs`, `only here`,
  `only there`. Clicking a differing row opens the peer's copy in the OTHER pane,
  read-only, beside your own. That is the differentiator no Designer can copy —
  the Designer cannot open two gateways at once at all.
- **Read-only by construction, not by restraint.** `RemoteClient` exposes ONE
  method and it is GET. There is no code path from the compare view to a write on
  another gateway, so no later edit can turn a comparison into a deployment by
  passing a different string. Promoting a change between gateways is a deployment
  with an approval and a rollback; a button in an editor would be pretending
  otherwise.
- **The client sends a NAME, never a URL**, and that is the whole security model.
  A route taking `?url=` would be a server-side request forgery primitive mounted
  inside a gateway — any authenticated user could aim it at `169.254.169.254`, at
  a database admin port, at anything the gateway can reach and the browser
  cannot. Peers are named in `policy.properties`; the set of reachable URLs is
  exactly the set the operator wrote down. Redirects are not followed, for the
  same reason.
- **The peer gate covers the four reads a comparison needs**, not just the
  digest. Mounted on the digest alone, drift worked and opening a differing row
  answered 401 — the body read is a separate route, and the reader could do
  nothing about it. Caught by the live suite, which asserts a peer's copy of a
  body arrives byte for byte rather than merely that a request was made.
- **Two requests, not two per script.** `GET /api/scripts/digest` answers a
  SHA-256 per body, so a 200-script project is compared in two round trips rather
  than four hundred. The corpus is the same "everything this IDE can open" that
  search uses, so a resource type becomes comparable in the same commit it
  becomes editable.
- **The one new authentication surface, and what bounds it.** A peer presents
  `X-ScriptIDE-Remote-Token`, matched constant-time against
  `com.gaskony.scriptide.remote.inboundToken`. It is **off unless configured**,
  it is **mounted on reads only** — never a write, an execution, an attribute
  save or the terminal — and a token under 24 characters is treated as ABSENT
  rather than accepted, because a control that reads as security and is guessable
  is worse than none. `SessionSecurity`'s own Javadoc predicted this: *"If a
  scripted caller is ever genuinely needed, add a Gateway API token check, not an
  actor string."* That is what this is.
- It is a shared secret rather than anything cleverer, and the cost is stated in
  the code: symmetric, non-expiring, rotated by editing two files. What it buys is
  that the credential lives in the one 0600 file the operator already owns
  instead of in a project resource, a database table or a UI this module would
  then have to protect.

### Added — R6, a Jython test runner

- **Nothing in Ignition offers one**, and the isolated execution primitive here is
  the only correct one in the estate. A Tests panel beside the console lists what
  the project declares and runs some or all of it: pass, fail, error, elapsed,
  the traceback, and what each test PRINTED before it stopped.
- **Three outcomes, never two.** A `fail` is an assertion that is not true; an
  `error` is a test that never got far enough to have an opinion. Collapsing them
  sends you to read an assertion that never executed.
- **Discovery is narrow on purpose.** A test is a top-level `def test_*` (or a
  `test_*` method on a `Test*` class) in a module whose last name starts with
  `test` or that sits under a `tests` package. Finding `def test_*` anywhere would
  put `plc.diagnostics.test_connection` under a Run All button — a function whose
  job is to open a socket to a PLC. The rule is stated in the panel, so it reads
  as a rule rather than as a bug.
- **Running a test is running arbitrary code, and is gated as such**: the
  gateway-write gate, a live `ExecPolicy` re-check per request, the same
  `ExecutionService` as the console, and an audit line before it starts. The ids
  in the request are a SELECTION — the server looks each one up in its own
  discovery, so an unknown id is a 400 and not a call to any function by name.
- **A Stop is not swallowed.** The harness catches `AssertionError` and
  `Exception` and never bare, so the Java `Error` a Stop and the timeout arrive as
  passes straight through — instead of being caught while the run calmly continues
  to the next test.
- **One execution for the whole run**, so the tests share an interpreter, as they
  do under any other runner. The panel says so: it is the one thing here that will
  surprise someone who knows pytest, and reading it beats discovering it from a
  flaky test.
- **Capturing what a test printed took three separate findings**, each of which
  fails silently — the run reports success and the output is simply gone. All
  three are asserted by `TestHarnessTest`, because the obvious edit to any one of
  them puts the bug straight back:
  1. **Every import happens before any output.** Writing to `sys.stdout` and then
     importing a project library module loses the WHOLE execution's output, not
     just the buffered write. So the harness runs in two passes: import and
     resolve first, print and run second.
  2. **The private system state is re-asserted after the imports.** Importing a
     project library module leaves the THREAD's `PySystemState` pointing at the
     platform's, so `print` — which resolves stdout through `Py.getSystemState()`
     — writes to the gateway's own console from then on. Explicit
     `sys.stdout.write` kept working the whole time, and that asymmetry is what
     made it visible: a captured write beside a missing print means the two are
     resolving different objects.
  3. **The harness flushes its own streams.** Jython buffers `sys.stdout` and the
     runner's tail-flush does not reach that buffer on a batch run. The script
     console never showed any of this, because a socket run has a periodic pump
     and a batch run does not.

### Changed
- A tab's read-only suffix now names the reason. An inherited script still reads
  `(Read-Only)`, measured off the Designer; a remote buffer says which gateway,
  because "read-only" alone sends a reader looking for the override button that
  would fix it, and for another gateway's copy there is none.

### Decided
- **F1 — the module stays INTERNAL.** Private at
  `Gaskony-Ignition/module-script-ide`, absent from `release.sh`, `test-all.sh`
  and the public portal, exactly as before. The difference is that it is now a
  decision on the record rather than fifteen releases of inertia.

### Fixed — three defects, none of which a unit test could have found
- **A peer could read the drift digest and not the script bodies.** With the
  peer gate on the digest route alone, a comparison worked and opening a
  differing row answered 401 — the body read is a separate route, and the reader
  could do nothing about it. Caught because the live suite asserts a peer's copy
  arrives BYTE FOR BYTE rather than merely that a request was made.
- **A remote buffer was offering to overwrite the peer's file.** Staleness
  compares a document's etag against the signature in THIS gateway's tree, and a
  remote document has neither — so the compare view opened a peer's copy and
  immediately offered to "pull the current copy" over it, which is the one thing
  the whole feature promises never to do.
- **The compare gesture parked the left pane on an unrelated script.** The pane
  rule that hands a vacated pane to a sibling is right in general and wrong here:
  "put these two side by side" has to show the OTHER ONE. With any tab already
  open the picture was a comparison of nothing.

The last two were found by LOOKING at the README screenshot, which is the whole
argument for F3 being a script rather than a chore.

### Documentation
- **F3 — the README screenshots are current, and now repeatable.**
  `scripts/testing/capture_readme_shots.py` re-takes all six against whatever is
  deployed. It asserts nothing on purpose: a screenshot's correctness is a human
  judgement and a suite comparing PNGs would fail on a font hint. Two are new —
  the compare view and the Tests panel. The fixtures it creates are named as
  plausible code rather than `_si_*`, because the Tests panel puts a module name
  on screen and the previous pass advertised a test fixture in the README.

### Not done, and why
- **F2 — it has still only ever run on one gateway.** The R5 suite configures a
  peer whose URL is this gateway's own, which exercises the config, the token, the
  client, the digest and the comparison, and cannot prove the two ends are
  different machines. Every other gateway on this workstation belongs to a
  different project that test modules must never be installed on.

## [1.16.1] — 2026-09-06

feat: search that covers what the IDE actually edits, guards on the way out, and most of the product review's own backlog.

Nigel, 06/09/2026, after five more ideas: *"do all 5 they are good"* — and then
*"also fix up everything from the past review. that should have all been done
already."*

### Added — the five
- **Search covers everything the IDE edits.** `ProjectIndex` filtered to
  library scripts while the module had grown to edit gateway event scripts, Web
  Dev handlers and pages, and named-query SQL. So search, references and (since
  1.15.0) replace covered about a quarter of what a user can open, and looking
  for a string in your own timer script returned nothing — which reads as "it
  isn't there". The NAME index stays library-only, deliberately: definition and
  quick-open symbols are about IMPORTABLE modules, and a timer script is not one.
- **A save that does not parse asks once.** Nothing stopped writing broken
  Python into a running gateway; on a timer script that starts failing on the
  next tick. Only an ERROR stops — a warning never does.
- **Rename a script**, with the call sites offered as a separate, confirmed
  project-wide replace. One resource, never a folder: the server refuses a
  folder rather than half-moving it, and the dialog says so before you type.
- **Compare an override with its parent.** *Discard Overrides* has always been
  one click and there was no way to see what it would discard — in this IDE or
  the Designer. Read-only, and it walks the parent CHAIN rather than stopping at
  the immediate parent.
- **An unused report.** Top-level functions and classes nothing else names.
  Name-based, and the panel says so at length: anything called from a
  Perspective binding, a Vision window or outside the project appears here and
  is not unused.

### Added — the product review's backlog
- **R1, impact before save.** A save that removes or re-declares a top-level
  function names its call sites first. A line scan, not the AST: the question is
  about two versions of a buffer and the server only knows one of them.
- **R3, run history that survives a restart.** The console kept nothing;
  `ExecAudit` stores a SHA-256 of the source by design, so it could say a run
  happened and never what was run. Source and output now, per user, bounded.
  "Load into console" does not re-run it.
- **R4, tag event scripts — the blocker was never the Designer.** This type has
  been body-only since 1.1.0 waiting for someone to measure the tag-path list in
  the Designer's workspace. A real tag-change resource on the rig had the shape
  written on it all along: `paths` and `changeTypes` as JSON ARRAYS and
  `enabled`. Both arrays are now editable, with `changeTypes` as an allowlist —
  the platform ignores an unrecognised one silently, so the script would sit
  there configured and never fire.
- **F4, the `Administrator` literal** is a policy key now
  (`com.gaskony.scriptide.admin.role`), resolved file &gt; `-D` &gt; default. A
  gateway whose admin role is called anything else fell back to a check that
  could only say no.
- **R2, half of it, and the half that is real.** The review asked for last fire,
  duration and next fire per event script. **The 8.3.0 SDK exposes none of
  them** — there is no timer-task registry to ask, and a log line appears only
  on failure, so inventing "last run" from one would make a healthy script look
  like one that never runs. What ships is which gateway event scripts are
  FAILING, how often and when, in the Problems panel.

### Not done, and why
**R5 (two gateways side by side)** and **R6 (a Jython test runner)** are
untouched. R5 is a cross-gateway authentication surface rather than a feature
flag; R6 is a product in its own right. **F1** (internal or public) and **F2**
(prove it on a second gateway) are decisions and environment, not code.

### Fixed
- Two over-broad test assertions that counted every `button` in the Search panel
  and broke the moment it grew a control — the same shape as 1.15.0's class-name
  collisions. They assert the result rows now, which is what they meant.

### Verified
`deploy_gate.py` PASS (6 checks, 14 routes, none unmounted). `v13` 27/27,
`v15_tree` 18/18, `v16_nav` 25/25, `v17_nq` 45/45, `v23_insight` 27/27.
Java 450, Vitest 619.

**The Tag Change labels came from driving the real Designer**, and they had to:
the resource stores `ValueChange` and the Designer's Change Triggers row says
`Value`. Reading the JSON alone — which is how the shape was found — would have
shipped a vocabulary this IDE invented for a control that already has names
people know. Screenshot at `docs/images/designer-tag-change.png`.

## [1.15.3] — 2026-09-05

feat: five things the IDE already knew and never said.

Nigel, 05/09/2026, having read the product review: *"Please do all 5."* They
ship as one release because they are one idea. The deprecation flag was already
in the hint index and only ever reached a hover card. The gateway's log already
knew which scripts were failing and nothing asked it. Search could find a string
across the project and could not change it. And every save went straight into a
running gateway with no way back to the version before it.

### Added
- **Local history.** Every save is kept on the gateway, per user, and the
  version that was there BEFORE the first save is recorded as well — otherwise
  the state you started from is the one state the history cannot return you to,
  and the first save is usually the one that broke it. Bounded by construction:
  25 versions and 2 MB per document, pruned oldest-first on every write, with a
  512 KB ceiling on a single version. **Restore loads the buffer; it does not
  write.** The old text goes into the tab as an unsaved edit and the ordinary
  Save writes it, with the same If-Match, inheritance rule and byte fidelity as
  any other save. Both path segments in the store are hashes, never names: a
  username and a resource path are attacker-influenced strings that would
  otherwise become directories.
- **Deprecated calls are now a diagnostic**, not just a word in a hover card.
  `CompletionDescriptor.getDeprecation()` has been read into `HintIndex` since
  1.0 and was used for exactly two things — sorting a completion down the list
  and printing "Deprecated." on hover. So the IDE knew a script called a
  deprecated API and would only say so if you happened to hover the call.
- **Scope-aware checks.** `system.gui` and `system.nav` do not exist on a
  Gateway, and a timer script calling one fails at the next tick in a log nobody
  is reading. Narrow by construction, and each narrowing removes a class of
  false positive rather than a class of bug: only where the scope is CERTAIN
  (gateway event scripts and Web Dev handlers, never a Project Library module a
  Vision client may import); only the PACKAGE, never the function, because the
  hint index is built under a time budget and a missing leaf can mean the walk
  gave up; and only when `system` itself resolves, because a broken index would
  otherwise report every line in the project.
- **Replace across the project.** Search has been able to find a string in every
  Project Library script since 1.0.0 and there was no way to change it — the
  Designer has no project-wide replace either. Literal, never a pattern. Each
  file is written through the ORDINARY save route with the If-Match from its own
  read, so inheritance, CSRF and byte fidelity all still apply; it is the same
  write, done several times. Inherited scripts and tabs with unsaved changes are
  skipped and named in the report rather than silently included.
- **Runtime errors in the Problems panel.** Everything the panel showed before
  was static analysis of code that has not run. A timer script failing every
  thirty seconds since Tuesday produced nothing there — it parses, its names
  resolve — while being the most urgent thing on the gateway. The second list is
  what the gateway has actually logged at WARN or worse in the last hour,
  grouped so a script failing every second is one row with a count rather than
  3,600 rows. The two lists are kept visibly apart: a runtime error has no line
  number, because the gateway logs a message and not a range.

### Fixed
- **Local history was filed under the wrong key.** A save that omits the data
  key is written under the resource's DEFAULT key, and the history recorded it
  under `""` — while the dialog asks with the document's real key. So every
  version was stored where no read could find it, and the dialog showed an empty
  history for a file that had one. `validate_v23_insight` reported 0 versions
  after two saves that both returned 200.
- **The three new routes shipped to the rig with a bare `/api/...` and 404'd
  there.** The SPA is served from `/data/scriptide/` on a gateway and from `/`
  in dev, so every call goes through `apiUrl`; a hardcoded path works under a
  mocked fetch and nowhere else. Caught by `validate_v13`'s console-error check
  with 588 unit tests green either side of it, and now pinned by four tests that
  assert the resolved URL rather than the call.
- **Two new classes collided with selectors the live suites count.** The runtime
  rows reused `.problems-row`, which is how `validate_v19_ruler` asserts how
  many static problems there are; and the replace box reused
  `.search-panel-input`, which made `validate_v16_nav`'s fill ambiguous the
  moment a search returned hits. Both have their own class now. A shared class
  name is a shared claim.

### Verified
`validate_v23_insight.py` — **27/27** — gates all five against the live gateway, and asserts
the scope check as a DIFFERENCE — the same `system.gui` line in a message
handler and in a library module, one marked and one not — because a check that
only looked for a mark would pass on a build that marked everything. It also
asserts that a local-history restore wrote NOTHING to the gateway, and that a
traversal id reads nothing.

`ApiCallsTest`, `PlatformApiChecksTest`, `SaveHistoryTest` and `ScriptErrorsTest`
cover the rules; `PlatformApiRealScriptsTest` runs the new AST walk over the
estate's own scripts, on the standing rule that any check judging a name gets a
real-corpus test before it ships — the rule `UnknownNames` earned in 1.13.0 by
producing 21 false positives on its first run over the same corpus.

## [1.14.4] — 2026-09-05

feat: diagnostics for every language the IDE opens, and the terminal mystery root-caused.

### Fixed
- **Only Python had error signalling at all.** A document was registered with
  the language server only when it was a `.py` file, so a Web Dev `cell3d.html`,
  a `site.css`, a WebDev JavaScript file and a named query's SQL had no
  squiggle, no gutter mark, no line-number mark, no ruler entry and no Problems
  row — and nothing said so. `syntaxLint.ts` uses each language's own parser,
  the one CodeMirror already loads for highlighting, and publishes into the same
  store the server publishes to, so the ruler and the Problems panel need no
  change. Measured per language first: CSS, JavaScript, JSON and SQL report real
  error nodes; **HTML's parser reports none**, by design, so HTML gets a narrow
  structural check behind an allowlist — `<div><p>hi</div>` is valid and must
  stay silent.
- **The 401 save bar and the phantom pull** (both 1.13.0) are gated by
  `validate_v22_editing.py` from this release, after two suite bugs of their own
  were found: it counted lint marks with an unscoped selector, so it saw the
  marks of hidden tabs, and one check formatted its message from a second query
  that disagreed with its own assertion.

### Changed — Nigel's four parked decisions, answered 05/09/2026
- **Gateway write access joins the role name as a UNION.**
  `SessionSecurity.canWriteGateway` grants on the platform's own
  `WebUiSession.SESSION_WRITE` **or** the `Administrator` role. Measured on
  8.3.8, `SESSION_WRITE` alone DENIED the gateway's own `admin`, so replacing
  the role check with it would have shipped a module nobody could save from.
- **`terminal.docker` stays on by default** — the larger grant, deliberately.
- **`_wd_scratch_` is Inheritable**, so `validate_v15_tree.py`'s read-only
  checks run instead of skipping. The child now inherits an Update, so the
  suite discovers two fixtures rather than assuming one.
- **The `groups: cannot find name for group ID` login notice is suppressed**
  via Debian's own `$HOME/.hushlogin`, which is the same condition guarding the
  block that printed it. The nameless gid is the host docker group.

### Verified
The v13 terminal input checks are **restored**. They were removed on 02/09/2026
as "NOT ROOT-CAUSED"; hooking `WebSocket.prototype.send` and replaying the
suite's exact sequence put every keystroke on the wire — 14 `term`/`input`
frames with a real terminal id, and the echo came back. There was no defect.
Everything in the earlier investigation had looked at the DOM; nothing had
looked at the socket, which is the only place that separates "the browser never
sent it" from "the server never answered". `stty size` now proves the pty
carries the fitted size rather than 80x24.

Two goes at the HTML check were wrong and a real file caught both.
`cell3d.html` is 1,559 lines that render in every browser; the first version
marked `<html>`, `<head>` and `<style>` "never closed", because CodeMirror
parses lazily and the close tags were outside the tree. `syntaxTreeAvailable`
looks like the API for this and is not — it returned TRUE for a tree covering
3,041 characters of 72,626 — and `tree.length` equals the document length in
the live editor while most of it is still placeholder. The rule confirms the
close tag in the **text**, which no parse state can lie about;
`syntaxLint.corpus.test.ts` pins it, opt-in behind `SI_HTML_CORPUS`.

`deploy_gate.py` PASS (6 checks) on `ignition-module-testing`. `v13` 27/27,
`v15_tree` 18/18, `v16_nav` 25/25, `v17_nq` 45/45, `v18_pull` 20/20,
`v19_ruler` 16/16, `v20_webdev` 32/32, `v21_split` 21/21, `v22_editing` 20/20,
theme sweep 10/10 with no illegible element. Java 379, Vitest 545.

Interim builds 1.14.0–1.14.3 were this work under test on the rig and shipped
to no one else.

## [1.13.0] — 2026-09-04

feat: six things Nigel found in one sitting, every one of them a case where it looked like it was working.

### Added
- **A name that is defined nowhere is now reported.** *"I can put absolute
  garbage in here and it doesn't show up as an error"* — `j;sdfj;asdfjk;dksfj`.
  The parser was right: that is four semicolon-separated expression statements
  and valid Python 2. There was simply no check for an undefined name.
  `UnknownNames` reports a name bound nowhere in the module that is neither a
  builtin nor one of the ~20 the platform injects, and gives up every scope rule
  deliberately — a mark on working code teaches a reader to ignore the marks.
  **`UnknownNamesRealScriptsTest` is the load-bearing test**: over the 38 real
  scripts on this rig the first version produced 21 complaints, every one a
  project script-library root (`MachineDemo`, `MiningDemo`, `Access`). It would
  have marked a line in nearly every script in the estate. The server supplies
  the roots from `ProjectIndex` now.

### Fixed
- **"the error mark showed up high instead of in line with the actual line."**
  The overview ruler maps the whole document, so a fault on line 22 of 190 sits
  a tenth of the way down it — correct, and unreadable as anything but a mark in
  the wrong place. `lintLineGutter` colours the **line number**, the thing a
  reader is already using to find a line. The ruler stays: this adds a signal,
  it does not move one.
- **"the hover over information display needs to be more solid."** The tooltip
  used `--surface`, which on a glass pack is that pack's own
  `rgba(255,255,255,0.10)` film, so code read straight through the
  documentation. It uses `--glass-panel` now — the composited fill the palette
  and the dialogs already had. The tooltip was the one floating layer that
  never got it.
- **"tried to save but it came up with an authentication error… I could
  potentially lose work."** A 401 fell through to the generic save-failed
  notice, which printed the servlet container's JSON body verbatim in a
  one-line strip, and nothing said the work was safe. Now a dedicated bar says
  the buffer is untouched and offers "Sign in again" and "Retry the save"; the
  20 s watch raises it too, so it surfaces before the next Ctrl+S rather than
  at it. `toApiError` reads the container's `message` field instead of the
  envelope and refuses to put a proxy's HTML on screen as a message.
- **"no changes were made via the designer… when I click on the compare I
  couldn't see any differences"**, then *"when I just refreshed the page it
  stopped showing me any need to pull"*. Both say the resource signature moved
  and the bytes did not, which a gateway restart does; the watch announced it
  anyway, because the listing carries only signatures. Every newly-stale
  document is now verified once by reading it — identical, adopt the signature
  and say nothing; different, leave the bar up. The compare dialog names the
  count of differing lines, marks each change with a fill, a solid edge **and**
  a ±glyph, scrolls the first into view, and says plainly when there are none.
- **"I want by default the WebDev to start shrunk but remember what I've
  expanded between tabs."** The Web Dev tree shipped fully expanded and reset on
  every view switch. It ships collapsed and keeps its open branches, like the
  other trees since 1.8.5.

### Verified
`validate_v22_editing.py` (20 checks) gates five of the six; the sixth is in
`v20_webdev`, now 32/32.

## [1.12.0] — 2026-09-04

fix: the status colours — three themes, not one.

### Fixed
- **Two themes painted error, warning and success as a single hex**, and a
  third painted two greys 13 apart:

      industrial-day-cyan     error #545454   success #4f545e
      leather-night-tan       error = warning = success = #c9996e
      leather-parchment-tan   error = warning = success = #7a550b

  Recorded at 1.7.0 as a contrast problem on one theme and left as Nigel's
  call. That was the wrong diagnosis and the wrong size: the pack's red clears
  4.5:1 easily, and what the generator picked was never a red. Nothing caught
  it because nothing had ever compared one status token against another, or
  asked whether either was a colour at all.

  The cause is the 1.2.0 lesson one level down. `text.status-alarm` is not the
  pack's alarm colour — it is the **ink** that goes on an alarm chip, and in a
  light industrial pack that ink is `#FFFFFF`. `pick_legible` takes the first
  token present, correctly, so a present-but-achromatic ink beat the real
  signal colour every time, and `lift_to_contrast` could not rescue it because
  lightness is the only axis it moves. Three changes in `tools/build-themes.py`:
  a signal role skips a candidate below `SIGNAL_CHROMA_MIN` (28/255, read off
  the measured spread of all 110 candidates — the rejects score 0…26, the keeps
  start at 31, and the bar goes in the one gap there is); `border.danger` moves
  ahead of `accent.alarm-high` for `--error`, because both industrial packs
  paint "alarm-high" AMBER, which is high priority and not danger; and
  `differentiate_signals` pulls apart status colours that resolved to one
  another **by weight only** — a status colour is never rotated, because an
  amber turned 50° to clear a red is a green.

Interim builds 1.12.1–1.12.2 were this work under test on the rig.

## [1.11.0] — 2026-09-04

feat: the themes pass — colour in the grounds, the packs' own rails, and a syntax palette that distinguishes.

Nigel, 03/09/2026: *"still quite a bit of the styling feels a bit dull… so that
the different themes really feel beautiful and provide that bit of variety."*

### Fixed
- **The light themes were four shades of pale grey.** Their grounds carried a
  chroma of 3, 5, 5 and 8 out of 255 — the hue was stated correctly in every
  pack and could not be seen, because at 97% lightness the most chroma any
  colour can hold is 15. Now 19–27, raised along each pack's own hue. A pack
  already carrying its colour is untouched: Glass Aurora keeps `#1a1233`
  exactly.
- **Two packs put a dark rail on a light page and it was thrown away.** Finance
  Ledger's navy `#0b3d5c` and Leather Parchment's brown `#2f2016` are the
  loudest thing about either design. The activity bar now takes them, with its
  own ink measured against itself.
- **Syntax highlighting did not distinguish on four themes.** Industrial Day
  shipped keywords and types at the same lightness, the same saturation and 8°
  apart. The separation is now scored on hue, weight and saturation together,
  with the bar set from the measured spread of the ten.
- **The Run button's label was a hardcoded white.** On Newsprint Night, whose
  accent is paper `#e8e2d6`, it was white on near-white — unreadable since
  1.1.0; on Glass Aurora Teal, white on bright teal. It follows the theme now.

### Verified
Theme sweep 10/10 with no illegible element, now measuring the activity bar's
icons and the filled primary button as well — neither had ever been measured,
which is how both defects survived. The generator asserts ground chroma, syntax
separation and accent-ink contrast and exits non-zero rather than writing a
theme that fails one; each assertion was proved to refuse the previous build
before being trusted. `v13` 23/23, `v16_nav` 25/25, `v18_pull` 20/20,
`v19_ruler` 16/16, `v20_webdev` 29/29, `v21_split` 21/21, Vitest 521.

## [1.10.0] — 2026-09-04

feat: split editors — two scripts side by side.

Nigel, 03/09/2026: *"I'm not seeing a way to split the screen between 2 or more
scripts so that I can do comparisons or copy and paste between etc."*

### Added
- **A second editor pane.** The button at the end of the tab strip, or Ctrl+\,
  moves the current document across; the same gesture brings it back, and the
  split collapses when the second pane empties. A draggable divider between
  them, remembered across sessions like the other two.
- A document lives in exactly one pane, and splitting **moves** it rather than
  duplicating it — so its CodeMirror view goes with it, undo history and scroll
  position intact.

### Fixed
- **A 1px divider between two flex children received no pointer events.**
  `elementFromPoint` on its own centre returned the neighbouring editor's
  gutter, so dragging it did nothing while every static check said it was
  there. `.resizer` now sits above its neighbours with a 3px grab area — which
  fixes the side-bar and panel dividers too.

### Verified
`validate_v21_split.py` 21/21, including a real copy-paste between the two panes
and an undo in the pane that was moved. `v13` 23/23, `v16_nav` 25/25,
`v18_pull` 20/20, `v19_ruler` 16/16, `v20_webdev` 29/29. Vitest 521.

## [1.9.0] — 2026-09-04

feat: Web Dev's static resources — HTML, JavaScript and CSS, edited properly.

Nigel, 03/09/2026: *"the Machine_HMI-Demo is a good example as it has cell3D
which appears to be javascript or html code which I should be able to view/edit
like a script but instead all I am seeing is doGet, doPost etc."*

A Web Dev resource comes in two shapes and this module knew one. `cell3d` is a
`text-resource`: 65 KB of HTML living in `config.json`'s `text` field, with its
MIME type beside it. `lib` is a `python-resource` that also carries
`three.min.js` as a data key.

### Added
- **Static resources open and save.** A text resource shows one row for the file
  it serves, named and highlighted by its content type. Writes are a
  read-modify-write of `config.json`, so the `content-type` and any field a
  newer Ignition adds survive the save.
- **The files an endpoint carries are visible.** `three.min.js` and anything
  beside it now appear in the tree with their size. Ones this IDE cannot
  round-trip as text — a PNG, a font, anything over 512 KB — are listed greyed
  rather than hidden, so a file cannot appear not to exist.
- **HTML, JavaScript, CSS and JSON editing surfaces**, alongside Python and SQL.
  The language comes from the resource's declared MIME type, falling back to the
  file extension, and a `.py` key is Python whatever else claims otherwise.

### Fixed
- **A text resource offered to add Python handlers to itself.** Every
  unimplemented verb rendered an "add doGet" button, and on a static HTML
  resource pressing one would have written `doGet.py` onto it. Both the button
  and the settings dialog are gone for that shape, and the gateway refuses a
  per-method settings write on one.
- **The Jython language server ran over non-Python documents.** One predicate,
  `isPythonDoc`, now gates completions, diagnostics, the problem ruler and
  "Run file" together.
- **Only one tab per resource could go stale.** `staleUris` was keyed by
  document rather than by resource, so on an endpoint with several files open
  every tab but one was exempt from the 1.8.5 pull feature.

### Verified
`validate_v20_webdev.py` 29/29 against the real `Machine_HMI_Demo` endpoints,
including a full edit-save-restore round trip on `cell3d` proving the body comes
back byte for byte and the HTML is stored readable rather than escaped tag by
tag. `v13` 23/23, `v16_nav` 25/25, `v18_pull` 20/20, `v19_ruler` 16/16.
Java 365 tests, Vitest 505.

## [1.8.10] — 2026-09-04

fix: the ruler marks the wrong line, closing a tab throws work away, and pull is missable.

Nigel's three follow-ups of 04/09/2026. Two are defects in 1.8.5–1.8.7.

### Fixed
- **The ruler mark was not level with its error.** *"it seems to just appear
  randomly."* It was — `markOffset` spread the line COUNT evenly over the
  ruler's height, which is only right when the document fills the pane. A
  28-line script fills about two thirds of an 819px editor, so the last line's
  mark was drawn at the bottom while its code sat at 62%.

  Marks are now placed from CodeMirror's own layout (`lineBlockAt().top`,
  divided by the greater of content and pane height), which also gets wrapped
  lines and folded ranges right — no arithmetic on line numbers can. Centred on
  the line rather than aligned to its top, which was a consistent half-line
  high. **Measured drift on the rig: 14px → 4px**, against the real DOM position
  of the line.

- **A dirty tab closed silently.** *"I can close a tab that has unsaved changes
  without any notice or anything."* The close button is a few pixels from the
  tab you meant to select, which makes it the easiest way in the app to lose
  work. It now asks, with **three** answers: Cancel, Discard changes, and **Save
  and close** — "cancel or lose it" is a false choice, and forcing someone to
  cancel, save, then close again is how a confirmation becomes something people
  click past. Save-and-close only closes if the save actually landed: a 409
  leaves the conflict dialog up, and closing under it would discard the very
  buffer being compared.

- **Pull was easy to miss.** The tab arrow and the toolbar count are both
  somewhere you are not looking, which is at the code. A bar now sits between
  the tab strip and the buffer, for the active document only, saying which
  script changed and whether you also have unsaved edits — with the action on
  it. The toolbar button is filled rather than outlined; an outlined button in a
  row of outlined buttons is just another button.

- **Escape did not dismiss the conflict dialog.** Cancel existed so nothing was
  unrecoverable, but a modal that ignores Escape is one people fight. Wired on
  both it and the new close dialog.

### Two test bugs, both encoding the old behaviour
- `validate_v19_ruler` asserted the mark sat "near the bottom for the last
  line" — the 1.8.7 defect written down as a requirement. It now measures the
  mark's centre against the **real DOM position** of the line, which is what
  Nigel's complaint was actually about.
- The pull suite left the conflict dialog open (Escape did nothing then), and
  its backdrop intercepted every later click. It cancels explicitly now.

- `ResizeObserver` does not exist in jsdom; unstubbed it threw during commit and
  **29 unrelated tests failed with it**. Stubbed in setup, and guarded in the
  component so no environment can fail to mount the code surface over it.

## [1.8.7] — 2026-09-03

feat: the Designer's error ruler, and the copy that makes it better than the Designer's.

Nigel's item 2 of 03/09/2026: a narrow strip right of the code with a mark in
line with every problem line, hover for the message — *"Ideally i would like to
take this one step further and if i click on it I can copy the error text
description for further analysis elsewhere."*

### Added
- **An overview ruler** beside the editor. A mark per problem LINE, positioned
  proportionally to the **document**, not the viewport — the whole point is a
  problem that is scrolled off screen; a ruler that only marked visible lines
  would say what the squiggles already say.
  - Several problems on one line merge into one mark carrying the worst
    severity, with the card listing all of them. Three marks at identical
    offsets read as one mark with a dirty edge.
  - Severity by colour **and** by width, so an error and a hint are still
    distinguishable without relying on colour.
  - Hover shows a card with the parser's message and a **Copy** button. The card
    is shown on hovering the SLOT, not the mark, so the pointer can travel onto
    it — otherwise the copy button can never be clicked.
  - Clicking a mark puts the caret on the problem **and** opens the Problems
    panel on it.
- **Copy on every Problems row too**, carrying file, line and message
  (`CellSim:28:9 no viable alternative at input '='`).
- **`validate_v19_ruler.py`** — 16 checks: geometry against the editor's own
  bounding box, the mark's position as a fraction of the ruler, the hover card,
  a real clipboard round trip, the click-through, and the mark clearing when the
  line is fixed.

### Fixed
- **Both Copy buttons did nothing at all, silently.** This gateway is served
  over **HTTP**, and the async Clipboard API is gated on a secure context — so
  `navigator.clipboard` is not "present and refuses", it is `undefined`, and the
  `navigator.clipboard?.writeText(...)` both buttons used was a no-op. New
  `clipboard.ts` falls back to `document.execCommand('copy')` over an off-screen
  textarea, restores focus afterwards (or copying from the ruler steals the
  caret out of the editor), and **reports whether it actually worked** so the
  button never claims "Copied" when nothing was.

  The unit tests passed throughout, because jsdom lets a test assign
  `navigator.clipboard` — the one environment that mattered was the only one
  nothing checked. Caught by the live suite on the first run.

### Two test bugs found by the same run, worth recording
- The suite verified the copy with `navigator.clipboard.readText`, which is
  **equally unavailable over HTTP** — it was testing the missing API from the
  other side. It now pastes into a scratch field, which is also closer to what
  the text is actually for.
- Opening the Problems panel puts a SECOND CodeMirror on the page (the console),
  so a bare `.cm-content` selector became ambiguous mid-suite. Every editor
  interaction is scoped to `.code-editor` now.

## [1.8.5] — 2026-09-03

feat: a favicon, sidebar state that survives a view switch, and pull-from-gateway.

Four of Nigel's 03/09/2026 items. The remaining three — the Designer's error
ruler, WebDev static resources and a split view — are queued in `docs/STATE.md`.

### Added
- **A favicon.** There was none at all; the tab showed Chrome's default document
  glyph. Inlined as a data URI rather than a file in `public/`, because the
  module is served from inside a jar and must work air-gapped.
- **Pull from the gateway**, per tab and for all at once. *"I made an edit on the
  designer to one of the scripts. I had the script open in my ide module. The
  change did not show up."*
  - A **stale marker** on the tab, and a counted `Pull N changes` in the toolbar
    that only exists while there is something to pull — a permanently visible
    Pull button trains people to press it on a schedule; a button that appears
    with a count IS the notification.
  - Detection runs on window **focus** and visibility as well as a 20 s timer,
    because the realistic sequence is edit in the Designer, alt-tab back. It
    refetches the LISTING, not each open document: one request whatever is open,
    and the listing already carries the signature that answers the question.
  - **The buffer is never replaced behind you.** Detection is not a silent
    reload; that is asserted in the suite.
  - Dirty **and** stale routes to the existing conflict dialog rather than
    reinventing it — the only difference from the save-time path is that the
    user asked for it. A pull-all leaves every dirty document alone and names
    them; quietly resolving several on someone's behalf is the one thing it must
    not do.
- **`validate_v18_pull.py`** — 15 checks, driving a real browser against a real
  gateway: open a script, change the resource underneath it, prove the marker
  appears on focus, prove the buffer is untouched until pulled, prove the pull
  loads the gateway copy, then prove dirty+stale raises the conflict dialog
  showing both copies.

### Fixed
- **Sidebar trees reset to default on every view switch.** *"its annoying how
  everytime I shift between a section it resets to default."* The activity-bar
  views are a `? :` chain, so switching from Scripting to Web Dev does not hide
  the tree — it REMOVES it, and `useState` goes with the component. All three
  trees now keep their open branches in `sessionStorage` behind `useStickySet`,
  with an in-memory fallback for contexts where storage throws.

### What the Problems panel actually does
Reproduced on the rig: a broken line produces a squiggle, a gutter marker, and a
row reading `no viable alternative at input '='  ·  CellSim 19:9`. The pipeline
works. What is wrong is the FEATURE — it lists only documents open as tabs, it
lives in a panel that starts collapsed, and a WebDev or named-query document is
not registered with the language server at all. The Designer's overview ruler is
the right answer and is next in the queue.

### Two things worth keeping
- **`npx tsc --noEmit` in `web/` checks NOTHING.** The root tsconfig is
  solution-style (`"files": []` plus references), so that invocation type-checks
  an empty program and exits 0. Verified by planting
  `const x: number = "not a number"` and watching it pass. The real check is
  `tsc -b`, which is what `npm run build` and therefore Gradle run — it caught a
  genuine temporal-dead-zone bug in this very change, where a `useCallback`
  dependency array referenced two `const`s declared 400 lines below it.
- The v13 live suite asserted `aurora-teal`'s ground `!=` `aurora-violet`'s,
  which **encoded the 1.7.x bug as a requirement**. Both packs are authored on
  one violet ground and differ by the light on it; the check now asserts that.

## [1.8.4] — 2026-09-03

feat: the themes carry a MATERIAL, not just a palette.

Nigel, on 1.7.2: *"the glass themes in perspective really look beautiful but in
this module they just look like a plain teal or violet"* — and then, once the
glass pair improved, *"I wasn't just referring to the 2 glass themes… still
quite a bit of the styling feels a bit dull."*

Two causes, both measured.

**The ground was being rotated away from the pack.** `aurora-teal` and
`aurora-violet` share ONE authored ground (`#1a1233`, hue 255) and differ only in
which colour glows on it — that shared violet ground is what Glass Aurora is.
`ACCENT_TINT = 0.30` mixed the brand accent into the page and swung aurora-teal
to hue 203, actual teal. The tint existed to make siblings tell apart; the pack
already does that by accent.

**The glass was being composited away.** The glass is not a colour, it is a
material: `rgba(255,255,255,0.06 → 0.16)` films stacked over a lit ground with a
22%-white hairline where the light catches each edge. Flattening those to opaque
hex turns three panes into three flat greys.

### Added
- **Material read from the pack, never from its name.** `is_glass` counts
  translucent surface tokens, so a new pack gets the right treatment without
  this file learning about it. Three tiers fall out of the ten: **glass** (the
  aurora pair), **soft** (nord ×2, leather ×2, finance), **hard** (industrial
  ×2, newsprint).
- **Translucent films, luminous hairlines and `backdrop-filter`** on the glass
  packs. Blur only on layers that float OVER content — never behind the editor.
- **A lit ground**, `--page-glow`: three strong accent stops for glass, two
  gentle ones for soft, and **`none` for hard** — flatness is what newsprint and
  an HMI *are*, and lighting them would be the same mistake in reverse.
- **Edge character by material.** One contrast band for all ten was most of why
  the chrome read alike; it now interpolates on the pack's own softness, so
  `industrial-day-cyan` gets a crisp rule and `nord-*` a whisper.
- `--glass-panel` (floating layers), `--bg-solid` (anything that must occlude
  what scrolls under it), `--blur-panel`.

### Fixed
- **Native checkboxes and radios rendered in Chrome's default BLUE in all ten
  themes** — a pastel blue box in the middle of leather-night-tan's amber panel.
  Present since 1.0.0, found by a pixel review. `accent-color` on the four
  native control types.
- **`theme_sweep.py` could not see alpha.** It walked up for the first
  non-transparent `backgroundColor` and took its RGB — correct while every
  surface was opaque, and wrong the moment one was not: `rgba(255,255,255,0.06)`
  has an RGB of PURE WHITE, so the gate read a 6% film as a white background and
  called both aurora themes illegible at 1.69:1 when the composited surface is
  dark. It now composites the layer stack. **A gate that cannot see alpha would
  have had me revert a correct change.**

### Two mistakes worth keeping
- **Glass with nothing behind it is not glass.** The films shipped first over a
  FLAT ground, where a 6% white film over dark violet is a shade of the same
  violet: the rail, the header and the canvas all read as one block and the
  review came back *"the panel IS the ground"*. An aurora is a gradient; the
  panes exist to reveal it.
- **A gradient centred off-canvas is mostly falloff.** The soft wash shipped as
  one stop at 4%/−10% and moved the ground by **2 of 255** at the centre of the
  window — ~8% of its nominal alpha survived that far. Measured, not eyeballed.
  Both tiers now carry a stop INSIDE the window. Ground delta at 1.8.4: glass
  29–31, soft 7–10, hard exactly 0.

### Measured on the rig (8.3.8)
`deploy_gate.py` PASS. Contrast, on the painted elements with alpha composited:
no illegible theme, worst element 5.27, and the aurora pair are now the **best**
in the set at 7.49 (they were 5.38 before — the authored ground is darker).
Vitest 450.

**The live sweep is blind to `--page-glow`**, because `getComputedStyle` reports
`background-color` and a gradient is a background-IMAGE. The glow is therefore
bounded in the generator instead: its brightest point is composited and added to
the surfaces every text token is verified against.

## [1.7.2] — 2026-09-03

fix: the themes pass shipped geometry nobody could see.

Nigel, on 1.7.0: *"I don't understand the theme changes still all look the same
as before. Did you actually make any changes to them?"* He was right, and the
answer is the interesting part: **every layer worked except the numbers.**

The tokens were emitted per theme, the `:root[data-theme=…]` selectors were
right, the CSS reached the browser, and the components consumed the variables.
Measured in the browser, seven of the ten themes came out **byte-identical**:

| | pack spread | emitted by 1.7.0 |
| --- | --- | --- |
| `radius.card` | 0, 2, 4, 6, 10, 16, 16, 16, 18, 18 | ceiling **12px** → five collapse to 12 |
| `radius.nav` | 0, 2, 3, 6, 6, 8×5 | ceiling **6px** → seven collapse to 6 |
| `space.content` | 12–26px | three bands → six collapse to 22px rows |

`_px`'s clamps existed for a real reason — `radius.chip: 999px` on a tab makes a
lozenge — but the ceilings were set below where the packs actually live, so the
clamp that was meant to catch one outlier flattened the whole set.

**Why no test caught it.** `theme_sweep.py` measures contrast, and contrast was
never the thing that changed; it passed identically either way. The unit tests
asserted each token was *present and in band*, never that the ten themes
*differed from each other*. Both were green while the feature did nothing. This
is finding 10 again — "the server does it is not a feature" — one layer up: the
tokens are emitted is not a theme.

### Fixed
- **Clamp ceilings raised to where the packs are** — `--radius-panel` 12→18px,
  `--radius-row` 6→8px. Panel radius now spans the pack's own 0→18px order.
- **Density is a continuous map, not three bands.** `space.content` 12–26px maps
  to 20–26px rows, so a pack that asked for tighter spacing gets it instead of
  being rounded into the middle band with five others.
- **The chrome bars derive from `--control-height`** instead of a hardcoded
  34px in three files. A 28px control in a 34px bar had 3px of air and
  reproduced the 1.4.2 "squished" complaint exactly; derived, it is 5px at
  every density. Same rule as the controls, one level up.
- **`--row-height` now binds on the palette, problems and outline rows.** They
  set vertical padding, which outweighs `min-height`, so `industrial-day-cyan`
  showed 20px tree rows and 25.5px palette rows — two densities in one theme.
  Set the height, not the padding.

### Added
- **A test that fails on the defect**: the ten themes must yield at least seven
  distinct geometry signatures, and no more than three may share one. Verified
  against the shipped 1.7.0 stylesheet, which scores 6 with a group of 5.

### Measured on the rig, not read off the packs
Painted values across the ten themes, gateway 8.3.8:

- palette radius **0 → 18px**, with four themes casting no shadow at all
- tree and palette rows **20 → 26px**, both tracking the token exactly
- control height **22 → 28px** (1.7.0 spanned 2px)
- contrast unchanged: worst element 5.07, no illegible theme

`validate_v15_tree` fails on this gateway at 1.7.0 and at 1.7.2 alike — it wants
`Site_Redgum_Sewer`, a water-suite project not installed here. Pre-existing
fixture gap, not a regression.

## [1.7.1] — 2026-09-03

Superseded within the hour by 1.7.2 — the clamp fix landed, then the row-padding
half of the same defect was found by measuring it.

## [1.7.0] — 2026-09-03

feat: named queries — the SQL and the Python that calls it, in one workspace.

Batch E. The Designer keeps named queries in a different workspace from scripts,
and Nigel's brief is that they are ONE piece of work: a script calling
`system.db.runNamedQuery("Orders/Insert", …)` and the query it names are edited
together or not at all.

Everything in `docs/NAMED-QUERIES.md` §1 was **measured** — off the platform jars
and then off the running 8.3.8 gateway through this module's own exec socket —
before a line was written. That was the right call three times over; see
"What the platform actually holds" below.

### Added
- **A Named Queries view** on the activity bar: folders from the path, create,
  rename (queries AND folders), delete, with inherited/override badges matching
  the script tree.
- **A SQL editor** with `@codemirror/lang-sql`, sharing the script editor's theme,
  gutters and byte-fidelity facets — so a tab means the same thing in both.
- **Settings, Authoring and Testing**, the Designer's own three concerns: type,
  database, caching, fallback, max return size, auto-batch, permissions, and
  typed parameters with the platform's ten legal SQL types.
- **A test run** against the live database, with a parameter form and a result
  grid — and it runs **the draft, not the saved copy**, through the
  prepared-statement route with `:identifier` placeholders converted to
  positional `?`. Testing what is on screen is the whole point; testing the saved
  version while showing the draft is the class of quiet lie this module keeps
  finding. A `QueryString` parameter substitutes textually, because that is its
  platform semantic.
- **Named queries in quick open** (Ctrl+P), ranked in ONE list with scripts
  rather than appended after them.
- **Five routes** under `/api/named-queries` — listing, content, settings, rename
  and test. `<path>` is the project-relative query path (`Folder/Sub/Name`), the
  same string `runNamedQuery` takes, with no resource prefix.

### What the platform actually holds (measured, and three of these contradicted the design)
- **There is no `Value` parameter type.** The enum names are `Database`,
  `QueryString` and **`Parameter`**; `Parameter.toString()` returns `"Value"`,
  which is the Designer's LABEL — exactly as `ScalarQuery.toString()` returns
  "Scalar Query". The wire carries the name; `Value` is accepted as an alias.
- **`cacheUnit` has eight values, not seven** — `MS` was missing from the design.
- **`description` is not an attribute.** `toResource` writes it to the resource's
  `documentation` while `fromResource` reads it from the attributes, so the
  platform's own writer and reader disagree about it. This module reads
  `getDocumentation()` with an attribute fallback and writes only through
  `toResource`.
- **`isValidParamName("database")` is false, yet `database` is exactly what the
  Designer names a `Database` parameter** — the reserved name is required for
  that one kind and refused for every other.
- **A parameter's `sqlType` is written as an INTEGER** (`String` is 7), by the
  registered Gson adapter. Ten types are legal, and `Date` is not one of them.

### Fixed
- **A version-1 named query is DEAD, and this release makes that visible.**
  `fromResource` returns a blank query whatever its attributes say — with or
  without a deserializer — and so does the platform:
  `system.db.runNamedQuery` on one throws
  `NullPointerException: … getType() is null`. **All 37 queries in the rig's
  `Whiteboard` project are in that state.** They list with a `legacy` badge, open
  with their SQL intact and a notice saying the gateway cannot run them, and a
  save repairs them by putting the resource back through `toResource`. The write
  path deliberately does not short-circuit on unchanged settings, or the repair
  would silently do nothing, and it falls back to the `query.sql` data key so the
  repair cannot erase the SQL. Both halves are pinned by tests.

### Added — the themes pass (batch F)

Nigel, 02/09/2026: "The themes in this project don't look nothing like what they
do in the perspective projects. Why? Aren't they equally as nice?" He was right,
and the answer was scope: a Perspective gateway theme is a ~1,300-line
`globals.css` with 40 tokens plus component chrome, while this module emitted
**nineteen tokens per theme, all colour**. Ten themes, one shape.

- **The packs' GEOMETRY is now taken as well as their colour** — control, panel
  and row radius, marker and rule widths, row and control height, and popup
  shadow. That is the axis that differentiates without risk, because geometry
  cannot make text illegible. `newsprint-night` is square and flush with 24px
  rows and no shadow; `aurora-*` is 12px-rounded with a deep shadow; the two
  `industrial` packs sit at 20px rows and 2–6px radius. Values are the packs'
  own, clamped into a band the chrome can wear.
- **`--border-light` and `--border-strong` carry the pack's own line colour**,
  held in a 1.5–4.0:1 band against the page. This is the ONE pack surface colour
  that reaches the IDE, and it is safe for the exact reason the 1.2.0 mapping was
  not: nothing is ever painted *on* a border. Translucent pack values are refused
  rather than flattened, because dropping the alpha on
  `rgba(255,255,255,0.22)` yields white.
- **A `--bg-chrome` for the activity bar**, derived from the page and stepped by
  a "softness" score built from the pack's geometry: flat packs separate their
  furniture with a step, soft packs sit flush and let the border do it.

**What was deliberately NOT done, and why.** No `surface.*` token is mapped onto
`--bg-secondary`, `--surface` or `--bg-tertiary`. That is precisely the 1.2.0
defect — a Perspective pack is a SEMANTIC palette, not a lightness ramp, and a
"sidebar" is branded chrome that is dark navy in a light theme — and nothing has
changed to make it safe. `--border-width` is not emitted either: all ten packs
say 1px, so it would be a token nobody reads. `font.body` stays dropped, and a
new test now fails on ANY `font-*` property in a theme block rather than only the
two stacks it knew by name.

### Fixed
- **A shadow that exists must be visible.** Four rounded themes were generating
  `0 3px 6px` at 0.18 alpha, which a pixel transect across the popup edge could
  not find at all — worse-separated than the themes that deliberately have none.
  A floor now puts any popup shadow at `0 6px 16px` and 0.22 alpha or better.

### Known, and Nigel's call rather than a generator change
- **`industrial-day-cyan` resolves `--error` to a grey** (`#575757`), and
  `--success` likewise. That pack's red cannot clear 4.5:1 on its light surfaces
  without losing its hue. Fixing it means either accepting less than 4.5:1 or
  repainting the pack.

### Measured on the rig (1.7.0, 8.3.8)
- Java **338 tests** (was 211; 127 new across six suites, `RouteMountOrderTest`
  extended from 3 to 6). Vitest **446** (was 312).
- Painted-element contrast sweep: **no illegible themes, nothing below 4.5**,
  worst element 5.07. Four themes IMPROVED on their 1.6.1 figures
  (`newsprint-night` 5.41 → 6.21, `industrial-control-cyan` 5.37 → 5.97,
  `leather-night-tan` 5.47 → 5.94, `industrial-day-cyan` 5.18 → 5.54).

## [1.6.1] — 2026-09-02

fix: the console could not run a function or a class — every script with one raised NameError.

### Fixed
- **`PrivateStateRunner` ran a script's locals and globals as two different
  dicts.** It called `Py.runCode(code, locals, scriptManager.getGlobals())`, so
  a module-level assignment (`x = 41`) landed in `locals` while a function or
  class body closes over `globals` — which was the manager's own, unrelated,
  and empty of anything the script had just defined. Any script with a `def` or
  a `class` raised `NameError: global name 'x' is not defined` the moment the
  function was called, including `def f(): return system.date.now()`. It now
  runs `Py.runCode(code, locals, locals)` — one dict, so a function sees the
  names its own script defined, `system` included, because `system` is seeded
  into `locals` before the run. `ExecNamespaceTest` covers it with 6 cases.
- **No suite had caught it.** Every existing exec check across `validate_p1_p2.py`
  and `validate_v15_exec.py` is a one-liner or a bare expression — none of them
  define a function. A one-liner cannot fail this way, so a green gate on every
  prior release proved nothing about the one construct the bug lived in.
  `validate_v15_exec.py` now carries a permanent check, "NAMESPACE: a function
  sees the script's own names", that defines a module-level name and reads it
  back from inside a function.

### Measured on the rig (1.6.1, 8.3.8)
- `deploy_gate.py` PASS (6).
- Live socket probe, five cases that all raised `NameError` before this fix and
  now all return a value: module-level var seen by a function → `'42'`;
  module-level import seen by a function → `'1.0'`; `globals()` identity — the
  module-level and in-function key lists match; a class body reading a
  module-level name → `'7'`; `system.*` inside a function → `'True'`.
- Regression: `validate_v15_exec.py` **20/20** (19 plus the new NAMESPACE
  check), `validate_p1_p2.py` 8/8.

## [1.6.0] — 2026-09-02

feat: the IDE navigates a project — go-to-definition, quick open, search, references and problems.

Batch D of the 02/09/2026 review queue. Everything the gateway needed for this
was answered from 1.0.0 and called by NOTHING: `textDocument/definition`,
`workspace/symbol` and the module's own `scriptide/searchText` all worked,
`lspClient` wrapped all three, and no component invoked any of them. P4 read
"done" and the product had an outline and Ctrl+F. This release is the join.

### Added
- **Go to definition — F12 and Ctrl-click**, across files. A platform call like
  `system.tag.readBlocking` has no source on this gateway and stays SILENT: a
  dialog on every F12 over a `system.` call teaches people not to press it.
- **Quick open — Ctrl+P** over the script tree, subsequence-matched, with `#`
  (or Ctrl+T) switching to project symbols from the AST index. The prefix is the
  guarantee and the shortcut the convenience: Chrome refuses Ctrl+T outright and
  it cannot be intercepted.
- **A Search view** on the activity bar, over `scriptide/searchText` — the view
  `ActivityBar` had said was missing since P4. Results are grouped by file and
  click to open at the line.
- **Name-based references — Shift+F12**, over a new `scriptide/references`.
  Deliberately NOT `textDocument/references`: that method promises a type-aware
  answer this server cannot give, and answering it would be lying in the
  protocol. The server matches whole IDENTIFIERS, so `compute` no longer matches
  `recompute`, and the results panel says on screen that the match is by name.
- **A Problems panel**, third tab in the bottom dock, listing every OPEN
  document's diagnostics with the errors first; click to jump. The inline
  squiggle and the gutter marker are per-file, so with six tabs open a syntax
  error in the one you are not looking at was invisible. The empty state says
  only open scripts are checked, so it cannot be read as "the project is clean".
- **A fold gutter** on files (not the console, which shares the same editing
  surface and has no use for it) and **go-to-line on Ctrl+G**, which is what
  people press — CodeMirror's own binding is Mod-Alt-g.

### Changed
- **The script tree ships COLLAPSED and no longer lists Web Dev endpoints**
  (Nigel, 02/09/2026). Quick open is the fast path now, so the tree is for
  browsing, which starts by choosing a branch; and Web Dev has its own
  activity-bar view with per-endpoint verbs and the config dialog, so listing
  endpoints in both made the poorer entry point the first one people found. A
  type this build has never heard of still gets a row — that is a different case
  from "handled elsewhere", and silently dropping a resource the gateway sent is
  how a script becomes uneditable with no message.
- **`ETag` is a quoted entity tag**, per RFC 9110 §8.8.3, and `If-Match` is now
  parsed tolerantly (`W/` and quotes stripped). Both halves matter together: a
  page loaded before this holds a bare signature, one loaded after holds a value
  its own reader already stripped, and a proxy may quote either — comparing raw
  strings turns any of those into a permanent 409 that reads on screen as
  somebody else editing the file.
- **The bottom panel opens at 34% of the viewport** (clamped 240–460px) instead
  of a fixed 260px, which was measured cramped at 1000px in the 02/09 review:
  340px there now.
- `LspClient.searchText` sends `caseSensitive`. The server has read that flag
  since 1.0.0 and the client never sent it, so "Match case" could not have
  worked whatever a UI offered.

### Fixed
- **A cross-file jump landed the caret on line 1.** Opening the target is React
  state, so the CodeMirror view for it does not exist when the reveal is
  published — the editor dropped it silently. It now holds one pending reveal
  and applies it when the view appears, which also fixes the clicked-traceback
  frame path that had carried the bug since 1.5.0.
- **The completion panel's signature-twice rule had nothing asserting it.**
  Fixed in 1.5.0 and untested, which is how it comes back; the rule is a pure
  function (`detailToShow`) with its own cases now.
- **`validate_p1_p2.py` had been reporting 0 lines of output since 1.5.0** and
  was not a gate. It read `finished.stdout`, which 1.5.0 emptied by contract —
  every line goes out as an `output` frame, and `deploy_gate.py` was updated at
  the time while this file was not. Byte fidelity and the 500/500 concurrency
  isolation check are live again.
- **`validate_v14.py` crashed** when its fixture project was absent (the
  water-suite projects have gone from the rig), taking the terminal, hint-scope
  and chrome checks down with the inheritance ones. An absent fixture is a
  stated SKIP now, as it already was in `validate_v15_tree.py`.

### Measured on the rig (1.6.0, 8.3.8)
- `deploy_gate.py` PASS (6). `validate_v16_nav.py` **25/25** — quick open by
  path and by symbol, F12 opening the defining file with the caret on
  `def compute`, references finding three sites and NOT `recompute`, Match case
  changing the answer, a syntax error in a background tab reaching the Problems
  panel, the fold gutter, Ctrl+G, a quoted ETag round-tripping through If-Match,
  and a 340px panel at a 1000px viewport.
- Regression: `validate_p1_p2` 8/8, `validate_lsp` 10/10, `validate_v11` 12/12,
  `validate_v13` 22/22, `validate_v14` 18/18 (4 stated skips), `validate_v15_term`
  6/6, `validate_v15_exec` 19/19, `validate_v15_tree` 15/15 (1 stated skip).
- Vitest 217 → **312 checks**; the Java suite gained `ProjectIndexReferencesTest`
  and the entity-tag cases in `HandlerSupportTest`.

## [1.5.4] — 2026-09-02

feat: the project listing says where inherited scripts come from.

### Added
- **`GET /api/projects` now carries `parent` and `inheritable`** for each
  project. A child of a non-inheritable parent lists no inherited scripts, and
  without these two fields that was indistinguishable from the listing being
  broken — the Ignition web UI exposes neither over a GET. Unit-tested.

### Changed
- `validate_v15_tree.py` SKIPs the read-only checks, with the reason printed,
  when the fixture's parent is not marked Inheritable on the target gateway,
  instead of failing on a property of the rig.

## [1.5.3] — 2026-09-02

fix: typed input never reached the terminal's shell, and closing it leaked a root shell.

### Fixed
- **Keystrokes were swallowed by the Docker terminal until the shell produced
  output, and closing it left the root shell running.** The hijacked
  `/exec/{id}/start` socket was wrapped with `Channels.newInputStream` and
  `Channels.newOutputStream`, and both of those `synchronized` on the channel's
  `blockingLock()` around every call — so with the pump thread parked in
  `read()` waiting for the shell, every `write()` from the socket thread waited
  for it, and the shell was waiting for the write. A prompt appeared (the first
  read returns), then nothing typed arrived, and `close()` hung on its own ETX
  write so the sweep never ran: measured on the rig as 3+ leaked `bash -i` per
  session. `DockerExec` now reads and writes the `SocketChannel` directly
  through its own `ChannelInput`/`ChannelOutput`, which use the channel's
  separate read and write locks. `ChannelStreamsTest` proves the JDK adapters
  cannot write while a read is parked and that the wrappers can.

### Measured on the rig (1.5.4)
- `validate_v15_term.py` 6/6: prompt in 0.31 s; `SCRIPTIDE_TERM` tag present;
  closing the browser ended the shell and its backgrounded `sleep 300` in
  0.8 s; no `bash -i` left in the container.
- `validate_v15_exec.py` 19/19: the terminal answers 3.0 s into a 20 s loop;
  Stop lands in 0.2 s; streaming, tracebacks, REPL locals and reset all pass.
- `validate_v15_tree.py` 15/15 with the read-only checks skipped as above.

## [1.5.2] — 2026-09-02

fix: a terminal opened before its socket did, on a tab nothing else had used.

### Fixed
- **A terminal could open a shell and never show a prompt.** On a tab where
  nothing else had used the socket, mounting the terminal called `open()` before
  the connection existed; `send()` starts the connection lazily but still
  returns `false` for the frame that triggered it, so the open request was
  dropped and never retried — the xterm mounted and the prompt never came.
  `TermClient.open()` now defers the frame to the transport's next `onOpen` when
  it cannot send immediately, and returns a disposer the view calls on unmount so
  a tab closed in that window does not get a shell opened for it afterwards.
  Unit-tested.

## [1.5.1] — 2026-09-02

fix: a stopped script poisoned its executor thread, and the next run on it was
cancelled at once.

### Fixed
- **Stopping a script left the pool thread it ran on unusable.**
  `ScriptManager.interrupt` installs a `BreakTraceFunction` on the running frame,
  and its throw escapes before the handler pops the frame, so
  `ThreadState.frame` is left pointing at the dead frame with the trace function
  still attached — measured on 1.5.0: every later run on that thread came back
  cancelled with no output and no error. `PrivateStateRunner` now snapshots
  `ThreadState.frame`/`tracefunc`/`exception` before a run and restores them in
  `finally` (`FrameSnapshot`). `PrivateStateRunnerStopTest` drives the real
  `ScriptManager.interrupt` as its regression test. Verified live: a run stopped
  mid-loop, two later runs on the same thread complete.

## [1.5.0] — 2026-09-02

A socket that keeps listening, and a shell that actually dies. Review fixes
across the exec channel, the terminal and policy — most of them invisible from
the page, which is why `scripts/testing/validate_v15_{exec,term,tree}.py` exist.

### Fixed
- **The exec frame handler no longer waits for the script.** `ScriptIdeSocket`
  is an `AutoDemanding` listener — one frame at a time, on the socket thread —
  and the run branch used to block there until the script finished: measured on
  1.4.3, a Stop sent 1.5 s into a 20 s busy loop was not read until the loop had
  run its full 20.0 s, and every ping, LSP request and terminal keystroke queued
  behind it. `ExecutionService.submit` now returns the moment the pool accepts
  the work; `started`, `output` and `finished` arrive through callbacks, and the
  timeout ladder moved off a `future.get(deadline)` onto the watchdog. Closing
  the socket now stops whatever that session was running (`stopAllFor`).
- **Tracebacks are structured, and no internal token reaches the screen.** The
  client had invented its own field names against a server payload of
  `{type, message, rendered, frames}`, so nothing matched and every frame read
  `<console>, line N` with no function and no exception type. A syntax error is
  now unpacked from its raw `(msg, (file, line, offset, text))` tuple instead of
  rendered with `toString()`, and the console draws a caret under the reported
  column.
- **A Docker exec's resize needs to happen after the attach, never before.** A
  `POST /exec/{id}/resize` sent before `/exec/{id}/start` has no exec session to
  size — the daemon blocks and answers `500 timeout waiting for exec session
  ready`, and the five-second watchdog cut that short, which is why every 1.4.x
  terminal took exactly 5.00 s to open and the resize never applied. Attach
  first and the same call returns 200 in about 90 ms; `DockerExec.start` retries
  it three times at 100 ms because the session becomes ready a moment after the
  upgrade.
- **Closing a terminal did not close it.** The Engine API has no "kill this
  exec": the daemon keeps a closed session's shell running, detached, forever —
  measured 02/09/2026 at 38 orphaned root `bash -i` in the test container, one
  per terminal ever opened, with the 120-minute idle reaper calling the same
  no-op every time. Close now sends ETX, EOT and `exit`, polls `Running:false`
  for up to 750 ms, and always runs a root sweep exec that walks
  `/proc/*/environ` for `SCRIPTIDE_TERM=<terminal id>` and kills what it finds,
  so a backgrounded child goes with its parent. `TerminalService.shutdown` waits
  on the sweep before returning, because it runs on a daemon thread. The
  `script(1)` route got its own escalation: `destroy()`, then
  `destroyForcibly()` 300 ms later, because an interactive bash ignores SIGTERM.
- **Policy switches were read once, at JVM start.** `PolicySource` now resolves
  every `ExecPolicy` and `TerminalPolicy` value live, as file > `-D` system
  property > default, from `<data dir>/modules/scriptide/policy.properties`,
  re-statted at most once every 2 s. The module never creates the file — absent
  means no overrides, which is where every existing gateway already is. "Turn
  it off without a restart" had been true of the code and false of the gateway.
- **An empty Project Library package rendered as an openable script.** The
  platform reports it as a resource with `dataKeys: []`; clicking it 404'd with
  "No such data key `code.py`". It is marked `isFolder` in the tree JSON now,
  scoped to `script-python`, the only resource type that nests.
- **Clicking an absent Startup/Shutdown/Update row wrote a resource on the
  click.** Browsing the tree wrote into a live project with no confirmation. It
  now opens a draft with no ETag; the first save creates the resource through
  the ordinary create path, and a create raced by somebody else comes back 428,
  not 409 — there is no base signature to send.
- **`HintIndex` printed a Kotlin data class instead of a type name.** The
  completion doc panel showed `TypeDescriptor(name=None, description=null, …)`
  for every return type; it calls `getName()` now. The panel also printed the
  signature twice, because the server's markdown already opens with `detail` in
  a fenced block.

### Added
- **The `finished` frame carries no stdout or stderr, by contract** — everything
  has already gone out as `output` frames as it was produced. A chunk is
  flushed on a newline, at 4 KB, or every 100 ms, with the UTF-8 decoder kept
  across flushes so a multi-byte character landing on a chunk boundary does not
  become two replacement glyphs. The console renders a `▸ run N · HH:MM:SS`
  divider, merges consecutive chunks of one stream into a block, and closes
  with `— finished in N.N s —` / `— stopped —` / `— failed —`.
- Two states the UI was not saying: an inherited, not-yet-overridden tab is
  labelled `(Read-Only)`, matching the Designer's own buffer header; the
  footer has an `idle` state for the LSP's lazy connect, so the landing page no
  longer shows "Language server offline" in red for a connection that was never
  attempted.
- The 1.5.0 validation harness — `scripts/testing/validate_v15_exec.py`,
  `validate_v15_term.py`, `validate_v15_tree.py` — was written against this
  release. Against 1.5.0–1.5.2 on the rig it found two more defects (the
  terminal's deferred open, 1.5.2, and the channel-lock deadlock, 1.5.3); it
  first ran fully green on 1.5.4.

## [1.4.3] — 2026-09-02

fix: the Docker route was never reachable, and the last terminal line was
clipped.

### Fixed
- **The Docker route reported itself absent on a socket that worked fine.**
  `SocketChannel.socket()` throws `UnsupportedOperationException` on a
  Unix-domain channel — it is specified to for any non-IP-based channel — so
  1.4.2's `connect()` call to set a read timeout threw on EVERY Docker API
  request, `available()` caught it as "the socket is unusable", and the whole
  route reported itself absent on a host where the socket was mounted,
  readable, writable and working. The only symptom was an unprivileged shell
  and one log line reading `elevation=none`. Timeouts now come from a watchdog
  that closes the channel, raising `AsynchronousCloseException` on the blocked
  read — the supported way to interrupt one — and a mounted-but-unusable
  socket logs a WARN rather than a debug line, because somebody deliberately
  mounted it. Verified on the live gateway: `elevation=docker-exec`, uid 0, on
  a stock image with no sudo anywhere in it.
- **A fitted terminal cut off its own last line** (Nigel: "The bottom of the
  text seems to be getting cut off even though its a full screen?"). xterm's
  `FitAddon` sizes from the computed height of the element the canvas sits in
  and does not subtract that element's own padding, so 8px of `padding-top`
  fitted 11 rows — 220px — into a 216px content area, and `overflow: hidden`
  ate the bottom 4px of the last line. Measured on the live gateway: host
  224px tall, rows 220px. The inset moved to the wrapper; the gate now asserts
  both zero vertical padding on the fitted element and that the rows fit
  inside it.

### Changed
- **The rig is back on a stock image** (Nigel: "We will not be using custom
  ignition images."). The image built 01/09 is deleted, `Dockerfile.test` with
  it, and the gateway runs `inductiveautomation/ignition:8.3.8` verbatim — the
  socket mount is a compose change and never needed a build.

### Added
- `validate_v13`'s terminal INPUT checks are removed, with the reason written
  into the file rather than glossed over: they stopped receiving any input in
  that suite's page state, not even a bare Enter, while identical code in
  `validate_v14` types and reads back fine on the same build and gateway. The
  cause is NOT found; input coverage lives in `validate_v14`.

### Verified
Gate 6/6 · validate_v14 25/25 · v13 22/22 · v11 12/12 · lsp 10/10 · p1_p2 8/8 ·
theme sweep clean. 192 frontend tests, Java green, SpotBugs clean.

## [1.4.2] — 2026-09-02

feat: chrome sizing, one chrome row, and a Docker route to root.

Nigel, on the 1.4.1 screenshot: "The drop downs all seem to be squished like
they are not the right size for the rest of the designed layout and the save
script button is bleeding into the edges... can't you make the hint scope &
Read only/override stuff all on 1 line so that it doesn't reduce the script
window unecessarily?"

### Fixed
- **There was no height token for chrome controls.** Every control carried its
  own `padding: 1px ...` and no height, so it was sized from its content, and a
  `<select>` and a `<button>` with identical padding came out different
  heights — in a 30px bar both looked squashed and the Save button ran into
  the border. `--control-height: 24px` now applies to the project picker, the
  theme picker, both save buttons and the hint scope; the toolbar is 34px.
- **`.workspace-toolbar` was declared twice, forty lines apart.** The later
  block won on gap and padding while the earlier one kept the height, which is
  how a 30px bar ended up with 2px of vertical padding — the same trap
  `FileTree.css` already carries a warning about. One rule now.
- **The theme select was capped at 190px**, truncating the longest theme name
  in the one control whose whole job is naming it.
- **The inheritance notice cost two chrome rows.** It was its own bar below
  the settings strip, so an inherited script paid ~105px above the code for
  two short sentences that are never both true at once. It is the settings
  strip's `leading` element now — measured 69px.

### Added
- **A Docker route to root.** A process cannot raise its own privilege; only
  something already more privileged can create a privileged process for it.
  The Docker daemon runs as root on the host, so `DockerExec` asks it for an
  exec with `User:"0"` and it simply creates one — nothing in the image, no
  sudo, no setuid binary, not even `script(1)`. The pty comes from the daemon
  rather than being borrowed from a session recorder, resize is an API call
  instead of a typed `stty`, and close reaches the shell as the daemon's own
  child, where a sudo-elevated root shell is a process this JVM cannot signal
  at all. ~380 lines of hand-rolled HTTP/1.1 over the Unix socket (Java 17
  ships this in the JDK) rather than `docker-java` (a large
  `modlImplementation` for four requests) or the `docker` CLI (a dependency
  back in the image this route exists to remove).
- **The two elevation routes get separate switches.** sudo grants root inside
  this container; the Docker socket is the daemon's full API as root ON THE
  HOST — the larger grant despite the tidier mechanism, and `SECURITY.md` says
  so in those words. `terminal.docker=false` refuses it while keeping sudo.
- Three traps that would have been silent bugs: `hostname` does NOT identify
  the container under `network_mode: host` (it returns the workstation's
  name) — `ContainerIdentity` reads `/proc/self/mountinfo` instead, verified
  against `docker inspect`. `Tty: true` does two jobs, a real pty AND a raw
  stream, so `Tty: false` reaches xterm.js as garbage behind an 8-byte frame
  header. And the hijacked connection's headers must be read a byte at a
  time, or a `BufferedReader` reads ahead into the terminal stream and the
  first thing typed disappears.

### Changed
- The rig's `Dockerfile.test` drops sudo and its sudoers rule; keeping a
  permanent container-wide root grant beside the socket route would have
  doubled the exposure for no gain. git stays.

### Verified
On 8.3.8: gate 6/6 · validate_v14 23/23 (one-height controls, Save-button
clearance, 69px of chrome above the code) · v13 25/25 · v11 12/12 · lsp 10/10
· p1_p2 8/8 · theme sweep clean. 192 frontend tests, Java suite green,
SpotBugs clean.

## [1.4.1] — 2026-09-01

fix: Script Hint Scope is small, last on the strip, and silent.

Nigel, on the 1.4.0 strip: "I had never even noticed it was there and never
needed to use it. So lets make it a bit the same. out of the way over on the
right hand side if possible. Remove all the text explanation."

### Fixed
- **Script Hint Scope is a small, silent control at the top-right of the
  editor header, matching the real Designer.** 1.4.0 correctly identified that
  the control is obscure and then drew the wrong conclusion — it gave the
  rarest setting in the module a paragraph of prose, which made it the
  loudest thing on the row. Matching a Designer control means matching how
  much room it takes up, not only what it is called. `FIELD_HELP` is gone
  entirely, and `hintScope` is a `TRAILING_FIELD` — ordered after the save
  button so it is the LAST thing on the strip and sits against its right
  edge. The push comes from `.config-save`'s existing `margin-left: auto`;
  giving the field its own auto margin instead left it stranded mid-strip
  with the save button beyond it, which is the one place it must not be. The
  live check now asserts "last on the strip", not "right of centre", because
  the first version of that assertion passed on exactly that wrong layout.

### Changed
- What the removed paragraph said is kept in the `TRAILING_FIELDS` comment —
  the measured filter behaviour and the caveat that "None" shows the widest
  list rather than switching hints off. Worth knowing, not worth screen
  space.

### Verified
On ignition-module-testing 8.3.8: gate 6/6 · validate_v14 19/19 · v13 25/25 ·
v11 12/12 · lsp 10/10 · p1_p2 8/8. 192 frontend tests.

## [1.4.0] — 2026-09-01

feat: inherited scripts are read-only, and a root terminal.

Three things Nigel asked for, one of which needed the real Designer driven
rather than recalled.

### Added
- **Inherited Project Library scripts are read-only until overridden.**
  Measured with `designer-drive` against `Site_Redgum_Sewer` ▸ `Template` on
  the module-testing gateway, 01/09/2026, because parity cannot be built from
  memory: double-clicking an inherited script does nothing; its context menu
  is exactly `Override Resource` / `Copy Path` / `Open read-only`; `Open
  read-only` heads the editor `(Read-Only)` and discards typing — four
  characters typed, buffer byte-identical. `Override Resource` writes
  nothing — the gateway's own filesystem still had no local copy afterwards —
  and an overridden resource's menu has no `Delete`, only `Discard
  Overrides`, whose dialog says "return to its inherited state? All local
  changes will be lost." `isLockedByInheritance` is the single rule; both
  save paths check it, because the keybinding does not go through the
  disabled button. Read-only is reconfigured per view, keyed on the doc, so
  overriding one tab does not unlock the strip. One deliberate deviation from
  the Designer: an already-open read-only tab stays read-only after you
  override.
- **The terminal is root, where the host allows it.** `terminal.privileged`
  defaults true and runs `sudo -n -H <shell> -i`. It cannot manufacture
  privilege — elevation happens only where `sudo -n true` already succeeds
  for the Gateway's OS user, proved by running it rather than parsing
  `/etc/sudoers`, and on a stock Ignition image it does not. `-n` is
  load-bearing; without it a prompting host hangs the shell. Elevation goes
  INSIDE the pty so `script` stays a process this JVM can signal. The
  sudoers rule lives in `modules/dockers/ignition/Dockerfile.test`, not in
  this module.
- **Script Hint Scope**, the Designer's own control, renamed and reordered
  from a bitmask ordering to the Designer's measured one (None · Designer ·
  Gateway · All) and explained on its own row, including the measured
  caveat that "None" shows the WIDEST list rather than switching hints off.

### Fixed
- **A CSS `max-width` on a flex item defeats `flex-basis: 100%`**, because the
  hypothetical main size is clamped before line-breaking. The Script Hint
  Scope help line sat beside the control instead of below it and every test
  passed — found only by looking at a screenshot.

### Verified
On ignition-module-testing 8.3.8: deploy gate 6/6 · validate_v14 17/17 ·
validate_v13 25/25 · validate_v11 12/12 · validate_lsp 10/10 ·
validate_p1_p2 8/8 · theme sweep 10/10 with no illegible text. 192 frontend
tests, Java suite green.

## [1.3.1] — 2026-09-01

Font rendering, measured side by side against VS Code (Nigel).

### Fixed
- **`-webkit-font-smoothing: antialiased` is gone.** 1.3.0 set it believing it
  would lighten heavy stems; on Linux it does the opposite of what was wanted.
  The platform default there is SUBPIXEL (RGB) antialiasing — the thing that
  makes small text crisp on an LCD — and `antialiased` forces greyscale, which
  is thinner and visibly softer. It is macOS advice, copied onto a Linux app.
  VS Code uses the platform default; so do we now. No automated check can see
  this, which is the same shape of problem as Chrome's auto dark mode.
- **`ui-monospace` moved off the front of the mono stack.** Measured in Chrome
  on Linux: `13px ui-monospace` on its own is **not monospaced** —
  `iiiiiiiiii` renders 36.1px wide against `WWWWWWWWWW` at 122.7px, because the
  keyword is unrecognised here and falls through to the default proportional
  face. Inside a stack Chrome currently skips it and the next entry wins, so the
  editor was correct by luck; the day a Chrome build resolves it through
  fontconfig, a code editor set in a proportional font is what ships. Named
  faces come first now.

### Changed
- **Code is 14px with 1.4 leading**, which is VS Code's split — 13px chrome,
  14px code. It was 13px at 1.55, smaller type with more air between the lines,
  and that reads looser and lighter than the editor beside it. The terminal
  reads the same token, so a character cell is identical in both.

### Added
- The browser suite measures the editor's **advance width** rather than reading
  its font-family string, and asserts the platform's antialiasing is in force.
  A stack whose name contains "mono" proves nothing about what was drawn.

## [1.3.0] — 2026-09-01

A terminal on the Gateway, a bottom panel, and Gateway Events measured against
the real Designer.

### Added
- **Terminal.** A real shell on a real pseudo-terminal, in the browser, running
  as the Gateway's own operating-system user — prompt, echo, history, Ctrl-C,
  colour. Java has no pty API and a JNI library would have to be signed and
  shipped per architecture, so the pty comes from **`script(1)`**:
  `script -q -c "tty > F; stty cols C rows R; exec /bin/bash -i" /dev/null`. The
  command given to `-c` is not echoed by the pty, which is what lets the size be
  set and the slave path captured without either appearing on the user's screen;
  the captured path is then what a later `stty -F` resizes, so dragging the panel
  does not type into the shell. Gated on Administrator + CSRF + same-origin with
  its **own** kill switch, so a site can keep the Script Console and refuse the
  shell — see `SECURITY.md`.
- **A bottom panel**, VS Code's dock, holding Script Console and Terminal. The
  console was a pane beside the editor and split the width with it; a console
  prints lines and wants to be wide and short (Nigel).
- **The four VS Code layout glyphs** in the toolbar: a customise-layout menu and
  a toggle each for the side bar, the panel and the outline. They replace the
  1.2.0 "Console" and "Outline" text buttons.
- **Startup, Shutdown and Update can be created from the tree.** A singleton the
  project does not have is still listed, dimmed; clicking it creates the script
  and opens it.
- `Dockerfile.test` beside the gateway's compose file, adding git, ssh and less.
  git is NOT in the stock Ignition image and cannot be installed from inside the
  terminal — the Gateway runs as uid 2003 with no sudo, so it has to be in the
  image.

### Fixed
- **"Glass Aurora — Teal" rendered violet, and was indistinguishable from
  "Glass Aurora — Violet"** (Nigel). The two packs differ in exactly two tokens,
  `accent.primary` and `accent.progress`; everything else, including
  `surface.page`, is identical. The 1.2.0 resolver walked a candidate list and
  took the first token that PASSED contrast, so teal's dark `#0f766e` failed and
  it fell through to `text.status-info` — a token both packs share verbatim. The
  list is now a fallback for a token that is ABSENT, not one that is dark: the
  brand colour is kept and lifted in HSL, hue and saturation intact. The neutral
  ground carries a trace of the brand too (hue only, the page's own lightness
  restored), which is what makes two sibling themes tell apart at a glance.
  **A build-time assertion now fails if any two themes generate the same
  palette** — the 1.2.0 bug shipped because nothing compared one theme's output
  against another's.
- **`hidden` did not hide.** `[hidden] { display: none }` from the user agent has
  the same specificity as any `.thing { display: flex }`, so the later rule won:
  both panel tabs rendered at once and shared the panel's height, leaving the
  terminal 39px tall and two rows deep, and a maximised panel did not hide the
  editor. Forced globally now.
- **A class-name collision sized the bottom panel wrong.** `App.css` styled a
  generic `.panel` card for the signed-out state; the dock's own `.panel` picked
  up its `max-width: 640px` and padding and rendered 640px wide inside a 1050px
  slot. The card is `.notice-card` now.
- **Gateway Events did not match the Designer.** Measured off an 8.3 Designer
  (`SCRIPTING.md` §1, captured 21/08/2026): the four folders come first, in the
  order Message / Scheduled / Tag Change / Timer, then Shutdown, Startup and
  Update as **single scripts**. This module listed the singletons first and
  rendered each as a collapsible folder containing one nameless row — two things
  the Designer does not do. Singletons are bold once created, and a disabled
  event script now carries the badge the Designer shows.
- **A timer's Delay Type is a radio pair**, ● Fixed Delay / ○ Fixed Rate, as the
  Designer has it. It was a checkbox labelled "Fixed delay", which leaves the
  reader to work out what unticking it does — and the answer, "fixed rate", never
  appeared on screen. The Timer description is the Designer's verbatim wording
  now rather than a paraphrase.

### Changed
- **Typography.** The UI font is no longer taken from the theme pack: a pack
  names a typeface as part of a brand — `newsprint-night` asks for Georgia — and
  the whole IDE was rendering in a serif on that theme. Both stacks now name
  faces that exist on a Linux desktop; VS Code's own default of `'Droid Sans
  Mono', monospace` names a font that ships on no current distribution, so the
  editor had been falling through to whatever fontconfig aliases `monospace` to.
  Type scale is VS Code's three sizes, 22px rows, 35px title and tab bars, and a
  30px toolbar.
- **Body text is softer.** The generator targeted 13:1, which renders very close
  to white; VS Code's own default is 10.4:1. Now 10.5:1, still well past WCAG
  AAA. All ten themes measured in the browser: worst element 5.08:1, none below
  4.5:1.
- **Script Console is out of the tree.** It read as a script among scripts; it
  has an activity-bar icon and a panel tab now (Nigel).
- **The Search icon is gone** from the activity bar. It opened the script tree
  under the heading "Scripting" — a promise of a view that does not exist. Find
  and replace are on Ctrl+F and Ctrl+H in the editor and the console.
- Inheritance badges are lower case and unboxed. Six boxed uppercase `INHERITED`
  badges down one rail were more ink than the script names they annotated.

### Verified
Deploy gate 6/6 · v1.1 regression 12/12 · LSP 10/10 · new v1.3 browser suite
24/24 (tree parity, layout, panel, terminal, fonts, themes) · theme legibility
10/10 with no element below 4.5:1 · 122 Java and 177 frontend tests.

## [1.2.0] — 2026-09-01

A VS Code-shaped shell, and Web Dev as a first-class view.

### Fixed
- **Five of the ten themes were illegible**, measured in the browser rather than
  reported. The cause was a design error: the generator mapped Perspective's
  SEMANTIC surfaces onto the IDE's lightness ramp, and a Perspective "sidebar" is
  branded chrome — dark navy in `finance-ledger` even though that theme is light,
  and `rgba(255,255,255,0.06)` in the glass themes, which is not a colour at all.
  Body text landed on it at 1.7–2.1:1. The generator's own check passed
  throughout because it measured against `--bg-primary` while the app paints most
  of its text on `--bg-secondary`.
  The neutrals are now DERIVED from each pack's page colour, VS Code style; the
  pack supplies the accent and syntax hues, each chosen by measured contrast
  against every surface it can land on. **All ten now pass at 4.5:1.**
- **A Web Dev endpoint's tabs shared one language-server document.** Eight
  scripts live at one resource path, and both the tab key and the LSP URI were
  built from the path alone, so opening `doPost` showed `doGet`'s outline and
  would have put diagnostics on the wrong buffer. Both are keyed by data key now.

### Added
- **Activity bar** (Scripting / Web Dev / Search / Console). Clicking the active
  view collapses the side bar to the icon strip and clicking it again restores
  it, as VS Code does.
- **Resizable, hideable panels.** Drag or arrow-key the side bar and the outline;
  widths are remembered per viewer. The outline has its own close button.
- **Web Dev** as a full view: endpoints, their eight HTTP methods, add a method
  to an existing endpoint, create and delete endpoints, and a settings dialog
  carrying every field the Designer shows — enabled, require-auth, require-https,
  required roles, user source, retry count. Measured off a real gateway: a Web
  Dev resource has NO editable `resource.json` attributes, so its settings live
  in a `config.json` data file and get their own route. Writes are per method and
  preserve unknown keys, so a field a newer Ignition adds is not deleted by an
  older build of this module.
- **Find and replace** (Ctrl+F / Ctrl+H) in both the editor and the console,
  with the panel restyled in tokens — it ships light-themed and was a white bar
  with invisible controls on every dark theme.
- **Gateway event scripts can be created and deleted like the Designer's.**
  Every event folder is listed even when empty, because an empty folder is the
  only place to create the first script of a kind. Singletons offer no "new".
- **Icons throughout the tree**, per resource type, and Script Console reads as
  the top-level heading it is rather than a stray file.
- **The console output is its own titled panel** with a header and a rule, so it
  no longer reads as more editor.
- **VS Code look**: 13px, flat chrome, 3px radii, one accent, a real focus ring,
  22px tree rows and overlay scrollbars.

## [1.1.0] — 2026-09-01

The IDE most of 1.0's backend was already built for. 1.0 shipped an execution
channel, a document-symbol provider, definition and project-wide search that all
worked — and that **no part of the UI called**. The gate proved them over the raw
socket, which is exactly why nobody noticed. Most of this release is wiring, and
that is the lesson.

### Added
- **Script Console.** Run and Run-selection on the Gateway, Ctrl+Enter and
  Ctrl+Shift+Enter, best-effort Stop with honest copy, and output with a clickable
  traceback. Locals persist between runs, like the Designer's console; a
  selection run pads with blank lines so traceback line numbers still match.
- **Split panes and pop-out.** Editor and console side by side, console full
  width, or the console in its own browser tab (`?view=console`). The editor is
  hidden rather than unmounted in full mode, so every open tab keeps its
  CodeMirror view, undo history and scroll position.
- **Outline panel.** Classes and functions in the open script, filterable, click
  to jump. Symbols come from the gateway's Jython parse, so a transient syntax
  error does not empty it.
- **Create and delete scripts.** A named create with live validation against
  Python 2 identifier rules (`print` and `exec` ARE keywords), and a delete that
  requires `If-Match` — 428 without one, 409 if the script moved on.
- **Designer-shaped tree.** Scripting ▸ Gateway Events ▸ (type) / Project Library
  / Script Console, matching the Designer's project browser. The console node is
  a deliberate addition (Nigel).
- **Themes.** Ten themes derived from the estate's Perspective packs by
  `tools/build-themes.py`, which picks each role's colour by MEASURED contrast
  against that theme's own page — every foreground token clears 3:1 on all ten.
- **Gateway event settings.** `cronExpression` on Scheduled — without it a
  scheduled script could be edited but never scheduled — and `enabled` on
  Shutdown and Update, both verified by round-tripping against a real gateway.
  The Designer's description and handler-parameter text is now shown too.

### Fixed
- **A folder was editable.** The platform reports every event-script directory
  that has children as a resource with a real signature and an empty name; there
  is no `resource.json` for it on disk. It appeared in the rail labelled with its
  type, and a save against it returned **200** while hanging a `cronExpression`
  off a directory. Found by live validation, not by review. The guard is
  `isResourceTypeFolder()`, NOT `getName()` — on `ignition/scheduled` `getName()`
  returns `"scheduled"`, so the first version of the fix did nothing at all and
  its own test caught it.
- **The first Run of a session always failed.** `send()` connects lazily but
  still returns false for the attempt that triggered it, so the console reported
  "not connected" and did nothing. Worse in the popped-out console, which has no
  language client to have opened the socket for it. It connects on mount now.
- **Themes did not apply.** `:root` and `[data-theme]` have identical
  specificity, so the generated block lost on source order to `index.css`.
  Emitted as `:root[data-theme=...]` now. `data-theme` changed and no colour did,
  which is invisible to every test that checks the attribute.
- **The deploy gate needed a retry after every install.** The gateway's own web
  UI is a SPA that boots after `load`, so the login link was not there within the
  first wait. It reloads once before giving up.

### Known limits
- **Tag Change settings are still refused.** Its workspace has a tag-path list
  that nothing measured describes, and a guessed key would look configured while
  doing nothing. The script body is editable; the settings are not.
- Console output is not streamed — it arrives whole when the run finishes.

## [1.0.0] — 2026-09-01

First complete release. Built and validated against Ignition 8.3.8.

### Added
- **Editor.** Browser IDE served from the Gateway at `/data/scriptide/`, with a
  file tree grouped by script type, tabbed multi-file editing, CodeMirror 6 with
  Python highlighting, and a conflict dialog on concurrent edits.
- **Resource editing.** Project Library and Gateway event scripts (timer, message,
  startup, shutdown, scheduled, tag change), written through
  `ProjectManager.push()` — no `resource.json` stamping and no project scan.
  Byte-identical to what the Designer writes: tabs preserved, no trailing newline.
- **Execution.** Run a buffer or selection on the gateway with streamed
  stdout/stderr, a structured clickable traceback, a best-effort Stop, a per-user
  REPL console, and per-execution auditing.
- **Language server.** Real LSP over one authenticated WebSocket: completions,
  `completionItem/resolve`, signature help and hover sourced from the running
  gateway's own script registry — so they include functions from whichever modules
  that gateway has installed.
- **Navigation.** Go-to-definition through import bindings, document outline,
  project-wide symbol search, and cross-file text search over the project's own
  scripts, built from a Jython 2.7 AST index.
- **Diagnostics.** Syntax errors from the gateway's real Jython parser, rendered as
  inline squiggles and gutter markers. Valid Python 2 is never flagged.

### Security
- Execution requires an authenticated session, the Administrator role, a CSRF token
  and a same-origin handshake; it is on by default and disableable gateway-wide.
- No actor-string authentication fallback — a deliberate divergence from the
  sibling web-designer module.
- Both read and write paths require `moduleId == "ignition"` plus a known script
  type, so no non-script resource can be written through these endpoints.
- Client-supplied data keys must be a plain `.py` filename.

### Known limitations
- No breakpoint debugging: the only serious Ignition debugger requires a live
  Designer and blocks a gateway worker thread.
- No find-references, and diagnostics are syntax-only — both were designed and
  deliberately held back rather than shipped below the zero-false-positive bar.
- Perspective and Vision event scripts are not editable; their code lives inside
  view JSON rather than as its own resource.
