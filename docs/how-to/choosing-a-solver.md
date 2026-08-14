---
icon: lucide/git-compare
description: A decision guide for FitOptions.solver — which of auto, lm, trf, VarPro, irls, global, and geodesic to pick based on what your data and model look like.
---

# Choosing a Solver

`FitOptions.solver` controls which numerical strategy `fit()` uses. This
guide is decision-oriented: start from what your data/model looks like, and
pick the solver that matches.

## Just want it to work? Use `"auto"`

```python
from spectrafit_core import FitOptions

options = FitOptions(solver="auto")
```

`"auto"` picks `"varpro"` when the model graph is separable (amplitudes are
the only linear parameters, no tied parameters, no bound constraints on the
nonlinear parameters) — VarPro's preconditions — and otherwise falls back to
`"trf"` (Coleman–Li bound-scaled Levenberg-Marquardt), which the project's
solver bake-off found to be the fastest, most accurate LM-family strategy
across problem classes. `"auto"` is a good default for a first pass; the
sections below explain when to override it deliberately.

## Decision guide

**Your fit has bounds that are frequently active** (e.g. widths constrained
to be positive, amplitudes constrained non-negative) →
use **`"trf"`** (Trust Region Reflective). Plain `"lm"` doesn't scale steps
as a parameter approaches an active bound; `"trf"` does, via Coleman–Li
bound scaling[^coleman-li-1996].

**Your model is well-conditioned and unimodal, and you don't need bound
constraints to hold tightly** → use **`"lm"`** (Levenberg-Marquardt, the
default). It runs on the faer-native trust-region core (pure-Rust SIMD, no
BLAS) and is regime-adaptive: normal equations for tall-skinny problems, SVD
for many parameters. It's the fastest general-purpose choice when bounds
aren't the bottleneck.

**Your spectrum has overlapping multi-peak structure and the fit is slow
to converge or stalls on a sloppy/degenerate surface** → use
**`"geodesic"`**. Levenberg-Marquardt with geodesic acceleration[^transtrum-sethna-2012]
adds a second-order correction
that speeds convergence on exactly this kind of surface.

**Your model is only mildly nonlinear and you want something robust and
cheap** → use **`"dogleg"`** (Powell's dogleg trust-region method[^powell-1970]).
It interpolates between the Gauss-Newton and
steepest-descent steps within an explicit trust radius, at the cost of one
Cholesky factorization per iteration — a solid, inexpensive alternative to
`"lm"`.

**Your problem has many parameters or many residuals, or is
ill-conditioned enough that forming `JᵀJ` is itself a problem** → use
**`"newton-cg"`** (aliases `"steihaug"`, `"newton_cg"`). This matrix-free
Newton-CG (Steihaug-Toint truncated conjugate gradients[^steihaug-1983]
[^toint-1981]) method never
forms `JᵀJ`, so its per-iteration cost scales with the residual count
rather than the squared parameter count — the right choice for large-scale
fits.

**Your model is separable — the only nonlinear parameters are shape
parameters like `center`/`sigma`, and amplitudes are purely linear, with no
tied parameters or bound constraints on the nonlinear side** → use
**`"varpro"`** (Variable Projection). It solves the linear amplitude
coefficients analytically at each step, which is the fastest option when
its preconditions hold. If they don't (bounds, ties, non-separable terms),
fall back to the LM family above instead of forcing VarPro.

**Your initial guesses are poor, or the objective is genuinely
multi-modal** (e.g. Ackley/Rastrigin-shaped landscapes, or you simply
don't trust your starting parameters) → use **`"global"`** (Differential
Evolution + LM refinement). It explores the full parameter space with DE
before refining locally with LM. This is slower than any local solver
above — reach for it only when a local method would plausibly land in the
wrong basin.

**Your data has outliers** → use one of the IRLS variants instead of
tightening bounds or hand-filtering points:

- **`"irls"`** — Iteratively Re-weighted Least Squares with Huber weights;
  good for mild contamination.
- **`"irls:bisquare"`** — Tukey bisquare weights; recommended once more than
  roughly 5–10% of points are corrupted.
- **`"irls:cauchy"`** — Cauchy weights; for very heavy-tailed noise or
  extreme outliers.

**You need a regression/parity cross-check** → use **`"lm-legacy"`**, the
previous nalgebra-based Levenberg-Marquardt implementation. It's slower
than `"lm"` and exists specifically so results can be compared against a
known-independent implementation — don't use it as your primary solver.

!!! warning "`"auto"`'s limits"

    `"auto"`'s routing is purely structural (separability, ties, bounds) — it
    never inspects your data to detect multi-modality or outlier contamination.
    If your data calls for `"global"` or an `"irls"` variant, select it
    explicitly; `"auto"` will not do it for you.

## Tuning trust-region behavior

For `"dogleg"` and `"newton-cg"`, three additional `FitOptions` fields tune
the trust-region mechanics directly. Each is a power-user knob for
research/debugging on ill-conditioned problems — leave all three `None`
unless you have a specific reason to override the library defaults.

### `delta0` — initial trust-region radius

`None` (the default) derives the starting radius from the initial
scaled-gradient norm, which tracks the problem's own scale instead of an
arbitrary constant. Set this explicitly only if you already know a good
starting radius for your problem (e.g. from a prior fit of similar data)
and want to skip the derivation.

### `max_delta` — hard upper bound on the radius

Default `1e3`. The trust radius never grows past this value, no matter how
well steps are being accepted. Lower it if early iterations are taking
wildly oversized, wasted steps on a well-behaved problem; raise it only if
you've confirmed the default is truncating radius growth on a problem that
would otherwise converge faster.

### `eta` — step-acceptance threshold

Default `1e-4`. A proposed step is accepted when the ratio of actual to
predicted cost reduction exceeds `eta`. Lower values accept smaller
improvements faster but less robustly (more accepted steps that barely
help); higher values are stricter and more conservative.

!!! tip "When to touch these at all"

    Almost never. They exist for two situations: (1) diagnosing why a fit on a
    genuinely ill-conditioned or sloppy problem converges slowly or stalls, and
    (2) matching a specific published trust-region configuration for a
    reproducibility comparison. Changing them on a well-conditioned problem is
    unlikely to help and can mask a modeling issue that a solver switch (see the
    [decision guide](#decision-guide) above) would actually fix.

[^coleman-li-1996]: Coleman, T.F. & Li, Y. (1996). "An interior trust region approach for
    nonlinear minimization subject to bounds." *SIAM Journal on Optimization*,
    6(2), 418–445.
[^powell-1970]: Powell, M.J.D. (1970). "A new algorithm for unconstrained optimization."
    In *Nonlinear Programming* (Rosen, Mangasarian, Ritter, eds.), Academic
    Press, 31–66.
[^steihaug-1983]: Steihaug, T. (1983). "The conjugate gradient method and trust regions in
    large scale optimization." *SIAM Journal on Numerical Analysis*, 20(3),
    626–637.
[^toint-1981]: Toint, Ph. L. (1981). "Towards an efficient sparsity exploiting Newton
    method for minimization." In *Sparse Matrices and Their Uses* (Duff, ed.),
    Academic Press, 57–88.
[^transtrum-sethna-2012]: Transtrum, M.K. & Sethna, J.P. (2012). "Geodesic acceleration and the
    small-curvature approximation for nonlinear least squares."
    [arXiv:1207.4999](https://arxiv.org/abs/1207.4999).
