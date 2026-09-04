# Script IDE — module instructions

**Version**: 1.8.10 · Module ID `com.gaskony.scriptide` · Repo `Gaskony-Ignition/module-script-ide`

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
