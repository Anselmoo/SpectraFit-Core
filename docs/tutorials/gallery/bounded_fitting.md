---
icon: lucide/square
description: A likely-active physical bound (amplitude >= 0) where trf adds Coleman-Li step scaling near the boundary that plain lm lacks, though both remain bound-compliant here.
---

# Bounded Fitting with an Active-Bounds Solver

!!! warning "Synthetic example"
    The fixture below is a single seeded, deliberately noise-floor-adjacent
    peak, chosen to make an unconstrained fit plausibly land at a negative
    amplitude — not a sweep that proves this happens generally, at any noise
    level or amplitude.

## Context

**When to use this pattern.** A physical bound — amplitude ≥ 0, a mixing
fraction ∈ [0, 1] — is likely to be *active*, not just a loose safety floor
that never actually binds. [Choosing a
Solver](../../how-to/choosing-a-solver.md) recommends `"trf"` (Trust Region
Reflective) whenever "bounds are frequently active": it adds Coleman–Li
bound scaling that shrinks trust-region steps as a parameter approaches an
active bound. Every LM-family solver in this codebase (including plain
`"lm"`) already shares a reflective-bounds projection, so `"lm"` alone never
*violates* `[min, max]` — `"trf"` changes *how* the optimizer approaches the
wall, not whether the final result respects it.

**Distinct from `varpro_vs_lm.md`**: that comparison is on an *unconstrained*
separable problem. This is solver choice under *active* bound constraints.

## Quick example

```python
--8<-- "bounded_fitting.py:data"
```

`AMPLITUDE_TRUE = 0.06` against a noise standard deviation of `0.15` sits
close enough to the noise floor that an unconstrained fit of this data
plausibly estimates a negative amplitude — physically meaningless for a
peak. `build_graph` accepts the bound to apply so the same shape can build
both the unconstrained reference graph and the bounded one.

```python
--8<-- "bounded_fitting.py:build_graph"
```

Three fits against the identical data: the unconstrained reference (to see
what the bound is actually ruling out), then the bounded problem solved by
both `"lm"` and `"trf"`.

```python
--8<-- "bounded_fitting.py:fit_all"
```

The unconstrained amplitude going negative is the concrete evidence for why
the bound matters; both bounded solvers are then checked against
`min=0` directly rather than trusted by eye.

```python
--8<-- "bounded_fitting.py:compare"
```

![Small near-zero peak with an active amplitude >= 0 bound](_static/bounded_fitting.png)

## What just happened

1. **Data creation** — a small Gaussian peak (`amplitude=0.06`) against
   comparatively large noise (`σ=0.15`), synthesized so an unconstrained fit
   plausibly lands negative.

2. **Three fits, one graph shape** — the unconstrained reference
   (`amplitude_min=-inf`) is fit first, then the bounded problem
   (`amplitude_min=0.0`) is fit with both `"lm"` and `"trf"`.

3. **The bound is the point** — the unconstrained fit's negative amplitude
   is exactly what `min=0` rules out; both bounded solvers are asserted to
   land inside `[0, inf)`.

4. **On this small problem, `"lm"` and `"trf"` converge identically** — same
   `n_iter`, same final amplitude, measured directly rather than assumed.
   This codebase's reflective-bounds projection is shared by every LM-family
   solver; Coleman–Li scaling changes the per-iteration step shape near an
   active bound, which matters more on problems where a bound stays
   persistently and severely active across many iterations than it does
   here. This script reports what is actually measured on this fixture, not
   a general performance claim.

## See also

- **Related examples**: [`varpro_vs_lm.md`](varpro_vs_lm.md) (solver
  comparison on an unconstrained problem), [`robust_fitting.md`](robust_fitting.md)
  (a different solver-choice axis: outlier robustness, not bounds).
- **Reference**: [Choosing a Solver](../../how-to/choosing-a-solver.md).
- **API docs**: `FitOptions`, `Parameter`.
