# Script IDE — module instructions

**Version**: 1.0.0 · Module ID `com.gaskony.scriptide` · Repo `Gaskony-Ignition/module-script-ide`

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
