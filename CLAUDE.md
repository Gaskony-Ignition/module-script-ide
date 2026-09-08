# Script IDE — module instructions

**Version**: 1.25.0 · Module ID `com.gaskony.scriptide` · Repo `Gaskony-Ignition/module-script-ide`

Read `/home/nigel/Ignition-Work/modules/CLAUDE.md` first — the suite-wide rules
(signing, dependency boundaries, Gradle/Java versions, skills) all apply here.
This file covers only what is specific to this module.

## What it is

A browser-based Jython IDE for Ignition 8.3, served from the Gateway. Edit
Project Library and Gateway event scripts with completions taken from the running
gateway, live error checking, an outline of the open script, and a script console
that executes on the Gateway with its output streamed as it is produced. Since
1.6.0 it also NAVIGATES a project: go-to-definition (F12, Ctrl-click), quick open
(Ctrl+P, `#` for symbols), a Search view over project-wide text search, name-based
references (Shift+F12), and a Problems panel over every open document.

**PUBLIC under Apache-2.0 since 08/09/2026, and on the modules portal.** In
`modules/release.sh` (release it with `./release.sh ignition-module-script-ide`);
still built with its own `./gradlew` and still outside `test-all.sh`. Nigel had
decided the opposite twice that day — public on the evening of 07/09, private
again on the morning of 08/09 ("until I have used it enough to be confident in its
ability"), and public that afternoon. The last word stands; do not re-litigate it.

The the alternative brief and the internal product review were **removed from history**
before publication (`git-filter-repo`, 08/09/2026) and the references to them in
source comments, the changelog and this file were rewritten. Do not reintroduce
either document, or a citation of one, into this repo.

## Entry points

| Need | Read |
| --- | --- |
| The plan and its phasing | `~/.claude/plans/i-m-interested-in-the-golden-wozniak.md` |
| What was measured, and what it changed | `docs/spikes/S1.md` + `S1-harness/` |
| Current state | `docs/STATE.md` |

## Non-negotiables specific to this module

- **Jython is `compileOnly`, NEVER `modlImplementation`.** A second interpreter on
  the classpath gives the JVM two `PySystemState` registries, and
  `ScriptManager.interrupt()` then walks frames the running script is not in — the
  Stop button silently stops nothing. `ModuleJarPackagingTest` asserts no
  `org/python/` classes reach the `.modl`. Same for Jetty, the servlet API and SLF4J.
- **Never execute user code through `ScriptManager.runCode()`.** It leaks output
  between concurrent users — measured, 22–25 lines of cross-talk (S1 §Q2). Use a
  private `PySystemState` per execution, with the manager's module map COPIED and
  the copy's `sys` repointed at our own state. Both refinements are load-bearing;
  removing either silently breaks isolation, and one of the two failure modes is
  cross-user data leakage rather than mere loss.
- **Catch `Throwable`, not `Exception`, around user code.** A Stop raises a Java
  `Error` that escapes Jython's exception machinery entirely.
- **The `"/*"` catch-all route mounts LAST.** First-match-wins with no
  most-specific preference; mounted earlier it shadows every API route and the
  only symptom is the API returning HTML. `RouteMountOrderTest` asserts it.
- **No actor fallback in `SessionSecurity`** — see its class Javadoc. This is a
  deliberate divergence from web-designer, because what sits behind this gate is
  arbitrary code execution in the Gateway JVM.
- **Byte fidelity when writing scripts** (from P1): never convert a tab to spaces,
  never add or remove a trailing newline. The real Designer writes no terminating
  newline.
- **The UI font never comes from a theme pack.** A pack names a typeface as part
  of a brand and `newsprint-night` asks for Georgia; applying it set the whole
  IDE in a serif. A theme here is a palette. `tools/build-themes.py` drops
  `font.body` deliberately — do not "restore" it.
- **`[hidden]` is forced globally in `index.css`.** Three components stay
  mounted-but-hidden to keep state (the editor under a maximised panel, the
  inactive panel tab, every non-active CodeMirror view) and the user agent's
  `[hidden]` rule loses to any `display:` rule in our own stylesheet. Removing
  the `!important` makes all three visible at once.
- **The terminal's shell path is validated by an allowlist, never passed
  through.** It is interpolated into the string handed to `script -c`. See
  `TerminalPolicy.isSafeShellPath` and its test.
- **Never set `-webkit-font-smoothing`.** It is macOS advice. On Linux the
  platform default is subpixel RGB antialiasing and `antialiased` forces
  greyscale — thinner and softer, and invisible to every automated check.
- **`ui-monospace` must never lead `--font-mono`.** Chrome on Linux does not
  recognise it and resolves it to a PROPORTIONAL face when nothing follows.
  Named faces first; the browser suite measures advance width to prove it.
- **An inherited script is READ-ONLY until it is explicitly overridden**, and
  that is measured off the real 8.3.8 Designer, not designed here. Double-clicking
  an inherited Project Library script in the Designer does *nothing*; its context
  menu offers `Override Resource`, `Copy Path` and `Open read-only`, and the last
  opens a buffer headed `(Read-Only)` that discards every keystroke. Overriding
  does NOT break inheritance — the menu on an overridden resource has no `Delete`,
  only `Discard Overrides`, whose dialog says "return to its inherited state".
  Until 1.4.0 this module opened inherited scripts writable and created the
  override silently on the first save. `isLockedByInheritance` is the one place
  the rule lives; both save paths (button and Ctrl+S) check it, because the
  keybinding does not go through the disabled button.
- **Overriding writes nothing.** It is staged in the Designer too — verified on
  the gateway's own filesystem after `Override Resource`, which had created no
  local resource. The local copy appears on save, through the existing
  own-project write path.
- **A results list that is name-based must SAY so, wherever it is shown.**
  `scriptide/references` matches whole identifiers, not receivers — it is
  deliberately NOT `textDocument/references`, because that method promises a
  type-aware answer this server cannot give and answering it would be lying in
  the protocol. Two unrelated classes with a `write` method both answer to
  `write`. The Search view carries the caveat in its status line and
  `validate_v16_nav.py` asserts the words are there: a list read as a real
  find-references is a rename waiting to break an unrelated method.
- **A cross-file jump publishes a reveal for a view that does not exist yet.**
  Opening the target is React state, so the CodeMirror view for it is created by
  an effect on the NEXT render — after the caller's `await` has resolved. The
  editor therefore REMEMBERS one pending reveal and applies it when the view
  appears; dropping it lands the caret on line 1 with nothing on screen saying
  why, which is what the clicked-traceback path did from 1.5.0. Every navigation
  feature added later goes through the same `scriptide:reveal` event and inherits
  the fix — do not "simplify" it back to a straight lookup.
- **The script tree ships COLLAPSED and does not list Web Dev** (Nigel,
  02/09/2026). Quick open is the fast path now, so the tree is for browsing,
  which starts by choosing a branch; and Web Dev endpoints have their own
  activity-bar view with per-endpoint verbs and the config dialog, so listing
  them in the tree as well made the poorer of two entry points the first one
  people found. `FileTree` tracks an EXPANDED set rather than a collapsed one so
  that default falls out of the empty set — the alternative has to enumerate keys
  that do not exist until the project loads, and a missed key opens itself.
  `SHOWN_IN_ANOTHER_VIEW` is the only reason a resource type may be omitted;
  `unknownGroups` still renders anything this build has never heard of, because
  silently dropping a resource the gateway sent is how a script becomes
  uneditable with no message.
- **`ETag` is a quoted entity tag, and `If-Match` is parsed tolerantly.** Quoted
  per RFC 9110 §8.8.3 since 1.6.0; `HandlerSupport.unquoteEtag` strips `W/` and
  the quotes on the way in. Both halves are load-bearing together: a page loaded
  before the change holds a bare signature and sends it bare, a page loaded after
  it holds a value its own reader already stripped, and a proxy may quote either.
  Comparing raw strings turns any of those into a permanent 409 that reads on
  screen as somebody else editing the file.
- **Every API call goes through `apiUrl`, never a bare `/api/...`.** The SPA is
  served from `/data/scriptide/` on a gateway and from `/` under `npm run dev`,
  so a hardcoded path resolves against the server root and 404s on every real
  install. It also passes every unit test, because a mocked `fetch` accepts any
  string — all three routes added in 1.15.0 shipped to the rig broken with 588
  tests green, and `validate_v13`'s console-error check is what caught it. Tests
  for a new route assert the RESOLVED url, not that fetch was called.
- **A CSS class name is a shared claim — do not reuse one for a new kind of
  thing.** The live suites select on these class names, so widening what a class
  matches silently changes what a suite asserts. 1.15.0 did it twice in one
  release: runtime rows reused `.problems-row`, which is how
  `validate_v19_ruler` counts static problems; and the replace box reused
  `.search-panel-input`, which made `validate_v16_nav`'s `fill` ambiguous the
  moment a search returned hits. A new kind of row gets a new class.
- **Our own save is not somebody else's change, and staleness has TWO windows.**
  A write lands on the gateway before its new signature reaches the client, so
  mid-save the background listing and the open document disagree — and every
  check that asks "has this moved on?" answers yes about the user's own
  keystroke, showing the tab marker, the bar and the counted pull button
  (Nigel, 07/09/2026). `savingUris` covers the round trip; the second window is
  AFTER it, where the document carries the signature the write returned and the
  listing still holds the previous one. `isStale` compares for difference and two
  opaque signatures cannot say which is older, so the tree re-read is awaited on
  every save BEFORE the document leaves `savingUris` — not left to the poll. A
  failed or conflicted save leaves the set at once, because that is the one case
  where the bar is telling the truth.
- **A history restore LOADS THE BUFFER; it never writes.** `SaveHistory` is a
  side store, and the one write path stays the ordinary save — with its
  If-Match, its inheritance rule and its byte fidelity. A restore that wrote
  directly would be a second write path with its own bugs, and it would remove
  the moment where someone can look at what they are about to do. Both segments
  of a history path are HASHES of the username and the resource path, never the
  names: both are attacker-influenced strings that would otherwise become
  directories.
- **The export zip's entry paths come from `HandlerSupport.encodePath`, never
  `ResourcePath.getPath()`.** The latter drops the module and type, so an entry
  is `MyPackage/helpers/code.py` instead of
  `ignition/script-python/MyPackage/helpers/code.py`. In the Designer's format
  the PATHS ARE THE INDEX — there is no manifest listing the resources — so a zip
  missing the prefix imports as nothing, in the Designer as much as here, while
  looking entirely reasonable in a listing. Measured 07/09/2026 by importing our
  own file into the real Designer; a round trip through our own import passes
  either way, which is exactly why it is not the test.
- **An uploaded archive is checked DECOMPRESSED, and traversal is refused rather
  than sanitised.** Per-entry, per-archive and TOTAL caps (the last is what a zip
  bomb defeats the first two with), an entry count, and a resource-type
  allowlist. A `..`, an absolute path or a backslash is an error naming the
  entry: these become `ResourcePath`s, not filenames, so the reflex of stripping
  the `..` leaves something that still resolves somewhere. Also:
  `ZipInputStream` does NOT throw on data that is not a zip — it yields no
  entries — so check the `PK` magic, or a `.py` uploaded by mistake is reported
  as "holds no resource.json" and sends the reader after the wrong problem.
- **A PEP 263 coding declaration breaks the parse, and the fix must not move a
  single column.** Everything here parses from a `StringReader`, which is Unicode
  text, and Python 2 refuses `# -*- coding: utf-8 -*-` in one. Measured
  07/09/2026: a file carrying one reported a syntax error on line 1 about nothing
  in its own code, gave no outline, no go-to-definition and no style findings, and
  **was skipped entirely by test discovery** — a header that is ordinary in any
  file that has ever held a non-ASCII character. `ModuleSymbols
  .neutraliseCodingDeclaration` changes only the word `coding` to one of the SAME
  LENGTH, because every position this module reports becomes a range in the
  editor: delete the line and every mark below it lands one line out.
- **It has two halves, in different places, and only one of them is the parse.**
  Repairing the parse made such a module visible and it still would not RUN: the
  test runner compiles the module's source itself and seeds it through
  `Py.java2py`, which hands Jython a UNICODE string, where the declaration is
  refused. The script console never had the problem — it passes a Java String,
  which compiles as a byte str. So the neutralisation is applied in
  `TestRouteHandler` as well, and the console path is deliberately left alone.
  `validate_v29_authoring.py` asserts all three, the last one so nobody "fixes" a
  path that was never broken.
- **A style lint goes over the AST, never over the text.** The same seven checks
  are commonly written as regular expressions, for want of a parser; this module
  runs the interpreter's own. A regex for `== None` fires inside a docstring
  explaining why not to write `== None`, and one for a bare `except:` fires on the
  string `"except:"` in a log message. The bar for a diagnostic here is ZERO false
  positives — a lint that cries wolf gets every lint switched off — so half of
  `StyleChecksTest` is the negative cases. Style findings are WARNINGS and are
  published LAST, after the syntax error and the undefined names, which are
  statements that the code will not work rather than opinions about correct code.
- **Completion never waits on a database or a tag browse.** Both are cached with
  a TTL, and a miss answers nothing for that keystroke while a background refresh
  fills the cache. Reading JDBC metadata on the completion thread makes typing
  wait on a database, and the refresh runs on the module's own pool, never the
  gateway's.
- **Organise imports must treat a module docstring as prose, not as code.** The
  first implementation read it as code, so the imports below it counted as "below
  code" and the whole feature was a silent no-op on nearly every module in this
  estate. It also refuses rather than guessing: a syntax error, a backslash
  continuation or an unbalanced bracket leaves the file byte-identical, and a
  module using `exec`, `eval`, `globals` or a star import keeps every import it
  has. Removing a line of somebody's code is the one thing here that cannot be
  undone by reading it again.
- **An imported project-library module object is the GATEWAY's, not the run's,
  so never write into one.** Measured 07/09/2026 on 8.3.8: `__import__` of a
  library module returns the manager's own object — the same `id()` from two
  separate runs, a module global set in one run read back by the next, and
  `system` living in each module's own globals rather than in builtins. So
  The usual mocking mechanism, swapping `globals()['system']` in the module under
  test, would change what every other user's scripts see for as long as the block
  is open: the same class of mistake as the JVM-wide `__builtins__` edit above.
  The runner therefore executes each selected test module's SOURCE into a
  namespace private to the run. That is what makes a mock safe, and it also stops
  module state carrying from one run to the next. **The interlock is load-bearing
  and must not be removed as a formality**: when the source cannot be read the
  runner falls back to importing, sets `private = False`, and a mock then REFUSES
  rather than quietly writing into the shared copy.
- **A mock reaches the TEST module only, and the docs say so.** Production code
  the test calls has its own module globals, untouched, so it still reaches the
  real gateway. Mocking that too means writing into shared modules, which is the
  thing above. A test framework that quietly half-mocked would be worse than one
  that mocks nothing.
- **The helpers exist only during a run, and that has a visible consequence.**
  `scriptide` is seeded into the run's own copy of `sys.modules`; a helper
  ordinary gateway code could import would be a second script library nobody
  administers. So a test module that imports it at the TOP is not importable
  outside a run — from the Designer's console or by another module. The runner
  never imports a test module, so this costs a run nothing, and a module that must
  stay importable imports inside the function. Both halves are asserted in
  `validate_v28_tests.py` so neither is reported later as a bug.
- **`@timeout` is a budget, not an interrupt, and the message says so.** The test
  is allowed to finish and then fails if it took longer. Interrupting a running
  Jython call needs the mechanism that stops the whole execution, which would end
  the run rather than the test; the run-wide timeout is still what saves you from
  a hang. An existing failure is left alone — it is the more useful of the two
  facts.
- **A decorator widens which FUNCTIONS count, never which MODULES are looked
  at.** `@test` in a module the naming convention does not admit discovers
  nothing. Everything the rule below says about `plc.diagnostics.test_connection`
  survives the decorators unchanged, and the live suite asserts it as the
  load-bearing case it is.
- **Test discovery is narrow on purpose, and widening it is a production
  incident.** `def test_*` anywhere in a project would put
  `plc.diagnostics.test_connection` under a Run All button — a function whose job
  is to open a socket to a PLC. A test lives in a module whose last name starts
  with `test`, or under a `tests` package. The panel states the rule out loud so
  it reads as a rule rather than as a bug.
- **Three rules keep a test run's output capturable, and each fails SILENTLY.**
  Measured on 8.3.8, 06/09/2026, all asserted by `TestHarnessTest`:
  (1) **import before you print** — writing to `sys.stdout` and then importing a
  project library module loses the whole execution's output, so the harness runs
  two passes; (2) **re-assert the private state after the imports** with
  `Py.setSystemState(sys)` from Jython — an import leaves the THREAD's
  `PySystemState` on the platform's, so `print` goes to the gateway's console
  while an explicit `sys.stdout.write` still reaches the capture; (3) **flush
  from inside the harness** — Jython buffers `sys.stdout` and the runner's
  tail-flush does not reach that buffer on a batch run. The script console shows
  none of this, because a socket run has a periodic pump and a batch run does not.
- **An import moves the thread off our system state, and the runner puts it
  back.** Ignition resolves a project-library import by running that module
  through `ScriptManager.runCode`, which calls `Py.setSystemState(manager.sys)`
  on the CALLING thread and never restores it — so from the first such import
  onward, `print` AND an explicit `sys.stdout.write` both reach the gateway's own
  console instead of the run's capture. A script then succeeds, takes the time it
  really took, and shows nothing. `PrivateStateRunner.installImportHook` wraps
  `__import__` for the run and restores the state in a `finally`. Two things make
  the bug hard to see and are asserted rather than described: only an import that
  EXECUTES code does it (a stdlib module, or one already in the manager's
  registry, is fine), so the SAME script prints on its second run; and an
  explicit write is lost too, so asserting only on `print` would pass a half-fix.
- **There is no namespace-local builtins table in Jython — never write to
  `__builtins__` in place.** Every `PySystemState` is handed the same
  `PySystemState.getDefaultBuiltins()`, so `__builtins__['__import__'] = hook`
  from one console run replaces `__import__` for the whole JVM: every project
  script, every gateway event script, with a closure belonging to one session.
  This was done by accident on the rig on 07/09/2026 while diagnosing the bug
  above, confirmed from an unrelated session and repaired with
  `__builtin__.fillWithBuiltins`. Copy the table, mutate the copy, and set it on
  the state AND in the run's globals — the frame reads its builtins from the
  globals when they name one. Copy from the STATE's builtins, never from the
  namespace's: the console's namespace outlives a run, so copying forward chains
  a hook that restores a system state which has already been finished.
- **A batch run passes NO output listener.** A listener means STREAMING, and a
  stream needs a socket to arrive on; one passed from an HTTP request thread was
  never called once and the output was silently lost. `null` makes the runner
  accumulate, which is what a batch wants anyway.
- **The test harness must never catch bare.** `except AssertionError` and
  `except Exception`, never `except:`. A Stop and the execution timeout arrive as
  a Java `Error`, which is a `Throwable` and not an `Exception`; a bare handler
  swallows one and carries calmly on to the next test — a Stop button that appears
  to work and does nothing. `TestHarnessTest` asserts the absence, and that it
  parses, and that it defines no `def` (one namespace — see the two-dict trap).
- **A run's test ids are a SELECTION, not an instruction.** The server looks each
  one up in its own discovery; an id it did not discover is a 400. Trusting the
  body would make "run this test" a way to call any function in the project by
  name, through the write gate but past every rule about what a test is.

- **A recovered draft is opened over the gateway's CURRENT copy, never
  reconstructed from itself.** A draft holds text; a document also needs its
  type, data key, inheritance state and the signature the next save will send.
  Building one from the draft hands the write path an etag from a previous
  session, which is exactly the stale write `If-Match` exists to refuse. So
  `restoreDrafts` calls `openScript` first and applies the text over it — the
  tab is then dirty against what the gateway holds NOW, which is the truthful
  state, and the ordinary conflict machinery is already pointed at the right
  version. `validate_v31` asserts the gateway's copy is untouched.
- **Drafts are `localStorage`, and the notice says so.** Per viewer, per
  browser, invisible to the gateway and to every other machine. Saying "kept in
  this browser only" is the limit of the promise; implying the work was
  anywhere else would be a claim this cannot support. A CLEAN buffer is never
  kept — it is already on the gateway byte for byte, and a store full of
  unmodified copies pushes the genuinely unsaved ones out against the quota.
  Every read and write is wrapped: `localStorage` THROWS outright in a private
  window and under a thumbnail capture.
- **A template is compiled by the gateway before it ships, and its calls are
  checked against the live `system.*`.** A template seeds code into somebody's
  new file, so a plausible-but-wrong call is repeated everywhere anyone starts
  from it. `validate_v31_authoring.py` compiles every template with the running
  Jython. Doing this caught `beginNamedQueryTransaction` (which is for
  `runNamedQuery`) where `runPrepUpdate` needs the id from `beginTransaction`.
  Templates are library-only: an event script's signature is dictated by its
  type and already seeded from a measured stub.
- **A test that greps source for a lint is the false positive the lints avoid.**
  `templates.test.ts` asserts no template catches `except Exception` — and its
  first version failed on a COMMENT explaining why not to. Strip comments before
  a textual assertion, or write it over the AST. This is the same rule
  `StyleChecks` exists for, and a test that breaks it is no better than a lint
  that does.
- **The console's timestamp is rendered OUTSIDE the `<pre>`.** Inside it, a copy
  of the output carries a column of times somebody then has to strip out of a
  bug report. The EXPORT stamps every line regardless of the toggle and says
  the times are the BROWSER's clock — the toggle is about reading the console
  now, the export is about reading it later, and only one of them can be lined
  up against a gateway log.

- **Presence is a WARNING, never a lock, and the wording is load-bearing.**
  Nothing in the presence path refuses a save; `If-Match` on the write path is
  what actually prevents a lost update, and adding a second gate would be a
  worse mechanism wearing a friendlier face. The bar says "Saving is not blocked
  — talk to them first" for that reason. It also says **has it open**, never "is
  editing": that is what a Designer reports and what this module reports, and a
  tab left open over lunch counts. Claiming "editing" would be a statement
  neither feed can support.
- **The Designer feed reaches an INTERNAL platform type, and the fallback is not
  optional.** `DesignerResourceSessionEvent` lives in `gateway.jar`, not in the
  SDK's `gateway-api` — checked on 8.3.6 and 8.3.8 — so it is reached by class
  name and could stop matching after any patch release with nothing failing
  anywhere. Everything it CARRIES is public SDK (`ResourceSession`,
  `ConcurrencySessionInfo`, `ResourcePath`), so the reflection is confined to
  reaching the accessor. `PresenceSweep` is the floor under it and uses only
  `GatewaySessionManager`, so a shape change costs specificity, never the
  feature. `GET /api/presence` reports `designerFeed` AND `designerEventSeen` —
  attached, versus a real event actually read — so the failure is visible rather
  than silent. Verified against a REAL Designer on 8.3.8 (07/09/2026), never off
  the bytecode alone.
- **`ConcurrencySessionInfo.id()` IS `ClientReqSession.getPublicId()`**, measured
  off 8.3.8's bytecode. The destroy event carries only that id, so if the two
  ever diverge a closed Designer is never removed and the indicator only grows.
  The session attribute keys are literally `userName`, `remoteHost`,
  `remoteAddr`.
- **A presence subscriber sees the WHOLE gateway's event bus.** Guava dispatches
  by the subscriber's parameter type and the event type cannot be named at
  compile time, so the listener subscribes to `Object` — every event on the
  gateway, on the poster's own thread. The handler is two string comparisons and
  a return for anything else, and it must never throw: an exception there
  propagates a module's problem into the platform's dispatch.
- **The presence registry is keyed on the resource PATH, and the session id is
  never sent to the browser.** A Web Dev endpoint is one resource holding up to
  eight scripts, so two tabs on `doGet` and `doPost` are one file to everybody
  else — and to a Designer, which has no concept of our data keys. The session id
  stays server-side: it addresses a live platform session, and name, host and
  project are all a person needs to go and talk to a colleague.
- **A session-level sweep must never blank resources the event feed found.** The
  two feeds race by construction — the sweep sees a Designer every 15 seconds,
  its resource list arrives on the bus — so `putSessionLevel` refuses to
  overwrite a peer that has resources. A plain `put` there makes the file
  indicator flicker on a fifteen-second cycle.

- **This module is not becoming a git module** (Nigel, 01/09/2026).
  `Gaskony-Ignition/module-git` exists. git is driven from the terminal's command
  line; anything added later is VS Code-shaped status and diffs on top of the
  CLI, not a second implementation.

- **The terminal tries to be root, and cannot force it** (Nigel, 01/09/2026).
  `terminal.privileged` defaults true, but a process cannot raise its own
  privilege — only something already more privileged can create a privileged
  process for it. Two routes, both proved by DOING them, never by reading
  config, and both decided by the HOST:
  1. **The Docker daemon** (preferred, 02/09/2026) — `DockerExec` asks it for an
     exec with `User:"0"`. Needs nothing in the image, gets a real pty and resizes
     through the API. Ending one is not free — see the two rules below.
  2. **`sudo -n`** where the host grants it. `-n` is load-bearing: without it a
     prompting host hangs the shell.
- **The two routes are NOT the same risk, and must keep separate switches.**
  sudo grants root inside this container; the Docker socket is the daemon's full
  API as root ON THE HOST. The socket is the LARGER grant despite being the
  tidier mechanism. `terminal.docker=false` refuses it while keeping sudo.
- **Never identify this container by hostname.** The rig runs with
  `network_mode: host`, so `hostname` returns the workstation's name and a
  caller that trusted it would exec into a container named after the laptop.
  `/proc/self/cgroup` is `0::/` on cgroup v2 and equally useless.
  `ContainerIdentity` reads `/proc/self/mountinfo`, which carries the full
  64-hex id — verified against `docker inspect -f '{{.Id}}'`.
- **`Tty: true` on a Docker exec does two jobs.** It gives the shell a real pty
  AND makes the attached stream raw; with `Tty: false` the daemon multiplexes
  stdout and stderr behind an 8-byte frame header, which reaches xterm.js as
  garbage every few hundred bytes.
- **Resize a Docker exec AFTER the attach, never before.** A
  `POST /exec/{id}/resize` sent before `/exec/{id}/start` has no exec session to
  size: the daemon blocks and then answers `500 timeout waiting for exec session
  ready`, and our own five-second watchdog cut that short — which is why every
  1.4.x terminal took exactly 5.00 s to open and the resize never applied. Attach
  first and the same call returns 200 in about 90 ms. `DockerExec.start` retries
  it three times at 100 ms, because the session becomes ready a moment after the
  upgrade.
- **Closing the hijacked attach does NOT kill the shell, so the sweep is
  load-bearing.** The Engine API has no "kill this exec"; the daemon keeps the
  process running, detached, and the exec's own `Pid` is a HOST pid this JVM
  (uid 2003, container pid namespace) can neither see nor signal. So a close
  sends ETX, EOT and `exit`, polls `Running:false` for up to 750 ms, and then
  ALWAYS runs a root sweep exec that walks `/proc/*/environ` for
  `SCRIPTIDE_TERM=<terminal id>` — `kill -HUP`, one second, `kill -KILL`. The tag
  is inherited, so a background job goes with its parent. `TerminalService.shutdown`
  waits on `DockerExec.awaitReapers` because the sweep runs on a daemon thread.
  The `script(1)` route has its own ladder: descendants and `script` get
  `destroy()`, then `destroyForcibly()` 300 ms later — `script` installs a SIGTERM
  handler and an interactive bash ignores SIGTERM outright.
- **Policy is read live, file first.** `PolicySource` resolves every `ExecPolicy`
  and `TerminalPolicy` switch as **file > `-D` system property > built-in
  default**. The file is `<gateway data dir>/modules/scriptide/policy.properties`
  (`java.util.Properties`, the same fully-qualified keys as the `-D` names),
  re-statted at most once every 2 s, and wired in `ScriptIdeModuleHook.startup()`.
  **The module never creates it** — absent means "no overrides", which is where
  every existing gateway already is. A system property is only readable at boot,
  so without the file the "turn it off without a restart" claim was true of the
  code and false of the gateway.
- **The exec frame handler must never wait for a script.** `ScriptIdeSocket` is an
  `AutoDemanding` listener — one frame at a time, on the socket thread — so a
  blocking run made the whole connection deaf: a Stop sent into a running loop was
  not read until the loop had ended, and the LSP and terminal froze with it.
  `ExecutionService.submit` returns as soon as the work is accepted, and
  `started`, `output` and `finished` are sent from its callbacks.

- **Git is READ-ONLY here, and must stay so.** The tree shows what differs from
  the last commit; `module-git` does staging, committing and remotes. There is no
  route in this module that writes to a repository, and adding one would reopen a
  decision Nigel took on 01/09/2026. `GitProbe` reads the working tree with JGit
  at `<dataDir>/projects/<Project>/.git` — the same path `module-git`'s
  `GitManager.getProjectFolderPath` resolves. Keep them agreeing.
- **An unresolvable HEAD makes JGit call every tracked file untracked.** Measured
  on 6.10.1: nothing is "in HEAD", so a whole committed project reports as newly
  added, and NOTHING throws or logs. Check `getFullBranch()` before asking for
  status — an indicator claiming a repository lost its history is worse than one
  admitting it cannot read it. The same rule generalises: an undecorated tree
  claims "nothing changed", so every failure state needs its own field on the
  wire, never an empty result.
- **A shipped library the Gateway already owns is a packaging fault, not a
  nuisance.** JGit pulls slf4j, and `ModuleJarPackagingTest` refused the build
  until it was excluded on the dependency. Exclude it there, never on the
  configuration: `modlImplementation` feeds the compile classpath too, and
  excluding at that level took slf4j away from this module's own loggers.
- **A live suite creates the fixtures it destroys.** `validate_v32_git` first
  edited and deleted whichever library script came first in the project, and
  three runs permanently removed two real probe scripts from the shared scratch
  project. Never operate on a resource you did not create, and clear your own
  fixtures BEFORE taking a baseline — leftovers from an interrupted run get
  committed into it and the next assertion reads the wrong state.

## Build, deploy, verify

```bash
./gradlew clean build                      # includes the Vitest suite via `check`
cd scripts/testing
SI_GATEWAY_CONFIG=$PWD/config.local.json PLAYWRIGHT_BROWSERS_PATH=$HOME/.cache/ms-playwright \
  <venv>/python install_via_webui.py       # installs; does NOT decide if it worked
SI_GATEWAY_CONFIG=$PWD/config.local.json PLAYWRIGHT_BROWSERS_PATH=$HOME/.cache/ms-playwright \
  <venv>/python deploy_gate.py             # THE arbiter — must print PASS
```

**Never claim a deploy worked, never start live validation, and never tag a
release unless `deploy_gate.py` prints PASS.** Every cheaper signal lies: the
version string and the JS hash are both stamped at build time, so neither can tell
you whether the code you just wrote is the code now running.

The gate's SOCKET check is not optional padding — it is the only thing that proves
the WebSocket servlet actually registered, and checks 1–4 all pass green when it
has not.
