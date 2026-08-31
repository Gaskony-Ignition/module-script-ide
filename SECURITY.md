# Security

## The threat model, stated plainly

**An Administrator using this module can do anything the Gateway JVM can do.**

That is not a new capability. Designer access already runs arbitrary Jython on the
gateway, and anyone with the Administrator role already has it. This module makes
that power reachable from a browser; it does not create it.

**There is no sandbox, and there will not be one.** A convincing-looking sandbox is
worse than none, because people trust it. The sibling `python3` module shipped an
AST-based "restricted mode" and deleted it in May 2026 after
`[].__class__.__mro__[1].__subclasses__()` walked straight through — the lesson is
recorded here so nobody rebuilds it.

## What is enforced

| Action | Requirement |
| --- | --- |
| Load the SPA shell | none (so the Gateway login can be presented) |
| Session probe `/api/auth/session` | none — answers `authenticated:false` rather than 401 |
| Read scripts, language features | authenticated Gateway session |
| **Write** a script or its attributes | session + **Administrator** + `X-CSRF-Token` + `If-Match` signature |
| **Execute** a script | session + **Administrator** + CSRF token on the socket + same-origin handshake |

Specifics that matter:

- **Identity is baked in at the WebSocket handshake** and is `final`. Nothing the
  client sends afterwards can change who a socket is.
- **Policy is re-read per frame**, not cached at connect, so disabling execution
  takes effect on sockets that are already open.
- **No actor-string fallback.** A sibling module grants access to a non-session
  caller presenting a non-empty `RequestContext.getActor()`, and its own Javadoc
  flags that as unvalidated. This module drops it entirely: what sits behind the
  gate is arbitrary code execution, and nothing but a browser talks to this module.
- **Type gating.** The resource routes are generic over `<moduleId>/<typeId>`, so
  both read and write demand `moduleId == "ignition"` *and* a known script type. A
  Perspective view or a tag configuration cannot be written through them.
- **Every execution is audited** before it runs, recording a SHA-256 of the source
  plus its size — never the source itself. An audit table is not a code store, and
  a credential typed into the console must not be copied into one.

## Turning it off

Set in `data/ignition.conf` as `wrapper.java.additional.N=-D<key>=<value>`:

| Property | Default | Effect |
| --- | --- | --- |
| `com.gaskony.scriptide.execution.enabled` | `true` | `false` refuses every execution, gateway-wide |
| `com.gaskony.scriptide.execution.timeoutSeconds` | `60` | per-execution budget, capped at 600 |
| `com.gaskony.scriptide.execution.maxConcurrent` | `4` | size of the module's own thread pool |
| `com.gaskony.scriptide.audit.includeSource` | `false` | `true` also writes full source to the module log |

`execution.requireAdmin=false` exists but is **ignored unless
`execution.acknowledgeRisk=true` is also set**, and then warns on every execution.
Two flags, because handing arbitrary Gateway-JVM execution to every authenticated
user should not be reachable by one typo'd property.

An unparseable boolean falls back to the **secure** value, never to `false`.

## Isolation

Each execution runs on the module's own bounded thread pool — never the gateway's
executor, because one `while True:` on that would take the gateway down rather than
just this module.

Each execution gets a **private `PySystemState`**, so concurrent users cannot see
each other's output. This is measured, not assumed: the obvious approach
(`ScriptManager.addStdOutStream` with per-thread routing) leaked 22–25 lines
between concurrent users, because Jython's `sys.stdout` is a single shared buffer.
The replacement measures 0 cross-talk over 500 lines each way, and that test runs
against the live gateway on every release.

## Stopping a script is best-effort

`ScriptManager.interrupt()` fires at the next Python trace point. Measured: a 15 s
busy loop stops in 3.0 s; an interrupted `time.sleep(10)` still runs the full
10.06 s. A script blocked in a JDBC call, a socket read, or `time.sleep` **cannot
be stopped**, and the UI says so rather than showing a button that lies. After
escalation the execution is marked abandoned and counted — a Java thread cannot be
killed.

## Reporting

Internal module. Raise anything you find with Nigel directly.
