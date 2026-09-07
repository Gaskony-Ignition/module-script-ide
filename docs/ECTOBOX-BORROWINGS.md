# Borrowings from Ectobox's Script IDE

Nigel evaluated Ectobox's free `Script IDE` module (v1.0.10, a Designer/Swing
replacement for the Script Console) on 07/09/2026 and decided to **discard the
module** but take four groups of ideas from it into ours. This is the brief for
that work. Nigel approved all four groups.

Their module is at
`https://github.com/Ectobox/EctoboxIgnitionModules/releases/tag/modules`
(`Script-IDE-8.3.modl`). Evidence below came from `javap -p` / `javap -c` over
`designer-1.0.10.jar` and from the live gateway store on the throwaway rig
`ignition-ectobox-eval` (http://localhost:8099).

## Why we are not adopting the module

Worth knowing before anyone re-opens this: **their IDE cannot run on the
gateway.** `ScriptExecutor` calls `DesignerContext.getScriptManager().runCode`
unconditionally. The Designer/Gateway/Vision/Perspective scope selector in
their UI only filters *autocomplete* — it does not change the run target. Their
`ScriptProfiler` class is referenced by nothing in the jar; it is dead code, not
a feature. On the core capability we are ahead, which is why only the peripheral
ideas below are worth taking.

Also not portable, and not worth chasing:

- Execution in the Designer JVM, reaching Designer/Vision-client scope objects.
- `ResourceListener` on the open Designer project for instant completion refresh.
- Raw `KeyStroke` capture/rebinding — a browser cannot claim Ctrl+W or F12.

## Progress

| Group | State |
| --- | --- |
| 1. Test framework | **Done, 1.21.0** (07/09/2026) — see `docs/TEST-FRAMEWORK.md` |
| 2. Snippets, templates, organise imports | in progress |
| 3. Tag-path and DB-schema autocomplete | not started |
| 4. Console and buffer polish | not started |

**The one thing group 1 changed about the brief.** Their mocking mechanism —
swapping `globals()['system']` in the module under test — is **not safe on a
gateway**, and that was measured rather than reasoned about. `__import__` of a
project-library module hands back the manager's OWN module object: the same
`id()` from two separate runs, a module global set in one run read back by the
next, and `system` living in each module's own globals. Writing to it would
change what every other user's scripts see for as long as the block is open —
the same class of mistake as the JVM-wide `__builtins__` edit at 1.19.0. Their
runner gets away with it because it executes in the Designer's JVM, one per
person; ours is one gateway serving everybody.

So the runner executes each selected test module's SOURCE into a namespace
private to the run instead. The mock is then safe, module state stops carrying
between runs, and where the source cannot be read the mock refuses rather than
quietly writing into the shared copy.

## 1. Test framework upgrade — the highest-value item

They ship **`testing/ignitest.py`, a 572-line Jython test framework inside the
jar**. It is plain Jython, so nearly all of it is portable to our runner, which
already builds an isolated interpreter per run.

What it has that ours does not:

| | Theirs |
| --- | --- |
| Decorators | `@Test @BeforeEach @AfterEach @BeforeAll @AfterAll @Skip @Timeout @TestCase` (`@TestCase` = parameterised) |
| Assertions | 12, including `AssertThrows`, `AssertAlmostEquals`, `AssertTagValue`, `AssertDbRowCount` |
| **Mocks** | `MockTagRead` / `MockDbQuery` context managers — implemented by swapping `globals()['system']` for a proxy |
| Runner | test queue, results tree, progress bar, **re-run failed only** (`TestRunnerPanel.runFailedTests`) |

Ours today (`TestRouteHandler.java`, `TestsPanel.tsx`, `web/src/api/tests.ts`)
has narrow `def test_*` discovery, `setUp`/`tearDown`, three outcomes, per-test
output and elapsed ms — and plain `assert` with no assertion helpers and no
mocking.

The mocking is the part that changes what can actually be tested: today a test
that touches tags or a database has to touch the real ones. Note our existing
rule that the harness must not catch bare `AssertionError` (`CLAUDE.md`,
`TestHarnessTest`) — any assertion helpers must respect it.

## 2. Snippets, templates, organise imports

- **Snippets** — `SnippetStorage`, 50 items with `${placeholder}` tab-stops,
  stored gateway-side and shared. We currently set `snippetSupport: false`
  (`web/src/api/lspClient.ts:643`). CodeMirror has native snippet tab-stops, so
  this is mostly authoring content plus flipping that flag.
- **Templates** — `ScriptTemplates`, 22 insertable "new from…" templates in six
  categories.
- **Organise / suggest imports** — `ImportManager.organizeImports` /
  `suggestImports` over a `KNOWN_IMPORTS` table.

## 3. Tag-path and DB-schema autocomplete

- `TagPathCompletionHelper.browseTagChildren` — live tag browse in completions,
  cached.
- `DatabaseCompletionHelper.getColumnCompletions` — datasource → table → column,
  plus SQL keywords.

Both browse through `system.tag.browse` / `getConnections`, which our gateway
side can call directly. Two new LSP completion sources.

## 4. Console and buffer polish

- **Style lints** — `ScriptValidator` carries seven regex checks: bare `except`,
  mutable default argument, `== None`, tab/space mix, unused import, unclosed
  string. Emit as LSP diagnostics beside our real parser errors. (Ours has the
  Jython parser they lack, so this is additive, not a replacement.)
- **Execution history table** — `HistoryStorage.addEntry(String, boolean, long)`:
  source, pass/fail, duration, searchable, reloadable into the editor. We have
  `RunHistory` server-side already; theirs is the UI treatment.
- **Autosave / crash recovery** — `SessionManager.hasAutosave/loadAutosave`,
  "Recovered unsaved script from a previous session", plus open-tab restore.
- **`cprint` / `jsonPrint` + ANSI console** — a `STDOUT_SETUP_SCRIPT` injected
  into the run namespace giving `cprint()` (named colours and `#rrggbb`) and a
  `jsonPrint()` pretty-printer, rendered as ANSI. We already have an ANSI pass
  in `termClient.ts` for the terminal; the console renderer needs one.
- Minor, take or leave: export console output to a file
  (`OutputPanel.exportOutput`), optional timestamps on output lines.

## Their library store, for reference

Gateway-side at `data/config/com.ectobox.ignition.scriptide/<scope>/{scripts,
snippets,tests}` as JSON, seeded once (`GatewayLibraryStore.claimSeeding`). The
live rig holds 1 script, 50 snippets and 6 tests — that is where the snippet and
template content can be read out of, if we want to look at their wording before
writing our own.

**Licence:** their modules are offered "as-is, at no cost" with no source
published and no licence file in the repo. Read their content for ideas; write
our own. Do not copy `ignitest.py` or the snippet JSON verbatim.
