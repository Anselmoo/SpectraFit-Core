# Developer Guidelines

> **Synopsis**
> - **Reach for MCP first, and reach often.** Invoke MCP servers (serena, context7, github, rrt, analyzer) before falling back to `grep`/`find`/training-data recall. Internal memory is the *last* resort, not the default. Compose them: serena to locate → context7 to confirm an API → github to check upstream → record durable facts in the file-based memory + `DECISIONS.md` (serena is navigation-only — its `write_memory` is not auto-surfaced, so it is not the durable store).
> - **Surface config breakage immediately.** If an MCP fails to connect, a tool returns 401, or a required CLI is missing, **stop and ask the user before the second retry**. Burning a whole session diagnosing a missing token / off Docker daemon / stale endpoint is worse than a 30-second clarification. Never silently fall back to a degraded path without flagging it.
> - **Code conventions are load-bearing.** Pydantic-first, registry-over-map, `match` over `if/elif ==` chains. The hooks enforce this; respect them.
> - **Models are multi-crate.** A new model touches Rust kernel + `ModelTypeStr` + the `spectrafit-builder` exhaustiveness gate (test-only) + Python `ModelType` + bench registry + a case recipe. Follow the sequence in "Adding a New Benchmark Model" — no shortcuts.
> - **The cycle methodology is documented.** See [`docs/methodology.md`](docs/methodology.md) for the cycle pattern (naming, exit criteria), the fan-out playbook (parallel Haiku + Opus, parallel Explore agents), the four-step verification loop (tests → bench → gate → playwright), and the which-skill-when matrix. New contributors (human or Claude) should read it before starting a multi-step task.


## Code Conventions (pydantic-first)

This codebase is **Pydantic-first** — the `enforce-pydantic-native` hook is not a
suggestion. Apply it consistently so a language server (pyright/ty) can check every
consumer:

- **Model your data with Pydantic `BaseModel`, not `@dataclass`** — case specs,
  backend outcomes, report payloads, registry records. Use
  `ConfigDict(arbitrary_types_allowed=True)` when a model must carry numpy arrays
  (e.g. a materialized case); use `extra="forbid"` for contract models.
- **Declare, don't loop.** Prefer declarative, validated specs (e.g. a `CaseSpec` /
  `CaseFamily`) plus a registry over imperative builders, so adding the 101st case or
  the next model is *data*, not new code paths.
- **Use `match`/`case` over `if/elif ==` chains** for dispatch on a discriminator
  (model key, solver, format). Enforced by the `enforce-match-dispatch` hook: two or
  more `if/elif <var> == …` branches on the same variable in a `python/extras/**` or
  `tests/**` `.py` file are blocked (exit 2) at Edit/Write time. A single
  `if x == y:` is fine — only chains must become `match`/`case`.
- **Prefer a registry over per-call maps.** New shapes register once in
  `oracles.models.MODEL_REGISTRY`; backends read the registry, never a private
  `_MODEL_MAP`/`_SHAPE`.

## Tooling: use MCP servers for discovery

Default to the right MCP for the job instead of guessing or relying on `grep` alone — reach for them early, not after a guess fails:

- **serena** — code patterns, symbols, references, and call sites (`find_symbol`, `find_referencing_symbols`, `get_symbols_overview`, `replace_content`). Prefer over raw `grep` for anything symbol-level (Rust/Python definitions, where a function is used). **serena is for code *navigation*, not durable memory:** its `write_memory`/`read_memory` round-trip fine but are **not** auto-surfaced at session start, so facts written there get written-but-never-recalled. Record durable facts via the file-based **memory** below (and `DECISIONS.md` / `docs/`), not `serena.write_memory`.
- **analyzer** (project-local, `.mcp.json`) — Python static checks: `mcp__analyzer__ruff-check-ci` (CI-strict, no autofix — matches `.gitlab/20-lint.yml`), `mcp__analyzer__ruff-format`, `mcp__analyzer__ty-check`, `mcp__analyzer__vulture-scan`. **Before any `git push` that touches `python/**` or `tests/**`, run `mcp__analyzer__ruff-check-ci` + `mcp__analyzer__ty-check`**; this is the same contract the GitLab `lint:python` job runs, just executed locally in <2 s instead of paying a ~3 min GWDG round-trip. CLI fallback when the MCP is unreachable: `uv run poe lint_ci`. Never silently fall back; surface the MCP failure first. Complement with `uv run poe scenario_smoke` for a fast (<500 ms) spectrafit/lmfit cross-check before pushing model changes (see `benchmark/scenarios/regression-smoke-gaussian.yaml`).
- **context7** — fetch current library/API docs (faer, pyo3, lmfit, scipy, pydantic, numpy, maturin, …) *before* relying on recalled API details. Resolve the library id, then query.
- **github** — search code/issues/PRs across this repo and upstream deps; read PRs and releases ("has this been done/discussed", upstream behaviour). Prefer over `gh pr` / `gh api` — the CLI's OAuth in this environment is unreliable, so the MCP is the working path. If the github MCP itself is unreachable (Docker daemon, stale token, conflicting scope), **ask the user before falling back** — do not invent PR metadata from memory.
- **web** (WebSearch / WebFetch) — anything outside the repo and not covered by a library's context7 docs (algorithms, error messages, recent changes).
- **memory (file-based — the single durable store)** — the auto-loaded session memory at `~/.claude/projects/<project>/memory/`; its `MEMORY.md` index is **injected into context at every session start**, which is *why* it is reliable (it resurfaces without being asked). Write durable facts/decisions here as you go, and graduate architectural decisions to `DECISIONS.md` / `docs/`. This is the durable-memory path — **not** `serena.write_memory` (which is not auto-surfaced; see **serena** above).
- **ai-agent-guidelines** — structured planning/architecture/governance workflows (`enterprise-strategy`, `strategy-plan`, `system-design`, `policy-govern`, `physics-analysis`, `fault-resilience`, `quality-evaluate`, `code-review`, …). Use **before** dispatching a planning subagent, entering plan mode, or building a multi-step task list on strategy/architecture/physics-shaped work — the structured workflow (vision → capability → strategy → architecture → governance → executive brief) prevents lazy planning that gets paid back in review cycles. The [`suggest-ai-agent-guidelines.sh`](.claude/hooks/suggest-ai-agent-guidelines.sh) PreToolUse hook routes Agent / EnterPlanMode / TaskCreate to the matching sub-tool. **Hybrid enforcement** (this repo runs `AAG_FIRST_MODE=block` — set on the `suggest-ai-agent-guidelines.sh` hook command in `settings.json`, currently `:206`): warn-mode (exit 0) prints to the user terminal but **does not inject into the model's context** — so the previous default was a silent no-op for AI behavior. Block mode hard-stops (exit 2 → message reaches the model) only on the four highest-leverage lanes (`enterprise-strategy`, `system-design`, `policy-govern`, `physics-analysis`); other lanes stay warn-mode and `=off` silences. The hook stays silent on narrow scope (rename/typo/lint/single-file) — enforcing AAG on a clearly bounded task would be over-engineering. **Known-pending**: the AAG MCP itself has been observed returning generic advisory / "model unavailable" stubs in some sessions; if a `block`-mode hard-stop routes you to a tool that returns a stub, surface the broken target rather than silently working around it (the visible failure is the point of block mode).

These compose: e.g. serena to locate a symbol → context7 to confirm the library API → github to read the upstream PR → record the decision in the file-based memory / `DECISIONS.md`.

> Project-scope `.mcp.json` carries only `rrt` and `analyzer` (project-local tooling). `serena`, `context7`, and `github` are configured **user-scope** in `~/.claude.json` (`github` is HTTP+Bearer to `https://api.githubcopilot.com/mcp`; tokens MUST NOT be committed). Run `claude mcp list` to verify all five resolve. **If any MCP shows `✗ Failed to connect` at session start, surface it to the user in your first message instead of degrading silently** — restarting with `--resume` after a one-line fix is cheaper than completing a session on the fallback path.

## Skill catalog (consolidated)

The skill catalog is **7 consolidated skills** (down from 28), anchored to
a single declarative registry. The registry is
[`.claude/skills/INDEX.yaml`](.claude/skills/INDEX.yaml) (validated by
[`scripts/validate_index.py`](.claude/skills/scripts/validate_index.py)
against [`INDEX.schema.json`](.claude/skills/INDEX.schema.json)). Each entry
declares: stream(s), the CLAUDE.md sections it must respect, the hooks it
honors, the process skills it composes with, and whether it is `serena_first`.

| Skill | Stream | Absorbs |
|-------|--------|---------|
| `crates-stream` | crates | `spectrafit-solver`, `spectrafit-bindings`, `spectrafit-scaffold`, `rust-model-scaffolder` |
| `python-stream` | python | `spectrafit-schemas`, `spectrafit-tests`, `spectrafit-tdd`, `python-arch-proposer`, `python-pattern-advisor` |
| `web-stream` | web | `spectrafit-devboard`, `spectrafit-benchmark` (web side) |
| `verification` | crosscut | `ground-truth`, `nist-strd-runner`, `benchmark-scenario-generator`, `dag-validator` |
| `quality-council` | crosscut | `one-more-thing`, `boring-to-brilliant`, `cupertino-council`, `evolutionary-platform-thinking` |
| `meta-builder` | meta | `skill-generator`, `agent-generator`, `hook-generator`, `prompt-generator`, `instruction-generator` |
| `andon-loop` | meta | `cycle-close` (folded in); gains `mode: tri-stream` for parallel sub-loops over crates ║ python ║ web |

`andon-loop` is the conductor. In `tri-stream` mode it reads `INDEX.yaml` at
Phase 0.5, forks one sub-loop per affected stream via
`superpowers:dispatching-parallel-agents`, and enforces inter-stream wires
(pyo3, JSON contract) under the existing andon rule. When a wire reopens, the
**stuck-mode escape ladder** kicks in (curiosity sub-cycle → reframe+spike →
quality-council convene), specified in
[`andon-loop/references/stuck-mode.md`](.claude/skills/andon-loop/references/stuck-mode.md).
End-of-cycle ritual (ADR + topic-index + ledger append + push-ready commit
message) is at
[`andon-loop/references/cycle-close.md`](.claude/skills/andon-loop/references/cycle-close.md).

**Serena first** is a hard contract on every code-touching skill (every
stream skill, `verification`). The first action on a code-related task is
`mcp__serena__find_symbol` / `get_symbols_overview` /
`find_referencing_symbols`. `Grep` for symbol-shaped patterns
(`fn …`, `struct …`, `class …`, `def …`) is flagged by the
[`enforce-serena-first.sh`](.claude/hooks/enforce-serena-first.sh) PreToolUse
hook (warn by default; `SERENA_FIRST_MODE=block` for hard enforcement).

**Three-pillar reporting** on cycle close: PERF
(`manifest.geomean_speedup_vs_baseline`), RIGOR (`max_abs_delta_r2` + the
oracle exercised), PRESENTATION (web panel + Audit W1–W7). In `intent:
harden` cycles these pillars become gates; in `intent: feature` they remain
reports.

Historical specialist SKILL.md content (the absorbed skills) is preserved
in git history at the commit prior to the consolidation. Use `git log
--diff-filter=D --summary -- .claude/skills/` to find it.

## Running & previewing the dashboard (Claude Desktop / preview)

Getting the dev-server + preview loop right is what makes iteration in Claude Desktop
fast. Two named servers live in `.claude/launch.json`; `preview_start <name>` launches
them (and reuses one already running):

| Name  | Port | What                           | CLI fallback (run **detached**)                       |
|-------|------|--------------------------------|-------------------------------------------------------|
| `api` | 8000 | FastAPI — serves `/api/report` | `nohup uv run poe serve &>/dev/null & disown`         |
| `web` | 5173 | Vite — proxies `/api` → :8000  | `nohup npm --prefix web run dev &>/dev/null & disown` |

Both ports are fixed (`autoPort: false`). Start `api` before `web` (Vite proxies to it).

- **Detached or it dies.** A server started inside a Bash tool call is reaped when the
  call returns — `preview_start` handles detachment for you; a bare `uv run poe serve`
  does **not** (wrap it `nohup … & disown`). This is the #1 cause of "the server was up a
  second ago." `preview_start` cannot adopt a server you launched manually — it will only
  report the port as in-use.
- **Port-conflict recovery.** A leftover process holding :8000 makes `preview_start api`
  error "port in use". Free it, then retry:
  `kill $(lsof -tiTCP:8000 -sTCP:LISTEN) 2>/dev/null || true` (swap 5173 for the web port).
- **Inspect the live page** with the preview tools — prefer these over guessing or
  re-screenshotting: `preview_screenshot` (visual), `preview_snapshot` (DOM/a11y tree),
  `preview_eval` (run JS — navigate via `location.hash = "#audit"`, query the DOM),
  `preview_inspect` (computed CSS — use this, **not** a screenshot, for colors/sizes),
  `preview_console_logs` (JS errors), `preview_network` (the `/api/report` fetch).
  `preview_list` shows running servers; `preview_stop <name>` stops one.
- **Contract regen needs `api` up:** `preview_start api` → `cd web && npm run contract`
  (writes `web/src/openapi.gen.ts` from the live `/openapi.json`).
- **Offline path (no servers):** `uv run poe report_html` bundles the data into a
  standalone `report.html`.
- **Web verify loop** (the four-step cycle is in [`docs/methodology.md`](docs/methodology.md) §3):
  `cd web && npm run test` (vitest / happy-dom, no browser) → `uv run poe web_e2e`
  (Playwright `dashboard-render-audit` — needs **both** servers up; it auto-starts Vite but
  **not** the API, so `preview_start api` first) → commit once green.

## Running long / slow tests (background + logged, never blocking)

Long or slow test runs must be **tracked and logged**, not fired into the
foreground where they hang and stream output into context (the "background tests
block memory for no reason" failure). Conventions, enforced by hooks:

- **Use `uv run poe run_bg <task>` for anything slow** (the full suite, the
  full-history audit roundtrip, benchmarks). It detaches via
  `scripts/run_pytest_bg.sh` and writes to `.pytest_logs/` — **tail the log**,
  don't capture the run. The slow full-history test (`test_audit_results_roundtrip`)
  is marked `slow` and excluded from the default audit suite for this reason.
- **Never `2>&1`-stream a big suite into context.** Redirect to a file:
  `… > .pytest_logs/run.log 2>&1` then `tail`/`grep` the file. A scoped run is
  fine inline — select a node-id / `-k` / `-q`; don't run an unscoped
  whole-tree `pytest`.
- **Never load a 46 MB `results.json`** (`.spectrafit_reports/**`) into context —
  use the live API (`curl localhost:8000/api/report | jq '<field>'`), the
  `spectrafit-reports` MCP, or the cheap `run_audit` path.
- **Hooks:** [`guard-test-hygiene.sh`](.claude/hooks/guard-test-hygiene.sh) (Bash,
  **warn**) nudges foreground/`2>&1`/slow runs toward `run_bg` + `.pytest_logs`
  (`TEST_HYGIENE_MODE=block` to harden; `TEST_HYGIENE_OFF=1` to silence).
  [`guard-memory-hazards.sh`](.claude/hooks/guard-memory-hazards.sh) (Bash/Read,
  **block**) stops 46 MB loads, workspace-wide `cargo`, and unbounded benchmark runs.

> **Functionality before presentation (Invariant 0).** Before any web/CSS/design
> work on a metric, its functionality must be implemented at the source
> (Rust/Python), exposed as a real contract field, and verified against ground
> truth — never a proxy. The value stream is `crates/python → verification →
> contract → web → cupertino`; the andon-loop blocks the web stage when the
> upstream metric wire is red. See
> [`big-picture-driven-development`](.claude/skills/big-picture-driven-development/references/invariant-classes.md).

## Model Conventions

Before implementing any model function, check the canonical parameter names:

- The Pseudo-Voigt Lorentzian mixing weight is always named **`fraction`** — never `eta`, never `frac`
- Amplitude = peak value at center (not area under curve)
- Width = σ = standard deviation, not FWHM (FWHM = 2√(2 ln 2)·σ ≈ 2.355·σ)
- See `MODELS.md` for the authoritative formula table and all parameter names

## Adding a New Benchmark Model

A new spectrafit model is **not** "one record." The benchmark layer is registry-driven,
but spectrafit itself (the Rust subject) must learn the shape first. The Rust↔Python
`ModelType` string was duplicated across crates; it is now one canonical match arm on
`ModelTypeStr::as_str()` in `spectrafit-types`. The full sequence is:

1. **Rust kernel** — add `crates/spectrafit-models/src/<name>.rs` implementing the
   `Model` trait: `eval`, `param_names`, and a finite-difference (FD) Jacobian. Wire it
   into `crates/spectrafit-models/src/lib.rs` with `pub mod <name>;` and a
   `model_from_str` arm that returns `Box::new(<Name>)`.
2. **Type variant + canonical string** — add the `ModelTypeStr` variant in
   `crates/spectrafit-types/src/types.rs` AND its match arm in the
   `impl ModelTypeStr { pub fn as_str(&self) -> &'static str }` directly below
   the enum. The serde rename and `as_str` return value must agree — the
   `model_type_as_str_matches_serde_wire_for_every_variant` test pins this.
   Callers in `spectrafit-graph::compiler` and `spectrafit-varpro` read this
   method; there are no longer duplicate per-crate `model_type_to_str` tables
   to update. **A new `ModelTypeStr` variant also trips the `spectrafit-builder`
   exhaustiveness gate** — a deliberate compile-time guard that lives in
   `#[cfg(test)]`, so `cargo build` passes but `cargo test` (and CI's
   `cargo test --workspace`) fails `E0004` until it is wired. Two files:
   in `crates/spectrafit-builder/src/lib.rs` add the fluent `add_<name>()`
   method, the `ALL_MODELS` entry, and the new arm in both the exhaustive
   `match` and the `representatives` list; in
   `crates/spectrafit-builder/tests/builder_roundtrip.rs` add the variant to the
   `available_models_matches_modeltypestr_parity_list` `expected` list plus a
   `roundtrip_<name>` test. (Easy to miss because the gate is test-only — scope
   a `cargo test -p spectrafit-builder` when adding any variant.)
3. **Python `ModelType`** — add the member in `python/spectrafit_core/models.py`
   (value identical to the serde rename from step 2). The
   `enforce-modeltype-parity` hook warns if the Python and Rust sides drift.
4. **Bench model** — add the numpy formula + `register_model(PeakModel(key=...,
   spectrafit_type=..., param_names=..., evaluate=..., jax_supported=...))` in
   `python/oracles/models.py`. The numpy `evaluate` must be **numerically
   identical** to the Rust kernel — it is the parity oracle, so any formula difference
   shows up as a |Δr²| gate failure, not a crash. lmfit introspects the named params of
   `evaluate`; `spectrafit_type` is the `ModelType` member name; `jax_supported=False`
   simply omits jax for that model's cases.
5. **Case recipe** — reference the model `key` from a `CaseSpec`/`CaseFamily` in
   `python/oracles/cases.py`, under the right category (`scaling` — large-N
   scaling, `edge` — edge / ill-conditioned, `lineshapes` — asymmetric / true-Voigt
   shapes; plus `easy`/`complex`/`reality`/`optfn`).
6. **Regenerate the contract** if `contract.py` changed (see below).

The catalog already carries the kernels that exercised this whole path:
`true_voigt` (Faddeeva), `skewed_gaussian`, `exp_gaussian` (EMG), `doniach_sunjic`,
and the 2-D `gaussian2d`. Use one of them as a worked example when adding the next.

The spectrafit / lmfit / jax bench adapters read `MODEL_REGISTRY` — there is no
per-backend model map to touch (that part really is "one record"). The cost is the
Rust + cross-crate string plumbing above, which the registry cannot abstract away.

### Regenerate the contract (OpenAPI flow)
The TypeScript types are generated from the **live** OpenAPI schema the FastAPI app
publishes for the Pydantic contract — there is no hand-kept JSON Schema. After any
change to `python/oracles/bench_contract.py` (the module that defines the frozen
`BenchReport` contract; `python/oracles/contract.py` is the small cross-cutting
shared-leaf module — it holds only `SolverMeta`, re-exported into `BenchReport`)
regenerate **all three** checked-in mirrors of the schema — the web TS
(`web/src/openapi.gen.ts`), the web snapshot (`web/openapi.snapshot.json`,
pinned by the openapi-sync vitest), and the Python golden
(`tests/audit/golden/openapi_normalised.json`, pinned by the audit watchdog).
The one-shot `poe contract_regen` below does all three; the manual TS step is:

1. Serve the API: `uv run poe serve` (publishes `/openapi.json` for the models).
2. `cd web && npm run contract` → runs `openapi-typescript http://localhost:8000/openapi.json`,
   writing `web/src/openapi.gen.ts`. `web/src/contract.ts` re-exports the named view
   types (`BenchReport`, `Featured`, `SuiteCase`, `BackendProfile`, `SolverMeta`,
   `SpreadPt`, `Point2D`, `MultiDim`, `Projection`, `GlobalFit`, `GlobalFitSlice`,
   `PeakTrace`) from it, so the views never change. `Featured` also carries
   `global_fit` (a `GlobalFitGraph` shared-model multi-spectrum joint fit) and `guess_params` (initial-guess values).

The `contract-sync-reminder` hook prints a (non-blocking) nudge when `contract.py` is
edited so this step is not forgotten.

> One-shot: `uv run poe contract_regen` regenerates **all three** mirrors
> (Python golden + `openapi.gen.ts` + `openapi.snapshot.json`) from one live
> API instance — use it instead of the manual steps so no mirror is missed.

## Benchmark Backend Comparison Fairness

spectrafit is the **subject**; lmfit and jax (+optimistix) are independent
cross-verification **oracles**. The solve is timed in isolation (the `run` call only)
and via the compact `fit_fast` path, so model construction and per-point array
serialization never pollute the comparison. Keep stopping tolerances matched across
backends; do not tighten one without the others.

## Benchmark Engine (`oracles`) + Report

The benchmark lives in `python/oracles/` (registry-driven, pydantic-first) and
emits the frozen `BenchReport` contract (`oracles/bench_contract.py` → served by
`oracles/api.py` → `web/src/openapi.gen.ts`/`contract.ts`). The web UI is `web/` (Vite + React).

Two consumption paths, same contract:

- **Live / dev** — `uv run poe serve` (FastAPI on :8000) + `cd web && npm run dev`. The
  web app fetches `/api/report` at runtime. One data flow: benchmark run → results.json
  → FastAPI → React. This is the default for iteration.
- **Offline bundle** — `uv run poe report_html` runs the benchmark and bundles the
  same `results.json` into a 12 MB self-contained `report.html` (data inlined; opens
  offline, no server) under `.spectrafit_reports/benchmark/<run>/report.html`. Use
  for archival, sharing, or CI artifacts.

The web UI (`web/`, Vite + React) has **3 destinations** in evidence order — **Standing**
(`#standing`, default; the verdict: gate PASS/FAIL, geomean speedup, win rate, and the
render-truth credibility-rung money figure), **Audit** (`#audit`; the verification-wire
matrix W1–W7 + the failure-mode taxonomy panel — what was verified and what wasn't), and
**Evidence** (`#evidence`; the data — all backends side by side). Evidence has two
sub-views: `overview` (all cases — suite table, Δr²/speedup CI, winner stability) and
`case` (single-case drill-down); a `#case=<id>` permalink routes to Evidence and opens the
case sub-view at mount. Every panel is a declarative `PanelRecord` in
`web/src/panels/registry.tsx` (**the single source of truth**); each destination renders
`renderPanels(dest, report, ctx)` (`web/src/shell/renderPanels.tsx`) over a scope-filtered
registry, and `Shell.tsx` is a thin (~110 ln) nav + destination switch. SVG charts mount
through `web/src/plots/PlotMount.tsx` (ResizeObserver + `replaceChildren`, responsive
width, isolated from React reconciliation — never imperative `appendChild` into a
React-managed div). The binding has **no silent `?? PRIMARY` fallback** and enumerates
backends via `solversOf(report)` (no hardcoded backend ids — a source-scan vitest test
enforces this). The Python engine fits a genuine **N-D (3-D)** problem with the parametric
`gaussian_nd` kernel (`_multidim`, SP-2 — D inferred from the node's `center_<i>` params)
and a shared-model multi-spectrum global fit via a `GlobalFitGraph` joint fit
(`_global_fit`), but those showcases are currently **deferred** — the contract fields
exist; no panel renders them yet.

- **Run:** `uv run poe benchmark` (or `uv run python -m oracles.cli run`) → writes
  `.spectrafit_reports/<category>/<YYYY-MM-DD>_run_NNN/{results.json, manifest.json}`.
  `--reps`/`--mc` tune cost. The `spc-bench` console script was removed (Option A
  packaging, 2026-06-20); run the bench via `uv run poe benchmark` or
  `uv run python -m oracles.cli`.
- **Serve:** `uv run poe serve` (uvicorn on :8000) exposes `GET /api/report` (latest),
  `GET /api/runs`, `GET /api/report/{run_id}`. The web app (`cd web && npm run dev`)
  proxies `/api` → :8000.
- **Gate:** `uv run poe benchmark_gate` (or `uv run python -m oracles.cli gate`) fails
  if geomean speedup vs the baseline solver (`manifest.baseline_solver_id`, default
  `lmfit`) < 1× or max |Δr²| (LM-family cases; `optfn`/global excluded) > 1e-3.

### After a benchmark run

1. Read the run's `manifest.json` (`oracles.reports.latest_results` finds the
   latest). The keys that matter:
   - `baseline_solver_id` — which solver speedup is "× 1.0" (default `lmfit`).
   - `geomean_speedup_vs_baseline` (canonical) + `geomean_speedup_vs_lmfit`
     (one-cycle legacy alias). Always read the canonical key first.
   - `max_abs_delta_r2`, `spectrafit_win_rate`, `regressions`.
   - `regression_case_ids` — the failing case ids; the `python -m oracles.cli run`
     summary line already echoes these so the per-case `_LOG.warning` noise stops
     being the only signal.
2. Run the gate (above). Report to the user:
   - **Regressions:** cases listed in `regression_case_ids` (any supported
     backend failed; `suite[].regression=True`).
   - **Accuracy parity:** max |Δr²| vs the baseline solver on the LM-family cases.
   - **Speed:** geomean speedup; flag any case where spectrafit trails the baseline.
3. If the gate fails, identify the offending cases from `results.json` `suite[]` and
   suggest the fix path (model kernel / solver / adapter).

### Adding a model / case
Adding a new MODEL is a multi-crate change — see "Adding a New Benchmark Model" above
for the canonical sequence (6 steps after the `ModelTypeStr::as_str()` collapse).
Adding only a *case* for an existing model is the cheap path: a single
`CaseSpec`/`CaseFamily` entry in `oracles/cases.py`. Regenerate the contract after a
`oracles/bench_contract.py` change (or an `oracles/contract.py` shared-leaf change): with
the API up (`uv run poe serve`), run
`cd web && npm run contract` (OpenAPI → `web/src/openapi.gen.ts`).

### Contract artifacts you will encounter

Newer additions a contributor will hit while running the bench. Each is a
single-record / single-table addition; the deeper story for any of them is in
`DECISIONS.md` (chronological ADRs).

- **`BenchReport.baseline_solver_id`** (`contract.py`) — names which solver
  defines speedup = 1.0. Default `"lmfit"`. Threaded through `build_report`,
  `run_suite`, `run_featured`, and the CLI gate. Web side reads
  `BENCH.baselineSolverId`; never assume slot-1.
- **`SCHEMA_VERSION` policy** — additive minor (new optional field with
  default; Pydantic fills in for old payloads — no migrator entry) vs breaking
  major (rename/removal; requires a registered upgrader). See the 2026-06-06
  ADR in `DECISIONS.md`.
- **`python/oracles/migrate.py`** — `MIGRATIONS` registry +
  `@register_migration("from", "to")` decorator + `migrate_report(payload, *,
  from_v, to_v)` dispatcher. Adding a path is one decoration; the registry is
  the exclusive source of truth (no `if/elif` chain inside the dispatcher).
- **`oracles.cli`** — Typer CLI module; invoke as `uv run python -m oracles.cli run
  / gate` (under `PYTHONPATH=python`) or via the `poe` tasks. The `spc-bench`
  console-script entry was removed (Option A packaging, 2026-06-20 — it ImportErrors
  on a clean install because `typer` lives in the `[benchmark]` extra).
  `python -m oracles.cli` still works for IDE debugging.
- **`_SHAPE_BOUNDS`** (`oracles.backends._lmfit`) — lmfit shape-param
  bound table (pearson7 `m`, moffat `beta`, students-t `nu`, fano `q`,
  asym_ir `k`) added after the CX-033 NaN cascade. Adding a model with a new
  long-tail shape param requires one entry here so lmfit's LM search can't
  drive it into the formula's overflow region.
- **Number formatting** — inline in `web/src/panels/registry.tsx` (`.toFixed()`)
  plus the collapse-proof tick formatter `tickLabels` in `web/src/series`. There is
  **no** `web/src/charts/` directory or `fmtSpeedup`/`fmtPct`/`fmtOrDash`/`fmtNum`
  module — those were dropped in the greenfield rebuild; do not reference them.
- **`web/src/__tests__/noHardcodedBackend.test.ts`** — vitest source-scan
  forbidding `prof("spectrafit")`, `profiles.spectrafit`, and any array literal
  starting `["spectrafit", "lmfit", …]` (regex
  `\[\s*["']spectrafit["']\s*,\s*["']lmfit["']`). A view file that picks up any of
  these patterns fails the check. Pair it with
  `web/src/__tests__/contractCoverage.test.ts`, which classifies every contract
  leaf as rendered or ignored.
- **`ModelTypeStr::as_str()`** (`spectrafit-types`) — canonical wire-format
  string for every model variant. Callers (`spectrafit-graph::compiler`,
  `spectrafit-varpro`) read this; no per-crate duplicate match tables.

