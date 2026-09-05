# Script IDE for Ignition

Write Ignition scripts in a real editor, in the browser, against the live gateway.

**Version**: 1.15.3 · **Module ID**: `com.gaskony.scriptide` · Ignition 8.3+

---

## Why this exists

Ignition's Designer ships a script editor that has been essentially unchanged for
years: syntax highlighting and a completion popup in a Swing text area. Anyone who
writes Python anywhere else is used to go-to-definition, symbol search, errors
before you save, and a console that runs what you just wrote.

Inductive Automation's own stated direction is to expose the Language Server
Protocol so you can use your own IDE — they rejected embedding a browser engine in
the Designer, because Chromium is only present when Perspective is installed. As of
April 2026 nothing had been committed.

So the gap is real and stable, and it is worth filling from the other side: not
"bring your project to your IDE", but **bring a real IDE to the gateway** — no
install, no Designer, reading the API of the gateway that is actually running.

## What it looks like

![The Script IDE editing a project library script: a file tree on the left grouped by script type, a tab strip, and the Python source with syntax highlighting and line numbers](docs/images/editor.png)
*Editing a project library script. The left rail groups scripts by type and marks
inherited resources; the footer shows whether the language server is connected.*

![Typing system.tag. brings up a completion list showing browse, configure, copy and more, each with its real parameter list, alongside a documentation panel describing the selected function](docs/images/completion.png)
*Completions come from **the gateway you are connected to** — real parameter names,
defaults and documentation, including functions from whichever modules that gateway
actually has installed. No static stub file can know that.*

![A deliberate syntax error marked with a red squiggle in the editor and a matching marker in the gutter](docs/images/diagnostic.png)
*Errors are checked by the gateway's own Jython 2.7 parser, so Python-2 code —
`print "x"`, `except E, e:`, `10L` — is never wrongly flagged.*

![The Ignition Gateway home page navigation with a Script IDE entry alongside the other installed modules](docs/images/gateway-nav.png)
*It appears on the Gateway home page like any other module.*

## What it does

- **Edit** Project Library scripts and Gateway event scripts (timer, message,
  startup, shutdown, scheduled, tag change), written through the platform's own
  resource API — so no file stamping and no project scan. Saved scripts are
  importable a couple of seconds later.
- **Run** a buffer, a selection, or the file in the active tab on the gateway.
  Output appears as it is produced — flushed on a newline, at 4 KB or every
  100 ms — so a loop shows its first line before its last. A failure comes back
  as a real traceback, `File "…", line N, in f`, and a frame inside a project
  library script opens that script at the line. Stop is read while the script is
  still running, and Reset drops the console's variables the way the Designer's
  does. Concurrent users never see each other's output.
- **Autocomplete and signature help** from the running gateway's script registry.
- **Live error checking** against the real Jython 2.7 parser.
- **Outline** the open script — every class and function, click to jump — parsed
  by the gateway rather than by a client-side grammar, so Python 2 code outlines
  correctly. Find and replace are in the editor on Ctrl+F.
- **Navigate the project.** Go to definition on F12 or Ctrl-click, across files.
  Quick open on Ctrl+P, with `#` to jump to a function or class anywhere in the
  project. A Search view that reads every Project Library script on the gateway,
  not just the open ones. Shift+F12 lists every place a name is written — matched
  by name rather than by type, which the results say plainly. A Problems panel
  collecting the errors in every open script, because a squiggle only helps in
  the file you are looking at. Folding, and go-to-line on Ctrl+G.
- **Web Dev** endpoints as a first-class view: all eight HTTP methods, per-method
  settings, create and delete.
- **A terminal on the gateway** — a real shell on a real pseudo-terminal, with a
  prompt, history, Ctrl-C and colour. It is what makes `git` usable against the
  projects directory. Same gate as execution, with its own switch. What it runs
  as is decided by the host, never by this module: a root shell through the
  Docker daemon where the socket is mounted and writable, otherwise root through
  `sudo -n` where the host already grants it, otherwise the Gateway's own
  operating-system user. Closing the tab ends the shell and the jobs it
  started.
- **A VS Code-shaped shell**: activity bar, resizable side bar and outline, a
  bottom panel holding the console, the problems list and the terminal, and the
  four layout glyphs in the title bar.

Breakpoint debugging is deliberately **not** included: the only serious Ignition
debugger requires a running Designer, which defeats the point of a browser IDE.

## Byte fidelity

A script saved here is byte-identical to one saved by the Designer — tabs stay
tabs, and no trailing newline is added. That is asserted on every release against
the gateway's own filesystem, not just in a round trip, because a diff-noisy save
makes every subsequent `git diff` useless.

## Requirements

- Ignition **8.3.0+**
- A Gateway account with the **Administrator** role to edit or run scripts.
  Any authenticated user gets the full language intelligence without the Run
  button.

## Security

An Administrator using this module can do anything the Gateway JVM can do. That is
the Designer's existing threat model, not a new one — Designer access already runs
arbitrary Jython on the gateway. There is no sandbox, and a fake one would be worse
than none.

Execution requires an authenticated session, the Administrator role, a CSRF token,
and a same-origin WebSocket handshake. Every run is audited by hash, and execution
can be switched off gateway-wide with
`-Dcom.gaskony.scriptide.execution.enabled=false`.

The terminal is gated the same way and has its **own** switch
(`-Dcom.gaskony.scriptide.terminal.enabled=false`), so a site can keep the Script
Console and refuse the shell. It grants no privilege that Jython's
`Runtime.exec` did not already reach — see `SECURITY.md`, which says so plainly
rather than resting on the equivalence.

Both sets of switches are also read live from
`<gateway data dir>/modules/scriptide/policy.properties` — same keys as the `-D`
names, standard `java.util.Properties`, re-read within two seconds — so a site
can turn execution or the terminal off on a **running** gateway. The module never
creates that file; absent means no overrides. A system property still states the
fleet default at boot, and the file wins over it. Because the file can also turn
the Administrator requirement off, its permissions belong to the Gateway's own
user and nobody else, exactly like `ignition.conf`.

## Build

```bash
./gradlew clean build     # runs the frontend test suite too
```

Requires JDK 17 and Node.js. Signing is skipped automatically when no keystore is
configured; see `gradle.properties.template`.

## Licence

Internal. Not published to the module portal.
