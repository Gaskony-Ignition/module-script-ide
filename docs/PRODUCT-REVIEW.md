# Script IDE at 1.14.4 — the review against purpose

**Product review · `com.gaskony.scriptide` · v1.14.4 · 05/09/2026**

Fifteen releases against a brief written on 31/08/2026
(`~/.claude/plans/i-m-interested-in-the-golden-wozniak.md`). What it promised,
what it delivers, where the Designer still wins, and the six things worth
building next.

## Verdict

**The brief is met, and in four places the module is past the Designer rather
than level with it.** The gap it named — write Ignition scripts in the browser,
against the live gateway, with what a modern IDE gives you — is closed.

What is not settled is everything around the code. It has run on exactly one
gateway. Its audience decision has been taken by default rather than taken
deliberately. And its README shows a user interface from before the themes, the
split view, the Web Dev tree, the named queries and the error ruler — nine
releases of undersell on the first thing a reader sees.

## Against the brief

The 31/08/2026 decision table and its acceptance lines, checked against the code
that shipped.

| The brief said | Outcome | Where it lives | |
| --- | --- | --- | --- |
| Completions that know your actual installed modules | Read from the running gateway at request time, third-party modules included | `textDocument/completion` · `signatureHelp` · `hover` | **Held** |
| Errors before you save | Exceeded. Python goes to the real Jython 2.7 parser; since 1.14.x every other language the IDE opens is checked by its own parser | `DiagnosticEngine` · `UnknownNames` · `syntaxLint.ts` | **Exceeded** |
| Go-to-definition across the project | Plus workspace symbols, quick open, project text search and name-based references — none of which the Designer's editor has | `textDocument/definition` · `workspace/symbol` · `scriptide/references` | **Exceeded** |
| A Run button | Streamed output, per-user isolation measured at zero crosstalk, and a Stop that says what it can and cannot do | `PrivateStateRunner` · `ExecPolicy` | **Held** |
| Scope: Project Library, Gateway events, a scratch console | All three, plus named queries with a live test run and Web Dev endpoints and static resources as first-class documents | `NamedQueryRouteHandler` · `WebDevResources` | **Exceeded** |
| No breakpoints in v1 | Held, and still for the original reason: the only serious Ignition debugger needs a live Designer and blocks a gateway worker thread | `docs/STATE.md` · Known gaps | **Held** |
| Execution gate: session + Administrator + CSRF | Held, and widened on 05/09 to a union with the platform's own write permission after that permission alone was measured denying the gateway's own admin | `SessionSecurity.canWriteGateway` | **Held** |
| No GPL-family dependency, ever, proven by a build check | Held. The audience option is still open at zero cost — which is the point, and also F1 below | licence check in the build | **Held** |

## Where it already beats the thing it was measured against

- **Errors in every language, before the save.** The Designer checks Python, and
  checks it late. This checks Python against the real Jython parser as you type,
  and since 1.14.x gives CSS, JavaScript, JSON, SQL and HTML the same gutter
  mark, ruler entry and Problems row.
- **It can find things across the project.** Definition, symbols, references and
  project-wide text search. The Designer's script editor has no cross-file
  navigation at all — you find a caller by remembering where it was.
- **A console that streams, per user, proven.** The platform primitive the
  Designer console is built on leaks output between concurrent users — 22 to 25
  lines of it, measured in S1. This runs each execution on its own interpreter
  state, and has a regression test standing on it.
- **Nothing to install.** No Designer, no Java launcher, no client. A URL on the
  gateway you are already logged in to — which is also why it can offer a shell
  on that gateway, something the Designer has no answer to.

## Where the Designer still wins

Ranked by how much Jython actually lives there, not by how hard each is.

| Gap | Status | What is actually blocking it |
| --- | --- | --- |
| Tag event scripts | **Real gap** | A measurement, not a design. The module already refuses tag-change attribute writes because that Designer workspace has never been driven, so its tag-path list is unknown and guessing the key writes a value the Designer never reads |
| Perspective and Vision event scripts | Deferred | Their code is inside view JSON rather than its own resource. Deferred in the original scope decision, and the reason still holds |
| Breakpoint debugging | Deliberate | Nothing to fix. The available model needs a connected Designer, blocks a real worker thread while paused, and cannot attach to event scripts |
| Alarm pipelines, SFC charts, reports, transaction groups | Out of scope | Each carries script blocks and none is reachable here. Never in the brief; worth naming so the scope is a choice rather than an oversight |
| The expression and binding language | Unclaimed | Nobody has an editor for it, Inductive Automation included. A gap in the market rather than a gap in this module |

## Recommendations — going beyond the Designer

Ranked by leverage per unit of work. The first three are built almost entirely
from parts that already exist and are already tested. That is why they rank
where they do.

**R1 · Impact before save** *(small)*
When a function's signature changes, show its call sites in the save bar before
the write goes through. The Designer cannot do this at all. The project index
and the references provider are already built and already gated. It also turns
the name-based-references caveat into a virtue: for "here are the places to
check", over-matching is safe and under-matching is not, so the honest
limitation stops being one.

**R2 · Gateway event scripts you can see running** *(medium)*
The tree lists timer, message, tag-change, startup, shutdown and scheduled
scripts, and tells you nothing about any of them. The gateway knows the last
fire, the duration, the last exception and the next fire. Put that on the row.
This is the thing that costs hours in the field — a timer script that has been
throwing since Tuesday looks identical to one that has not, in the Designer and
here. No Designer surface shows it either.

**R3 · Run history that survives a restart** *(small)*
Executions are already audited and nothing reads the audit back. Per-user
history with the output kept, and one click to run it again. The Designer's
console forgets everything the moment it closes, which is why people keep
scratch scripts in project libraries they never meant to commit.

**R4 · Tag event scripts** *(medium)*
The one parity gap worth closing, because a great deal of estate Jython lives on
tags rather than in libraries. Drive the real Designer once to measure the
tag-path list, exactly as 1.4.0 did for inheritance — that table settled a
design which had been guessed wrong for four releases. The write path afterwards
is the one that already exists.

**R5 · Two gateways, side by side** *(large)*
The split view already holds two editors. Point the right-hand one at a
different gateway and diff development against production. This is the
differentiator no Designer can copy, and it is also the largest lift here —
cross-gateway authentication is a genuine security surface, not a feature flag.
Worth doing last, or when someone asks for it.

**R6 · A Jython test runner** *(speculative)*
Nothing in Ignition offers one, and the isolated execution primitive here is the
only correct one in the estate. Flagged rather than recommended: it is a product
in its own right and would compete with the module's actual job for attention.

## Findings that are not features

**F1 · The audience decision has been taken by default.** Internal and PoC after
fifteen releases, a clean security review, an execution gate and nine live
suites. Deciding costs nothing — keep it internal, or make it public the way
`project-themes` went public. Not deciding means it stays out of the release
tooling by inertia, which is not the same as by choice.

**F2 · It has only ever run on one gateway.** Every proof in `docs/STATE.md` is
`ignition-module-testing`. The terminal assumes a container and a mounted Docker
socket; that is the assumption we know about. A second gateway is the cheapest
way to find the ones we do not.

**F3 · The README sells a version from nine releases ago.** Its four screenshots
are dated 01/09 — before the themes pass, the split view, the Web Dev tree,
named queries and the error ruler. The house README standard puts screenshots
ahead of the feature list precisely because they are read first, so this is the
most expensive stale thing in the repo.

**F4 · `Administrator` is still a literal string.** The 05/09 decision widened
the gate rather than replacing it, so a gateway that names the role anything
else falls back to the platform's write permission alone — which, measured on
8.3.8, denies. Fine on this rig, and a trap on the first gateway that is not
this rig. Related to F2.

---

*As reviewed: 1.14.4, deployed on `ignition-module-testing` (8.3.8),
`deploy_gate.py` PASS. Suites: v13 27/27 · v15_tree 18/18 · v16_nav 25/25 ·
v17_nq 45/45 · v18_pull 20/20 · v19_ruler 16/16 · v20_webdev 32/32 · v21_split
21/21 · v22_editing 20/20 · themes 10/10. Unit: Java 379 · Vitest 545.*
