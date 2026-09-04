# State

**Read this first each session.** Single source of truth for where the module is.

**Version 1.11.0 · deployed on `ignition-module-testing` (8.3.8) 04/09/2026 —
`deploy_gate.py` PASS (6 checks) and every suite green: `v13` 23/23,
`v16_nav` 25/25, `v18_pull` 20/20, `v19_ruler` 16/16, `v20_webdev` 29/29,
`v21_split` 21/21, theme sweep 10/10 with no illegible element.
Java 365 tests, Vitest 521.**

**Running the live suites needs a venv with playwright**, which is not on the
system python and was absent on 03/09/2026:
`python3 -m venv .venv-test && .venv-test/bin/pip install playwright &&
.venv-test/bin/playwright install chromium` (1.62+; older cannot install a
browser on Ubuntu 26.04). Then
`WD_ALLOW_LOCAL_CONFIG=1 .venv-test/bin/python3 scripts/testing/<suite>.py` —
`gateway_session` refuses to guess a gateway without either that flag or
`SI_GATEWAY_CONFIG`.

**`v15_tree` does not pass on this gateway and did not at 1.7.0 either** — it
wants `Site_Redgum_Sewer`, a water-suite project not installed here. A fixture
gap, not a regression; it needs the `skip()` treatment `validate_v14.py` got.

**If this is a fresh chat: the work queue is in "What is next", below the
status table.** Batches A–F are done and deployed. The one real gap is that
**batch E has no live suite** — see the top of "What is next".

**1.7.2 fixed the themes pass, which shipped in 1.7.0 doing nothing visible.**
Every layer worked except the numbers: the clamps in `build-themes.py` were set
below where the packs actually live, so seven of the ten themes came out
byte-identical. See finding 17 — it is the sharpest example in this module of a
green test suite measuring the wrong axis.

1.1.0–1.5.0 are post-1.0 feature work driven by Nigel's review, not new phases.
1.3.0 added a **Gateway terminal**, moved the console into a **bottom panel**, and
brought **Gateway Events** into line with the real Designer. 1.4.0 makes
**inherited scripts read-only until overridden**, names and explains **Script Hint
Scope**, and makes the terminal a **root shell** where the host allows it. 1.5.0
makes the **exec channel non-blocking and streaming**, gives tracebacks
**structure**, makes **closing a terminal actually close it**, and makes every
policy switch **changeable on a running gateway**.

### 1.10.0 — two editors, side by side

Nigel, 03/09/2026: *"I'm not seeing a way to split the screen between 2 or more
scripts so that I can do comparisons or copy and paste between etc. This is a
major limitation on the designer."*

**A document lives in exactly ONE pane, and splitting MOVES it.** That is
smaller than VS Code's split and it is the honest version here: `CodeEditor`
keeps one `EditorView` per document — deliberately, so scroll position and undo
history survive a tab switch — and two views over one buffer would need
synchronising on every keystroke. That is an editing model, not a layout. The
live suite proves the moved editor keeps its undo stack.

The rules are pure functions in `panes.ts`, tested on their own, because this is
the part that is easy to get subtly wrong and impossible to see going wrong: a
pane showing a tab strip and no buffer, a document in both panes at once, or a
second pane left open with nothing in it. `PaneState` is three fields and there
is deliberately **no "is split" flag** — an empty set is one pane, and a flag
and the set behind it drift apart.

`activeUri` keeps its old meaning throughout: the document you are working in,
and the one the outline, Problems, the config strip and "Run file" describe.
Which PANE that is falls out of the split set, so the two cannot disagree. The
chrome above the buffer is built once and rendered into whichever pane holds the
focused document — never duplicated, for the same reason the inheritance note
shares the settings row rather than taking one of its own.

**The divider between two panes received no pointer event at all** on the first
build. `elementFromPoint` on its own centre returned the neighbouring
CodeMirror's line-number gutter: a 1px divider between two flex children loses
the half pixel to whichever paints last. Every static check passed — the
divider was in the DOM, at the right x, the right height, with its handlers
bound — and dragging it did nothing. `.resizer` now takes `z-index: 2` and a
3px grab area, which fixes the rail and panel dividers too; `v21` asserts
`elementFromPoint` hits it, not merely that a drag changed a number.

### 1.9.0 — Web Dev has two shapes, and this module knew one

`cell3d` on `Machine_HMI_Demo` showed eight empty verb slots and no way to reach
the file. It is not an endpoint with no handlers; it is a different KIND of
resource, and `config.json`'s first line has said so all along:

| Endpoint | `resource-type` | What it holds |
| --- | --- | --- |
| `admin` | `python-resource` | eight `do*.py` handlers |
| `lib` | `python-resource` | `doGet.py` **plus `three.min.js`** as a data key |
| `cell3d` | `text-resource` | 65 KB of HTML in `config.json`'s `text` field, with `content-type: text/html`. `files` is `["config.json"]` and nothing else |

The module intersected the data keys against `doGet.py…doPatch.py` and rendered
the result. For `cell3d` that is the empty set, so the tree drew eight "add"
buttons — **and pressing one would have put a Python handler onto a resource the
platform serves as static HTML.** For `lib` it meant `three.min.js` appeared
nowhere at all, though the content route had been able to serve it since 1.0.0.

What went in:

- `WebDevResources` — the shape, in one place: which kind, the content type, the
  body, which data keys are assets, and which of those this IDE will open.
- A **synthetic data key**, `config.json#text`. A text resource's body is a JSON
  string, not a data key, and everything in this module is addressed by
  `(path, dataKey)` — the tab identity, both content routes, the LSP uri.
  Rather than thread a second addressing mode through all of that, the listing
  advertises that key and `read`/`write` translate it. `isPlainFilename` now
  rejects `#`, so it can never also exist as a real key.
- Writes are **read-modify-write of `config.json`**, so the `content-type`
  survives. A `{"text": …}` overwrite would strip it and the platform would then
  serve the page as `text/plain`.
- Six editor surfaces instead of two: HTML, JavaScript, CSS and JSON alongside
  Python and SQL, chosen from `docLanguage.ts` — MIME type first, extension
  second, and a `.py` key overriding both.
- **`isPythonDoc` gates the language server.** It is a Jython server: pointed at
  65 KB of HTML it publishes a syntax error per line. It now gates completions,
  diagnostics, the ruler and "Run file" together, so there is one predicate to
  get wrong rather than four.
- Files too large or too binary to edit are **listed greyed with their size**
  rather than hidden. `three.min.js` is 670 KB of minified JavaScript; a row
  saying so is a better answer than a file that appears not to exist.

Two things found while doing it, both pre-existing:

- **`staleUris` was keyed by document, not by resource.** A signature covers the
  whole resource, and a Web Dev endpoint has up to eight handlers plus its files
  open against one signature — so only the tab opened at the listing's default
  key could ever be reported stale. Every other tab on that endpoint was
  silently exempt from the 1.8.5 pull feature.
- **Saving a config normalises its non-ASCII escapes.** Gson writes `\u2014` as
  a literal em dash (`disableHtmlEscaping` handles `<`/`>`/`&`, and there is no
  switch for the rest). The string is identical — `v20` proves the body round
  trips byte for byte and the served page is unchanged — but the FILE shrinks by
  the difference on its first save through this module. Pre-existing in the
  settings route; left alone, because hand-rolling a JSON writer to preserve
  another tool's escape choices is the worse trade.

### 1.6.1 — the console could not run a function

`PrivateStateRunner` called `Py.runCode(code, locals, scriptManager.getGlobals())`
— locals and globals were two different dicts. A module-level assignment landed
in `locals`; a function or class body closes over `globals`, which was the
manager's own and had nothing the script had just defined in it. Calling the
function raised `NameError: global name 'x' is not defined`, including for
`def f(): return system.date.now()` — the console could run assignments and
expressions and nothing that defined a callable. It now runs
`Py.runCode(code, locals, locals)`, one dict, with `system` seeded into it
before the run.

This had been there since P2, when the private-`PySystemState` execution model
was built. No suite caught it because every exec check written since is a
one-liner or a bare expression — none of them define a function, so none of
them could fail this way. A green gate on every release through 1.6.0 proved
the console could run code, not that it could run a program.
`validate_v15_exec.py` now carries a permanent check that defines a
module-level name and reads it back from inside a function.

### 1.6.0 — the navigation the gateway had been answering all along

Batch D. **P4 was marked done and the product could not navigate.** The gateway
answered `textDocument/definition`, `workspace/symbol` and the module's own
`scriptide/searchText` from 1.0.0, `lspClient` wrapped all three, and no
component called any of them — the outline and Ctrl+F were the whole of it. The
lesson generalises past this module: **"the server does it" is not a feature**,
and a phase is not done until something a user can press reaches the code.

- **Go to definition** on F12 and Ctrl-click, across files. Silent when there is
  nothing to open — a `system.` call has no source here, and a dialog saying so
  on every press teaches people not to press it.
- **Quick open** on Ctrl+P over the tree (subsequence-matched: `fpa` finds
  `FooParser`), `#` for project symbols. Files are filtered locally so typing
  feels like typing; symbols are a live round trip and debounce. `#` is the
  guarantee and Ctrl+T the convenience — Chrome refuses Ctrl+T and it cannot be
  intercepted.
- **A Search view**, the one `ActivityBar` had said was missing since P4. It is
  also where references land, because both answer "where else does this appear?"
  and a list you can leave open beats a peek that closes when you click it.
- **References on Shift+F12**, over a new `scriptide/references`. NOT
  `textDocument/references`, and that is the whole design: the standard method
  promises a type-aware answer this server cannot give. What it does buy over a
  text search is identifier boundaries — `compute` does not match `recompute` —
  and the panel says on screen that the match is by name.
- **A Problems panel** over every OPEN document. Its empty state names the limit,
  so it cannot be read as "the project is clean".
- **A fold gutter** (files only; the console shares the surface and has no use
  for one) and **Ctrl+G** for go-to-line, which is what people press.
- **The tree ships collapsed and drops Web Dev** (Nigel, 02/09): quick open is
  the fast path, and Web Dev has a richer view of its own.
- **`ETag` is quoted** per RFC 9110 and `If-Match` is parsed tolerantly. Both
  halves together, or a page loaded across the change 409s for ever.
- **The bottom panel opens at 34% of the viewport** — 340px at the 1000px the
  02/09 review measured as cramped, not 260px.

Three things found on the way, all of them the same shape — a fix with nothing
asserting it:

- **A cross-file jump landed on line 1.** The view for a just-opened document
  does not exist when the reveal is published (React state), and the editor
  dropped it silently. It holds one pending reveal now. The clicked-traceback
  path had carried this since 1.5.0.
- **`validate_p1_p2.py` had not been a gate since 1.5.0.** It read
  `finished.stdout`, which 1.5.0 emptied by contract; `deploy_gate.py` was
  updated at the time and this file was not, so byte fidelity and the 500/500
  concurrency check reported 0 lines and looked like an execution failure.
- **`validate_v14.py` crashed** when its fixture project was absent — the
  water-suite projects have gone from the rig — taking the terminal, hint-scope
  and chrome checks down with the inheritance ones. It SKIPs with a reason now.

And one worth remembering about testing a browser: **the suite's own caret
placement was wrong, and it looked exactly like the feature being unbound.**
Estimating a column from the line's width ÷ character count drifts on any line
with a tab in it (one character, four columns), so the click landed beside the
identifier and F12 correctly did nothing. `CARET_ON` uses a DOM `Range` around
the real text node. Before blaming a keybinding, prove the caret is where you
think it is.

### 1.5.1–1.5.4 — what the v15 suites found once they ran

The three suites written for 1.5.0 were first run on 02/09/2026 and found three
more defects in a row, each invisible from the page, each fixed in its own
build. All three suites are green on 1.5.4.

- **1.5.1 — Stop poisoned the thread.** `ScriptManager.interrupt` leaves
  `ThreadState.frame`/`tracefunc`/`exception` pointing at the dead script, and
  the pool thread's NEXT run inherited them. `PrivateStateRunner.FrameSnapshot`
  restores all three in `finally`; `PrivateStateRunnerStopTest`.
- **1.5.2 — the terminal opened before its socket did.** On a tab nothing else
  had used, `TermClient.open()` sent its frame into a transport whose lazy
  `connect()` had not completed; `send()` returns `false` and drops the frame,
  so the xterm mounted and the prompt never came. `open()` now defers to the
  transport's next `onOpen` and returns a disposer the view calls on unmount.
- **1.5.3 — the JDK's channel adapters made the terminal half-duplex.**
  `Channels.newInputStream` and `Channels.newOutputStream` both `synchronized`
  on the channel's `blockingLock()`; with the pump parked in `read()`, every
  `write()` waited for it. A prompt (the first read), then every keystroke
  swallowed, and `close()` hung on its own ETX write so the sweep never ran —
  3+ leaked root `bash -i` per session, measured. `DockerExec.ChannelInput` /
  `ChannelOutput` use the `SocketChannel` directly (separate read/write locks);
  `ChannelStreamsTest` proves the adapters block and the wrappers do not.
- **1.5.4 — `/api/projects` carries `parent` and `inheritable`.** So the tree
  suite can tell "no inherited scripts because the parent is not inheritable"
  from "inherited scripts are not listed". Fixture `_si_child_` (parent
  `_wd_scratch_`, title `Script IDE child fixture (dev)`) was created on the rig
  for the suite; `_wd_scratch_` is NOT inheritable, so the read-only checks
  SKIP with that reason — flipping the flag is a change to web-designer's
  scratch project and is Nigel's call. Its child also logs `HintIndex: No
  ScriptManager available` for `_si_child_` — a child of a non-inheritable
  parent has no project ScriptManager, and the module tolerates it.

### 1.5.0 — a socket that keeps listening, and a shell that actually dies

Every item below was measured broken on 1.4.3, and most of them cannot be seen
from the page at all, which is why
`scripts/testing/validate_v15_{exec,term,tree}.py` exist. Run them as:

```bash
cd scripts/testing
export SI_GATEWAY_CONFIG=$PWD/config.local.json PLAYWRIGHT_BROWSERS_PATH=$HOME/.cache/ms-playwright PYTHONPATH=$PWD
PY=/home/nigel/Ignition-Work/ignition-toolbox/backend/.venv/bin/python
$PY validate_v15_term.py
SI_EXEC_PROJECT=_wd_scratch_ $PY validate_v15_exec.py
SI_INHERIT_PROJECT=_si_child_ $PY validate_v15_tree.py
$PY validate_v16_nav.py            # batch D; builds and removes its own fixture
```

- **The exec frame handler no longer waits for the script.** `ScriptIdeSocket` is
  an `AutoDemanding` listener — one frame at a time, on the socket thread — and
  the run branch blocked there until the script finished. The connection was deaf
  for the duration: a Stop was not READ until the loop it was meant to stop had
  already ended, and pings, LSP requests and terminal keystrokes queued behind it.
  The Stop button could not have worked. `ExecutionService.submit` now returns as
  soon as the pool accepts the work; the timeout ladder moved from a
  `future.get(deadline)` onto the watchdog; `started`, `output` and `finished` are
  sent from its callbacks.
- **The wire protocol.** Requests `run{project,source,csrfToken,target?,
  lineOffset?}`, `stop{executionId}` and `reset{project}`; events `started`,
  `output{stream,text}`, `stopping`, `finished{truncated,cancelled,ok,error?}` and
  `reset{project}`. Omitting `target` is what marks a console run and keys its
  REPL locals; `reset` drops them and is refused while that connection has a
  script in flight. Closing the socket stops whatever it was running.
- **`finished` carries EMPTY stdout and stderr, by contract.** Everything has
  already gone out as `output` frames, so a client that rendered both would print
  every line twice. Chunks are flushed on a newline, at 4 KB, or every 100 ms —
  the newline rule is what makes `print` in a loop feel live, the timer saves a
  long line that never ends. The UTF-8 decoder is kept across flushes, or a
  multi-byte character landing on a chunk boundary becomes two replacement glyphs
  permanently. `deploy_gate.py` gathers the stream rather than reading
  `finished.stdout`.
- **Tracebacks are structured, and our own token never reaches the screen.** The
  error object is `{type, message, rendered, frames:[{file, function, line,
  isSubmitted, libraryModule}]}`. The client had invented its own field names
  (`path`, `module`, `functionName`, `isTarget`), so every frame on screen read
  `<console>, line N` with no function and no exception type — nothing threw,
  because TypeScript cannot check a wire. A frame with a `libraryModule` maps to
  `ignition/script-python/<dotted/path>` and opens that script; a submitted-source
  frame moves the console's own cursor. `<script-ide:project:target>` is replaced
  with a display label wherever it appears in free text.
- **A syntax error is not a traceback.** Its value is the tuple
  `(msg, (file, line, offset, text))`, which 1.4.3 rendered with `toString()` —
  a raw PyTuple, internal token and all. It is unpacked into `message` plus
  top-level `line`/`offset`/`text`, the line is reported in the EDITOR's numbering
  (the selection-run offset is subtracted), and the console draws a caret under
  the column.
- **The console shows where a run starts and ends.** A `▸ run N · HH:MM:SS`
  divider, consecutive chunks of one stream merged into one block, and a closing
  `— finished in N.N s —` / `— stopped —` / `— failed —`. **Run file** runs the
  active tab as typed, with a `target`, so it gets fresh locals. **Reset** drops
  the console's locals, where the Designer puts it.
- **The terminal resize goes AFTER the attach.** A resize before
  `/exec/{id}/start` has no exec session to size: the daemon blocks and then
  answers `500 timeout waiting for exec session ready`, and our own five-second
  watchdog cut it — which is why every 1.4.x terminal took exactly 5.00 s to open
  and why the resize never applied (the client's own resize after `opened` was
  doing all the sizing). Attach first and the same call answers 200 in about
  90 ms, measured against the raw daemon. Three attempts at 100 ms, because the
  session becomes ready a moment after the upgrade. `validate_v15_term.py` gates
  the prompt at under 2 s.
- **Closing the hijacked attach does not kill anything.** Measured 02/09/2026:
  the daemon keeps the exec running, detached, for ever — **38 orphaned root
  `bash -i`** in the test container, one per terminal ever opened, and the
  120-minute idle reaper had been calling the same no-op. Close is now ETX, EOT,
  `exit\n`, a ≤750 ms poll on `Running:false`, and then an unconditional root
  sweep exec that walks `/proc/*/environ` for `SCRIPTIDE_TERM=<terminal id>` —
  `kill -HUP`, one second, `kill -KILL`. The tag is inherited, so `sleep 300 &`
  goes with its parent; the exec's own `Pid` is a HOST pid this JVM cannot see or
  signal, which is why a tag beats pid bookkeeping. `TerminalService.shutdown`
  waits up to 10 s on `DockerExec.awaitReapers`, because the sweep runs on a
  daemon thread. The `script(1)` route got its own fix: `destroy()`, then
  `destroyForcibly()` 300 ms later, because `script` installs a SIGTERM handler
  and an interactive bash ignores SIGTERM outright.
- **The audit line can no longer overstate privilege.** It is written before the
  shell starts, so it records what was expected; `TerminalSession.elevation()`
  reports what the shell actually got (`docker-exec` / `sudo` / `none`) and a
  mismatch is a WARN naming both.
- **Policy is live.** `PolicySource` resolves every `ExecPolicy` and
  `TerminalPolicy` value as **file > `-D` system property > default**. The file is
  `<data dir>/modules/scriptide/policy.properties` (`java.util.Properties`, the
  same fully-qualified keys), re-statted at most once every 2 s on mtime AND size,
  wired once in `ScriptIdeModuleHook.startup()`. The module never creates it.
  Both classes were honest about re-reading on every call; every value came from a
  property read once at JVM start, so "no restart needed" was true of the code and
  false of the gateway.
- **An empty Project Library package is a folder, not a script.** A package the
  platform reports as a resource in its own right (`dataKeys: []`) passed every
  filter and listed as openable; clicking it 404'd with "No such data key
  'code.py'". `isPackageContainer` marks it `isFolder` in the tree JSON, it
  carries no `scriptKey`, the rail renders it as a folder and the footer counts
  exclude it. Scoped to `script-python`, the only type that nests.
- **Clicking an absent Startup/Shutdown/Update row opens a DRAFT.** It used to
  call `createScript` on the click — browsing the tree wrote resources, and git
  diffs, into a live project with no confirmation. `DocOrigin 'new'` is a buffer
  with no ETag that is always dirty; the first save creates the resource through
  the ordinary create branch, and the tree is re-read afterwards. A create raced
  by somebody else comes back as **428**, not 409 (there is no base signature to
  send), and raises the same conflict dialog. The named "New script…" dialog is
  unchanged: it still creates on OK.
- **Two things the UI was not saying.** A tab holding an inherited,
  not-yet-overridden script is labelled `(Read-Only)`, matching the Designer's own
  buffer header — the editor already refused every keystroke, but with six tabs
  open nothing said which one. And the footer has an `idle` state, "Language
  server idle": the LSP connects lazily on the first document, so the landing page
  showed "Language server offline" in red when nothing had failed. `offline` is
  now reserved for a connection that was attempted and lost.
- **Completion docs read like documentation again.** `HintIndex` rendered a return
  type with `String.valueOf(rt)`, and `TypeDescriptor` is a Kotlin data class —
  the doc panel showed `TypeDescriptor(name=None, description=null, …)` for every
  return type. It uses `rt.getName()` now. The panel also printed the signature
  twice, because the server's markdown already opens with `detail` in a fenced
  block; `detail` is only rendered separately when the body does not start with
  it.

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

### 1.4.3 — the Docker route actually working, and a clipped last line

- **`SocketChannel.socket()` throws on a Unix-domain channel.** 1.4.2's control
  connections called it to set a read timeout, so every Docker API request threw,
  `available()` caught it as "socket unusable", and the whole route reported
  itself absent on a host where it was mounted and working. The only symptom was
  an unprivileged shell and one log line reading `elevation=none`. Timeouts come
  from a watchdog that closes the channel instead. **A mounted-but-unusable
  socket now logs a WARN**, because the failure is otherwise indistinguishable
  from never having mounted it.
- **A fitted element must carry no vertical padding.** xterm's FitAddon sizes
  from the computed height of the element the canvas sits in and does not
  subtract that element's own padding, so 8px of `padding-top` fitted 11 rows
  (220px) into a 216px content area and `overflow: hidden` ate the bottom of the
  last line. Measured: host 224px, rows 220px. The inset moved to the wrapper.
- **The rig runs a STOCK Ignition image** (Nigel, 02/09/2026: "We will not be
  using custom ignition images"). The custom image built on 01/09 is gone, and so
  is `Dockerfile.test`. git is `apt-get install -y git` from the root terminal.

**Open, not resolved:** `validate_v13.py`'s terminal INPUT checks were removed
because they stopped receiving any input in that suite's page state — not even a
bare Enter — while the identical code in `validate_v14.py` types and reads back
fine on the same build. Focus method, the customise-layout menu, panel
visibility and duplicate xterm instances are all ruled out. The comment in
`validate_v13.py` says so at the point it happened. If the terminal ever drops a
user's input, start there.

### 1.4.2 — chrome sizing, one row, and a second route to root

Three things, all from Nigel's 02/09/2026 review of the 1.4.1 screenshot.

- **Every control in the chrome is one height.** There wasn't a token for it:
  each control carried its own `padding: 1px …` and no height, and a `<select>`
  and a `<button>` with the same padding come out different sizes. In a 30px bar
  both looked squashed and the Save button touched the border. `--control-height:
  24px` now, the toolbar is 34px, and the live check asserts one height across
  project/save/theme/hint plus ≥3px clearance. **Set the height, not the
  padding.**
- **`.workspace-toolbar` was declared TWICE**, forty lines apart, with the later
  block silently winning on gap and padding while the earlier one kept the
  height. Same trap `FileTree.css` already carries a warning about.
- **The inheritance notice moved INTO the settings row.** It was its own bar
  below it, so an inherited script paid two chrome rows — ~105px above the code —
  to say two sentences that are never both true at once. It is the settings
  strip's `leading` element now: 69px, measured.
- **A Docker-daemon route to root**, preferred over `sudo` where available.
  See the CLAUDE.md non-negotiables; the short version is that a process cannot
  raise its own privilege, the daemon runs as host root and will simply create
  an exec with `User:"0"`, and that needs nothing at all in the image.

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
| P4 — project navigation | **Done, and reachable since 1.6.0.** It was "done in the LSP" from 1.0.0 to 1.5.4 with nothing in the UI calling it: go-to-definition, quick open, the Search view, references and Problems all landed in batch D |
| P5 — diagnostics | **Done.** Real Jython parser; valid Python 2 never flagged |
| P6 — cross-file search, polish | **Done** |
| P7 — hardening, docs, 1.0.0 | **Done.** Security review clean |

## What is next

### Nigel's 03/09/2026 list — all six done

Done in 1.8.5: favicon; sidebar trees keep their open branches across a view
switch; pull-from-gateway with stale markers. The rest followed:

1. ~~The Designer's error ruler.~~ **DONE in 1.8.7**, `validate_v19_ruler.py`
   16/16. Still true and still open: Problems covers neither WebDev nor
   named-query documents, because neither is registered with the language
   server — so the ruler is absent on those too.
2. ~~WebDev static resources.~~ **DONE in 1.9.0**, `validate_v20_webdev.py`
   29/29 against the real `Machine_HMI_Demo` endpoints. See "1.9.0" below.
3. ~~Split view.~~ **DONE in 1.10.0**, `validate_v21_split.py` 21/21. See
   "1.10.0" below.

### Themes — the material pass (1.11.0, 04/09/2026)

Nigel, 03/09/2026: *"still quite a bit of the styling feels a bit dull… so that
the different themes really feel beautiful and provide that bit of variety."*

Unparked and done. Four things, each of which was MEASURED first and is now
asserted by `tools/build-themes.py` itself, which exits non-zero rather than
writing a theme that fails one.

**1. The grounds carried almost no colour.** The four light packs painted
chroma — the spread between the strongest and weakest channel — of 3, 5, 5 and 8
out of 255, and three of their six pairings sat within 8 RGB on both the page
and the rail. The cause is arithmetic, not taste: a pack states its ground in
HSL (`leather-parchment-tan` is hue 36 at 33% saturation) and at 97% lightness
the most chroma any colour can hold is 15/255. The hue was in the pack,
correctly, and invisible on screen. `saturate_ground` now raises saturation at
the pack's own lightness and gives up lightness only when saturation runs out.
Light grounds went 3–8 → 19–27, dark 5–33 → 20–33. **A pack already above the
floor is not touched** — the aurora pair keeps `#1a1233` exactly, because the
ground IS the family and moving it is how 1.7.x lost the two best themes.

**2. Two packs put a DARK rail on a LIGHT page and the generator flattened it.**
`finance-ledger` brands its sidebar `#0b3d5c` navy and `leather-parchment-tan`
`#2f2016` brown; both rendered as one more pale grey. `--bg-chrome` now takes
the pack's own rail where the pack deliberately inverts it (measured: every
other pack's sidebar is inside 6% of its page, those two are at 74% and 83%,
nothing is near the 34% threshold). **This is the one place a `surface.*` token
is allowed onto a neutral**, and it is safe only because `--bg-chrome` paints
exactly one component — so the rail carries its OWN ink, `--text-chrome` /
`--text-chrome-active` / `--accent-chrome`, computed against itself. Widening it
to `--bg-secondary` would be the 1.2.0 defect again.

**3. Syntax highlighting was one colour with six names on four themes.** The
old guard measured straight RGB distance at 0.07 in a 0–1 cube, which on a light
theme — where every syntax colour must be dark, and dark colours crowd near the
origin — passed almost everything. `industrial-day-cyan` shipped keyword and
type at the same lightness, the same saturation and 8° apart. `_separation` now
scores hue (weighted by the LOWER of the two saturations, because the hue of a
grey is noise), plus weight, plus saturation; the bar is 28, chosen from the
measured spread of the ten (7.8, 9.4, 9.9, 17.1, 29.1, 29.4, 29.9, 32.2, 57.5,
66.0) so it fires on the four real collisions and leaves the six a reader can
already tell apart. Rotation is nearest-first and both ways, with a LIGHTNESS
fallback for a pack whose six roles all sit inside 40° — `nord-light-frost`
needed it. Worst is now 28.4.

**4. The filled primary button's label was the literal `#ffffff`, since 1.1.0.**
On `newsprint-night`, whose brand is paper (accent `#e8e2d6`), the Run button
was white on near-white; on `aurora-teal` (accent `#1accbe`) white on bright
teal. `--accent-ink` is black or white, whichever the accent can be read
against, and is asserted at 4.5:1. **The theme sweep could not see this for ten
releases because it reads colours off elements and a literal in a stylesheet is
not a token a theme can move** — it now measures `button.primary` too, and the
activity bar, whose icons have no text and were therefore skipped by a loop that
required some.

Each guard was proved to FAIL on the broken version before being trusted:
disabling the chroma floor refuses the build on `finance-ledger` (3/255 under
18), disabling `differentiate_syntax` refuses on `aurora-teal` (4.5 under 28).

**What is left, and is the packs rather than the generator:**
`industrial-day-cyan` and `nord-light-frost` author near-identical pages
(`#EEF0F3` and `#ecf0f4`, hues 216 and 210) and remain the closest pair — 3 RGB
apart on the page, separated in practice by chrome (23 RGB), accent lightness
and geometry. Rotating either off its own hue is the 1.7.x mistake and is not
on the table; repainting a pack is Nigel's call, not the generator's.
`industrial-day-cyan` still resolves `--error`/`--success` to greys, for the
reason recorded at 1.7.0.



Nigel's brief (02/09/2026): at least the Designer's capabilities, then more and
better — "clean, easy to use, extremely functional and far superior to the
Designer at the functions it is designed for". Read access may be BROADER than
the Designer's. Named queries are in scope: the programming workflow builds
named queries and Python together and needs them side by side.

**Batch D — navigation (1.6.0). DONE 02/09/2026**, gated by
`validate_v16_nav.py` (25/25): go-to-definition (F12 / Ctrl-click),
quick-open (Ctrl+P, `#` for symbols), the Search view over
`scriptide/searchText`, a Problems panel, name-based references
(`scriptide/references`, Shift+F12), fold gutter, Ctrl+G, the bottom-panel
height at 1000px, the signature-twice check and quoted ETags. Two extras
Nigel asked for the same day: the tree ships collapsed, and Web Dev is no
longer duplicated in it.

**Batch E — Named Queries (1.7.0). CODE COMPLETE 03/09/2026**, not yet
live-gated (waiting on batch F so one build covers both). Five routes under
`/api/named-queries`, a Named Queries view with folders and rename, a SQL editor
on `@codemirror/lang-sql`, Settings/Authoring/Testing parity, a test run against
the live database that runs THE DRAFT, and named queries ranked into quick open
beside scripts. The measured contract is `docs/NAMED-QUERIES.md` — read §1
before touching any attribute, and see the findings below for why.

**Batch F — the themes pass. DONE 03/09/2026, shipped in 1.7.0** alongside
batch E rather than as its own 1.8.0, because the two were built and gated as one
artefact. The packs' GEOMETRY is now taken as well as their colour — radius,
marker and rule widths, row and control height, popup shadow — which is the axis
that differentiates without risk, plus the pack's own border colour and a
`--bg-chrome` stepped by a geometry-derived softness score. **No `surface.*`
token is mapped onto a neutral**: that is the 1.2.0 defect and nothing has made
it safe. Sweep: no illegible themes, worst element 5.07, four themes better than
their 1.6.1 figures. One thing left for Nigel: `industrial-day-cyan` resolves
`--error` and `--success` to greys, because that pack's red cannot clear 4.5:1 on
its light surfaces without losing its hue — accepting less contrast or repainting
the pack are both his call, not the generator's.

**FIRST, before anything else — batch E has NO LIVE SUITE.** Every other batch
is gated by one (`validate_v11`, `v13`, `v14`, `v15_*`, `v16_nav`); named
queries shipped in 1.7.0 with 127 Java tests and 134 Vitest tests and **nothing
that drives the real browser against the real gateway**. Unit tests did not catch
the batch-D caret bug, the batch-D `finished.stdout` staleness or the 1.6.1
namespace defect either. `validate_v17_nq.py` should create a fixture query, edit
its SQL, set typed parameters, run the test tab against `Postgres_Test` and
assert the returned rows, prove the draft (not the saved copy) is what runs,
round-trip every settings field, rename a query AND a folder, and — the one only
a live gate can do — open one of the 37 dead version-1 queries in `Whiteboard`,
confirm the legacy badge, save it, and confirm `system.db.runNamedQuery` then
succeeds where it previously threw. Until that exists, batch E is built and
deployed but not PROVED.

**Then — the review against purpose.** Once D and E are live-gated: review the
module as a product against Nigel's brief and deliver recommendations for going
beyond the Designer (offer the write-up as an artifact page).

**Open decisions for Nigel**, parked, none blocking:
- `terminal.docker` default (currently true — the larger grant, on by default).
- The `groups: cannot find name for group ID` notice — leave, or suppress in
  the shell's environment.
- The Administrator role name is assumed (`Administrator`); make it policy?
- ETag format (bare vs quoted).
- The rig's API tokens are gone (noticed 02/09; nothing here uses them).
- `_wd_scratch_` inheritable: flipping it lets the tree suite's read-only
  checks run; it is web-designer's project.
- `_si_child_` on the rig: keep as the fixture, or delete after the suites.
- The rig admin password reached a scratchpad file and one agent transcript
  line during the 02/09 fixture work (both scrubbed): rotate it.

## What is proved on a real gateway

Eight suites plus a per-theme contrast sweep, **all green on 1.6.0**, all run
against the live gateway rather than mocks.

Two of them had stopped being gates and were repaired in 1.6.0, which is worth
knowing before trusting a tally: `validate_p1_p2.py` had been reading
`finished.stdout` since 1.5.0 emptied it by contract, so byte fidelity and the
concurrency check reported 0 lines; and `validate_v14.py` crashed outright when
its fixture project was absent from the rig. **A suite that cannot pass is not a
gate, and neither of these announced itself.**

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

**`validate_v14.py` — 25 checks, all in a real browser.** An inherited script
opens with a bar naming the project it came from; **typing into it changes
nothing** (2593 characters before, 2593 after — the same assertion that was made
against the real Designer); Save is disabled and Ctrl+S does not fork the parent;
the Override action unlocks that buffer and nothing else; `Script Hint Scope`
carries the Designer's name and option order, is the last thing on the strip and
sits against its right edge; and the terminal reports `uid=0 root` with `git version 2.43.0` on the
command line.

**`validate_v13.py` — 22 checks, all in a real browser.** Gateway Events in the
Designer's order with the three singletons as rows rather than folders; the three
layout toggles; the panel opening below the editor rather than beside it; a
console run inside the panel; a terminal that shows a prompt, runs a command,
starts in the data directory and reports a real window size; maximise hiding the
editor and restore bringing it back; the UI font not resolving to a serif and the
editor font resolving to a monospace; ten themes with no two sharing a palette;
and no failed request or console error attributable to this module.

**`validate_v16_nav.py` — 25 checks, all in a real browser, the batch-D gate.**
Quick open filters by path and opens what it highlighted; `#` searches project
SYMBOLS on the gateway; F12 opens the DEFINING file **and lands the caret on
`def compute`**, not line 1; Shift+F12 finds three writes of `compute` and does
NOT report `recompute`, under a status line that says the match is by name;
Match case changes the answer (2 hits → 0), proving the flag reaches the server;
a syntax error typed into a tab that is then switched AWAY from appears in the
Problems panel and clicks back to it; the fold gutter exists; Ctrl+G opens
go-to-line; a quoted `ETag` round-trips through `If-Match` as a 200; and the
bottom panel opens at 340px on a 1000px viewport. The fixture — two library
modules, one calling the other — is created and deleted by the suite.

**`validate_v15_exec.py`, `validate_v15_term.py`, `validate_v15_tree.py` — the
1.5.0 suites, green on 1.6.0 (19/19, 6/6, 15/15).** exec
covers Stop landing mid-run, the socket still answering terminal keystrokes while
a script spins, the first printed line appearing before the last, a traceback that
names its exception type and its functions, a syntax error carrying no internal
token, and Reset. term times the open, proves the shell carries a
`SCRIPTIDE_TERM` tag, and counts processes INSIDE the container after a close —
the only place a leaked shell is visible. tree covers the click-to-draft negative
(nothing is created by the click, or by closing the tab) as well as the positive,
the empty-package folder, the idle footer and the `(Read-Only)` tab. term and tree
need a container (`SI_TERM_CONTAINER`) and a project with a parent
(`SI_INHERIT_PROJECT`) respectively, and skip rather than fail without them.

A seventh script, `theme_sweep_v13.py`, measures contrast on the **painted**
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
9. **CLOSED.** "git is not in the Ignition image and cannot be added from the
   terminal — the Gateway runs as uid 2003 with no sudo, so it has to go in the
   image." Both halves are gone: the rig runs a STOCK image again (Nigel,
   02/09/2026) and `Dockerfile.test` with it, and the terminal reaches root
   through the Docker daemon rather than through anything in the image, so git is
   `apt-get install -y git` from the root terminal. What survives is the reason
   the module never tries to elevate itself: a process cannot raise its own
   privilege.

10. **"The server does it" is not a feature.** P4 was marked done for five
    versions while `definition`, `workspace/symbol` and `searchText` had no
    caller in the UI — the phase table said navigation was finished and the
    product had an outline and Ctrl+F. A phase is done when something a user can
    press reaches the code, and the gate for it runs in a browser.
11. **A suite that cannot pass is not a gate, and it does not announce itself.**
    Two of them had quietly stopped gating: `validate_p1_p2.py` read a field
    1.5.0 had emptied by contract (so the byte-fidelity and 500/500 isolation
    checks reported 0 lines and read as an execution failure), and
    `validate_v14.py` crashed on an absent fixture project, losing every
    unrelated check with it. When a contract changes, grep every suite for the
    field — not just the one you remember updating.
12. **Prove the caret is where you think before blaming a keybinding.** The
    batch-D suite estimated a column as line width ÷ character count, which
    drifts on any line with a tab in it (one character, four columns). The click
    landed beside the identifier, F12 correctly did nothing, and it looked
    exactly like the binding being absent — an hour spent on 02/09/2026 proving
    the feature worked. `CARET_ON` uses a DOM `Range` around the real text node.
13. **Running code with two different dicts for locals and globals breaks every
    function and class, and a one-liner test suite cannot see it.**
    `Py.runCode(code, locals, scriptManager.getGlobals())` put a module-level
    assignment in one dict and had a function's closure read the other, empty,
    one — `NameError` on the first call, since P2. Every exec check written
    before 1.6.1 was a bare expression or a single assignment, so a green gate
    on five releases proved only that the console could evaluate a line, not
    that it could run a program. A namespace check needs a `def` in it, or it
    tests nothing this bug touches.

14. **A `"version": 1` named query is DEAD, not merely mis-keyed.**
    `fromResource` returns a blank `NamedQuery` whatever the attributes say, with
    or without a deserializer, because the legacy branch reads a `data.bin` a
    hand-written resource does not have. The platform agrees:
    `system.db.runNamedQuery` on one throws
    `NullPointerException: … getType() is null`. All 37 in the rig's
    `Whiteboard` project are like this. A hand-built resource is not "slightly
    wrong" — it does not run. This is the same lesson as finding 2
    (`setApplicationScope`), one resource type along: **use the platform's own
    serialiser, never hand-build attributes.**
15. **A label is not a name.** `ParameterType.Parameter.toString()` returns
    `"Value"` and `Type.ScalarQuery.toString()` returns `"Scalar Query"`. A
    design note written from the Designer's screen said the parameter type was
    called `Value`; there is no such constant. Read `values()` and `name()`, not
    the UI.
16. **The platform's own writer and reader can disagree.** `NamedQuery.toResource`
    writes `description` to the resource's `documentation`; `fromResource` reads
    it from the attributes. So a description written by the platform does not come
    back through the platform. Round-trip anything you believe about a resource
    THROUGH BOTH HALVES before trusting it.

17. **A generated design token is not a visible design.** The 1.7.0 themes pass
    emitted per-theme geometry, mounted the right selectors, reached the browser
    and was consumed by the components — and Nigel's first words on seeing it
    were *"they all look the same as before."* He was right. `_px`'s clamps sat
    below where the packs actually live (`--radius-panel` ceiling 12px against
    packs asking 16–18; `--radius-row` 6px against seven asking 8), so **seven of
    ten themes were byte-identical**.

    Two green suites certified it. `theme_sweep.py` measures contrast, which was
    never what changed — it passed identically before and after. The unit tests
    asserted each token was present and in band, never that the ten themes
    **differed from one another**. The axis nobody measured is the axis that
    broke.

    Three rules out of it, all cheap:
    - When the deliverable is "these look different", the test asserts they
      differ. Presence and range are not difference.
    - Verify a clamp against the data it clamps. A ceiling chosen to catch one
      outlier (`radius.chip: 999px`) flattened the whole distribution.
    - Measure the painted value, not the emitted one. The tokens differed on
      paper at 1.7.0; `getComputedStyle` on the running gateway is what showed
      that five themes resolved to the same 12px.

    Same shape as finding 10, one layer up: *the tokens are emitted* is not a
    theme, exactly as *the server does it* was not a feature.

18. **A theme is a MATERIAL, not a palette — and a material needs something
    behind it.** The glass in Glass Aurora is translucent films over a lit
    ground; compositing them to opaque hex gives three flat greys. But shipping
    the films over a FLAT ground achieved nothing either — a 6% white film on
    dark violet is a shade of the same violet, and the review came back "the
    panel IS the ground". An aurora is a gradient. The panes exist to reveal it.

    Four things this cost, each worth not repeating:
    - **The biggest surface is the one that matters.** The glow went on `.app`,
      but `editorCore.ts` painted `.cm-editor` an opaque `--bg-primary` over it,
      so the light survived only in the outline rail — the smallest region on
      screen. `background-attachment: fixed` lets separate elements share one
      continuous light; that is how it reaches the code.
    - **A gradient centred off-canvas is mostly falloff.** One stop at 4%/−10%
      moved the ground by 2 of 255 at the centre of the window. Always put a
      stop INSIDE the viewport, and measure the delta rather than trusting the
      emitted alpha.
    - **A contrast gate that cannot see alpha is worse than none.**
      `theme_sweep.py` took the RGB of the first non-transparent background:
      `rgba(255,255,255,0.06)` is PURE WHITE by that rule, so it called both
      aurora themes illegible at 1.69:1 when the real composited ratio was 7.49.
      It would have had me revert a correct change.
    - **A gradient is invisible to that gate regardless**, because
      `getComputedStyle` reports `background-color` and this is a
      background-IMAGE. Anything the live sweep cannot see has to be bounded in
      the generator — the glow's brightest point is composited and added to the
      surfaces every text token is checked against.

    And the counterpart: **do not give every theme the same treatment.**
    `newsprint-night` is ink on paper and `industrial-*` is a control-room HMI.
    Flatness is what they ARE; lighting them would be the same mistake as
    flattening the aurora pair. The material is read from the pack — translucent
    surface tokens, shadow, radius — never switched on its name.

## Known gaps and deliberate omissions

- **No breakpoint debugging.** The only serious Ignition debugger needs a live
  Designer and blocks a gateway worker thread; neither fits a browser IDE.
- **References are NAME-based, and every surface says so.** A correct
  find-references needs the type system the AST index does not build, so
  `scriptide/references` matches whole identifiers instead — `compute` does not
  match `recompute`, but two unrelated `write` methods both answer to `write`.
  It is deliberately not `textDocument/references`: answering the standard
  method with this would be lying in the protocol. The gap is narrowed, not
  closed, and the UI must keep saying which.
- **The Problems panel covers OPEN documents only.** The server publishes
  diagnostics for documents this client opened, so a project-wide problem list
  would need every script opened on the server. The empty state names the limit
  rather than reading as "the project is clean".
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
  through `v1.5.4` tagged 01–02/09/2026, `CHANGELOG.md` complete to 1.5.4. The
  folder is gitignored by the workspace repo, like every sibling module. There
  is **no GitHub release artefact** — the signed `.modl` is built locally and
  has not been attached to any tag.

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
- **The test rig runs a STOCK Ignition image** (Nigel, 02/09/2026). The custom
  image built on 01/09 and its `Dockerfile.test` — git, less, openssh-client and a
  passwordless sudoers rule for the `ignition` user — are gone. Root in the
  browser terminal comes from the Docker daemon instead, which needs nothing in
  the image, and git is installed from that root shell. The sudoers route is still
  supported and still the LARGER-looking-but-smaller grant: it is bounded by the
  container, where the socket is the daemon's full API as root on the host.
