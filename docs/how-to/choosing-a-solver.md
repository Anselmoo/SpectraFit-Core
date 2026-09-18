---
icon: lucide/git-compare
description: A decision guide for FitOptions.solver — which of auto, lm, trf, VarPro, irls, global, and geodesic to pick based on what your data and model look like.
tags:
  - VarPro
  - Solvers
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
`"trf"` (Coleman–Li bound-scaled Levenberg-Marquardt).

That fallback is a recorded decision rather than a guess, but its evidence is
narrower than "across problem classes" would suggest, so take it with the
caveat its own record carries. The 2026-06-03 ADR in `DECISIONS-archive.md`
documents a one-off comparison of all nine strategies over **one representative
case per scenario family, each the smallest by point count**; TRF came out the
fastest LM-family strategy at top accuracy in roughly **seven of nine** problem
classes. The ADR states the limit explicitly: *"the TRF-over-VarPro speed result
may invert for very large separable problems"* — which is exactly why VarPro
routing is retained for the fully-unconstrained separable case. The comparison's
script and report are not committed to this repository; the ADR is the only
surviving record, so treat it as a documented one-off, not a reproducible
benchmark.

`"auto"` is a good default for a first pass; the sections below explain when to
override it deliberately.

## Decision guide

**Your fit has bounds that are frequently active** (e.g. widths constrained
to be positive, amplitudes constrained non-negative) →
use **`"trf"`** (Trust Region Reflective). Plain `"lm"` doesn't scale steps
as a parameter approaches an active bound; `"trf"` does, via Coleman–Li
bound scaling[^coleman-li-1996].

**Your model is well-conditioned and unimodal, and you don't need bound
constraints to hold tightly** → use **`"lm"`** (Levenberg-Marquardt[^levenberg-1944][^marquardt-1963], the
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
`"lm"`. Avoid it on large problems or ones with many active bounds: the
Cholesky factorization is still an explicit `JᵀJ` formation
(`O(N_params^2)` to build, `O(N_params^3)` to factor), and dogleg's
interpolated step has no bound-reflection logic of its own the way `"trf"`
does — `"newton-cg"` or `"trf"` scale better on the first count, `"trf"` is
the better fit on the second.

**Your problem has many parameters or many residuals, or is
ill-conditioned enough that forming `JᵀJ` is itself a problem** → use
**`"newton-cg"`** (aliases `"steihaug"`, `"newton_cg"`). This matrix-free
Newton-CG (Steihaug-Toint truncated conjugate gradients[^steihaug-1983]
[^toint-1981]) method never forms `JᵀJ` explicitly, so each iteration costs
`O(N_residuals * N_params)` for a handful of Jacobian-vector products rather
than `O(N_params^2)` to build the normal equations plus `O(N_params^3)` to
factor them — the win is dodging that construction and factorization cost at
large `N_params`, not independence from it: a matrix-vector product is still
linear in both dimensions. On a small, well-conditioned problem the CG inner
loop is pure overhead against `"lm"`/`"dogleg"`'s direct solve — reach for
this only once `N_params` is large enough that forming `JᵀJ` is the actual
bottleneck.

**Your model is separable — the only nonlinear parameters are shape
parameters like `center`/`sigma`, and amplitudes are purely linear, with no
tied parameters or bound constraints on the nonlinear side** → use
**`"varpro"`** (Variable Projection[^golub-pereyra-1973]). It solves the linear amplitude
coefficients analytically at each step, which is the fastest option when
its preconditions hold. This implementation computes the projected
Jacobian via the Kaufman (1975) approximation[^kaufman-1975] rather than
full Golub-Pereyra, following the algorithm in O'Leary & Rust
(2013)[^oleary-rust-2013] that the underlying `varpro` crate implements.
For a broader survey of the method and its applications, see Golub &
Pereyra (2003)[^golub-pereyra-2003]. If they don't (bounds, ties,
non-separable terms), fall back to the LM family above instead of forcing
VarPro.

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

Must be in `[0, 0.25)`. The trust-region radius only shrinks when that ratio
is below `0.25`, so an `eta` at or above `0.25` would open a band in which a
step is rejected without shrinking the radius — the solver could then spin
at an unchanged radius until it exhausts its evaluation budget instead of
failing cleanly. `eta >= 0.25` is rejected with an error on both the Python
and JSON/Rust entry points.

!!! tip "When to touch these at all"

    Almost never. They exist for two situations: (1) diagnosing why a fit on a
    genuinely ill-conditioned or sloppy problem converges slowly or stalls, and
    (2) matching a specific published trust-region configuration for a
    reproducibility comparison. Changing them on a well-conditioned problem is
    unlikely to help and can mask a modeling issue that a solver switch (see the
    [decision guide](#decision-guide) above) would actually fix.

## Next steps

- **See two solvers on the same data** — [VarPro vs. Levenberg-Marquardt](../tutorials/gallery/varpro_vs_lm.md)
  fits the same problem both ways so you can compare the numbers `"auto"`'s
  routing would only show you one side of.
- **Escaping local minima** — [Escaping local minima with the global solver](../tutorials/gallery/global_optimizer.md)
  walks the `"global"` differential-evolution strategy mentioned above in a
  worked example.
- **Understand the statistics a solver's output carries** — [Solver](../explanation/solver-selection.md)
  covers what `stderr`/`cov` mean and when they come back `None`.

[^coleman-li-1996]: Coleman, T.F. & Li, Y. (1996). "An interior trust region approach for
    nonlinear minimization subject to bounds." *SIAM Journal on Optimization*,
    6(2), 418–445. [10.1137/0806023](https://doi.org/10.1137/0806023).
[^golub-pereyra-1973]: Golub, G. H. & Pereyra, V. (1973). "The Differentiation of
    Pseudo-Inverses and Nonlinear Least Squares Problems Whose Variables
    Separate." *SIAM Journal on Numerical Analysis* 10(2), 413–432.
    [10.1137/0710036](https://doi.org/10.1137/0710036).
[^golub-pereyra-2003]: Golub, G. & Pereyra, V. (2003). "Separable nonlinear least squares: the
    variable projection method and its applications." *Inverse Problems*
    19(2), R1–R26. [10.1088/0266-5611/19/2/201](https://doi.org/10.1088/0266-5611/19/2/201).
[^kaufman-1975]: Kaufman, L. (1975). "A variable projection method for solving separable
    nonlinear least squares problems." *BIT* 15(1), 49–57.
    [10.1007/bf01932995](https://doi.org/10.1007/bf01932995).
[^levenberg-1944]: Levenberg, K. (1944). "A method for the solution of certain non-linear
    problems in least squares." *Quarterly of Applied Mathematics* 2(2),
    164–168. [10.1090/qam/10666](https://doi.org/10.1090/qam/10666).
[^marquardt-1963]: Marquardt, D. W. (1963). "An Algorithm for Least-Squares Estimation of
    Nonlinear Parameters." *Journal of the Society for Industrial and
    Applied Mathematics* 11(2), 431–441.
    [10.1137/0111030](https://doi.org/10.1137/0111030).
[^oleary-rust-2013]: O'Leary, D. P. & Rust, B. W. (2013). "Variable projection for nonlinear
    least squares problems." *Computational Optimization and Applications*
    54(3), 579–593. [10.1007/s10589-012-9492-9](https://doi.org/10.1007/s10589-012-9492-9).
[^powell-1970]: Powell, M.J.D. (1970). "A new algorithm for unconstrained optimization."
    In *Nonlinear Programming* (Rosen, Mangasarian, Ritter, eds.), Academic
    Press, 31–66.
[^steihaug-1983]: Steihaug, T. (1983). "The conjugate gradient method and trust regions in
    large scale optimization." *SIAM Journal on Numerical Analysis*, 20(3),
    626–637. [10.1137/0720042](https://doi.org/10.1137/0720042).
[^toint-1981]: Toint, Ph. L. (1981). "Towards an efficient sparsity exploiting Newton
    method for minimization." In *Sparse Matrices and Their Uses* (Duff, ed.),
    Academic Press, 57–88.
[^transtrum-sethna-2012]: Transtrum, M.K. & Sethna, J.P. (2012). "Geodesic acceleration and the
    small-curvature approximation for nonlinear least squares."
    [arXiv:1207.4999](https://arxiv.org/abs/1207.4999).
    [10.48550/arXiv.1207.4999](https://doi.org/10.48550/arXiv.1207.4999).
