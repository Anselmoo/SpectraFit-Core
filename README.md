# spectrafit-core

> High-performance numerical curve fitting — a Rust kernel with analytical
> Jacobians, Pydantic-typed schemas, and a **self-auditing benchmark** that
> audits its own credibility against independent oracles (lmfit, JAX, scipy) and
> NIST StRD certified values.

![status: beta](https://img.shields.io/badge/status-beta-yellow)
![license: MIT](https://img.shields.io/badge/license-MIT-blue)
![python: 3.13+](https://img.shields.io/badge/python-3.13%2B-blue)

> **Status: beta (`0.1.0b1`) — public sneak preview.** APIs and the benchmark contract may still change before the stable 1.0 release. See [LIMITATIONS.md](LIMITATIONS.md) for disclosed gaps.

## What is this?

spectrafit-core fits spectroscopic and general nonlinear models with a Rust
Levenberg–Marquardt / trust-region core, exposed to Python through a PyO3 wheel
and a Pydantic schema mirror. Its distinguishing feature is a **trustworthy
benchmark**: rather than asking you to take its speed/accuracy claims on faith,
it ships a dashboard that verifies its own numbers (independent parity oracle,
timing-isolation guards, render-truth provenance, NIST StRD validation) and
visibly discloses what it has *not* verified.

[![CI (GitLab MPCDF)](https://gitlab.mpcdf.mpg.de/anhahn/spectrafit-core/badges/main/pipeline.svg)](https://gitlab.mpcdf.mpg.de/anhahn/spectrafit-core/-/pipelines)
[![Coverage (GitLab)](https://gitlab.mpcdf.mpg.de/anhahn/spectrafit-core/badges/main/coverage.svg)](https://gitlab.mpcdf.mpg.de/anhahn/spectrafit-core/-/pipelines)

> GitLab MPCDF is the primary development host and CI source of truth — it runs the full test/lint/coverage gates on every push to `main` and publishes the Coverage Atlas + benchmark dashboard to GitLab Pages. This GitHub repository carries a public, history-free snapshot mirror of `main` (no CI runs here — see `rrt git publish-snapshot` in `pyproject.toml`'s `[tool.rrt.publish_targets.github]`).

High-performance numerical fitting framework with Rust kernels and Python APIs.

For the Rust/Python "code dualism" map and the benchmark methodology (the
reference-kernel vs. Rust-kernel "break in method"), see
[`docs/whitepaper_methodology.md`](docs/whitepaper_methodology.md).

## Quick start

```bash
uv sync --extra benchmark   # dev tooling is a dependency-group, installed by default
uv run maturin develop
uv run pytest
```

## Benchmark

The benchmark engine (`python/oracles/`) compares **spectrafit** (the Rust
kernel, the subject) against **lmfit** and **jax/optimistix** (independent
cross-verification oracles) across a deterministic case catalog whose counts and
categories are defined by the registry in `python/oracles/cases.py`
(`CATEGORY_REGISTRY` — easy / complex / scaling / lineshapes / reality / edge /
optfn / fixed / tied). **Every case** is deep-divable in the selector (optfn
included — its panels render the global-vs-local landscape story, with jax
legitimately absent). The benchmark also fits a 2-D map with spectrafit's native
`gaussian2d` kernel (a real subject, not the scipy oracle) and runs a
time-resolved series as a real `GlobalFitGraph` joint multi-dataset fit (shared
peak centers/widths, per-slice amplitude kinetics); the contract carries both
showcases, though no web panel renders them yet. It emits the frozen
`BenchReport` contract, served at runtime by a FastAPI app; the `web/` React app
fetches and renders it. One data flow: **benchmark run → results.json → FastAPI
→ React** (at runtime; the optional `poe report_html` bundle below inlines the
same report for offline use). The UI has two destinations: **Standing** (facts
masthead — what was measured, no verdict) and **Evidence** (all backends, all
cases, side by side).

```bash
uv run poe benchmark         # full run → results.json + manifest.json
uv run poe benchmark_quick   # lean reps, fast local iteration
uv run poe serve             # serve the latest report over FastAPI (http://localhost:8000)
uv run poe benchmark_gate    # spectrafit-vs-lmfit regression gate on the latest run

# or the CLI directly
PYTHONPATH=python uv run python -m oracles.cli run --reps 10 --mc 30
PYTHONPATH=python uv run python -m oracles.cli gate
```

Each run writes an isolated, run-centric folder (no overwrites, no legacy mirror):

```
.spectrafit_reports/<category>/<YYYY-MM-DD>_run_NNN/
  results.json     # the BenchReport contract payload (served by the FastAPI app)
  manifest.json    # run metadata + headline stats (geomean speedup, max |Δr²|, win-rate)
.spectrafit_reports/index.json   # all runs, newest first
```

The latest run resolves via `oracles.reports.latest_results(category)`.

### Regression gate

`benchmark_gate` (and CI) fails if spectrafit becomes **slower than lmfit overall**
(geomean speedup < 1×) or **breaks accuracy parity** (max |Δr²| > 1e-3 on the
LM-family cases; the multimodal `optfn`/global category is excluded since two
stochastic global optimizers legitimately reach different optima).

### Web report

```bash
uv run poe serve   # serve the latest report over FastAPI (in another shell)

cd web && npm install
npm run dev        # dev server; proxies /api → http://localhost:8000 (the FastAPI app)
npm run build      # production build → dist/ (fetches /api/report at runtime)
npm run test       # vitest: render all views from fixtures, no browser/API (alias: npm run smoke)
npm run contract   # regenerate src/openapi.gen.ts from the live /openapi.json
```

**Self-contained HTML** — one command builds the extension, runs the benchmark, and bundles a
single, deployable `report.html` (all JS/CSS inlined, the report inlined as `window.__BENCH__`)
that opens **offline** with no server:

```bash
uv run poe report_html   # → .spectrafit_reports/benchmark/<run>/report.html (one file, ~12 MB)
```

The Python contract (`oracles.contract`) is the single source of truth; the
FastAPI app publishes its OpenAPI schema and the TypeScript types are generated from
that live schema (`npm run contract` → `openapi-typescript`), so the engine and UI can
never drift. The view-facing `web/src/contract.ts` re-exports the named types from the
generated `openapi.gen.ts`, so the views never change when the contract is regenerated.

## Background jobs

Any long task can run detached via `scripts/run_pytest_bg.sh` (prints a job id;
archives under `.spectrafit_reports/background-jobs/<family>/<NNN>/`):

```bash
uv run poe run_bg benchmark          # any poe task in the background
uv run poe bg_status                 # all jobs
uv run poe bg_status --job <job_id> --tail 40
bash scripts/bg.sh                   # interactive menu
```

## Adding a model or case

The benchmark is registry-driven (see `CLAUDE.md` → "Adding a New Benchmark Model"):
register one `PeakModel` in `oracles.models`, reference its key from a
`CaseSpec`/`CaseFamily` in `oracles.cases`. After a contract change, regenerate
the TS types from the live OpenAPI schema: `uv run poe serve` then
`cd web && npm run contract`.

## Citing

If you use spectrafit-core in academic work, please cite it via
[`CITATION.cff`](CITATION.cff) (GitHub's "Cite this repository" button reads it).

## License

[MIT](LICENSE) © Anselm Hahn. See also [CONTRIBUTING.md](CONTRIBUTING.md),
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), and [SECURITY.md](SECURITY.md).
