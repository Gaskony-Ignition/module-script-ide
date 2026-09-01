# Changelog

All notable changes to this module. Format follows [Keep a Changelog](https://keepachangelog.com/).

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
