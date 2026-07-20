# Cycle Methodology — How We Work Here

A new contributor (human or Claude) reading this in 5 minutes should be able to
join an in-flight cycle and ship a commit without having to reverse-engineer the
patterns from `git log`.

The infrastructure exists already: **21 skills** under `.claude/skills/`, **13
agents** under `.claude/agents/`, the `AGENT_SKILL_MAP.md` that maps between
them, **5 MCP servers** (serena / context7 / github / rrt / analyzer), and
**10 lifecycle hooks** in `.claude/settings.json`. What this document adds is
the **orchestration rules** that turn those primitives into a repeatable
delivery rhythm.

## 1. The cycle pattern

A *cycle* is the smallest unit of shippable work — one bounded outcome that
can be verified end-to-end and committed in a single coherent diff.

```
Cycle N          ←  one product-readiness move
  Phase 1          ←  optional, when the cycle has multiple stages
  Phase 2
Cycle N.M        ←  sub-cycle: refinement / follow-up to Cycle N
  Cycle N.M.1    ←  occasionally a third level when N.M splits in flight
Cycle N+1        ←  next cycle (NOT another N.M unless logically dependent)
```

**Naming conventions, empirically observed in `git log`:**

* `Cycle 1`, `Cycle 2` — major outcomes (eyes-on-glass, coverage policy).
* `Cycle 2.1` — refinement of Cycle 2 with measured baselines.
* `Cycle 4 · Phase 1` — multi-phase cycle where each phase is its own commit.
* `Cycle 5.5` — successor to Cycle 5 that solves an adjacent problem found
  during 5 (OF-005 success policy after CX-017 off-domain).
* `Cycle 6A / 6B / 6C` — peer sub-tasks within one cycle (ADRs / coverage /
  Atlas) that ship together.
* `Cycle 7.5` — visual triage during Cycle 7's wrap (playwright surfaced an
  Overview issue; fixed in the same swing).
* `Cycle 7.6` — depth pass on a single bottleneck Cycle 7 exposed.

**Exit criteria** (every cycle answers all four):

1. **What changed.** One sentence in the commit summary.
2. **Why it changed.** Either a triage finding, an ADR, or a user request.
3. **What proves it works.** A test, a gate run, a playwright snapshot, or
   a measured number (geomean, coverage %, etc.).
4. **What's still open.** Named in the commit body under "Cycle N+1 candidates"
   or a follow-up `TaskCreate`.

## 2. The fan-out playbook

The deepest lesson from Cycles 1–8: **parallel beats serial when the work
is genuinely independent.** Three patterns we use:

### A. Haiku-while-Opus

When a cycle has one strategic piece (Opus) and one mechanical piece
(Haiku), dispatch them simultaneously. Examples that worked:

* Cycle 7.6 — Opus extended `BenchReport` contract + GateBadge rendering;
  Haiku added 22 scipy-ls OKLCH tokens to `theme.css` across 7 palettes.
* Cycle 8 — Opus implemented `tests/test_irls_weights.py` + TR knobs Rust
  binding; Haiku wrote the 4 `docs/examples/*.md` pages.
* gitlab fix — Haiku added `cmake` + `gfortran` to the apt-install list
  while Opus drafted the `.gitlab/` includes refactor.

**Rule of thumb.** Use Haiku for: yaml edits, copy/paste with light
adaptation, docstring writes, color-token sweeps, mechanical refactors.
Keep Opus on: design decisions, multi-file coordination, anything that
needs a model of the codebase.

### B. Parallel Explore agents (Plan Mode Phase 1)

For cycle scoping that touches > 1 area of the codebase, fan out up to 3
Explore agents in a single message:

```
Agent 1: "Survey the existing X surface"
Agent 2: "Find every consumer of Y"
Agent 3: "Confirm the test patterns at Z"
```

We did this once for the Cycle 4 regression triage. The single-agent path
is faster when scope is known (Cycles 5, 6, 7).

### C. Subagents for cross-PR review

When the cycle is "land N independent PRs into main," use the github MCP
in parallel with file:get_files calls, then sequence the merges. Cycle's
prep used this for `#42 #48 #49 #50 #51 #52` consolidation.

**Anti-pattern.** Don't fan out when work is sequential by data
dependency — e.g. you can't run pytest before maturin develop completes.

## 3. The verification loop

Every cycle exits through this loop. Skipping a step is how regressions
ship.

```
  ┌────────────┐    ┌────────────┐    ┌────────────────┐    ┌────────────┐
  │   Code     │ → │  Tests     │ → │  Bench / Gate  │ → │  Playwright │
  │  changes   │   │  pytest    │   │  poe benchmark │   │  snapshot   │
  └────────────┘   │  cargo     │   │  gate          │   │  (web only) │
                   │  vitest    │   │                │   └────────────┘
                   └────────────┘   └────────────────┘            ↓
                                                          ┌──────────────┐
                                                          │   commit     │
                                                          │   + push     │
                                                          └──────────────┘
```

Per-layer test surfaces (from the binding audit `docs/rust_binding_audit.md`):

| Layer | Test runner | Critical-path floor |
|---|---|---|
| Rust crates (workspace) | `cargo test --workspace --tests` | 85 % global, 75 % `spectrafit-core` + `spectrafit-solver` |
| Python `spectrafit_core` | `pytest tests/test_fit.py tests/test_global_fit.py …` | 90 % `fit.py` + `evaluate.py`, 80 % `graph.py` |
| Python `benchmark` | `pytest tests/test_bench_*.py` | 85 % `engine.py` |
| Web (`vitest`) | `npx vitest run --coverage` | (no per-file floor yet) |
| End-to-end visual | `playwright_mcp` against `report.html` | manual gate (Cycle 7.5+) |

**Pre-push lint gate** (Cycle 30L): before the bench/gate step above, run
`mcp__analyzer__ruff-check-ci` + `mcp__analyzer__ty-check` via the project's
analyzer MCP (configured in `.mcp.json`, ~2 s), or `uv run poe lint_ci` as the
CLI fallback. Both mirror `.gitlab/20-lint.yml` `lint:python` byte-for-byte
(no `--fix`, `uv run --no-sync ruff check .` + `ty check python/benchmark
python/spectrafit_core`), so a green local run is sufficient evidence the
GitLab job will pass — there is no reason to discover ruff drift in a ~3 min
GWDG pipeline. The pre-push git hook (`.pre-commit-config.yaml` `ruff-check`
strict stage with `alias: ruff-check-strict`) enforces this client-side for
direct `git push` even when a commit bypassed pre-commit (`--no-verify`,
fresh worktree without `pre-commit install`).

**Gate axes** (`uv run poe benchmark_gate` / `python -m oracles.cli gate`, four-axis):

1. Speed: `geomean speedup vs baseline ≥ 1.0×` (default).
2. Accuracy: `max |Δr²| < 1e-3` on non-optfn cases.
3. Regression count: `regression_case_ids ≤ max-regressions` (default 0).
4. Self-vs-self: `current/pinned ≥ 1 − perf_tolerance` (default 0.10).

All four must be green. Cycles 4 + 5 + 5.5 + 7 + 7.6 each closed a gap
in this loop.

### Deep benchmark (reps ladder)

The everyday CI bench (`build:report_html`) runs at `--reps 1` — fast, but a
single timing repetition carries measurement noise the paper cannot cite. The
**deep benchmark** (`.gitlab/55-deep-bench.yml`) answers "how many timing reps
until the headline numbers stop moving?" by running the REAL benchmark at
reps ∈ {1, 2, 5, 10, 25, 50, 100} as a parallel GitLab matrix (`benchmark:deep`,
one cell per budget; ~12 min at reps=1 up to an estimated ~2 h at reps=100 —
the cell carries a 3 h timeout).

**How to trigger** — never on push, by design:

- *Manual*: GitLab → CI/CD → Pipelines → **Run pipeline** (web source). Every
  matrix cell is `when: manual`; play all seven (the merge verdict is
  meaningless over a partial ladder).
- *Scheduled*: CI/CD → Schedules; on a `schedule` pipeline the matrix runs
  automatically.

**What the artifacts mean** (30-day retention, under `artifacts/deep/`):

- `reps-N/{results,manifest}.json` — one full contract-valid run per budget.
- `stability.json` — `oracles.stability.StabilityStudy` (a CI artifact
  schema, deliberately NOT in the frozen `contract.py` wire format): per
  backend, the suite headline numbers (geomean speedup, median speedup,
  median per-case ms) at each reps budget plus the relative half-width
  `|v_N − v_100| / v_100` vs the N=100 reference.
- `stability.md` — the human table (rows = reps, cols = backends, cells =
  geomean with signed Δ% vs N=100) and the one-line verdict: the smallest N
  where every backend sits within 2 % of its N=100 value ("measurement
  converged at N=…"). This is the variance-vs-N evidence for the paper's
  uncertainty section.
- `canonical/{results,manifest}.json` — the promoted **N=100 run: the
  citation-grade publication numbers**. Quote these in the manuscript, not a
  `--reps 1` smoke run.

Local equivalent: `python -m oracles.cli run --reps N --mc 4` per rung into
per-rung directories, then
`python -m oracles.cli stability <dir-with-reps-subdirs> --out <dir>`.
(`python -m oracles.cli sweep` is the related quick-look tool: same machine,
sequential tiers, no stability artifact.)

## 4. Which-skill-when matrix

The 21 skills in `.claude/skills/` form a discoverable layer. Pick by
*intent*, not by name:

| Intent | Skill | When |
|---|---|---|
| Adding a new model kernel | `rust-model-scaffolder` | Before touching `crates/spectrafit-models/`. Generates the scaffold + parity test stub. |
| Triage a bench regression | `spectrafit-tdd` | Read `manifest.regression_case_ids`, route to the right specialist. |
| Investigate a solver convergence failure | `spectrafit-solver` | LM / trust-region / VarPro behavior. The Cycle 5 + 5.5 work used this implicitly. |
| Fix a PyO3 boundary error | `spectrafit-bindings` | `ImportError`, signature drift, maturin panics. |
| Audit Python↔Rust schema drift | `spectrafit-schemas` | After contract bumps (Cycle 7.6 should have called this; we ran the playbook from memory). |
| Add a benchmark scenario | `spectrafit-benchmark` or `benchmark-scenario-generator` | New `CaseSpec`/`CaseFamily` in `python/oracles/cases.py`. |
| Refresh devboard HTML reports | `spectrafit-devboard` | Devboard, not the bench `report.html` (that's `web/`). |
| Validate the workspace DAG | `dag-validator` | After cycle-prone cross-crate edits. |
| Design a UI panel with Apple sensibility | `cupertino-council` | When the brief is "feel premium," not "label clarification." |
| Elevate a boring feature | `boring-to-brilliant` | "Time Machine treatment" for a chore-feature. |
| Find the one non-obvious addition | `one-more-thing` | At cycle wrap — what would Jobs save for last? |
| Plan a long-term API surface | `evolutionary-platform-thinking` | Before committing to a new contract (Cycle 7.6 ManifestSignals could have used this). |
| Generate a new skill/agent/hook/prompt | `skill-generator` / `agent-generator` / `hook-generator` / `prompt-generator` | Meta-work; rare. |
| Find current library docs | `find-docs` / `context7-mcp` | Before recalling library APIs from training data. |

When in doubt: `Skill` tool with the name, never `Read` on the skill file.

## 5. Agents vs skills

* **Skills** are *prompts*: invoked synchronously via the `Skill` tool, run
  in the main conversation. They shape the next-few-turns behavior.
* **Agents** are *subagents*: dispatched via the `Agent` tool, run with
  their own context window. They return a single summary result.

Use a skill when the task changes how *I* think; use an agent when the
task is independent enough to delegate.

The `AGENT_SKILL_MAP.md` codifies which agent's behavior shadows which
skill — so a TaskCreate that says "use the spectrafit-solver agent" can
fall back to the `spectrafit-solver` skill if the agent isn't available.

## 6. Sprint cadence — the user-facing rhythm

Every cycle has the same beat:

1. **Brief** — the user names the cycle target (or accepts a recommendation).
2. **Plan** (optional) — `EnterPlanMode` when ≥ 2 valid approaches exist or
   the change spans > 3 files. Phase 1: explore. Phase 2: design. Phase 3:
   review with `AskUserQuestion` if a real decision remains.
3. **Direct** — code edits, parallel agent dispatch, test runs.
4. **Verify** — the four-step loop in §3.
5. **Commit** — one cycle = one commit (or two, if the diff splits cleanly
   along a code/docs or backend/web seam). Commit message follows the
   conventional-commits prefix used in `git log`: `feat() / fix() /
   chore() / docs() / ci()`.
6. **Wrap** — a short text summary, named follow-ups, and (optionally) a
   `TaskCreate` for the next cycle.

The user closes a cycle by saying "continue" or naming the next item.
Don't proactively start the next cycle without a signal.

## 7. Anti-patterns we've actively avoided

* **Cycle hoarding.** Don't bundle 5 cycles into one commit. The
  per-cycle commit is the unit of revert-ability.
* **Plan-mode for trivial fixes.** Cycle 7.5's win-denominator fix took
  20 minutes inline; plan mode would have spent more time on the plan
  than the fix.
* **Skipping the verify step.** Cycle 7's `maturin develop` instead of
  `maturin develop --release` produced a 0.57× geomean for ~10 minutes
  until the verification surface caught it.
* **Memory-as-source-of-truth.** The Cycle 8 audit's first pass claimed
  IRLS WeightFn was unbound (memory said so); the actual code path
  handled it. Audit > recall.
* **Documenting what code already says.** This file describes patterns
  that aren't visible in any single file; everything else is in
  `git log` or `DECISIONS.md`.

## See also

* `CLAUDE.md` — code conventions + MCP discovery rules.
* `DECISIONS.md` — ADR-style record of policy decisions (e.g. Cycle 4–5.5
  five-ADR landing 2026-06-08).
* `docs/rust_binding_audit.md` — what's bound vs unbound between Rust + Python.
* `docs/examples/{fitting,shared_params,multi_dataset,3d_fitting}.md` —
  runnable patterns for each contract surface.
* `.claude/AGENT_SKILL_MAP.md` — the canonical agent ↔ skill mapping.
* `scripts/audit_bindings.py` — example of the "living-doc CI guard"
  pattern that prevents this document from rotting.
