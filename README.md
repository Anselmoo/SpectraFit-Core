# SpectraFit-Core

> High-performance numerical curve fitting — a Rust kernel with analytical
> Jacobians, Pydantic-typed schemas, and a **self-auditing benchmark** that
> audits its own credibility against independent oracles (lmfit, JAX, scipy) and
> NIST StRD certified values.

![status: beta](https://img.shields.io/badge/status-beta-yellow)
![license: MIT](https://img.shields.io/badge/license-MIT-blue)
![python: 3.13+](https://img.shields.io/badge/python-3.13%2B-blue)

> **Status: beta (`0.1.0-rc.1`) — public sneak preview.** APIs and the benchmark contract may still change before the stable 1.0 release. See [LIMITATIONS.md](LIMITATIONS.md) for disclosed gaps.

**Documentation:** <https://anselmoo.github.io/SpectraFit-Core/> — start with
[Installation](https://anselmoo.github.io/SpectraFit-Core/getting-started/installation/)
and [Quickstart](https://anselmoo.github.io/SpectraFit-Core/getting-started/quickstart/).

## What is this?

SpectraFit-Core fits spectroscopic and general nonlinear models with a Rust
Levenberg–Marquardt / trust-region core, exposed to Python through a PyO3 wheel
and a Pydantic schema mirror. Its distinguishing feature is a **trustworthy
benchmark**: rather than asking you to take its speed/accuracy claims on faith,
it ships a dashboard that verifies its own numbers (independent parity oracle,
timing-isolation guards, render-truth provenance, NIST StRD validation) and
visibly discloses what it has *not* verified.

> Development and the authoritative CI run on an institutional GitLab instance;
> this repository is its public mirror, updated after every green pipeline on
> `main`. Issues and pull requests here are welcome — see
> [CONTRIBUTING.md](CONTRIBUTING.md).

## Quick start

```bash
git clone https://github.com/Anselmoo/SpectraFit-Core.git
cd SpectraFit-Core
uv sync --extra benchmark   # dev tooling is a dependency-group, installed by default
uv run maturin develop
```

Then fit a single Gaussian peak to synthetic data, using only the public
`spectrafit_core` API (verified to run — see
[Quickstart](https://anselmoo.github.io/SpectraFit-Core/getting-started/quickstart/)
for the full walkthrough):

```python
import numpy as np
from spectrafit_core import MeasurementData, compose, fit, gaussian

# Synthetic "measured" data: a Gaussian peak plus a little noise.
x = np.linspace(-5, 5, 200)
y = 3.0 * np.exp(-0.5 * ((x - 0.5) / 1.2) ** 2) + np.random.default_rng(0).normal(
    0, 0.05, x.size
)

# Build the model graph: one Gaussian node with initial guesses.
graph = compose([gaussian("peak1", amplitude=1.0, center=0.0, sigma=1.0)]).build()

# Run the fit.
result = fit(graph, MeasurementData(x=x.tolist(), y=y.tolist()))

print(result.parameters)  # fitted amplitude/center/sigma, keyed "peak1.<param>"
print(result.r_squared)  # goodness of fit
```

This is deterministic (seeded RNG) and recovers the true amplitude/center/sigma
(3.0, 0.5, 1.2) to within about one standard error, with `r_squared` ≈ 0.998:

```text
{'peak1.sigma': ParameterResult(value=1.2024163241228947, ..., stderr=0.004211511681961483),
 'peak1.center': ParameterResult(value=0.49756589193680784, ..., stderr=0.004211469158787863),
 'peak1.amplitude': ParameterResult(value=2.997594452290324, ..., stderr=0.00909249987508253)}
0.9979075074894731
```

> The block above is reformatted for readability: `print` emits it as one long
> line, and dict ordering is an implementation detail — your keys may appear in a
> different order. The values are what matter, and they are reproducible: the
> example seeds its RNG.

Run `uv run pytest` for the full test suite.

## Benchmark

The benchmark (`python/oracles/`) fits the same problems with **spectrafit**
(the Rust kernel under test) and five reference backends: **lmfit**,
**jax/optimistix** and three `scipy.optimize.least_squares` methods (`lm`,
`trf`, `dogbox`).

- **Cases:** a deterministic catalogue defined in `python/oracles/cases.py`
  (`CATEGORY_REGISTRY`: easy, complex, scaling, lineshapes, reality, edge,
  optfn, fixed, tied). Every case can be opened on its own in the report.
- **Showcases:** a 3-D fit with the native `gaussian_nd` kernel and a joint
  multi-spectrum fit with `GlobalFitGraph` (shared centres and widths,
  per-spectrum amplitudes).
- **Data flow:** benchmark run → `results.json` (the `BenchReport` contract)
  → FastAPI → the React app in `web/`. `poe report_html` bundles the same
  report into one offline file.
- **Report:** *Standing* shows what was measured, without a verdict;
  *Evidence* shows every backend on every case, side by side.

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

`benchmark_gate` (and CI) always checks three axes — spectrafit must not
become **slower than lmfit overall** (geomean speedup < 1×), must not
**break accuracy parity** (max |Δr²| > 1e-3 on the LM-family cases; the
multimodal `optfn`/global category is excluded since two stochastic global
optimizers legitimately reach different optima), and must not **regress any
backend's convergence**. Up to four more axes are appended only when their
backing evidence exists (self-perf, model-selection, σ-calibration, speed
inference) — the gate is never a fixed axis count. See
[Why SpectraFit-Core](docs/why-spectrafit-core.md), "A benchmark that
verifies itself" section, for the full, canonical axis-by-axis description;
this file summarizes it, it doesn't restate it.

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
uv run poe report_html   # → .spectrafit_reports/benchmark/<run>/report.html (one file, tens of MB;
                          # size scales with the backend roster and case catalog)
```

The Python contract (`oracles.bench_contract`) is the single source of truth.
The FastAPI app publishes it as OpenAPI, and `npm run contract` generates the
TypeScript types from that schema, so engine and UI cannot drift apart.

## Adding a model or case

The benchmark is registry-driven (see [Extending SpectraFit-Core](https://anselmoo.github.io/SpectraFit-Core/contributor-guide/extending/)):
register one `PeakModel` in `oracles.models`, reference its key from a
`CaseSpec`/`CaseFamily` in `oracles.cases`. After a contract change, regenerate
the TS types from the live OpenAPI schema: `uv run poe serve` then
`cd web && npm run contract`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, conventions, and the PR
process.

## Citing

If you use SpectraFit-Core in academic work, please cite it via
[`CITATION.cff`](CITATION.cff) (GitHub's "Cite this repository" button reads it).

## License

[MIT](LICENSE) © Anselm Hahn. See also [CONTRIBUTING.md](CONTRIBUTING.md),
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), and [SECURITY.md](SECURITY.md).
