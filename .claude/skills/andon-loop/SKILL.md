---
name: andon-loop
description: >
  Auto-enforcing, self-optimizing hardening loop that walks a project's value
  stream — its ordered chain of services/packages and the wires (data contracts)
  between them — fixing one gap per stage and refusing to advance past a broken
  wire (the andon rule). A pass is one traversal; a cycle is the converged run
  of several passes; a hard fix triggers a sub-cycle that backtracks upstream to
  re-verify; in fix mode it auto-assigns subagents and MCPs to go faster.
  Language- and platform-agnostic. Always use when the user wants to: "harden my
  pipeline", "self-optimization loop", "scan for gaps and fix them in order",
  "wired test", "can service A deliver to service B", "value stream", "attack
  the bottleneck", "split fast vs slow (Playwright) checks", or any request to
  autonomously iterate over a multi-service codebase closing gaps while keeping
  each handoff proven. Also trigger on: contract test, Jidoka, Theory of
  Constraints, error budget, PDCA, harden faster.
---

# Andon Loop

A disciplined, resumable hardening loop for multi-service / multi-language
projects. It treats the codebase as a **value stream** — an ordered chain of
stages with a **wire** (a data/API contract) between each — and walks that
stream closing the single highest-leverage gap at each stage, proving the wire
is green before advancing.

The name is the enforcement mechanism. On a Toyota line, any worker can pull the
**andon cord** to stop the line the instant a defect appears; nothing moves
downstream until it is fixed. This skill is that cord for software: **a red wire
halts the loop**. See `references/methodology.md` for the full lineage (Toyota
Jidoka, Deming's PDCA, Goldratt's Theory of Constraints, Google SRE) and why
"wired test" is just contract testing under a better name.

## Core vocabulary

| Term | Meaning |
|------|---------|
| **Stream** | The ordered chain of stages and the wires between them. |
| **Stage** | One service / package / build target (e.g. the Rust crate, the Python core, the web app). |
| **Wire** | The handoff between two stages — the contract A must satisfy for B. Status: 🟢 proven · 🔴 broken/unproven · ⚪ unknown. |
| **Wired test** | The test that proves a wire green: a contract / integration test across the boundary, *not* a unit test inside a stage. |
| **Andon rule** | You may not advance past a 🔴 or ⚪ wire. Stop, fix, re-prove, then advance. |
| **Constraint** | The stage or wire currently limiting throughput. The loop attacks it first (Theory of Constraints). |
| **Lane** | **Fast / non-visible** (JSON, schema, contract — runs every pass) vs **Slow / visible** (browser, E2E, Playwright — runs on cadence or offloaded to a subagent). |
| **Pass** | One left-to-right traversal of the stream (crate→…→render). The unit the board scrubs. |
| **Cycle** | A **converged run**: consecutive passes until a pass closes zero new gaps and every wire holds green. Expect 2–3+ passes per cycle. |
| **Sub-cycle** | A backtrack excursion *within* a pass: when a fix touches a contract an upstream wire depends on, jump back to re-verify (former = N−1, former-former = N−2, bounded). |
| **Cursor** | Where the loop currently is — `{stage, pass}` — recorded in the ledger so a resumed session and the board both know the position. |
| **Mode** | Operating mode. `propose` (default): recommend the one fix, don't write. `fix`: apply + prove + advance, and honor the acceleration contract. `tri-stream`: when the gap touches ≥2 streams, fork one sub-loop per stream as parallel subagents; inter-stream wires (e.g. pyo3, JSON contract) must stay 🟢 for the cycle to converge. See `references/tri-stream.md`. |
| **Acceleration** | In `fix` mode, the loop **must** offload the slow lane and parallel branches to subagents and use the constraint-elevating MCP — a speed commitment, not an option. |
| **Ledger** | Persistent state (`.andon/ledger.json`, schema v2; v3 in tri-stream mode, with `cursors: [...]` instead of a single `cursor`) that makes the loop resumable and enforceable across sessions. |
| **Stuck-mode escape** | When a wire reopens (1st → curiosity sub-cycle via serena neighbor map, 2nd → reframe+spike, 3rd → quality-council convene). See `references/stuck-mode.md`. |
| **Skill index** | `.claude/skills/INDEX.yaml` — the anchor registry the loop reads at Phase 0.5 to pick the right consolidated stream skill and carry its anchor slice (CLAUDE.md sections + hooks) into the subagent. |

## What you produce

1. A **Value Stream Map** of the project (stages + wires + lane per wire).
2. A **ledger** (v2) recording wire status, open gaps, current constraint,
   cursor, pass/cycle counters, mode, and the acceleration contract.
3. Per step: one implemented gap, a unit test, and a **wired test** that proves
   the outgoing wire — or a hard stop if it stays red, or a sub-cycle backtrack
   if the fix disturbed an upstream contract.
4. A **cycle report** when the stream converges, plus the next constraint — and
   an **`andon-board.html`** rendered from the ledger, showing the stream lit up
   with the andon lamp migrating across passes, sub-cycle excursions drawn as
   backtracks, and acceleration badges on accelerated steps.

## How the loop runs: passes, cycles, sub-cycles, modes

The loop has three time scales and one operating switch. Keep them distinct.

- A **pass** is one traversal crate→…→render. Each pass is one turn of the PDCA
  wheel (plan the fix, do it, check the wire, act).
- A **cycle** is a *converged run*: keep doing passes until a pass closes zero
  new gaps and every wire stays green. One pass almost never hardens a real
  stream — budget for 2–3+. The board scrubs over passes; the converged pass is
  marked.
- A **sub-cycle** is a backtrack inside a pass. The andon rule already stops you
  from carrying a defect *downstream*; the sub-cycle handles the opposite hazard
  — a fix that disturbs something *upstream*. When the fix you just made touches
  a contract that an upstream wire depends on, mark those upstream wires (down to
  N−2) `unknown` and re-prove them before moving on. Bounded to former-former
  (N−2); the existing thrash guard (a wire reopening three times becomes the
  constraint) keeps it from oscillating.
- **Mode** is the switch. `propose` (default) recommends the single best fix and
  stops — nothing is written. `fix` applies the fix, proves the wire, advances,
  and is **bound by the acceleration contract**: on a platform with subagents,
  the slow/visible lane and any independent sub-streams must run in subagents,
  not inline; and the MCP that elevates the current constraint (a Playwright MCP
  for the visible lane, a GitHub MCP for PR gating) must be used rather than
  hand-rolled. Acceleration is a commitment because the loop's own bottleneck is
  serial, un-delegated work. See `references/lanes-and-mcp.md`.

---

## Phase 0 — Platform & stream detection

> **Mode check — do this first.** Attempt a trivial `echo ok` bash call.
> - **Code mode** (bash succeeds): run detection automatically.
> - **Desktop / manual mode** (no bash): give the user the commands to paste back.

### 0a. Detect languages and package boundaries

In Code mode, run the bundled scanner from the project root:

```bash
SKILL_DIR=$(find ~/.claude/skills .claude/skills -type d -name "andon-loop" 2>/dev/null | head -1)
python "$SKILL_DIR/scripts/stream_scan.py" "$(pwd)"
```

If the scanner isn't found, fall back to a manual probe (also use this in
Desktop mode — ask the user to paste the output):

```bash
# Languages + package manifests, anywhere in the tree
find . -maxdepth 3 \( -name Cargo.toml -o -name pyproject.toml -o -name setup.py \
  -o -name package.json -o -name go.mod -o -name vite.config.* -o -name '*.csproj' \) \
  -not -path '*/node_modules/*' -not -path '*/target/*' 2>/dev/null
# Count source files per language (rough size signal)
for ext in rs py ts tsx js jsx go java rb; do \
  n=$(find . -name "*.$ext" -not -path '*/node_modules/*' -not -path '*/target/*' 2>/dev/null | wc -l); \
  [ "$n" -gt 0 ] && echo "$ext: $n files"; done
```

Read `references/stream-detection.md` for the manifest→stage→wire heuristics.

### 0b. Build the Value Stream Map

From the manifests, infer the ordered stream and the wire between each pair.
**Do not guess silently** — propose the stream and have the user confirm or
correct it. A declared stream always wins over a detected one.

Worked example (the canonical case this skill was shaped around):

```
[crate: Rust] --ABI/pyo3--> [spectrafit_core: Python] --import API--> [bench: Python]
       ▲                                                                    │
       │                                                          ┌─────────┴─────────┐
   (constraint?)                                          --JSON-->          --HTTP/JSON-->
                                                          [results.json]      [web: vite/react]
```

For each wire, tag a **lane**:
- **Fast / non-visible** — anything provable from data or types: ABI calls,
  Python import contracts, JSON schema conformance, HTTP response shape.
- **Slow / visible** — anything needing a rendered surface: the React app via
  Playwright, screenshots, visual diff.

This split is the answer to "Playwright is slow": the fast lane runs every
cycle; the slow lane runs on a cadence (every *N* cycles) or in parallel. See
`references/lanes-and-mcp.md`.

### 0c. Note MCP leverage points

A bottleneck you flagged is *under*-use of MCPs. As you map the stream, mark
every wire whose proof could be automated by an MCP (a Playwright/browser MCP
for the visible lane, a GitHub MCP for PR gating, a DB MCP for data contracts).
Record these as candidate accelerators in the ledger, not as work to do yet.

---

## Phase 0.5 — Read the skill index

Before initialising the ledger, read `.claude/skills/INDEX.yaml`. This is the
single declarative source of truth for the consolidated skill catalog. For each
detected stream:

1. **Find the consolidated skill** owning that stream — the entry whose
   `stream:` list contains the stream id.
2. **Snapshot the anchor slice** — `anchors.claude_md_sections` (CLAUDE.md
   headers the stream must respect) and `anchors.hooks` (hook files whose
   contract the stream owes).
3. **Record `composes_with`** — the process skills (TDD,
   verification-before-completion, …) the sub-loop will invoke alongside the
   domain skill.
4. **Honor `serena_first`** — if true, the sub-loop's first executable step
   on any code-touching action must be a `mcp__serena__find_symbol`-class call
   before any `Grep`. The `enforce-serena-first.sh` PreToolUse hook is the
   safety net; the contract is in the skill.

If `INDEX.yaml` is missing or fails `validate_index.py`, stop and surface the
error — the catalog is the load-bearing layer; running without it degrades
the entire loop. See `.claude/skills/scripts/validate_index.py` and
`.claude/skills/INDEX.schema.json`.

In **tri-stream** mode this phase is mandatory; in `propose`/`fix` modes it
is recommended but not strictly required (the loop can run sequential on a
single stream without the index, just less anchored).

---

## Phase 1 — Initialize or resume the ledger

The ledger is what makes this **auto-enforcing**: it survives across sessions so
the andon rule can be checked at any time, not just when a human is watching.

```bash
mkdir -p .andon
```

If `.andon/ledger.json` exists, resume from it: report current cycle and pass,
the cursor position, which wires are green, and the active constraint. If not,
create it from the stream map. Read `references/ledger-and-lanes.md` for the full
schema. Minimum shape (v2):

```json
{
  "version": 2,
  "cycle": 1,
  "pass": 1,
  "cursor": {"stage": "crate", "pass": 1},
  "mode": "propose",
  "intent": "harden",
  "acceleration": {"subagents": "required", "mcp": "required"},
  "stages": ["crate", "core", "bench", "json", "web"],
  "wires": [
    {"from": "crate", "to": "core", "lane": "fast", "status": "unknown"},
    {"from": "core",  "to": "bench","lane": "fast", "status": "unknown"},
    {"from": "bench", "to": "json", "lane": "fast", "status": "unknown"},
    {"from": "bench", "to": "web",  "lane": "slow", "status": "unknown"}
  ],
  "constraint": null,
  "gaps": [],
  "mcp_candidates": [],
  "history": []
}
```

`mode` is the operating switch (`propose` | `fix`); `intent` is what the current
cycle is *for* (`harden` | `feature` | `split`). They are independent: you can
propose a feature cycle, or fix-mode a harden cycle.

---

## Phase 2 — Scan the current stage for gaps

Start at the **first stage with a non-green outgoing wire** (or, if all are
green, at the current constraint stage). Scan only that stage and its outgoing
wire. Collect gaps and classify each:

| Field | Values |
|-------|--------|
| **kind** | `bug` (existing behavior broken) · `feature` (behavior absent) · `wire` (handoff broken/unproven) |
| **on_constraint** | `true` if this gap sits on or feeds the current bottleneck |
| **lane** | inherited from the wire it affects |

Gap sources to check: failing or missing tests, broken/red wires, type errors,
`TODO`/`FIXME`/`unimplemented!`/`raise NotImplementedError`, schema drift between
producer and consumer, dead or stubbed handoffs, lint/security findings.

**Do not fix anything yet.** Output the gap list for this stage only.

---

## Phase 3 — Decide and implement exactly one item

Pick **one** gap using this priority order (Theory of Constraints + SRE):

1. Anything `on_constraint: true` — the bottleneck is worth more than anything else.
2. `wire` gaps before `bug` gaps before `feature` gaps — a broken handoff blocks
   everything downstream; a missing feature blocks nothing.
3. Within a tie, smallest blast radius first.

**Error-budget override (SRE):** if the stage's wires are already green and its
bugs are within tolerance, it is legitimate to spend the step on a `feature`
instead. State the call explicitly: "Wires green, error budget intact →
implementing feature X rather than polishing."

Reason about *what* to fix from the **domain expertise of the current stage**,
not generic project-management heuristics — Rust ownership/safety at the crate,
the import or Pydantic contract at a Python boundary, schema and render concerns
at the web edge. (Apple's principle: align expertise with decision rights — let
whoever knows the domain deepest drive the call.)

Implement that one item minimally. One item per step keeps the loop tight and
the diff reviewable — resist bundling. Radical focus is a feature, not a
limitation: a loop that fixes one proven thing per step beats one that touches
ten and proves none.

---

## Phase 4 — Prove the wire (the enforcement gate)

This is the andon cord. Two checks, in order:

1. **Unit test** the change *inside* the stage. Red → fix before continuing.
2. **Wired test** across the outgoing boundary — prove the stage can actually
   deliver to the next one. Run the **fast lane** first.
   - Rust→Python: call the built extension and assert the returned object.
   - Python→Python: import the producer, feed a real payload, assert the
     consumer accepts it.
   - →JSON: validate output against the consumer's JSON schema.
   - →Web (fast): assert the API/JSON the front-end fetches has the right shape.
   - →Web (slow): a Playwright check that the rendered surface shows it —
     **only on cadence or in parallel**, never blocking the fast loop.

**The green bar is zero-artifacts.** A wire is 🟢 only when its contract holds
on the edge cases too — empty input, NaN, the off-by-one, the malformed payload
— not just the happy path. A wire that is "green except for a rare case" is 🔴.
Sidestepping corner cases to claim progress is precisely the defect the andon
cord exists to catch.

**Andon rule:** if the wire is 🔴, set its ledger status to `red`, **do not
advance**, and return to Phase 3 on the *same* stage. If 🟢, set status `green`
and advance. Never paper over a red wire to make progress — a defect that flows
downstream costs more than the stop. Crucially, separate *how right* the fix is
from *how hard* it is: the difficulty of greening a wire is never a reason to
skip it.

**Sub-cycle backtrack (re-verify upstream).** Greening the wire is not the end
if the fix reached backward. Ask: *did this change touch a contract an upstream
wire depends on?* — a shared type, an ABI signature, a JSON field, a schema both
sides read. If yes, mark the affected upstream wires `unknown` (down to N−2, no
further), record a `subcycle` step in the ledger, and re-prove them before
advancing. If the same wire reopens three times, it stops being a sub-cycle and
becomes the constraint — escalate it, don't keep bouncing.

**Mode & acceleration.** In `propose` mode the loop stops here with a
recommendation and writes nothing. In `fix` mode it applies the change, proves
the wire, and is bound by the acceleration contract: the slow/visible lane and
any independent sub-streams run in **subagents** (never inline), and the MCP that
elevates the current constraint is **used, not hand-rolled**. Either way, before
any irreversible action (commit, push, delete, schema migration) pause and
confirm — `fix` mode automates the *fixing*, not the *destroying*. The loop
proposes; the human disposes.

---

## Phase 5 — Advance, and close passes into a cycle

Move to the next stage and repeat Phases 2–4, recording each forward move and
each sub-cycle as a **step** in the ledger's `history` (with `kind: pass |
subcycle`, the `constraint`, a `wires` snapshot, the `cursor`, and any
acceleration `via` used). When you reach the last wire, the **pass** is done —
not necessarily the cycle.

**Convergence test.** A cycle is complete only when a pass closes **zero new
gaps** and every wire is green. If the pass that just finished still opened or
reopened gaps, increment `pass`, **wrap the cursor from the last stage back to
the first** (render → crate), and run another pass — this wrap is a *new pass
within the same cycle*, never cycle 2. `cycle` increments only when a converged
run ends and a fresh run begins (typically a new `intent`). Budget for 2–3+
passes; one is almost never enough.

When a pass converges, mark it `converged: true`, then render the board — the
**wheel** layout shows the wrap as a "↺ next pass" arc and keeps the cycle/pass
count in the hub (it is the PDCA wheel made literal); **linear** is the default:

```bash
python scripts/andon_board.py .andon/ledger.json                 # → linear board
python scripts/andon_board.py .andon/ledger.json --layout wheel  # → ring / PDCA wheel
```

Write a cycle report:

```
## Cycle N converged after P passes
Stream: crate → core → bench → json → web   (all wires 🟢)
Passes: P   ·   Sub-cycles: <k backtracks>   ·   Mode: <propose|fix>
Closed this cycle: <n bugs>, <n features>, <n wires re-proven>
Accelerated via: <subagents / mcp:playwright / —>
Slow lane (visible): <ran in subagent | deferred>
Closing a cycle produces a durable record: the converged commit, a decision
record (Context / Decision / Rationale / Trade-offs), the appended ledger
entry, and a push. The full close ritual is documented inline at
`references/cycle-close.md` (folded in from the prior `cycle-close` skill —
the loop owns the *iteration*, the close reference owns the *record*).
Follow that file's six-step recipe: gather commit metadata, synthesize the
ADR, write the topic-index entry under the right of 6 DECISIONS.md buckets
(Solver / Schema / Web / Benchmark / CI / Governance), append the ledger
`cycle_close` history entry, and emit the push-ready commit message.
```

---

## Phase 6 — Self-optimize between cycles

Fixing a constraint *moves* it (Theory of Constraints again). Don't assume the
next cycle attacks the same place.

1. **Recompute the constraint.** Where is throughput now limited? Slowest wire to
   prove? Flakiest test? The stage with the most reopened gaps (the sub-cycle
   thrash signal)? Update `constraint` in the ledger.
2. **Promote an MCP candidate.** If a `mcp_candidate` would remove the current
   constraint (e.g. a Playwright MCP to make the visible lane cheap), surface it.
   In `fix` mode this is not a suggestion — the acceleration contract requires
   adopting it before the next cycle, and likewise pushing the slow lane and any
   parallel sub-streams onto subagents.
3. **Decide the next cycle's intent** (independent of mode):
   - *Harden* — wires unstable or bugs over budget → another hardening cycle.
   - *Feature* — wires green, budget intact → spend the cycle adding capability.
   - *Split* — fast and slow lanes have diverged enough to run on different
     cadences, or independent sub-streams can run in parallel subagents.
4. **Standardize what recurred (kaizen).** Toyota's discipline isn't only to fix
   a defect — it's to *standardize the fix* so it is never re-derived by hand. If
   a fix or closure pattern has repeated three or more times across cycles in
   essentially the same shape (same fetch→generate-test→run→commit, same
   close-and-record ritual), that is the signal to extract it into its own skill.
   Name the pattern, then hand it to `skill-creator` rather than open-coding it a
   fourth time. This is how the loop improves the *toolchain*, not just the code —
   the most valuable thing a mature cycle produces. Do not absorb such a pattern
   into this skill; spin it out as a focused, separately-triggered skill and have
   the loop *delegate* to it (see Phase 5 close).
5. **Stop condition.** If a full cycle converges in a single pass with zero gaps
   closed, the stream is hardened — hand back to the user rather than spinning.

Read `references/lanes-and-mcp.md` for parallelization and lane-splitting
patterns, and `references/methodology.md` for the deeper rationale behind each
phase.

---

## Output format

Per working session, deliver in this order:

1. **Stream map** (once, or when it changes) — stages, wires, lane per wire.
2. **Ledger delta** — what changed since last time: cycle #, wire statuses,
   active constraint.
3. **This step** — the one gap picked, why (constraint/priority), the change, the
   unit + wired test result, and the andon verdict (advanced / halted).
4. **At cycle close** — the cycle report and the next constraint.

Keep each step terse and verifiable. The value is in the discipline of the loop,
not in long prose — one proven wire at a time.

---

## Edge cases

- **Single-language / single-service project** — the stream has one stage and no
  inter-service wire. The loop degrades gracefully to: scan → fix one → unit
  test → repeat, with the "wire" being the public API contract of that one
  package. Still useful; still enforcing.
- **No tests exist yet** — the first gap on every stage is "no wired test
  exists." Writing it *is* the step. A wire with no test is ⚪ unknown, which the
  andon rule treats as not-advanceable.
- **Cyclic dependencies between stages** — there is no clean stream order. Report
  the cycle as its own constraint (it usually is) and attack breaking it first.
- **User declares the stream** — always honor a declared stream over a detected
  one; record it verbatim in the ledger.
- **Desktop mode, user won't run commands** — work from whatever the user pastes;
  mark undetectable wires ⚪ and focus the loop on the stages you can see.
