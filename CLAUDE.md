# Script IDE — module instructions

**Version**: 1.21.0 · Module ID `com.gaskony.scriptide` · Repo `Gaskony-Ignition/module-script-ide`

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

**Internal/PoC status, like web-designer and playwright: NOT in `modules/release.sh`
or `test-all.sh`, and never on the public portal.** Build with its own `./gradlew`.

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
- **An imported project-library module object is the GATEWAY's, not the run's,
  so never write into one.** Measured 07/09/2026 on 8.3.8: `__import__` of a
  library module returns the manager's own object — the same `id()` from two
  separate runs, a module global set in one run read back by the next, and
  `system` living in each module's own globals rather than in builtins. So
  the alternative's mocking mechanism, swapping `globals()['system']` in the module under
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
