# Changelog

All notable changes to `spectrafit-core` will be documented in this file.

This project follows repository release policy enforced by `repo-release-tools`.

> **Release status — nothing below has been tagged or published.**
> No version tag exists in this repository (`git tag -l` lists only `pr/*` refs,
> on the primary remote as well), and there is no `spectrafit-core` project on
> PyPI. The `[0.1.0b1]` and `[0.1.0a1]` sections below record the dates on which
> those version bumps were *prepared in-tree*; neither was ever cut as a release,
> so neither date is a release date. `CITATION.cff` omits its `date-released`
> field for exactly this reason.
>
> The package currently ships as **`0.1.0`** (`pyproject.toml`, `Cargo.toml`).
> Everything since the `0.1.0b1` bump — including that version's own promotion to
> `0.1.0` — is collected under `[Unreleased]` below, and will be folded into the
> first `[0.1.0]` section when a release is actually tagged and deposited.
>
> **Scope note.** `[Unreleased]` below summarises the development log by theme
> rather than reproducing it entry by entry. Nothing here has been rewritten:
> no entry below describes a release that happened, because none has.

## [Unreleased]

### Added

- **Only the CI sync can write to the GitHub mirror.** A `guard-public-push`
  pre-push hook (`scripts/guard_public_push.py`) refuses any push to a
  github.com remote whose tree holds a path outside the publish include list,
  so no branch can reach the mirror around `scripts/publish_sync.py`. The
  benchmark-host helper (`scripts/remote_bench.sh`) now pushes to GitLab only
  and fails loudly instead of silently trying the mirror first, and the
  "Fast iteration on GitHub" lane (a direct branch push to the mirror) is gone
  from the contributor docs, replaced by a server-side ruleset checklist for
  the mirror repository.
- **Zenodo and release metadata.** `.zenodo.json` for the GitHub integration,
  a `releasing.md` contributor checklist for the first archival release, and a
  meta-test that keeps `pyproject.toml`, `CITATION.cff`, `codemeta.json` and
  `.zenodo.json` agreeing on version, licence, author ORCID and repository.
- **A guard against shipped tests reading stripped paths.** A meta-test scans
  every test that ships to the public mirror for path literals matching a
  publish exclusion, the failure class behind a red mirror CI run. It exempts
  its own scanner self-tests, which feed it excluded literals on purpose.
- **A `robust` benchmark category.** Iteratively reweighted least squares on
  outlier-contaminated spectra, six cases, all JAX-eligible.
- **Credibility-ladder rung 3 closed.** Significant digits are measured against
  NIST StRD certified values rather than asserted, and an uncertainty budget
  splits error into numerical, model-form and input terms.
- **Surrogate oracles** — metamorphic relations that must hold where no
  reference answer exists, for the cases certified values cannot reach.
- **Analytic Jacobians are checked across every kernel** in multiple regimes,
  rather than trusted.
- **Three new model kernels** wired end to end: `rational_cubic`,
  `generalised_logistic` and `exp_over_linear`.
- **All 22 NIST StRD data modules carry a documented `Attributes:` section**,
  so the certified values, starting points and degrees of freedom are readable
  without opening the upstream page.
- **Two gallery pages about being wrong** — a converged fit reporting success
  with a negative $r^2$, and a model that is simply misspecified while every
  scalar score improves.
- **FAIR tooling for the published evidence** (`uv run poe fair`): a whole-tree
  sha256 manifest that also reconciles the per-subtree manifests and every
  RO-Crate digest against the files themselves, a provenance registry for
  vendored third-party data, and an RO-Crate 1.1 describing the tree.

### Changed

- **Web toolchain on React 19 and TypeScript 7.** The dashboard (`web/`) and the
  root tooling package move to React 19, the TypeScript 7 native compiler for
  `npm run typecheck`, Vitest 5, `@vitejs/plugin-react` 6, KaTeX 0.18 (which
  ships its own types, so `@types/katex` is gone) and current Vite, Biome,
  Playwright and Testing Library releases. `openapi-typescript` still needs the
  TypeScript JavaScript API, so the plain `typescript` package stays on 5.9 for
  contract codegen. `npm audit` reports no vulnerabilities in either lockfile.
- **Python dev and docs tooling bumped.** ty 0.0.84, ruff 0.16.9, zensical
  0.0.65, mkdocstrings-python 2.0.9 and repo-release-tools 1.18.0, with the
  pre-commit hook revs moved in step; minor bumps of hypothesis, maturin,
  pydantic, numpy, matplotlib, typer, uvicorn and jax. The two cross-pipeline
  CI artifact fetches are now declared for `rrt doctor`'s new check.
- **Docs name the project SpectraFit-Core in prose.** The architecture page
  used the package spelling `spectrafit-core` as the project name.
- **Shorter README benchmark section.** The benchmark overview and the
  contract paragraph are a short list now; content and links unchanged.

- **GitHub contributor PRs are squash-merged.** The mirror allows squash
  merges only (repository setting and the `main` ruleset), so each PR is one
  commit on `main`, authored by the PR author with other committers as
  `Co-authored-by:` trailers; `backport:github` cherry-picks that commit
  unchanged. The anonymous sync still lands by deploy-key fast-forward
  (`docs/contributor-guide/github-mirror-workflow.md`).

- **The GitHub mirror sync is anonymous one way and keeps history the other.**
  GitLab -> GitHub: each sync lands as one commit authored *and* committed by
  `spectrafit-core-sync[bot]`, the bot account of a dedicated GitHub App (so
  GitHub shows a bot, never a person), with the fixed subject `sync: gitlab main`, a fixed
  body and the `GitLab-Commit:` trailer as the only GitLab-derived content. It
  no longer lands by GitHub squash auto-merge (which re-authors the commit to
  the token's owner and sets the committer to GitHub): `scripts/publish_sync.py`
  waits for the ruleset's required checks on the sync PR and fast-forwards
  `main` to the exact checked commit through a deploy-key SSH remote, the
  mirror's only push identity; a moved `main` is refused, never forced.
  GitHub -> GitLab: `scripts/backport_from_github.py` expands a merge-commit PR
  into its individual commits (original author, date and message, `-x`)
  instead of one `-m 1` commit attributed to whoever merged, and opens the
  GitLab MR with `squash: false`.

- **The GitHub mirror keeps its history.** GitLab `main` now reaches GitHub
  as one squashed pull request per change (`scripts/publish_sync.py`): a single
  commit whose tree is the filtered GitLab tree, parented on GitHub `main`,
  carrying a `GitLab-Commit:` trailer, merged by squash auto-merge once CI is
  green. The history-rewriting orphan snapshot survives only as the manual
  `publish:github:reset` job. The reverse direction is automated too: a
  scheduled `backport:github` job cherry-picks GitHub-native commits (Dependabot,
  outside pull requests) onto a branch and opens a GitLab merge request,
  skipping anything already carried over.
- **BREAKING: `FitOptions.eta` must be `< 0.25`** (was `< 1.0`). Values at or
  above the new bound never produced a usable trust-region step.
- **IRLS warm-starts each outer pass** and converges on its own weight sequence.
- **`fit`/`fit_fast` raise `ValueError`** when datasets disagree on `n_dims`,
  instead of failing later and less legibly.
- **`spectrafit-solver::fit` is the only site that sets faer's global thread
  configuration**, so a library caller's threading is no longer silently
  overridden from several places.
- **The evidence tree moved to `reproducibility/`** and third-party measured
  data is vendored under its own licence, recorded per asset in
  `reproducibility/assets.toml`.

### Deprecated

- Two public surfaces are deprecated but **still ship in 0.1.0**; neither is
  removed by this version.

### Fixed

- **Both mirror directions work against a private GitHub repository.**
  `backport:github` sends `GITHUB_TOKEN` as a second `http.extraheader`
  scoped to `https://github.com/` (`GIT_CONFIG_COUNT=2`, one header per host),
  and `publish:github` / `publish:github:fast` authenticate their fetches too;
  previously only pushes carried a token, so every fetch of a private mirror
  failed.

- **`tests/meta/test_publish_sync.py`'s fast-forward tests no longer depend on
  the ambient `init.defaultBranch`.** Its bare-remote `git init` and its
  `_race_remote_main` clone didn't pin `-b main`, so under a non-`main`
  default (git <2.28's built-in "master", or any global override) the race
  helper's `git push origin main` failed outright. Both call sites now pin
  `-b main`, matching the pattern already used in
  `test_backport_from_github_script.py`.

- **The PyO3 binding crate is held to a 75% line floor on both CIs again.**
  GitHub's gate read 41.7% because llvm-cov counted three instrumented copies
  of `lib.rs`, only one of which ever ran: `cargo test` now excludes the
  test-less `spectrafit-core` crate, and the instrumented pytest step no longer
  lets `uv` rebuild the extension. GitLab had dropped the floor in June; its
  `rust-cov` job now runs the binding tests against the instrumented build and
  enforces it. New binding tests cover the zero-copy numpy path, sigma
  weighting, ragged and empty inputs and overflow guards, taking the measured
  binding coverage from 68% to 93%.
- **The RO-Crate no longer drifts on every commit.** `datePublished` was read
  from `git log`, so a crate generated before its own commit could never match
  a rebuild after it (and shallow clones broke it outright). It now comes from
  `CITATION.cff`'s `date-released`, falling back to a pinned date; the two
  nested crates also name their author with an ORCID.
- **Packaging metadata uses the PEP 639 licence form** (`license = "MIT"` plus
  `license-files`), with classifiers for the platforms, interpreter and typing
  the project actually supports and a `Documentation` URL. The maturin floor
  rises to 1.9, the first release with full PEP 639 support.

- **`fit_arrays`/`fit_arrays_numpy` mapped a Rust panic to an uncatchable
  `PanicException`**; solver-invoking entry points now raise a catchable
  `ValueError`.
- **VarPro reported permuted standard errors** — `fill_parameter_stderr`
  associated each error with the wrong parameter.
- **Floating-point values crossing the PyO3 boundary could round to a different
  value** than the one computed.
- **`gradient_norm` and the last `gradient_norm_history` entry mixed two
  different quantities.**
- **The rat43 NIST StRD fixture certified the wrong degrees of freedom.**
- **Three published model formulas were wrong**, including `log_normal`'s
  docstring.
- **Documentation claims the code does not support**, and counts across `docs/`
  that had drifted with nothing guarding them.

## [0.1.0b1] - 2026-06-23

> Prepared, not released — see the release-status note at the top of this file.
> No `0.1.0b1` tag exists.

### Changed
- Promoted to **beta** (`Development Status :: 4 - Beta`). Intended as a
  non-public, GitLab/GWDG-only reproducible **source** release
  (clone + `uv run maturin develop`); no PyPI/wheel publish, no DOI. The
  version bump and metadata landed in-tree on this date; the tag was never
  cut.

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

> Prepared, not released — see the release-status note at the top of this file.
> No `0.1.0a1` tag exists.

### Added
- MIT `LICENSE` file; `CITATION.cff` (CFF 1.2.0); `CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), `SECURITY.md`.
- `LIMITATIONS.md` disclosing the benchmark's self-audit gaps (W2c κ(J),
  NIST 4-of-27 subset, χ²-floor convergence proxy, JAX-no-σ).
- `pyproject` `authors`, `[project.urls]`, and PyPI classifiers (alpha).
- Research-grade `README.md` intro with status, citation, and license sections.

### Changed
- Markdown documentation consolidated (129 → 91 tracked files).
- `rrt` `repo-root-required-files` contract extended to enforce the new
  governance/legal files.

### Added — 2026-06-08 / 2026-06-09
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
- **Rust binding audit** at `docs/reference/rust/binding-audit.md` enforced by a
  `scripts/audit_bindings.py` CI guard — fails the pipeline when a new
  `#[pymodule]` registration or `Solver::` variant lands without a doc entry.
- **Runnable examples** at
  `docs/examples/{fitting,shared_params,multi_dataset,3d_fitting}.md`.

### Changed — 2026-06-08 / 2026-06-09
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
  the other 8 jobs skip the ~1.5 min apt cost. The step-summary step
  refactored from four `uv run coverage report` shell-outs to one
  `coverage json` + four `jq` reads. Expected savings: GitLab ~40–55
  min/pipeline (image swap + cache + apt gating); GitHub ~2.5–3.5
  min/pipeline.
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

### Fixed — 2026-06-08 / 2026-06-09
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
- Project-scoped MCP servers (`context7`, `github`) in `.mcp.json`.
