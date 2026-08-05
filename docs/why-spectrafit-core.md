---
icon: lucide/sparkles
description: Why spectrafit-core is a new Rust-kernel implementation rather than a Python wrapper — compiled model evaluation, analytical Jacobians, structure-aware solver routing, and a benchmark that verifies its own claims.
---

# Why SpectraFit-Core

Most of this site is reference material — what a function does, what a
parameter means. This page is different: it's the engineering case for
*why* spectrafit-core exists as a new implementation, not a wrapper around
an established one. lmfit and scipy's `curve_fit` represent a mature,
widely-used **pure-Python approach** — Python-level model composition,
Python-level dispatch, NumPy for the math. spectrafit-core takes a
different, **compiled-kernel approach**: the same class of problem, solved
by moving composition and evaluation into a typed Rust core. Neither
approach is wrong; this page is about what the compiled approach actually
buys, with a pointer to where each claim is enforced in the codebase — not
just asserted here.

## At a glance

| | Pure-Python approach (lmfit, `curve_fit`) | spectrafit-core |
|---|---|---|
| Model composition | Python objects, `model1 + model2` | Rust DAG, compiled once |
| Per-iteration evaluation | Python dispatch loop | Single compiled Rust loop |
| Jacobian | Numerical (finite-difference) by default | Analytical by default, FD as an explicit fallback |
| Solver selection | Chosen by the caller | Structure-routed (`"auto"`), 10 strategies available |
| Multi-dataset fitting | Hand-rolled per project | Native: stacked-slice and N-D, exact DOF accounting |
| Speed/accuracy claims | Not independently re-verified per release | Gated against independent oracles + NIST StRD every run |

## :lucide-shield-check: A benchmark that verifies itself, not just asserts

The speed/accuracy numbers on the [Performance](performance/index.md) page
aren't self-reported. Every benchmark case is cross-checked against
independent parity oracles — lmfit and scipy (always) and JAX/optimistix
(when available) — and a subset against NIST StRD's externally certified
datasets, with a regression gate that fails the run if spectrafit is
measurably *slower* or *less accurate* than the baseline on any case. See
[Benchmark engine](contributor-guide/benchmark-engine.md) for
how the gate is computed (`oracles.cli run` / `gate`,
`oracles.models.MODEL_REGISTRY` as the parity oracle), and
[Limitations](limitations.md) for what this verification deliberately does
**not** yet cover — the goal here is an honestly-scoped claim, not a
maximal one. This is the headline differentiator, not an afterthought: a
speed number nobody can independently re-derive is a marketing claim, not
an engineering one.

## :lucide-cpu: A compiled kernel, not a Python dispatch loop

lmfit's `model1 + model2` builds a binary tree of Python objects, evaluated
recursively at Python speed on every solver iteration — the pure-Python
approach's natural shape, and a perfectly reasonable one for smaller
problems or rapid prototyping. spectrafit-core instead compiles a model
graph **once** into a Rust struct and evaluates it as a single
`O(N_nodes × N_x)` loop with no per-iteration Python round-trips — see
[Model Composition — DAG IR](explanation/model-composition-dag.md#why-not-operator-overloading-lmfit-style)
for the direct comparison. This is the single biggest source of the speed
numbers on the [Performance](performance/index.md) page: solving is a Rust
hot loop, not an interpreted one, regardless of which of the ten solver
strategies below is driving it.

## :lucide-braces: Analytical Jacobians, not finite differences by default

The pure-Python approach typically falls back to numerical (finite
difference) Jacobians, since deriving and maintaining analytical ones by
hand for every model is real ongoing work. spectrafit-core's built-in
kernels mostly ship a **hand-derived analytical Jacobian** instead — see
`crates/spectrafit-models/src/gaussian.rs` for a worked example, and the
`Model` trait's doc comment in `crates/spectrafit-models/src/lib.rs` for the
exact forward-difference formula (`h = 1e-7 * |params[i]|.max(1e-7)`) used
on the handful of kernels that don't yet have one. Finite-difference is a
real, working fallback, not a placeholder — it's what makes a brand-new
kernel usable on day one (see
[Adding a Model](how-to/adding-a-model.md#1-implement-the-rust-kernel)) —
but it's the fallback, not the primary path, precisely because it costs
`N_params` extra model evaluations per Jacobian that an analytical formula
doesn't need.

## :lucide-route: Ten solver strategies, picked by structure, not by hand

`FitOptions.solver="auto"` inspects the model graph's *structure* —
separability, tied parameters, active bounds — and routes to the strategy
that structure calls for: Variable Projection when the graph is separable,
Trust-Region-Reflective when bounds are active, plain Levenberg-Marquardt
otherwise. Seven more strategies are available for cases `"auto"` can't
structurally detect: `dogleg` and `newton-cg` for research-grade
trust-region tuning, `geodesic` for sloppy/degenerate multi-peak surfaces,
`global` for genuinely multi-modal objectives, and three `irls` variants
for heavy-tailed outliers. See [Choosing a Solver](how-to/choosing-a-solver.md)
for the full decision guide, with literature references for each method —
these are established numerical-optimization techniques
([Coleman & Li 1996](how-to/choosing-a-solver.md#fn:coleman-li-1996),
[Powell 1970](how-to/choosing-a-solver.md#fn:powell-1970),
[Steihaug 1983](how-to/choosing-a-solver.md#fn:steihaug-1983),
[Transtrum & Sethna 2012](how-to/choosing-a-solver.md#fn:transtrum-sethna-2012)), not
reinvented ones — what's new is having all of them behind one structure-aware
dispatch, in a single compiled core.

## :lucide-layers: Multi-dataset and native N-D fitting, not a hand-rolled loop

Joint fitting across multiple spectra is usually something a pure-Python
project builds by hand per use case — a loop over datasets with manually
shared parameters, and DOF accounting the caller has to get right
themselves. spectrafit-core makes two distinct joint-fitting patterns
native, both with exact degrees-of-freedom accounting: **stacked slices**
(many lower-dimensional datasets sharing a subset of parameters, e.g. a
series of spectra sharing one instrument-broadening width) and **native
N-D** (one model evaluated over a genuinely multi-dimensional coordinate
space, e.g. a 2-D Gaussian map, with dimensionality inferred from the
graph rather than declared separately). See
[Multi-Dataset Joint Fitting](tutorials/gallery/multi_dataset.md) and
[N-Dimensional Fitting](tutorials/gallery/3d_fitting.md) for runnable
examples of each.

## :lucide-scale: Typed all the way down

The model graph, parameters, fit options, and results are Pydantic models on
the Python side and a `serde`-tagged IR on the Rust side, kept in sync by a
compile-time exhaustiveness gate (`spectrafit-builder`'s `E0004` check) and
a schema-parity test (`tests/parity/test_schema_parity.py`) rather than by
convention alone. A new model variant that isn't wired into both sides
fails `cargo test`, not silently at runtime — see
[Parameter Model](explanation/parameter-model.md) and
[Model Reference](reference/models/index.md) for the resulting contract,
and [Adding a Model](how-to/adding-a-model.md) for what the gate actually
catches.
