---
icon: lucide/compass
description: A deliberately bad initial guess where the global solver explores broadly before a local solver would just get stuck.
---

# Escaping Local Minima with the Global Solver

!!! warning "Synthetic example"
    The fixture below is a single seeded, deliberately bad-start two-peak
    problem, chosen to demonstrate the mechanism — not a sweep proving
    `"global"` always escapes a bad local optimum, at any problem size or
    starting-guess distance.

## Context

**When to use this pattern.** Initial guesses are poor, or the objective is
genuinely multi-modal — two overlapping peaks with ambiguous or swapped
starting positions. `"global"` (Differential Evolution + LM refinement, per
`FitOptions.solver`'s own docstring) explores the full parameter space
before refining locally, where a local solver like `"lm"` would just
converge — cleanly, with `success=True` — to the wrong answer.

**Distinct from everything else in the gallery**: `solver="global"` does not
appear in any other gallery script (confirmed by grep before writing this
one). It is real and dogfooded internally against synthetic
optimization-landscape test functions in the Rust solver's own test suite,
but this is its first demonstration on a spectroscopy-shaped fit.

## Quick example

```python
--8<-- "global_optimizer.py:data"
```

Two well-separated true peaks, but the graph below seeds both nodes'
`center` at the same wrong location — squarely between the two true peaks,
with no gradient information pointing a local solver toward the correct
split.

```python
--8<-- "global_optimizer.py:build_graph"
```

The same bad-start graph is fit by both solvers, timed — `"global"`'s
differential-evolution search is meaningfully slower per call than `"lm"`'s
single local descent.

```python
--8<-- "global_optimizer.py:run_solvers"
```

`success=True` alone can't distinguish "converged to the right answer" from
"converged, confidently, to the wrong one" — `chi2`/`r_squared` against the
data is what actually does.

```python
--8<-- "global_optimizer.py:compare"
```

![Bad initial guess: lm's wrong local optimum vs. global's correct fit](_static/global_optimizer.png)

## What just happened

1. **Data creation** — two well-separated Gaussian peaks at `center=-3.0`
   and `center=3.0`.

2. **A deliberately bad start** — both graph nodes' `center` initial guesses
   are seeded at `0.0`, the same wrong location.

3. **`"lm"` converges to a wrong local optimum** — `success=True`, but a
   single broad blob straddling the gap between the true peaks
   (`r_squared` well below the `"global"` run's, asserted numerically).

4. **`"global"` finds the true two-peak solution** — differential evolution
   explores broadly first (`n_de_generations` reports how many generations
   that took) before LM refines locally, landing on the correct split.

5. **Measured, not general, timing** — `"global"` took meaningfully longer
   wall-clock time than `"lm"` on this one small demo problem; the gap's
   exact size depends on problem size and hardware, not asserted as a fixed
   ratio.

## See also

- **Related examples**: [`robust_fitting.md`](robust_fitting.md) (outlier
  robustness, a different solver-choice axis), [`bounded_fitting.md`](bounded_fitting.md)
  (active bounds, a third distinct axis).
- **Reference**: [Choosing a Solver](../../how-to/choosing-a-solver.md#decision-guide).
- **API docs**: `FitOptions`, `FitResult.n_de_generations`.
