# Changelog

All notable changes to this module. Format follows [Keep a Changelog](https://keepachangelog.com/).

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
