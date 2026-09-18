---
icon: lucide/sparkles
description: Why spectrafit-core is a new Rust-kernel implementation rather than a Python wrapper — compiled model evaluation, analytical Jacobians, structure-aware solver routing, and a benchmark that verifies its own claims.
tags:
  - Benchmarking
  - Solvers
  - Rust
---

# Why SpectraFit-Core

Most of this site is reference material: what a function does, what a
parameter means. This page is different. It makes the engineering case for
*why* spectrafit-core exists as a new implementation rather than as a
wrapper around an established one.

lmfit and scipy's `curve_fit` represent a mature, widely-used
**pure-Python approach**. They compose models in Python, dispatch in
Python, and leave the math to NumPy. spectrafit-core takes a different,
**compiled-kernel approach** to the same class of problem: it moves
composition and evaluation into a typed Rust core.

Neither approach is wrong. This page is about what the compiled approach
actually buys. Each claim below points at the place in the codebase that
enforces it, so you need not take the page's word for anything.

## At a glance

| | Pure-Python approach (lmfit, `curve_fit`) | spectrafit-core |
|---|---|---|
| Model composition | Python objects, `model1 + model2` | Rust DAG (directed acyclic graph), compiled once |
| Per-iteration evaluation | Python dispatch loop | Single compiled Rust loop |
| Jacobian | Numerical (finite-difference) by default | Hand-derived closed form for all but eleven kernels; those eleven use a central difference |
| Solver selection | Named by the caller | Named by the caller too (`solver="lm"` by default) — the opt-in `solver="auto"` is what routes on graph structure; 10 strategies available |
| Multi-dataset fitting | Hand-rolled per project | Native: stacked-slice and N-D, exact degrees-of-freedom (DOF) accounting |
| Speed/accuracy claims | Accuracy verified in lmfit's own test suite against NIST StRD — the Statistical Reference Datasets of the US National Institute of Standards and Technology | Accuracy *and* speed recomputed against independent oracle backends every run, behind a regression gate (3–7 axes; see below) |

## :lucide-shield-check: A benchmark that verifies itself, not just asserts

The speed and accuracy numbers on the
[Performance](performance/index.md) page aren't self-reported. Every
benchmark case is cross-checked against independent parity oracles, and a
subset is checked further against the externally certified datasets of
NIST StRD.

Oracle coverage is **per-backend, not universal**. Each backend runs only
the cases whose model it can express, and the optional JAX/optimistix
backend runs only when it is installed at all.

The shipped benchmark ladder's 50-repetition run recorded 151 cases in
total. That run is `2026-08-16_run_037`, and its manifest lives at
`manuscript/examples/ladder/rungs/rung_050/manifest.json` — the artefact
published on the public mirror, not the placeholder
[Performance](performance/index.md) page. Of those 151 cases, lmfit (the
baseline) and spectrafit itself covered all 151, the three `scipy-ls-*`
variants covered 147 each, and JAX covered 127. Each run records its own
per-backend coverage in its own artefacts, so you can check these numbers
rather than take them on trust. Never assume an oracle ran everywhere.

Those are the shipped run's counts, not today's. The case catalog keeps
growing. At this page's current commit, `oracles.cases.build_catalog()`
returns **154** cases, 130 of them JAX-eligible, not 151. The derived
headline figures are the geomean speedup, the win counts, and the per-case
$\lvert \Delta r^2 \rvert$. Each is only meaningful against a fresh run
over the current catalog, and producing one means re-running the
benchmark, which is out of scope for this documentation pass. Until that
run ships, read 151 / 147 / 127 as *that shipped artefact's* counts, not
as a statement about the current catalog.

A **regression gate** then judges the run as a whole (`oracles.cli gate`;
the thresholds are the defaults in `python/oracles/cli.py`). This page is
the canonical description of the gate's axis count. That count is not
fixed, so other pages should link here rather than restate a number.

`_gate_evaluate` always emits three axes, then appends up to four more. It
appends each of those four only when its backing evidence actually exists,
so nothing passes by absence. `_gate_self_perf_check` adds `self_perf`
only when a perf baseline is pinned. `_append_bool_axis` adds
`model_selection`, `sigma_calibration` and `speed_inference` one at a
time, each only when the matching evidence — nested-adequacy,
$\sigma$-calibration and speed-inference respectively — is present and not
skipped. A single gate run therefore carries a **minimum of three axes and
a maximum of seven**:

| Axis | Always present? | What it actually measures | Default threshold |
|---|---|---|---|
| `speed` | always | *Aggregate* geometric-mean speedup over the baseline across every case | $\geq 1.0$ |
| `accuracy` | always | Largest $\lvert \Delta r^2 \rvert$ between spectrafit and the baseline on any one case, with the `optfn` category excluded | $\leq 10^{-3}$ |
| `regressions` | always | Cases where *any* supported backend failed to converge — a suite-health count, not a spectrafit-vs-baseline comparison | 0 |
| `self_perf` | only when a perf baseline is pinned | spectrafit's current geomean speedup vs its own pinned self-baseline, as a ratio | ratio floor $1 - \text{perf\_tolerance}$ |
| `model_selection` | only when nested-adequacy evidence is supplied | BIC recovers the true model order | boolean pass |
| `sigma_calibration` | only when calibration evidence is supplied and not skipped | bootstrap coverage of the reported uncertainty | boolean pass |
| `speed_inference` | only when speed-inference evidence is supplied and not skipped | statistical significance of the measured speed advantage | boolean pass |

Read those axes literally, because their scope matters. The speed axis is
an aggregate, so a single case where spectrafit is slower does not fail
the run. The accuracy axis is a tolerance, so a case with
$\lvert \Delta r^2 \rvert = 5 \times 10^{-4}$ passes cleanly. The gate
sets a floor on the run as a whole; it is not a per-case guarantee.

NIST StRD is a **separate** mechanism, not a fourth gate axis. It is
trust-ledger wire W8, and it governs the report's evidence *rung* — how
far the credibility ladder can be climbed — rather than whether the run
passes or fails.

The shipped ladder's deepest run, at 50 repetitions, reached
**credibility rung 5**
(`manuscript/examples/ladder/rungs/rung_050/trust.json`, run
`2026-08-16_run_037`). That run audits all **21 registered claims** in the
claim ledger (`oracles.audit.claims.CLAIM_REGISTRY`). A claim counts as
audited only when its backing verification wire passed
(`oracles.audit.claims.audited_count`). The run carries **19 verification
wires** of its own (`W1`, `W2a`–`W2d`, `W3`–`W11`, `S1`–`S5`); of those,
17 passed, 2 were skipped and 0 failed. The two skips are `W5`
render-fidelity, which only runs in continuous integration (CI), and `S3`
doc-owner-truth.

NIST alone does not unlock rung 5. `_compute_rung`
(`python/oracles/audit/runner.py`) requires **W8 (NIST StRD) *and* W10
($\sigma$-calibration) *and* W11 (speed inference)** to all pass, on top
of the core ladder already clearing rung 4.

[Benchmark engine](contributor-guide/benchmark-engine.md) describes how
the gate is computed (`oracles.cli run` / `gate`, with
`oracles.models.MODEL_REGISTRY` as the parity oracle).
[Limitations](limitations.md) sets out what this verification deliberately
does **not** yet cover, because the goal here is an honestly-scoped claim
rather than a maximal one. This is the headline differentiator, not an
afterthought: a speed number nobody can independently re-derive is a
marketing claim, not an engineering one.

One scope limit on that harness deserves stating plainly, because the
paragraphs above are easy to read as promising more. The rig in
`python/oracles/` is backend-agnostic by construction: a backend is a
class implementing `is_supported`, `build`, `run` and `extract`, and only
one adapter in the whole harness is specific to spectrafit-core. Anyone
publishing a fitting library can therefore, in principle, add a backend
and obtain the same cross-implementation timings, parameter agreement and
NIST comparison.

But no external adopter has done so, and the non-spectroscopic cases in
the suite are synthetic. **Reuse of the harness against another library is
therefore a documented capability rather than a demonstrated one.** Read
it that way until someone outside this project runs it.

## :lucide-cpu: A compiled kernel, not a Python dispatch loop

lmfit's `model1 + model2` builds a binary tree of Python objects, and
every solver iteration walks that tree recursively at Python speed. That
is the pure-Python approach's natural shape, and a perfectly reasonable
one for smaller problems or rapid prototyping.

spectrafit-core instead compiles a model graph **once** into a Rust
struct, then evaluates it as a single `O(N_nodes × N_x)` loop with no
per-iteration Python round-trips. The
[Model Composition — DAG IR](explanation/model-composition-dag.md#why-not-operator-overloading-lmfit-style)
page draws the direct comparison; DAG IR here means the
directed-acyclic-graph intermediate representation that a model compiles
to.

This is the single biggest source of the speed numbers on the
[Performance](performance/index.md) page. Solving runs as a Rust hot loop
rather than an interpreted one, whichever of the ten solver strategies
below is driving it.

## :lucide-braces: Analytical Jacobians, not finite differences by default

The pure-Python approach typically falls back to numerical
(finite-difference) Jacobians, because deriving and maintaining analytical
ones by hand for every model is real ongoing work. spectrafit-core's
built-in kernels instead ship a **hand-derived Jacobian in closed form for
all but eleven kernels** — eleven of the **37** Rust kernels registered in
the `model_manifest!` macro in `crates/spectrafit-types/src/types.rs`.

Two denominators are in play here, and conflating them would overstate the
result. The Python parity oracle (`oracles.models.MODEL_REGISTRY`)
currently registers **35** of those 37 shapes, and
`tests/parity/test_kernel_parity.py` parameterises over that registry.
Kernel parity is therefore proven for 35 of the 37 kernels, not for "all"
of them. For a worked closed-form example, see
`crates/spectrafit-models/src/gaussian.rs`.

The eleven exceptions — `asym_ir`, `breit_wigner`, `harmonic_ir`, `kww`,
`log_normal`, `moffat`, `pearson7`, `split_gaussian`, `split_pearson7`,
`students_t`, `tauc` — each hand-roll a **central**-difference Jacobian in
their own `jacobian` implementation. That costs `2 · N_params` extra model
evaluations per Jacobian. None of the eleven inherits the `Model` trait's
forward-difference default, which `crates/spectrafit-models/src/lib.rs`
documents but no shipped kernel uses.

Finite-difference is a real, working fallback, not a placeholder. It is
what makes a brand-new kernel usable on day one; see
[Adding a Model](how-to/adding-a-model.md#1-implement-the-rust-kernel).
It stays the fallback rather than the primary path for one reason: a
closed-form formula does not need those `2 · N_params` extra evaluations.

## :lucide-route: Ten solver strategies, with opt-in structure-aware routing

By default, **the caller names the solver family**. `FitOptions.solver` is
`"lm"` — Levenberg-Marquardt — unless you say otherwise, and
`Solver::parse` (`crates/spectrafit-solver/src/dispatch.rs`) accepts ten
strings: `lm`, `lm-legacy`, `trf`, `geodesic`, `dogleg`, `newton-cg`,
`global`, `varpro`, `irls[:weight]` and `auto`. Deriving the solver from
the graph is what the **opt-in `"auto"`** does; it is not the default.

When you do ask for `solver="auto"`, it inspects the model graph's
*structure* — separability, tied parameters, active bounds — and routes on
what it finds. A graph that is separable, with no tied parameters and no
bounds on the nonlinear parameters, goes to VarPro (Variable Projection).
Everything else goes to **Trust-Region-Reflective** (TRF), the Coleman–Li
bound-scaled variant of Levenberg-Marquardt.

Under `"auto"` there is no plain-Levenberg-Marquardt branch at all,
because bound scaling is set for `Auto` on every non-VarPro path
(`bound_scaling: solver == Solver::Trf || solver == Solver::Auto`). That
was a deliberate change on 2026-06-03: `"auto"` previously *did* fall
through to plain LM. The ADR that records
the replacement is in `DECISIONS-archive.md`.

The remaining strategies are explicit choices, for cases `"auto"` cannot
detect from graph topology alone. Reach for `dogleg` and `newton-cg` for
research-grade trust-region tuning, `geodesic` for sloppy or degenerate
multi-peak surfaces, `global` for genuinely multi-modal objectives, and
the three `irls` (Iteratively Reweighted Least Squares) weight variants
for heavy-tailed outliers. `"auto"` never selects `global` or `irls`,
because the signal for them lives in the data rather than in the graph.

[Choosing a Solver](how-to/choosing-a-solver.md) carries the full decision
guide, with literature references for each method. These are established
numerical-optimization techniques
([Coleman & Li 1996](how-to/choosing-a-solver.md#fn:coleman-li-1996),
[Powell 1970](how-to/choosing-a-solver.md#fn:powell-1970),
[Steihaug 1983](how-to/choosing-a-solver.md#fn:steihaug-1983),
[Transtrum & Sethna 2012](how-to/choosing-a-solver.md#fn:transtrum-sethna-2012)),
not reinvented ones. What's new is having all of them behind one
structure-aware dispatch, in a single compiled core.

## :lucide-layers: Multi-dataset and native N-D fitting, not a hand-rolled loop

A pure-Python project usually builds joint fitting across multiple spectra
by hand, once per use case: a loop over datasets, parameters shared
manually, and degrees-of-freedom accounting the caller has to get right
themselves.

spectrafit-core makes two distinct joint-fitting patterns native, both
with exact DOF accounting. **Stacked slices** covers many
lower-dimensional datasets that share a subset of parameters, such as a
series of spectra sharing one instrument-broadening width. **Native N-D**
covers one model evaluated over a genuinely multi-dimensional coordinate
space, such as a 2-D Gaussian map; there the graph itself fixes the
dimensionality, which you never declare separately.

For runnable examples of each, see
[Multi-Dataset Joint Fitting](tutorials/gallery/multi_dataset.md) and
[N-Dimensional Fitting](tutorials/gallery/3d_fitting.md).

## :lucide-scale: Typed all the way down

The model graph, parameters, fit options and results are Pydantic models
on the Python side, and a `serde`-tagged IR on the Rust side. Two
mechanisms keep the two sides in sync, rather than convention alone: a
compile-time exhaustiveness gate (`spectrafit-builder`'s `E0004` check)
and a schema-parity test (`tests/parity/test_schema_parity.py`).

A new model variant that isn't wired into both sides fails `cargo test`.
It does not fail silently at runtime. See
[Parameter Model](explanation/parameter-model.md) and
[Model Reference](reference/models/index.md) for the resulting contract,
and [Adding a Model](how-to/adding-a-model.md) for what the gate actually
catches.

## Next steps

- **Get it running** — [Installation](getting-started/installation.md) covers
  the `uv`/`maturin` build and the test-suite check that confirms it worked.
- **See the compiled kernel fit real data** — [Quickstart](getting-started/quickstart.md)
  fits a single Gaussian peak in a few lines against the public API.
- **Go deeper on solver routing** — [Solver selection](explanation/solver-selection.md)
  covers what `solver="auto"` actually inspects on the graph before routing to
  VarPro or the LM family.
