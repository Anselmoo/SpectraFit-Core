# Rust ↔ Python Binding Audit

**Cycle 8 audit, 2026-06-08.** Cross-reference between every Rust crate's
public surface and the PyO3 / pure-Python wrappers that expose it to
`spectrafit_core` (the Python package). Use this to decide where to spend
binding-completeness work.

## TL;DR

* **6 PyO3 functions** are exposed in `crates/spectrafit-core/src/lib.rs`:
  `fit`, `fit_arrays`, `fit_arrays_numpy`, `evaluate`, `evaluate_components`,
  `model_type_wire_strings`.
* **10 of 11 `Solver` variants** are reachable via the `FitOptions.solver`
  string. The eleventh (`Irls(WeightFn)`) only exposes the *default* weight
  function — the variant is reachable, the parameter is not.
* **Major unbound surfaces**: the `spectrafit-builder` typed Rust DSL (PR
  #51 — intentionally Rust-only), custom `Model` registration in
  `spectrafit-models`, the trust-region driver's low-level config
  (`StrategyConfig.{max_delta, eta, delta_init}`), and the `WeightFn` enum
  in `spectrafit-trust-region`.
* **3D fitting**: **RESOLVED (SP-2)** — native N-dimensional (≥3-D) fitting via the
  parametric `gaussian_nd` kernel (D inferred from indexed `center_<i>` params); a
  D-length coordinate row in the existing `MeasurementData` is the N-D point, so no
  `MeasurementData3D` class was needed. The bench's `_multidim` now fits a genuine 3-D
  Gaussian. The shared-model `GlobalFitGraph` global fit (`_global_fit`) remains the
  tool for *several datasets sharing one model*. See §5 below.

## What's bound

### PyO3 entrypoints (6 of 6 declared in `_core` module)

| Rust function | Python import | Notes |
|---|---|---|
| `fit` | `spectrafit_core._core.fit` (used by `fit.py:fit()`) | Pydantic-validated `FitGraph` + `MeasurementData` + `FitOptions` |
| `fit_arrays` | `spectrafit_core._core.fit_arrays` | Numpy-array fast path; used by `fit_fast()` |
| `fit_arrays_numpy` | `spectrafit_core._core.fit_arrays_numpy` | Zero-copy numpy variant for hot loops |
| `evaluate` | `spectrafit_core._core.evaluate` | Forward model evaluation |
| `evaluate_components` | `spectrafit_core._core.evaluate_components` | Per-component decomposition |
| `model_type_wire_strings` | `spectrafit_core._core.model_type_wire_strings` | Canonical model-type wire strings from the `model_manifest!`-generated `ModelTypeStr::ALL`; pins the Python `ModelType` enum to the single Rust source (parity test) |

### Solver dispatch (10 of 11 variants reachable)

| `Solver::` variant | Python string | Reachable? | Configurable params from Python? |
|---|---|---|---|
| `Lm` | `"lm"` | ✅ | `max_iterations`, `tolerance` |
| `LmLegacy` | `"lm-legacy"` | ✅ | `max_iterations`, `tolerance` |
| `Trf` | `"trf"` | ✅ | `max_iterations`, `tolerance` (bound-scaling on by default) |
| `Geodesic` | `"geodesic"` | ✅ | `max_iterations`, `tolerance` |
| `Dogleg` | `"dogleg"` | ✅ | `max_iterations`, `tolerance` |
| `NewtonCg` | `"newton-cg"` / `"steihaug"` / `"newton_cg"` | ✅ | `max_iterations`, `tolerance` |
| `Global` | `"global"` | ✅ | DE seed pinned at 0; pop/CR/F not exposed |
| `Varpro` | `"varpro"` | ✅ | Reached via dispatch; no separable-vs-nonlinear knobs |
| `Auto` | `"auto"` | ✅ | Routes to `Varpro` or `Trf` from graph shape |
| `Irls(WeightFn)` | `"irls"` / `"irls:huber"` / `"irls:bisquare"` / `"irls:cauchy"` | ✅ | Three weight functions selectable via `"irls:<name>"` colon syntax (`Solver::parse` at `dispatch.rs:108`). Tuning constants `k / c / γ` use library defaults |

### Models (kernels are reachable; can't add new ones from Python)

* All `ModelType::*` variants in `spectrafit-types` are reachable as
  `spectrafit_core.ModelType.<NAME>`. PyO3 exposes the enum implicitly via
  the `ModelNodeSpec.model_type` field.
* The `Model` trait in `crates/spectrafit-models/src/lib.rs` is NOT
  exposed — Python cannot register a new kernel without recompiling. (This
  is by design per CLAUDE.md "Adding a New Benchmark Model"; new kernels
  go through the Rust + 6-step plumbing.)

### Multi-dataset + shared parameters (bound)

* `GlobalFitGraph.fit` — single joint solve over N datasets.
* `GlobalFitGraph.fit_all_slices` — staged Stage 1 (joint globals) +
  Stage 2 (per-slice locals). Tested in Cycle 6B.
* `GlobalFitGraph.shared_local_params` — per-slice parameter ties (flat
  list or per-node dict). Bound via Pydantic.
* `ExprEdge` cross-node expression ties (bound via Pydantic on `FitGraph`).

## What's unbound (and what that costs)

### 1. `spectrafit-builder` typed Rust DSL — by design

PR #51 (commit `fa971cb`) shipped the Rust-only DSL. The Python equivalent
is `compose()` in `python/spectrafit_core/compose.py`. **Status: not a
gap.** Rust callers who don't want JSON have the DSL; Python callers have
`compose()`. Two separate front-doors for two languages.

### 2. `WeightFn` tuning constants (k / c / γ)

**UPDATE 2026-06-08:** the audit's first pass was wrong about IRLS
weight selection. `WeightFn` *is* reachable from Python via the
`"irls:<name>"` colon syntax: `"irls"` defaults to Huber, `"irls:huber"`
is explicit Huber, `"irls:bisquare"` / `"irls:biweight"` give Tukey
bisquare, `"irls:cauchy"` gives Cauchy. The parser at
`crates/spectrafit-solver/src/dispatch.rs:108-110` already does the
right split. Python docstring at `python/spectrafit_core/options.py`
documents the three names. **Status: fully bound** (Cycle 8.1, see
`tests/test_irls_weights.py`).

The only residual gap is the per-weight *tuning constant* (Huber's
`k=1.345`, bisquare's `c=4.685`, Cauchy's `γ=2.385`). These are
hard-coded in `WeightFn::from_str` (`crates/spectrafit-solver/src/irls.rs:80-86`).
Exposing them would require a richer `solver` string grammar
(`"irls:huber:1.5"`) or a new `weight_param: float` field. **Fix
scope.** ~30 lines + tests. Marginal value — the defaults are the
literature-recommended robust constants; only a research user tuning
breakdown points would care.

### 3. Trust-region driver low-level knobs

`spectrafit-trust-region::StrategyConfig` exposes only `ftol / xtol / gtol
/ max_nfev / kind / geodesic / bound_scaling` to Python. NOT exposed:

* `max_delta` (cap on trust-region radius growth)
* `eta` (step-acceptance threshold)
* `delta_init` (initial radius scaling)

**Cost.** Power-user tuning for ill-conditioned problems. A research user
wanting to set `eta=1e-4` for aggressive stepping cannot.

**Fix scope.** Add optional fields to `FitOptions` with `None` sentinel
that means "use default." ~40 lines.

### 4. Custom problem trait (`TrustRegionProblem`)

The trait at `crates/spectrafit-trust-region/src/lib.rs` is the
*generalised* fit problem (residuals + Jacobian + bounds). Python can only
fit the `MeasurementData (x, y)` shape. Custom objectives — likelihood,
chi² with arbitrary residual definition, etc. — are unreachable.

**Cost.** Cycle 11+ territory; not a current need.

### 5. 3D fitting — RESOLVED (SP-2)

Native N-dimensional (≥3-D) fitting now exists. **No `MeasurementData3D` class was
needed** (the audit's "Option A"): a D-dimensional point is just a coordinate row of
length `D` in the existing `MeasurementData(x: list[list[float]], y: list[float])`,
and the parametric `gaussian_nd` kernel handles any `D` — its dimensionality is
*inferred* by the compiler from the node's indexed `center_<i>` parameters. The bench's
`_multidim` deep-dive now fits a genuine **3-D** Gaussian (not a 2-D `gaussian2d` map).
The Python `n_dims > 2` guard is gone; the Rust executor/Jacobian/LM were already
N-D-general (a 2026-06-21 spike proved it).

The stacked-slices pattern (the audit's "Option B") remains valid but answers a
*different* question — *several datasets sharing one model with per-slice free
parameters* (a `GlobalFitGraph` shared-model global fit), not a single model over an
N-dimensional coordinate space. See [`docs/examples/3d_fitting.md`](examples/3d_fitting.md).

## Recommended Cycle 8.x follow-ups

| Sub-cycle | What | Effort | Value |
|---|---|---|---|
| **8.1** | Expose `WeightFn` to Python (IRLS robust-loss selection) | ~20 lines + 3 tests | Medium — covers spectroscopy outlier use cases |
| **8.2** | Expose `max_delta / eta / delta_init` knobs on `FitOptions` | ~40 lines + tests | Low-medium — power-user research |
| **8.3** | Document "3D via stacked slices" pattern in `docs/examples/3d_fitting.md` | ~50 lines markdown | Low effort, high docs coverage |
| **8.4** | Add a runnable example for each of: single fit, shared params, multi-dataset, "3D" via slices (theme B from the backlog) | ~150 lines docs+code | Medium |

## Test reachability

* Every PyO3 entrypoint is exercised by `tests/test_fit.py`,
  `tests/test_evaluate.py`, `tests/test_global_fit.py`, and the bench
  suite (139 cases × `spectrafit` backend = 139 distinct fit calls per
  bench run).
* Every solver string is exercised by either the bench (lm/trf/global/
  varpro via `solver_hint`) or the parity tests (`lm-legacy` against the
  nalgebra oracle).
* `Solver::Irls` is exercised but only with the default weight — see #2
  above.

## Maintenance

Re-run this audit when:

* Any new `#[pyfunction]` lands in `crates/spectrafit-core/src/lib.rs`.
* Any new `Solver::` variant is added in
  `crates/spectrafit-solver/src/dispatch.rs`.
* `FitOptions` gains a field (regenerate the matrix in §"Solver dispatch").
* A new model kernel is added under `crates/spectrafit-models/src/`
  (verify the `ModelType` round-trip is bound).

The minimal regeneration recipe is the same `grep + serena find_symbol`
sweep that built this document; no scripted audit yet (Cycle 8.5 candidate).
