# State

**Read this first each session.** Single source of truth for where the module is.

**Version 1.25.0 · deployed on `ignition-module-testing` (8.3.8) 07/09/2026.**

### 1.25.0 — git status in the tree (07/09/2026)

Nigel asked for it directly. **Read-only**, and it stays that way: `module-git`
does staging, committing and remotes. This is the half you want while editing —
which of these files have I changed — shown as one letter per row.

**Pure Java, because there was no other route.** The rig runs a stock image with
no `git` binary and building a custom one is settled the other way, so the
gateway reads `.git` with JGit at `<dataDir>/projects/<Project>/.git` — the same
path `module-git`'s `GitManager` resolves, checked against its source so the two
cannot disagree on one gateway. slf4j is excluded from the dependency;
`ModuleJarPackagingTest` refused the build otherwise, correctly.

**Two files are one script.** `code.py` and `resource.json` fold into one
resource mark on the gateway. The client rolls a deleted resource's mark up to
the nearest surviving node, and folders take the WORST mark below them — a
collapsed package must not let a deletion hide behind an addition.

**The measurement that changed the design.** With an unresolvable HEAD, JGit
reports every tracked file as untracked: nothing is "in HEAD", so a whole
committed project renders as newly added, with no exception and no log line. The
first `GitProbe` did exactly that. It checks the branch before asking for status
now. The states are distinct on the wire — `repo:false`, `error`, `head:null`
for an unborn branch — because an undecorated tree claims "nothing changed" and
every failure has to look different from that claim.

**Cost:** polled only for projects a client actually has open, read from the
presence registry rather than a second list. Ten seconds; an unchanged read does
not push.

`validate_v32_git.py` 25/25, twice, against a real repository. **Its own first
version deleted two real probe scripts from the shared scratch project across
three runs** — it edited and deleted whichever library script came first instead
of one it owned. Restored from the fixture baseline; the suite now creates what
it destroys.

### 1.24.0 — templates, autosave, console export (07/09/2026)

The last three items of `the borrowed-ideas brief`; **all four groups are now
done**.

**Autosave.** Every dirty buffer is kept in `localStorage` as you type and
offered back on the next load. Restore opens the gateway's CURRENT copy and
applies the recovered text over it, so the tab is dirty against what the gateway
holds now rather than carrying a signature from a dead session. The notice says
"kept in this browser only", because that is the limit of the promise.

**Six templates** for a new library script. Library only — an event script's
signature is dictated by its type. Each obeys the rules it would otherwise teach
people to break (tabs, `except Throwable`, parameterised SQL), and
`validate_v31` COMPILES every one of them with the gateway's own Jython. That
caught the transaction template using `beginNamedQueryTransaction`, which is for
`runNamedQuery` — `runPrepUpdate` takes the id from `beginTransaction`.

**Console export and timestamps.** Export writes a stamped text file with ANSI
stripped; Times is an off-by-default toggle, remembered per viewer, rendered
outside the `<pre>` so copying the output does not copy the times.

### 1.23.0 — presence: who else has this file open (07/09/2026)

Nigel asked whether we could detect that somebody else has a script open, from
another browser or from the Designer. We can, and the gateway was already keeping
the answer.

**Two feeds, one registry.** Browser clients report their open paths over the
socket they already hold. Designers are read from Ignition's own concurrent-editing
feed: the platform posts `DesignerResourceSessionEvent` on the Guava `EventBus`
that `CommonContext.getEventBus()` returns — public SDK — carrying session id,
username, hostname, IP, start time and the exact `ResourcePath`s open. The module
registers on the same bus the platform's own manager uses. Everything is pushed;
only departure is swept, because there is no event for a session that went away
without saying so.

**Verified against a REAL Designer on 8.3.8, not off the bytecode.** Opening
`MiningDemo.config` in the Designer put `ignition/script-python/MiningDemo/config`
in the module's list within seconds, and the browser showed *"admin in the
Designer on 172.31.0.2 also has this open."* Closing the script cleared the path;
exiting the Designer cleared the peer.

**The caveat that will matter later:** `DesignerResourceSessionEvent` is in
`gateway.jar`, NOT the SDK's `gateway-api` — checked on 8.3.6 and 8.3.8. It is
internal and may change in a patch. Everything it carries is public SDK, the
reflection is confined to reaching the accessor, and `PresenceSweep`
(`GatewaySessionManager`, fully supported) is the floor: a shape change costs
specificity, never the feature or the startup. `GET /api/presence` reports
`designerFeed` and `designerEventSeen` so it fails visibly.

**It is a warning, not a lock.** `If-Match` is what prevents a lost update.
Presence exists so two people find out about each other before the conflict, and
the bar says so. It says "has it open", never "is editing" — that is what both
feeds actually report.

Also: run history is searchable (over source AND output) and records how long
each run took.

### 1.22.0 — authoring: snippets, imports, live completion, lints, colour (07/09/2026)

Groups 2 and 3 of `the borrowed-ideas brief`, and the first part of group 4.
Eighteen tab-stop snippets; organise-imports and suggested imports on the open
buffer; live tag-path completion inside a string literal and table/column
completion inside SQL; seven style lints; and `cprint` / `jsonPrint` with a
console that renders ANSI rather than showing the escape bytes.

**The most valuable thing in it is a bug nobody was looking for.** A
`# -*- coding: utf-8 -*-` header made the WHOLE FILE a syntax error — everything
here parses from a `StringReader`, which is Unicode text, and Python 2 refuses a
coding declaration in one. A file carrying one got a red mark on line 1 about
nothing in its own code, gave no outline and no go-to-definition, could not be
organised, and **was skipped entirely by test discovery**. Confirmed on the
released 1.21.0: a test module with that header was invisible.

It had **two halves, in different places**. Repairing the parse made the module
visible and it still would not RUN, because the test runner compiles the source
itself and seeds it through `Py.java2py`, which hands Jython a unicode string. The
console never had the problem — it passes a Java String, which compiles as a byte
str, and is deliberately left alone. All three are asserted.

**Three defects were caught in review rather than by a user**, and each is the
same shape — something asserted from recall rather than read off the repo:

- organise-imports read a module docstring as CODE, so the imports below it were
  "below code" and the feature was a silent no-op on nearly every well-written
  module here;
- the `tagchange` snippet named `event.getTagPath()`, when there is no `event` in
  a tag change script and `tagPath` is bound directly — the correct list was
  already in this repo, in `UnknownNames`;
- the console's ANSI reset turned bold off and left the text coloured, because
  `Object.assign` cannot copy keys that are not there.

**The lints are structural, not textual.** the alternative ships the same seven checks as
regular expressions because they have no parser. Half of `StyleChecksTest` is
negative cases a regex fails: `except:` inside a string, `== None` in a docstring.

Gate PASS. `validate_v29_authoring.py` 20/20.

### 1.21.0 — the test framework (07/09/2026)

The first of the four groups of ideas taken from the alternative's Script IDE
(`the borrowed-ideas brief`, Nigel approved all four). What is portable from
their runner is the SHAPE of a test framework, not its mechanism — theirs cannot
execute on the gateway at all — and the mechanism they use for mocking turns out
to be unsafe here. That is the substance of the release. `docs/TEST-FRAMEWORK.md`
is what a person writing a test reads.

**The measurement it rests on.** `__import__` of a project-library module hands
back the manager's OWN module object, shared with every script on the gateway:
the same `id()` from two separate runs, a module global set in one run read back
by the next, and `system` living in each module's own globals rather than in
builtins. So swapping `globals()['system']` — how their mocks work — would change
what every other user's scripts see for as long as the block is open. Same class
of mistake as the JVM-wide `__builtins__` edit at 1.19.0.

**So the runner executes each selected module's source into a namespace private
to the run** rather than importing it. Three things follow, all asserted on the
gateway by `validate_v28_tests.py` (38/38):

- a mock replaces `system` in that namespace and the SHARED module is untouched —
  proved by importing it from the console after a run that mocked it;
- **module state no longer carries between runs**, a cost the panel used to have
  to warn about;
- when the source cannot be read the runner imports instead and a mock **refuses**
  rather than quietly writing into the gateway's copy.

**What was built.** `@test`, `@skip`, `@timeout`, `@cases`, `@beforeAll` /
`@afterAll` / `@beforeEach` / `@afterEach` (with `setUp` / `tearDown` still
working); twelve assertions; `mockTags` and `mockQuery`, which record every write
and every call and RAISE for anything they were not given; a fourth outcome
`skip`; and re-run-failed-only, which sends parent ids because a parameterised
case is not separately runnable.

**Two limits, stated rather than left to be discovered.** A mock reaches the TEST
module only — production code the test calls has its own module globals and still
reaches the real gateway. And `scriptide` exists only during a run, so a test
module that imports it at the top is not importable outside one; a module that
must stay importable imports inside the function. Both are asserted, so neither
gets reported later as a bug.

`@timeout` is a **budget, not an interrupt**: the test finishes and then fails if
it took too long. Interrupting a running Jython call needs the mechanism that
stops the whole execution, which would end the run rather than the test.

**The Jython is a resource now**, not a Java string: `scriptide.py` and
`runner.py` in the gateway jar, parsed by `TestHarnessTest` and asserted into the
built `.modl` by `ModuleJarPackagingTest` — this estate has already shipped a
green build of a `.modl` missing a file nobody had asserted was in it.

### 1.20.0 — export and import, in the Designer's format (07/09/2026)

Nigel: *"there is no export/import code options like in the designer"*, choosing
the **Designer-compatible resource zip** over plain `.py` files, on the tree's
right-click menu. Both are built; the tree has a right-click menu for the first
time.

**The format was measured and the round trip finished.** `docs/EXPORT-FORMAT.md`
records what the Designer actually writes, captured by driving it. A zip written
by this module was then opened in the real Designer, imported, and the script
afterwards was byte-identical. Two findings came out of finishing that rather
than stopping when it looked right:

- **a defect our own round trip could never have caught.** Entry paths were built
  from `ResourcePath.getPath()`, which drops the module and type. In this format
  the paths ARE the index, so the zip imported as nothing — in the Designer and
  here — while looking perfectly reasonable in a listing.
- **a correction to the note written an hour earlier.** It claimed the Designer
  does not warn about overwriting and offers no rename, from watching the
  selection dialog and cancelling before pressing Import. `Import` raises a modal
  **Resolve Conflicts** with Overwrite / Skip / Rename. Both claims were wrong,
  and both flattered the design being built against them.

**The security surface is the upload.** Traversal refused rather than sanitised;
per-entry, per-archive and total size caps checked on the DECOMPRESSED stream; an
entry count; and a resource-type allowlist so a Designer export's Perspective
views are listed but never written. All in `TransferRouteHandlerTest`, one of
whose tests found that `ZipInputStream` yields no entries rather than throwing on
non-zip data — so a `.py` uploaded by mistake blamed the wrong thing.

### 1.19.0 — a run that printed nothing, and a console you can arrange (07/09/2026)

**The serious one: output was lost from the first project-library import
onwards.** Nigel: *"it worked but didn't output the print as it was supposed to.
I then went and ran the exact same thing in the designer script console and it
outputed the json results as I expected."*

Ignition resolves a project-library import by running that module's code through
`ScriptManager.runCode`, which moves the calling thread onto the manager's
`PySystemState` and never moves it back. From that point `print` and an explicit
`sys.stdout.write` both reach the gateway's own console. The run succeeds, takes
the time the work really took, and shows nothing.

Two properties are why it survived fifteen releases and eleven live suites, and
both are now asserted:

- **only an import that EXECUTES code does it.** A standard-library module uses
  Jython's own importer, and a module already in the manager's registry is copied
  across by `applyModuleRegistry` and never imported at all — so the same script
  prints on its SECOND run. That is the part that makes it read as random.
- **an explicit `sys.stdout.write` is lost too.** So this is not the
  `print`-versus-write asymmetry `TestHarness` documents: the whole `sys` moved.

The fix is a **private builtins table per run** whose `__import__` restores the
state in a `finally`. `PrivateStateRunnerImportTest` (5) pins it, and
`validate_v26_console.py` (23/23) proves it on the gateway across every case in
the table on `installImportHook`.

**A mistake worth keeping.** The first attempt hooked `__builtins__` in place
from a console run. There is no namespace-local builtins table in Jython — every
`PySystemState` gets the same `getDefaultBuiltins()` — so that replaced
`__import__` **for the whole gateway JVM** with a closure holding a list in one
console session, which then grew on every import anywhere. Confirmed from an
unrelated session (`__import__ is <function _si_hook>`), repaired with
`__builtin__.fillWithBuiltins`, and verified back to
`<built-in function __import__>`. The rig was the right place for it to happen
and a production gateway would not have been. It is now a rule in `CLAUDE.md` and
an assertion in both the unit test and the live suite.

**A save looked like a conflict.** *"When I click save while it is saving to the
gateway a pull request pops up on the script."* The write lands before its
signature comes back, so mid-save the listing and the document disagree and every
staleness check answered yes about the user's own keystroke. Two windows: the
round trip (a per-document `savingUris` set) and the moment after it, where the
document is ahead of the listing — closed by awaiting a tree re-read before the
document leaves the set, because two opaque signatures cannot say which is older.
The check samples every 25 ms and **was proved able to fail** with the fix
reverted and redeployed; a timing assertion never seen red is one whose window is
too narrow to sample.

**The console splits where you want it.** *"I need to be able to adjust the size
between the script and output windows... I also want to be able to choose to have
them both horizontal or vertical side by side."* A draggable divider, a
rows/columns toggle in the toolbar, and both remembered. The split is kept as a
SHARE rather than a pixel count — the popped-out console is a tab people resize —
and each orientation keeps its own.

**And the teal corner.** *"When I pop out the script console to a new tab there is
a tiny bit on the top left that looks teal but the rest looks violet."* Measured
rather than guessed: both aurora packs share the base `#1a1233`, which IS violet,
and all the teal lives in `--page-glow`, whose first radial is centred at
`6% -14%`. The console painted an opaque `--bg-primary` over the glow and the
popped-out page framed it in `.app-main`'s 32px padding, so the only lit ground
left was that padding — at the corner where the teal is. `.console` now carries
the glow with `background-attachment: fixed`, and `.app-main-console` fills its
tab.

### 1.18.0 — the compare feature is gone (07/09/2026)

Nigel: *"The comparison to other gateways is not required. You can remove that.
I didn't realise that was something you were trying to do."*

R5 was built at 1.17.0 and is **withdrawn**, in full — the Compare view, the peer
configuration, the outbound client, the `/api/remote/*` routes, the
`/api/scripts/digest` route, `ProjectIndex.digest`, `dockers/peer.sh` and the
`v25` suite. What matters beyond the deletion:

- **The module has no non-session authentication again.** The peer token gate
  (`requireAuthenticatedOrPeer`) went with it, so every route is back to an
  authenticated session, and the four reads it covered take the ordinary
  authenticated gate. There is now nothing in this module a caller without a
  browser session can reach.
- **The module makes no outbound HTTP calls.** `RemoteClient` was the only one.
- **`policy.properties` is back to the two switches it had before** — execution
  and the terminal. `PolicySource.childNames`, which existed only to let an
  operator invent peer names, is gone with its only caller.
- **`validate_v24_gateways_tests.py` is now `validate_v24_tests.py`** and covers
  the test runner alone. F2 in the review — "it has only ever run on one gateway"
  — was a question about the compare feature and goes with it.

R6 (the test runner) is untouched: it was the other half of 1.17.0 and it stays.

**The split-editor button is a labelled control now**, not a `⇹` in muted grey at
the end of the tab strip. Nigel found it only by going looking for it — *"the
button is so small I didn't even notice it"* — which is the same defect as an
absent feature. It carries an icon, the word (`Split`, `Move right`, `Move left`)
and a border, and the README has a picture of the split for the first time,
in the slot the compare screenshot used to hold.

### 1.17.x — the two large ones the review left open (06/09/2026)

Nigel: *"Please finish the unfinished tasks"* — and, asked which of R5 and R6 to
build given the review recommended AGAINST R6, chose **both**. F1 was decided at
the same time: **the module stays internal**, now on the record rather than by
inertia.

**R5 — two gateways side by side.** Built here and **removed at 1.18.0** at
Nigel's request; see above. The rest of this section is the release as it stood.

**R6 — a Jython test runner.** Nothing in Ignition offers one, and the isolated
execution primitive here is the only correct one in the estate. Three outcomes
(pass / fail / error — an error never got far enough to have an opinion), per-test
captured output, `setUp`/`tearDown`, and click-to-open on the `def`.

**Capturing a test's own output cost three findings, and every one of them fails
silently.** They are the most transferable thing in this release, so they are
written up in full on `TestHarness` and asserted by `TestHarnessTest`:

1. **Import before you print.** Writing to `sys.stdout` and THEN importing a
   project library module loses the whole execution's output — not just the
   buffered write, everything after it. Hence two passes.
2. **Re-assert the private state after the imports.** An import leaves the
   THREAD's `PySystemState` pointing at the platform's, so `print` (which goes
   through `Py.getSystemState()`) writes to the gateway's console from then on
   while an explicit `sys.stdout.write` still reaches the capture. That asymmetry
   is what made it findable: a captured write beside a missing print means the
   two are resolving different objects.
3. **Flush from inside.** Jython buffers `sys.stdout`, and the runner's own
   tail-flush does not reach that buffer on a batch run. The script console never
   showed any of it, because a socket run has a periodic pump.

None of the three was reachable by reasoning about the code; each came from a
probe against the running gateway that reported its answer back through an
exception message, because the thing under test was the output path itself.

- **Discovery is narrow deliberately.** `def test_*` anywhere would put
  `plc.diagnostics.test_connection` under a Run All button. A test lives in a
  module whose last name starts with `test`, or under a `tests` package — and the
  panel states the rule, so it reads as a rule rather than as a bug.
- **The ids in a run request are a SELECTION**, looked up in the server's own
  discovery. An unknown id is a 400, not a call to any function by name.
- **The harness never catches bare.** A Stop and the timeout arrive as a Java
  `Error`; a bare `except:` would swallow one and carry calmly on to the next
  test. `TestHarnessTest` asserts the absence.

**F3 is closed, and made repeatable.** `scripts/testing/capture_readme_shots.py`
re-takes the README's screenshots against whatever is deployed. It asserts
nothing on purpose — a screenshot's correctness is a human judgement, and a suite
comparing PNGs would fail on a font hint.

### Superseded header — 1.16.1 (06/09/2026)

### 1.16.x — the reach of what was already built (06/09/2026)

Nigel: *"do all 5 they are good"*, then *"also fix up everything from the past
review. that should have all been done already."* Almost everything here is a
feature that existed and did not reach far enough.

**Search covered a quarter of what the IDE edits.** `ProjectIndex` filtered to
`script-python` — the same filter the NAME index uses — while the module had
grown to edit gateway event scripts, Web Dev handlers and pages, and named-query
SQL. So search, references and (from 1.15.0) replace all stopped at the library,
and looking for a string in your own timer script returned nothing, which reads
as "it isn't there". Two corpora now: the NAME index stays library-only, because
definition and quick-open symbols are about IMPORTABLE modules and a timer
script is not one. The TEXT scan covers everything openable.

**A save that does not parse asks once** (only an ERROR; a warning never stops
a save). **A save that removes or re-declares a top-level function names its
call sites first** — R1, and a line scan rather than the AST, because the
question compares two versions of a buffer and the server only knows one.

**R4 — Tag Change, and the lesson about measuring.** Body-only since 1.1.0
waiting for someone to drive the Designer. It needed BOTH a real `resource.json`
AND the Designer, and they disagree: the resource stores `ValueChange`, the
Designer's checkbox says `Value`. Reading the JSON alone would have shipped a
vocabulary this IDE invented for a control that already has names people know.
See "Tag Change, measured off the real Designer" below.

**R2 is half-delivered, deliberately.** The review asked for last fire, duration
and NEXT fire per event script. **The 8.3.0 SDK exposes none of them** — there
is no timer-task registry on `GatewayContext` to ask. A gateway log line appears
only on FAILURE, so deriving "last run" from one would make a healthy script
indistinguishable from one that has never run. What ships is which event scripts
are failing, how often, and when.

**R5 (two gateways) and R6 (a test runner) are untouched**, and are not small:
R5 is a cross-gateway authentication surface, R6 a product in its own right.
F1 (internal or public) and F2 (prove it on a second gateway) are decisions and
environment rather than code.

### Superseded header — 1.15.3 (05/09/2026)

**Version 1.15.3 · deployed on `ignition-module-testing` (8.3.8) 05/09/2026 —
`deploy_gate.py` PASS (6 checks). `v13` 27/27, `v15_tree` 18/18, `v16_nav`
25/25, `v17_nq` 45/45, `v18_pull` 20/20, `v19_ruler` 16/16, `v20_webdev` 32/32, `v21_split` 21/21,
`v22_editing` 20/20, `v23_insight` 27/27 (the 1.15.0 features), theme sweep
10/10 with no illegible element (worst 4.56). Java 437 tests, Vitest 588.**

### 1.15.x — five things the IDE knew and never said (05/09/2026)

Nigel, 05/09/2026, having read `docs/PRODUCT-REVIEW.md`: *"Please do all 5."*
They are one release because they are one idea. The deprecation flag was already
in the hint index and only ever reached a hover card; the gateway's log already
knew which scripts were failing and nothing asked it; search could find a string
across the project and could not change it; and every save went into a running
gateway with no way back to the version before it.

**1. Local history** (`SaveHistory`, `/api/history`, `HistoryDialog`). Every
save is kept per user, and **the version that was there BEFORE the first save is
recorded too** — otherwise the state you started from is the one state the
history cannot return you to, and the first save is usually the one that broke
it. Bounded by construction: 25 versions and 2 MB per document, pruned
oldest-first on every write, 512 KB ceiling on one version. **Restore loads the
BUFFER, it does not write** — the ordinary Save then applies, with its If-Match,
its inheritance rule and its byte fidelity. Both path segments are HASHES, never
names: a username and a resource path are attacker-influenced strings that would
otherwise become directories, and `../` in either escapes the data dir.

**2. Deprecated calls are a diagnostic now.** `CompletionDescriptor.getDeprecation()`
had been read into `HintIndex` since 1.0 and used for exactly two things:
sorting a completion down, and printing "Deprecated." on hover. So the IDE knew
a script called a deprecated API and would only say so if you happened to hover
the call.

**3. Scope-aware checks.** `system.gui`/`system.nav` do not exist on a Gateway.
Three narrowings, each removing a class of FALSE POSITIVE rather than a class of
bug — and each is a place a wider rule would have been the 1.13.0 mistake again:

- **Only where the scope is CERTAIN** — gateway event scripts and Web Dev
  handlers. A Project Library module is never checked, whatever its hint scope
  says, because a Vision client may legitimately import it. That gives up the
  case people most want (a library function called only from a timer) and
  answering it needs a call graph across scopes.
- **Only the PACKAGE, never the function.** `system.gui` absent from the whole
  index is a fact; `system.tag.readBlokcing` absent from a package that IS
  present looks like a typo and usually is — but `HintIndex` is built under a
  time budget with `safe()` wrappers, so a missing leaf can also mean the walk
  gave up. One is a claim, the other is a guess.
- **Only under a root the index knows.** If `system` itself does not resolve the
  index is empty or broken, and every path in the project would be reported.

**4. Replace across the project.** Literal, never a pattern — the server's
search is a literal substring match, and a regex box would find things the
results list cannot. Each file goes through the ORDINARY save route with the
If-Match from its own read, so inheritance, CSRF and byte fidelity all still
apply: it is the same write, done several times. Inherited scripts and tabs with
unsaved changes are SKIPPED and named in the report — a write over a dirty
buffer would be silently undone by that tab's next Ctrl+S.

**5. Runtime errors in the Problems panel.** Everything the panel showed before
was static analysis of code that has not run. **How a log line is tied to a
project was measured, not guessed**, off this gateway's own log:

    logger:  com.inductiveautomation.ignition.common.script.ExtensionFunctionTimerScriptTask
    message: Parse Error in timer script: 'Site_Redgum_Sewer/MyTimerScript @1,000ms '

The project and the script name are in the MESSAGE TEXT — not the logger name,
not a property. So attribution is by project name in the message or the logger,
and there is deliberately no allowlist of logger names: the timer task is one of
many and a list of the ones we have seen would silently hide every other kind of
script failure. The panel states that rule in the server's own words, because
"what the gateway logged about this project" is a weaker claim than "errors this
project caused" and the UI must not imply the stronger one.

**Two defects found by the live gate, both the same shape as each other.**

- **All three new routes 404'd on the rig.** They used a bare `/api/...`; the
  SPA is served from `/data/scriptide/` on a gateway and `/` in dev, so every
  call goes through `apiUrl`. A hardcoded path passes every unit test, because a
  mocked fetch accepts any string. Caught by `validate_v13`'s console-error
  check with 588 unit tests green either side of it. Four tests now assert the
  RESOLVED URL rather than the call.
- **Two new classes collided with selectors the live suites count.** The runtime
  rows reused `.problems-row` — which is how `validate_v19_ruler` asserts how
  many static problems there are — and the replace box reused
  `.search-panel-input`, which made `validate_v16_nav`'s fill ambiguous the
  moment a search returned hits. **A shared class name is a shared claim.** Both
  have their own class now.

`validate_v23_insight.py` gates all five. The scope check is asserted as a
DIFFERENCE — the same `system.gui` line in a message handler and in a library
module, one marked and one not — because a check that only looked for a mark
would pass on a build that marked everything.

### 1.14.x — the last two known gaps, closed (05/09/2026)

**Diagnostics existed only for Python.** The editor registered a document with
the language server only when it was a `.py` file, so a Web Dev `cell3d.html`,
a `site.css`, a WebDev JavaScript file and a named query's SQL had **no error
signalling at all** — no squiggle, no gutter mark, no line-number mark, no
ruler, no Problems row — and nothing said so. `syntaxLint.ts` uses each
language's OWN parser, which CodeMirror already loads for highlighting, and
publishes into the same store the server publishes to (`LspClient.publishLocal`)
so the ruler and the Problems panel see them. Measured per language before
being trusted: CSS, JavaScript, JSON and SQL report real error nodes (SQL with
`:v` parameters is clean, which is what makes it checkable at all); **HTML's
parser reports NOTHING**, by design, so it gets a narrow structural check with
an allowlist — `<div><p>hi</div>` is valid HTML and must stay silent.

**Two goes at the HTML check were wrong, and a real file caught both.**
`cell3d.html` is 1,559 lines that render in every browser; the first version
marked `<html>`, `<head>` and `<style>` as "never closed". CodeMirror parses
LAZILY, so the close tags were simply outside the tree. `syntaxTreeAvailable`
looks like the API for this and is not — it returned TRUE for a tree covering
3,041 characters of 72,626 — and `tree.length` equals the document length in
the live editor while most of it is still placeholder. The rule now confirms
the close tag in the **text**, which no parse state can lie about.
`syntaxLint.corpus.test.ts` pins it, opt-in behind `SI_HTML_CORPUS`.

**The v13 terminal mystery is root-caused, and the checks are back.** Three
input checks were removed on 02/09/2026 with "NOT ROOT-CAUSED … if the terminal
ever drops input for a user, start here". Hooking `WebSocket.prototype.send`
and replaying the suite's exact sequence showed **every keystroke on the wire**
— 14 `term`/`input` frames with a real terminal id, and the echo came back.
Everything in the 02/09 investigation looked at the DOM; nothing looked at the
socket, which is the only place that separates "the browser never sent it" from
"the server never answered". `v13` is 27/27 with the checks restored, and
`stty size` now proves the pty carries the fitted size rather than 80x24.

**Nigel's four decisions, 05/09/2026:**

- **`terminal.docker` stays on by default** — the larger grant, deliberately.
- **Gateway write access replaces the role NAME**, as a UNION not a
  replacement: `SessionSecurity.canWriteGateway` grants on the platform's own
  `WebUiSession.SESSION_WRITE` **or** the `Administrator` role. Measured on
  8.3.8, `SESSION_WRITE` alone DENIED the gateway's own `admin` — the gate went
  straight to `canExecute=false` — so using it alone would have shipped a module
  nobody could save from. Whatever that constant gates, it is not "may this
  caller write configuration".
- **`_wd_scratch_` is Inheritable now**, so `v15_tree`'s read-only checks
  actually RUN instead of skipping. That made the DRAFT and READONLY fixtures
  incompatible — the child now inherits an Update, whose row is
  present-but-read-only and serves neither — so the suite discovers two.
- **The login chatter is suppressed** via Debian's own `$HOME/.hushlogin`,
  which is the same condition guarding the block that printed it. The gid with
  no name is the HOST docker group this container is given.

Two suite bugs found on the way, both the same shape as ones found the day
before: `validate_v22` counted lint marks with an UNSCOPED selector, so it saw
the marks of hidden tabs (`CodeEditor` keeps one view per open document,
mounted, to preserve scroll and undo) — it reported a fault in `cell3d.html`
that belonged to a Python probe behind it. And one check formatted its message
from a second query, which disagreed with its own assertion.

### 1.13.0 — six things Nigel found in one sitting (04/09/2026)

All six were reported while using the module, and every one is a case where it
looked like it was working. `validate_v22_editing.py` gates five of them; the
sixth is in `v20_webdev`.

- **"I can put absolute garbage in here and it doesn't show up as an error"** —
  `j;sdfj;asdfjk;dksfj`. The parser was right: that is four semicolon-separated
  expression statements and is valid Python 2. There simply was no check for a
  name that is never defined, because the server published exactly one
  diagnostic and it was the syntax error. `UnknownNames` reports a name that is
  bound NOWHERE in the module, is not a builtin, and is not one of the ~20
  names the platform injects. Deliberately loose — every scope rule is given up
  — because a mark on working code teaches a reader to ignore the marks.
  **`UnknownNamesRealScriptsTest` is the load-bearing test**: run over the 38
  real scripts on this rig, the first version produced 21 complaints and every
  one was a project script-library ROOT (`MachineDemo`, `MiningDemo`, `Access`).
  It would have marked a line in nearly every script in the estate. The server
  now supplies the roots from `ProjectIndex`.
- **"the error mark showed up high instead of in line with the actual line"** —
  the overview ruler maps the WHOLE document, so a fault on line 22 of 190 sits
  a tenth of the way down it. Correct, and unreadable as anything but a mark in
  the wrong place. `lintLineGutter` colours the LINE NUMBER instead — the thing
  a reader is already using to find a line. The ruler stays: this adds a
  signal, it does not move one.
- **"the hover over information display needs to be more solid"** — the tooltip
  used `--surface`, which on a glass pack is the pack's own `rgba(255,255,255,
  0.10)` film, so code read straight through the documentation. It uses
  `--glass-panel` now — the same composited fill the palette and dialogs
  already had. The tooltip was the one floating layer that never got it.
- **"tried to save but it came up with an authentication error... I could
  potentially lose work"** — a 401 fell through to the generic save-failed
  notice, which printed the servlet container's JSON body verbatim
  (`{"message":"Unauthorized","url":...}`) in a one-line strip. Nothing said
  the work was safe. Now: `ApiError.isUnauthenticated`, a dedicated bar that
  says the buffer is untouched, a "Sign in again" and a "Retry the save"; the
  20 s watch raises it too, so it surfaces before the next Ctrl+S rather than
  at it. `toApiError` also reads the container's `message` FIELD instead of the
  envelope, and refuses to put a proxy's HTML on screen as a message.
- **"no changes were made via the designer... when i click on the compare I
  couldn't see any differences"**, and then **"when I just refreshed the page
  it stopped showing me any need to pull"** — both say the resource SIGNATURE
  had moved and the bytes had not, which a gateway restart does. The watch
  announced it anyway, because the listing carries only signatures. Every
  newly-stale document is VERIFIED once now, by reading it: identical, adopt
  the signature and say nothing; different, leave the bar up. The compare
  dialog also names the count of differing lines, marks each change with a
  fill, a solid edge AND a ±glyph, scrolls the first one into view, and says
  plainly when there are none.
- **"I want by default the WebDev to start shrunk but remember what i've
  expanded between tabs"** — that tree tracked the COLLAPSED keys while the
  other two track the EXPANDED ones, so "nothing remembered yet" meant
  "everything open", and a python endpoint opens eight rows. Flipped, key
  renamed with it. Gated in `v20_webdev`.

Two suite bugs the new check exposed, both real: `v19_ruler` deleted its broken
line by COUNTING characters and was off by one (the editor auto-closes `(`), so
a stray `t` survived every run — invisible while a syntax error was the only
diagnostic there was. And `v20_webdev` clicked the Web Dev view a second time,
which is a TOGGLE, and measured an empty column.

**Every batch is now live-gated.** `validate_v17_nq.py` closed the last gap on
04/09/2026 and found two defects on its first run against the gateway, both in
code that 261 unit tests had passed:

- **A named query changed on the gateway was never reported stale.** The 1.8.5
  watch refetched the SCRIPT listing only, while `staleUris` reads both
  listings — so the tab kept an old copy until a save 409'd. That is exactly
  the defect the watch was added to fix ("The change did not show up", Nigel
  03/09), left in place for the other half of the tree.
- **Pulling a stale query replaced its SQL and kept its old SETTINGS.**
  `readCurrent` read one half of a two-half resource, so the tab ended up
  holding one revision's buffer beside another's parameters — and the next
  save wrote the stale half back. A lost update, not a display bug. The
  conflict dialog's "take theirs" had the same hole and carries the settings
  now too.

**Running the live suites needs a venv with playwright**, which is not on the
system python and was absent on 03/09/2026:
`python3 -m venv .venv-test && .venv-test/bin/pip install playwright &&
.venv-test/bin/playwright install chromium` (1.62+; older cannot install a
browser on Ubuntu 26.04). Then
`WD_ALLOW_LOCAL_CONFIG=1 .venv-test/bin/python3 scripts/testing/<suite>.py` —
`gateway_session` refuses to guess a gateway without either that flag or
`SI_GATEWAY_CONFIG`.

**`v15_tree` passes now, 16/16 (04/09/2026).** It had been pinned to
`Site_Redgum_Sewer`, a water-suite project that is not on the module rig and
never was, so `select_option` threw and eleven checks went unreported rather
than failing. Both its fixtures are DISCOVERED now, preferring a project with a
parent, and `SI_INHERIT_PROJECT` still pins one — a name the gateway does not
offer is a FAIL, not a silent fallback. The run also caught that the suite
predated the 1.8.10 unsaved-close guard: closing the dirty draft now asks
first, and that ASK is asserted rather than dismissed.

**If this is a fresh chat: the work queue is in "What is next", below the
status table.** Batches A–F are done, deployed and live-gated.

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
   16/16. The gap left open here — Problems and the ruler both absent on WebDev
   and named-query documents, because neither is registered with the language
   server — **was closed in 1.14.x**: those documents are linted by their own
   language's parser and published into the same store, so both surfaces work
   without knowing the difference.
2. ~~WebDev static resources.~~ **DONE in 1.9.0**, `validate_v20_webdev.py`
   32/32 against the real `Machine_HMI_Demo` endpoints. See "1.9.0" below.
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

**SETTLED, 04/09/2026 — `industrial-day-cyan` and `nord-light-frost` stay as
they are. Do not re-open this.**

They author near-identical pages (`#EEF0F3` and `#ecf0f4`, hues 216 and 210) and
are the closest pair in the set — 3 RGB apart on the page. Nigel was given the
options and chose to leave them.

What separates them today, and why that was judged enough: `--bg-chrome` differs
by 23 RGB, the accents differ in lightness (32% vs 47%), and the GEOMETRY is not
close at all — 2px corners against 8px (panel 2px against 16px), a 4px marker
against 3px, 20px rows against 25px. They read as two themes; it is only the
editor ground that is twinned.

Two things were considered and are NOT happening:

- **Taking the rail's DIRECTION from the pack**, not just its distance.
  `nord-light-frost` is the only light pack whose sidebar, card and topbar are
  all `#ffffff` — 6% LIGHTER than its page — while every other light pack steps
  down; the generator forces them all down, which is the override that makes the
  two collide. It would have touched exactly two themes, the other being
  `leather-night-tan`, whose pack asks for a rail 4% DARKER than its page and
  currently gets a lighter one. **That small inaccuracy therefore stays**, by the
  same decision. Neither costs contrast.
- **Repainting a pack.** `ignition-themes` is public Apache-2.0 and is the
  estate's source of truth for Perspective, so moving `industrial-day-cyan`'s
  page changes every gateway theme and every Perspective session — the wrong
  blast radius for a resemblance that only shows in a theme picker. Nigel's call
  either way, and he has made it.

Rotating either ground off its own hue was never on the table: that is the 1.7.x
mistake that cost the estate the aurora pair.

`industrial-day-cyan`'s grey `--error`/`--success` were fixed at 1.12.0, along
with two more themes nobody had noticed. The reason recorded at 1.7.0 was wrong
— see "Status colours" above.



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
their 1.6.1 figures. One thing was left open at 1.7.0 —
`industrial-day-cyan` resolving `--error` and `--success` to greys — and it was
RESOLVED at 1.12.0. The recorded cause was wrong: that pack's red clears 4.5:1
easily. What the generator picked was never a red. See "Status colours" below.

### Status colours — three themes, not one (1.12.0)

`industrial-day-cyan`'s grey error/success was recorded at 1.7.0 as a contrast
problem and left as Nigel's call. Measured on 04/09/2026, that was the wrong
diagnosis and the wrong SIZE. What shipped:

    industrial-day-cyan     error #545454   success #4f545e   — two greys, 13 apart
    leather-night-tan       error = warning = success = #c9996e
    leather-parchment-tan   error = warning = success = #7a550b

Two themes painted all three status colours as ONE hex. Nothing caught it
because nothing had ever compared one status token against another, or asked
whether either was a colour at all.

The cause is the 1.2.0 lesson one level down. `text.status-alarm` is not the
pack's alarm colour — it is the INK that goes on an alarm chip, and in a light
industrial pack that ink is `#FFFFFF`. `pick_legible` takes the first token
PRESENT (correctly: that is what stops a brand teal being swapped for an info
blue), so a present-but-achromatic ink token beat the real signal colour every
time, and `lift_to_contrast` could not rescue it because lightness is the only
axis it moves.

Three changes in `tools/build-themes.py`, and the third is the one that matters:

- a signal role SKIPS a candidate below `SIGNAL_CHROMA_MIN` (28/255, read off
  the measured spread of all 110 candidates — the rejects score 0…26 and the
  keeps start at 31, and the bar goes in the one gap there is);
- `border.danger` moved ahead of `accent.alarm-high` in the `--error` list,
  because both industrial packs paint "alarm-high" AMBER — high PRIORITY, not
  danger — and taking it would have made `--error` and `--warning` one colour;
- `differentiate_signals` pulls apart status colours that resolved to one
  another, by WEIGHT only. `nord-light-frost` needed it: Nord's red and its
  orange, both darkened for a light page, arrived as `#8a464c` and `#7b4f42`,
  scoring 19.9 against a bar of 28. A status colour is never ROTATED — an amber
  turned 50° to clear a red is a green, and a green warning is worse than a
  near-red one.

Both new assertions were proved to REFUSE the 1.11.0 build before being
trusted, and `themes.test.ts` pins the property on the COMMITTED css so it
holds without running Python. The shipped values now: `industrial-day-cyan`
error `#a71b1b`, warning `#8c3d0d`, success `#0d632d`. Eighteen lines of the
generated stylesheet changed and nothing else moved.

**Batch E is live-gated as of 1.12.1 — `validate_v17_nq.py`, 45/45.** It
creates a fixture query and checks it lands on the defaults the contract pins;
saves SQL and settings against one signature and reads every field back;
proves the five refusals (an unknown settings key, `Date`, `dataType`, an
unknown `cacheUnit`, an unknown type) are 400s that NAME what they refused and
change nothing; drives the Testing tab and asserts the draft on screen is what
ran, beside an API run with no `sql` that returns the SAVED query's columns;
checks the typed coercions both ways; and repairs a real version-1 query in
`Whiteboard` — refused with a 409 before, run by the platform after, SQL
byte-identical across the repair. That last one leaves the gateway changed, in
one direction only and deliberately: there is no way to write a version-1
resource back, and no way to test the repair without doing it. `Whiteboard` had
29 dead queries; the suite takes one per run and skips with a reason when none
is left.

Two suite bugs it exposed about itself, both worth remembering: a legacy badge
only exists on a RENDERED row and the tree ships collapsed, and quick open ranks
the listing the CLIENT holds — searching for a name changed through the API is
testing the 20 s watch interval, not the palette.

**The review against purpose — DONE, 05/09/2026**, in
`docs/PRODUCT-REVIEW.md`. The brief is met and the module is past the Designer
in four places; six recommendations are ranked by leverage per unit of work, and
four findings are decisions rather than features.

**Nigel then asked for five FURTHER ideas and said "do all 5" — that is 1.15.x**,
at the top of this file: local history, deprecation as a diagnostic, scope-aware
checks, replace across the project, and runtime errors in the Problems panel.
The review's own R1–R6 are still open and unchanged.

**F3 remains the cheapest thing on either list and is not a feature: the
README's screenshots are from 01/09 and now show a UI eleven releases old.**

**Open decisions for Nigel**, parked, none blocking. Four were answered on
05/09/2026 and are recorded under "1.14.x" at the top of this file:
`terminal.docker` stays on; gateway write access joins the role name as a
UNION; `_wd_scratch_` is Inheritable; the login notice is suppressed. What is
still open:

- The Administrator role name is still assumed (`Administrator`). The 05/09
  decision widened the gate rather than replacing it, so the literal string is
  still in the code and a gateway that names the role anything else falls back
  to `SESSION_WRITE` alone — which, measured on 8.3.8, denies. Make it policy?
- ETag format (bare vs quoted).
- The rig's API tokens are gone (noticed 02/09; nothing here uses them).
- `_si_child_` on the rig: keep as the fixture, or delete after the suites.
- ~~The rig admin password reached a scratchpad file and one agent transcript
  line during the 02/09 fixture work (both scrubbed): rotate it.~~ **WAIVED**
  by Nigel, 05/09/2026 — *"it's purely a test gateway"*.

## What is proved on a real gateway

Nine suites plus a per-theme contrast sweep, **all green on 1.14.4**, all run
against the live gateway rather than mocks. The per-suite tally is at the top of
this file; the paragraphs below say what each one covers and why it exists.

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
- **Diagnostics are syntax, undefined names, deprecated calls and missing
  packages — and nothing more.** Unused imports and arity checks are still
  designed-but-not-shipped, on the same bar that held undefined names back until
  1.13.0: zero false positives, because one wrong squiggle on correct code costs
  more trust than ten missed problems. Every language has SOME check since
  1.14.x — Python's is the gateway's Jython parser, the other five use their own
  Lezer parser, and HTML's is structural only because its parser reports no
  errors at all. The two API checks added in 1.15.0 answer to the RUNNING
  gateway's registry rather than to a table, and the scope one runs only where
  the document is certainly gateway-scoped; see `PlatformApiChecks`.
- **A library function calling a client-only API is still not reported.** The
  scope check refuses to judge a Project Library module, because a Vision client
  may legitimately import the same module. Closing that needs a call graph
  across scopes, and guessing puts a warning on correct client code.
- **Perspective/Vision event scripts** are not editable — their code lives inside
  view JSON, not as its own resource.
- **Git STATUS ships (1.25.0); git actions do not.** The tree marks what differs
  from the last commit and the side bar names the branch — the VS Code-shaped
  status half Nigel's 01/09/2026 decision allowed for. There is still no stage,
  commit, diff, branch or remote here, and there should not be:
  `Gaskony-Ignition/module-git` exists and git is driven from the command line.
  The module has no route that WRITES to a repository.
- **Tag Change is no longer a gap.** It sat here from 1.1.0 to 1.16.0 waiting on
  a measurement; the workspace was driven on 06/09/2026 and `paths` /
  `changeTypes` / `enabled` are editable, with `changeTypes` on an allowlist. See
  "Tag Change, measured off the real Designer" below. Kept here because the entry
  outlived the gap by three releases, which is how a doc comes to describe a
  product that no longer exists.
- **Git**: own repo, private at `Gaskony-Ignition/module-script-ide`. Tagged
  `v1.0.0`–`v1.5.4` (01–02/09/2026) and `v1.7.0`–`v1.14.4` (05/09/2026,
  retroactively — the tag dates are the day they were written, the commit dates
  are real). `CHANGELOG.md` is complete to 1.14.4. **Some shipped versions have
  no tag and can never have one**: 1.6.0, 1.6.1 and 1.7.1 have no commit of
  their own — their source is inside the 1.7.0 commit — and the same is true of
  1.12.0 inside 1.13.0's. The interim rig builds (1.12.1–1.12.2,
  1.14.0–1.14.3) were never separate commits either, by intent. The folder is
  gitignored by the workspace repo, like every sibling module.
  **`v1.14.4` carries the signed `.modl` as a GitHub release asset**, verified
  md5-identical to the file the rig is running; no earlier tag has one, because
  those builds no longer exist.

## Tag Change, measured off the real Designer (06/09/2026)

Held back since 1.1.0 for want of a measurement. It needed BOTH sources, and
they disagree in a way only driving the Designer could show.

**What the resource stores** (`_wd_scratch_/ignition/tag-change/WDTagChangeProbe/
resource.json`, written by the platform):

```json
"attributes": {
  "paths": ["[default]A201"],
  "changeTypes": ["ValueChange", "QualityChange", "TimestampChange"],
  "enabled": true
}
```

**What the Designer's workspace shows** — `designer-drive` against
`ignition-test-gateway`, screenshot at `docs/images/designer-tag-change.png`:

| Designer control | Resource attribute |
| --- | --- |
| `Enabled` checkbox, top right | `enabled` |
| **Change Triggers**: `Value` · `Quality` · `Timestamp` | `changeTypes`, stored as `ValueChange` / `QualityChange` / `TimestampChange` |
| **Tag Path(s)**: a multi-line box, one path per line | `paths` |

**The labels are NOT the stored values**, and that is the whole reason to drive
the thing rather than read a JSON file and stop. Showing `ValueChange` on a
checkbox would have been a vocabulary this IDE invented for a control that
already has names people know. The stored form still goes on the wire.

The Designer also states a rule worth carrying into the tooltip: **wildcards
work at the FOLDER level only** — `[default]folder/*` runs for every tag in the
folder; `[default]folder/ramp*` does not work at all.

## The real-script corpus, and how to dump it

`UnknownNamesRealScriptsTest` and `PlatformApiRealScriptsTest` are opt-in behind
`SI_REAL_SCRIPTS`, and both said "dump it with the snippet in docs/STATE.md"
when no such snippet existed. It does now. Every `.py` under the gateway's own
project directories, flattened so the filename carries the project and the
resource path — which is what `UnknownNamesRealScriptsTest` parses the
script-library ROOTS out of:

```bash
OUT=/tmp/si-real-scripts && mkdir -p "$OUT"
docker exec ignition-module-testing sh -c \
  'cd /usr/local/bin/ignition/data/projects && find . -name "*.py" -not -path "*/.*"' \
| while read -r p; do
    flat=$(echo "${p#./}" | tr '/' '_')
    docker exec ignition-module-testing cat \
      "/usr/local/bin/ignition/data/projects/${p#./}" > "$OUT/$flat"
  done
SI_REAL_SCRIPTS=$OUT ./gradlew :gateway:test --tests '*RealScripts*'
```

66 files on this rig on 05/09/2026 — the mining and machine demos, Access
Manager, Whiteboard, `_wd_scratch_`, and every Web Dev handler. **Check the
results XML rather than the exit code**: an opt-in test that skips also passes.
`grep -o 'tests="[0-9]*" skipped="[0-9]*"' gateway/build/test-results/test/TEST-*RealScripts*.xml`
must show `skipped="0"`.

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
