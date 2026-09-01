# Changelog

All notable changes to this module. Format follows [Keep a Changelog](https://keepachangelog.com/).

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
