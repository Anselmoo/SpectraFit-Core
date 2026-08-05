---
icon: lucide/book-open
description: Project-specific terms used across the spectrafit-core docs — DAG IR, VarPro, trust region, wire strings, and more.
---

# Glossary

Project-specific terms used across these docs. General numerical-fitting
vocabulary (residual, Jacobian, covariance) is assumed; this page covers the
terms that are specific to spectrafit-core's own architecture and benchmark
harness. For lineshape-formula conventions (amplitude, σ vs. FWHM/HWHM,
`fraction`), see [Model Reference](reference/models/index.md#symmetric-peak-lineshapes)
instead of duplicating them here.

### AIC / BIC { #aic-bic }

Akaike / Bayesian Information Criterion. Derived from a proper Gaussian
deviance term (`neg2_log_l = N_points * ln(chi2 / N_points)`), not raw
`chi2` directly. See [Solver](explanation/solver-selection.md#post-fit-statistics).

### DAG IR { #dag-ir }

The directed-acyclic-graph intermediate representation models are
compiled to: defined in Python as [`ModelNodeSpec`](#modelnodespec) +
`ExprEdge`, serialised to JSON, and evaluated entirely in Rust. See
[Model Composition — DAG IR](explanation/model-composition-dag.md).

### DOF { #dof }

Degrees of freedom, `N_points - N_free`. For multi-dataset global fits,
`DOF = sum_d(N_d) - N_free_shared`. See
[Solver](explanation/solver-selection.md#post-fit-statistics).

### `ExprEdge` { #expredge }

A graph-level parameter tie: `ExprEdge(target_node=…, target_param=…,
expression=…)` added to `FitGraph.expr_edges`. One of two equivalent
surfaces for constraining a parameter to another's value or a formula —
the other is [`Parameter.expr`](#parameterexpr). See
[Model Composition — DAG IR](explanation/model-composition-dag.md#edges)
and [Model Reference](reference/models/index.md#parameter-constraint-surfaces).

### Gate (regression gate) { #gate }

The benchmark's pass/fail check on every run: spectrafit must not be
slower than the baseline solver, and accuracy parity must hold on the
LM-family cases. Enforced by `oracles.cli run` / `gate`; reported as
`gate_state` in the benchmark manifest. See
[Benchmark engine](contributor-guide/benchmark-engine.md).

### Geomean speedup { #geomean-speedup }

The geometric mean of spectrafit's per-case speedup versus the baseline
solver (lmfit), across the benchmark case catalog — the headline number
on the [Performance](performance/index.md) page and in the benchmark
manifest's `geomean_speedup_vs_baseline` field.

### `ModelNodeSpec` { #modelnodespec }

A typed model instance node in the [DAG IR](#dag-ir): an `id`, a
`model_type` ([`ModelType`](#modeltype)), a `parameters` dict, and an
optional `dataset_index` for multi-dataset scoping. See
[Model Composition — DAG IR](explanation/model-composition-dag.md#nodes).

### `ModelType` { #modeltype }

The Python enum of model kinds (`GAUSSIAN`, `LORENTZIAN`, …), pinned at
runtime to the Rust `model_manifest!` macro's 34 canonical
[wire strings](#wire-string) via `model_type_wire_strings()`. See
[Model Reference](reference/models/index.md) and
[Rust ↔ Python binding audit](reference/rust/binding-audit.md).

### Oracle (parity oracle) { #oracle }

An independent reference implementation (lmfit, jax/optimistix, or the
numpy formulas in `oracles.models.MODEL_REGISTRY`) that spectrafit's Rust
kernel is cross-verified against — any formula or numerical difference
surfaces as a benchmark accuracy-gate failure rather than a crash. See
[Benchmark engine](contributor-guide/benchmark-engine.md).

### `Parameter.expr` { #parameterexpr }

A per-parameter tie: set `expr="source_node.param"` directly on a
`Parameter`. Equivalent to an [`ExprEdge`](#expredge) — both compile
through the same dependency-ordered, cycle-checked tied-plan evaluator,
and `vary` is ignored whenever `expr` is set. See
[Parameter Model](explanation/parameter-model.md).

### PyO3 binding { #pyo3-binding }

A Rust function exposed to Python via `#[pyfunction]` in
`crates/spectrafit-core/src/lib.rs` (e.g. `fit`, `evaluate`,
`model_type_wire_strings`) — the FFI boundary between the Rust kernel and
the Python package. See
[Rust ↔ Python binding audit](reference/rust/binding-audit.md).

### `Solver::Variant` { #solvervariant }

A Rust enum case in `spectrafit-solver::dispatch` (`Solver::Lm`,
`Solver::Trf`, `Solver::Varpro`, …) that a Python `FitOptions.solver`
string resolves to at the PyO3 boundary. See
[Rust ↔ Python binding audit](reference/rust/binding-audit.md#solver-dispatch-cratesspectrafit-solversrcdispatchrs)
and [Choosing a Solver](how-to/choosing-a-solver.md).

### Tied parameter { #tied-parameter }

A parameter whose value is derived from another parameter or an
expression every solver iteration, via either [`ExprEdge`](#expredge) or
[`Parameter.expr`](#parameterexpr), rather than being independently
optimised. Not supported by the `"varpro"` solver. See
[Model Reference](reference/models/index.md#parameter-constraint-surfaces).

### Trust region { #trust-region }

A family of solver strategies (`"trf"`, `"dogleg"`, `"newton-cg"`) that
bound each optimisation step within an explicit radius (`delta0`,
`max_delta`) rather than taking an unconstrained Gauss-Newton step. See
[Choosing a Solver](how-to/choosing-a-solver.md#tuning-trust-region-behavior).

### VarPro (Variable Projection) { #varpro }

A solver strategy (`solver="varpro"`) for *separable* nonlinear least
squares: linear amplitude coefficients are solved analytically at each
step, leaving only the nonlinear shape parameters (center, sigma, …) for
the outer optimisation. Fastest option when its preconditions hold — no
tied parameters, no bounds on the nonlinear side. See
[Choosing a Solver](how-to/choosing-a-solver.md).

### Wire string { #wire-string }

The canonical, serialised name for a model type (e.g. `"gaussian"`,
`"pseudo_voigt"`) generated from the Rust `model_manifest!` macro — the
single source of truth [`ModelType`](#modeltype) is pinned against. See
[Model Reference](reference/models/index.md).

### Win rate { #win-rate }

The fraction of benchmark cases where spectrafit's fit is faster than
the baseline solver — reported alongside [geomean speedup](#geomean-speedup)
on the [Performance](performance/index.md) page.
