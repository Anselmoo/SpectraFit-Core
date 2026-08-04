---
icon: lucide/scale
---

# VarPro vs. Levenberg-Marquardt

## Context

**When to use this pattern.** Your model graph is *separable* — the only
nonlinear parameters are shape parameters like `center`/`sigma`, and each
node's `amplitude` is purely linear, with no tied parameters or bound
constraints on the nonlinear side. This is exactly the shape
`FitOptions(solver="auto")` itself detects and routes to `"varpro"` (see
[Choosing a Solver](../../how-to/choosing-a-solver.md)). This example fits
the same two-peak graph with both `"lm"` and `"varpro"` to show they land on
the identical optimum, from a smaller nonlinear-only parameter space.

## Quick example

```python
--8<-- "varpro_vs_lm.py:data"
```

```python
--8<-- "varpro_vs_lm.py:build_graph"
```

```python
--8<-- "varpro_vs_lm.py:run_solvers"
```

```python
--8<-- "varpro_vs_lm.py:verify_agreement"
```

![Two-peak fit compared between the VarPro and Levenberg-Marquardt solvers](_static/varpro_vs_lm.png)

## What just happened

1. **Data creation** — two overlapping Gaussian peaks, no background node.
   Each peak's only linear parameter is its `amplitude`; `center` and `sigma`
   are the nonlinear shape parameters VarPro's outer optimizer works over.

2. **Two solver runs, same graph shape** — `run_solvers()` calls `fit()` once
   with `FitOptions(solver="lm")` and once with `FitOptions(solver="varpro")`,
   on a fresh `FitGraph` (from `build_graph()`) each time. `"lm"` optimizes
   all six free parameters together (2 peaks × 3 params); `"varpro"`
   optimizes only the four nonlinear ones (`center`, `sigma` per peak) and
   solves the two amplitudes analytically at every step.

3. **Same optimum, different path** — `verify_agreement()` asserts `chi2`
   matches between solvers to `1e-4`, and every fitted parameter agrees to
   within `1e-7`–`1e-9` in practice. This is the actual guaranteed property:
   VarPro is not a different model, just a different (smaller) parameter
   space to search.

4. **Measured wall-clock time, honestly scoped** — `run_solvers()` reports the
   median of 9 timed reps per solver (after an untimed warm-up call) and
   plots both numbers without declaring a "winner". Whether VarPro or LM is
   faster in absolute terms depends on problem size, peak count, and
   hardware — on this small two-peak demo the two are comparable. The
   project's own aggregate speed comparison across its full benchmark case
   catalog lives on the [Performance](../../performance/index.md) page, not
   in this gallery script.

## See also

- **Related examples**: [`shared_params.md`](shared_params.md) (tied parameters — not supported
  under `"varpro"`), [`confidence_intervals.md`](confidence_intervals.md) (uncertainty reporting).
- **Reference**: [Choosing a Solver](../../how-to/choosing-a-solver.md),
  [Rust ↔ Python binding audit](../../reference/rust/binding-audit.md#solver-dispatch-cratesspectrafit-solversrcdispatchrs).
- **API docs**: `FitOptions`, `FitGraph`, `ModelNodeSpec`, `fit`.
