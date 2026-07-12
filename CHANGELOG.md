# Changelog

All notable changes to `spectrafit-core` will be documented in this file.

This project follows repository release policy enforced by `repo-release-tools`.

## [Unreleased]

### Changed
- **F13 tree consolidation (2026-06-27).** `python/benchmark/` was absorbed into
  `python/oracles/` (one engine package); `benchmark/contract.py` became
  `oracles/bench_contract.py`. The CLI is now `python -m oracles.cli` — the
  `python -m benchmark.cli` mentions in the 0.1.0b1 notes below were accurate at
  release time. Full ADR in `DECISIONS.md`.

## [0.1.0b1] - 2026-06-23

### Changed
- Promoted to **beta** (`Development Status :: 4 - Beta`). Non-public,
  GitLab/GWDG-only release cut as a tagged reproducible **source** release
  (clone + `uv run maturin develop`); no PyPI/wheel publish, no DOI.

### Fixed
- **Lean wheel (Option A packaging).** Removed the `spc-bench` `[project.scripts]`
  console script (it ImportError'd on a clean install because its deps live in
  the `[benchmark]` extra) and repointed every caller — the `poe` tasks and the
  GitLab CI jobs — to `python -m benchmark.cli` / `uv run poe benchmark`. Scoped
  maturin to `python-packages = ["spectrafit_core"]`.
- **Benchmark gate integrity.** The accuracy axis now fails on a non-finite
  `|Δr²|` (previously `NaN > threshold` silently passed and the value was coerced
  to `0.0`); the primary GitLab pipeline now enforces `python -m benchmark.cli
  gate` on push.

## [0.1.0a1] - 2026-06-13

### Added
- MIT `LICENSE` file; `CITATION.cff` (CFF 1.2.0); `CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), `SECURITY.md`.
- `LIMITATIONS.md` disclosing the benchmark's self-audit gaps (W2c κ(J),
  NIST 4-of-27 subset, χ²-floor convergence proxy, JAX-no-σ).
- `pyproject` `authors`, `[project.urls]`, and PyPI classifiers (alpha).
- Research-grade `README.md` intro with status, citation, and license sections.

### Changed
- Markdown documentation consolidated (129 → 91 tracked files); design history
  absorbed into `DECISIONS.md` and Serena project memories.
- `rrt` `repo-root-required-files` contract extended to enforce the new
  governance/legal files.

### Added — 2026-06-08 / 2026-06-09 session (Cycles 1–22)
- **`spc-bench` CLI surface gained four subcommands.** `forensics [--run ID]`
  renders matplotlib PNGs of {observed spectrum, per-backend fit, residuals}
  for every `regression_case_ids` entry of a run; `sweep --tiers 1,2,5,10`
  runs the bench at multiple `--reps` budgets and emits a budget-vs-signal
  table; `trend [--field --last N]` reads `.spectrafit_reports/index.json`
  and prints ASCII sparklines plus a table of the four gate axes across
  history; `pin-baseline` / `show-baseline` / `clear-baseline` manage
  `.spectrafit_reports/perf_baseline.json`.
- **`BenchReport.manifest: ManifestSignals | None`** (`SCHEMA_VERSION` 1.1 →
  1.2). Surfaces the four gate-axis numbers — `geomeanSpeedupVsBaseline`,
  `maxAbsDeltaR2`, `spectrafitWinRate`, `regressions` — plus optional
  `PinnedBaseline` on the typed contract so the web `GateBadge` renders real
  values instead of pointing users at the CLI. Additive minor; Pydantic
  defaults keep every 1.1 payload on disk valid.
- **IRLS robust-loss selection from Python.** `FitOptions(solver="irls:huber"
  | "irls:bisquare" | "irls:biweight" | "irls:cauchy")` reaches the underlying
  `WeightFn` variant via the colon-split parser in `dispatch.rs:108-110`. New
  `tests/test_irls_weights.py` pins each variant.
- **Trust-region power-user knobs.** Three new `Option<f64>` fields on
  `FitOptions` — `delta0`, `max_delta`, `eta` — reach `TrustRegionConfig` in
  `dispatch.rs` for the `dogleg` / `newton-cg` solvers. `None` keeps the
  library default; `Some(v)` overrides. New `tests/test_tr_knobs.py` proves
  the knobs reach the TR core (an impossible `eta=1.5` forces
  `NoImprovement`).
- **Cycle methodology codified** at `docs/methodology.md` (cycle pattern,
  fan-out playbook, verification loop, which-skill-when matrix, sprint
  cadence, anti-patterns). `CLAUDE.md` Synopsis links to it.
- **Rust binding audit** at `docs/rust_binding_audit.md` enforced by a
  `scripts/audit_bindings.py` CI guard — fails the pipeline when a new
  `#[pymodule]` registration or `Solver::` variant lands without a doc entry.
- **Runnable examples** at
  `docs/examples/{fitting,shared_params,multi_dataset,3d_fitting}.md`.
- **6 new ADRs** in `DECISIONS.md` covering ManifestSignals, TR knobs sentinel
  design, methodology codification, GateBadge council redesign, Suite
  distributions data-integrity rule, informational breath signal.

### Changed — 2026-06-08 / 2026-06-09 session
- **CI redundant-loading elimination (Cycle 30, four commits).** GitLab
  base image switched from `python:3.13-slim` to the public Docker Hub
  `nikolaik/python-nodejs:python3.13-nodejs22-bookworm` (Python 3.13 +
  Node 22 + uv baked in — no own-registry maintenance per user
  constraint). `CARGO_HOME` + `RUSTUP_HOME` moved under
  `$CI_PROJECT_DIR` so rustup + cargo-llvm-cov persist via the
  project-tree cache. `cargo install cargo-llvm-cov --locked` replaced
  with the prebuilt tarball from `taiki-e/cargo-llvm-cov/releases/v0.8.7`
  (GitLab) and `taiki-e/install-action@v2` (GitHub). Apt build-deps
  install gated on a job-level `NEEDS_BUILD_DEPS=1` variable —
  cmake/gfortran/lapack/openblas now installs only in the 3 jobs that
  actually compile `netlib-src` (lint:rust, test:python, test:rust);
  the other 8 jobs skip the ~1.5 min apt cost. Cycle 27 step-summary
  refactored from four `uv run coverage report` shell-outs to one
  `coverage json` + four `jq` reads. Expected savings: GitLab ~40–55
  min/pipeline (image swap + cache + apt gating); GitHub ~2.5–3.5
  min/pipeline. See DECISIONS.md 2026-06-09 ADR for the search trail.
- **GateBadge redesign (`cupertino-council` skill).** Vertical accent edge,
  four equal-weight number cells, "All clear" / "Investigate N case(s)"
  subtitle (grepable tag survives in `data-gate-status`), informational 6 s
  breath on the status dot (pulses only when PASS AND perf ratio ≥ 95 % of
  pinned), 60×14 SVG sparkline under the geomean cell when a pin exists.
- **Suite distributions trio redesign (council + data fix).** `panels.tsx`
  `suiteSpeedRows` and `suiteAccRows` no longer use `?? 1` / `?? 0` defaults
  for missing backend metrics — the previous behaviour faked 85 jax samples
  per violin. Per-backend `n=N` annotations surface via the existing `annot`
  slot; partial-surface backends get a dimmed row label via a new `dim?:
  boolean` field on `DistRow`. Layout overridden to `1fr 1fr 2fr` so the
  scatter (the thesis) is the centrepiece.
- **scipy-ls trio** (`scipy-ls-lm` / `scipy-ls-trf` / `scipy-ls-dogbox`)
  rejoins the benchmark backend roster (3 → 6 oracle). `SOLVER_META`
  extended; `synth.py` perturb/base_ms extended; tests relaxed to subset
  assertions.

### Fixed — 2026-06-08 / 2026-06-09 session
- **Engine regression policy** (`engine.py:run_suite`) excludes oracle
  failures on `optfn` cases, mirroring the accuracy-axis policy. Without
  this, 9 of 11 regressions on `2026-06-06_run_012` were oracle
  multimodal-trap noise the accuracy axis already accepted.
- **Off-domain runaway guard r²-escape**
  (`crates/spectrafit-solver/src/postfit.rs`). CX-017 reached r² = 0.96236
  but was mislabelled `success=false` because `amplitude = 2.55e3` was
  outside the data envelope — for area-normalised peak models the amplitude
  is an integrated area, not a peak height. Guard now skips above `r² ≥
  0.5`.
- **Soft-failure r²-quality upgrade** in `apply_postfit_guards`. OF-005
  reached r² = 0.9921 but reported `no_improvement_possible`; the upgrade
  promotes `success=false → true` when termination is soft AND r² ≥ 0.9.
  Numerical errors stay failures regardless.
- **`graph.py` coverage** raised from 69.8 % to 82.6 % by exercising
  `GlobalFitGraph.fit_all_slices`; per-module CI floor lifted from 65 → 80.
- **GitLab CI hardening.** `.gitlab/00-defaults.yml` `before_script` now
  fail-fasts when build tools are missing post-apt-install — surfaces the
  cause in 20 lines instead of 200 lines of cargo trace.

### Fixed
- **CI / pre-commit governance:** repaired a long-red pre-commit suite — corrected
  validator script paths after the `.github/skills` → `.claude/skills` move, removed
  two obsolete validators (`validate-scenarios` YAML, `validate-model-stub` `ModelKernel`)
  that checked a superseded architecture, updated `pre-merge-dag.sh` allowed-deps for the
  per-method solver-crate split, dropped the uninstalled `mypy` hook (superseded by `ty`),
  and scoped the `ty` / docstring checks to project sources (not `.claude/` tooling).
- **Type checking:** cleared all `ty` errors across `python/` and `tests/` — widened
  `MeasurementData.x` to match its 1-D→2-D runtime promoter, typed `Parameter` bound
  validators and the graph eval `params` (`Mapping[str, object]`, no bare `Any`).
- **Solver:** order-safe VarPro routing (filter `amplitude` by name, not positional
  `.skip(1)` over a HashMap) and point-major n-D `x` layout in the DE/global path.
- **Graph:** reject duplicate node IDs and out-of-range `dataset_index` instead of panicking.
- **PyO3 boundary:** removed the dead `ExpressionNotImplemented` error variant, corrected
  the `_core.pyi` exception docs, and made `evaluate` reject multi-dataset / n-D input.
- **Tests:** removed a stale `xfail` masking the (landed) 2-D fit path and enabled
  `xfail_strict`; added a `ModelType` ↔ Rust parity entry for the new kernels.

### Added
- **`poe report_html` pipeline:** build the Rust extension → run the benchmark → bundle a
  single, self-contained, deployable `report.html` (JS/CSS inlined via
  `vite-plugin-singlefile`, the report inlined as `window.__BENCH__`) that opens offline with
  no server. Stored at `.spectrafit_reports/benchmark/<run>/report.html`. `data.loadReport()`
  prefers the inlined data when present, else fetches `/api/report` as before.
- **Benchmark web UI — greenfield rebuild** on the frozen JSON contract: a Vite + React
  app with 5 views — **Overview** (new default hero: all-backend head-to-head with
  co-winner ties on metric equality, suite distributions, initial→best parameter recovery
  ±σ, error-vs-runtime, and the 2-D map + time-resolved series as sections) / Dashboard /
  Report / Cockpit / Export. Category-grouped sidebar navigation. The data binding has no
  silent `?? PRIMARY` fallback and enumerates backends via `solversOf(F)` (no hardcoded
  backend ids — enforced by a source-scan test). A `vitest` suite
  (`web/src/__tests__/*`) replaces the ad-hoc `web/scripts/*.mjs` smokes; `npm run smoke`
  now runs vitest.
- **2-D fitting as a real subject:** the benchmark `_multidim()` now fits the 2-D map with
  spectrafit's native `gaussian2d` kernel (`source=spectrafit-core`), replacing the prior
  scipy oracle.
- **Time-resolved series:** a real `GlobalFitGraph` joint multi-dataset fit
  (`_time_resolved()`) — peak centers/widths shared across all time slices, per-slice
  amplitudes free (recovered kinetics).
- **Contract:** `TimeResolved` / `TimeSlice` / `PeakTrace` shapes and
  `Featured.{time_resolved, guess_params}` (initial-guess values for the recovery table).
- **Ground-truth invariants:** `tests/test_bench_invariants.py` (Tier-1 fast + Tier-2
  `slow`) — every suite category is deep-dived, the analyzed set is multiple + unique,
  per-case plots are distinct, all floats finite, and optfn carries spectrafit + lmfit but
  not jax.
- New model kernels: `tauc`, `cauchy_dispersion`, `kww` (+ catalog drift-guard test).
- Project-scoped MCP servers (`serena`, `context7`, `github`) in `.mcp.json`.
