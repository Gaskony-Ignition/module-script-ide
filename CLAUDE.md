# Script IDE — module instructions

**Version**: 1.4.2 · Module ID `com.gaskony.scriptide` · Repo `Gaskony-Ignition/module-script-ide`

Read `/home/nigel/Ignition-Work/modules/CLAUDE.md` first — the suite-wide rules
(signing, dependency boundaries, Gradle/Java versions, skills) all apply here.
This file covers only what is specific to this module.

## What it is

A browser-based Jython IDE for Ignition 8.3, served from the Gateway. Edit
Project Library and Gateway event scripts with completions taken from the running
gateway, live error checking, project-wide navigation, and a script console that
executes on the Gateway.

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
     exec with `User:"0"`. Needs nothing in the image, gets a real pty, resizes
     through the API, and closes cleanly because the shell is the daemon's child.
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
