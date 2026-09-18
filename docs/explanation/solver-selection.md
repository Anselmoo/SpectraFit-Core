---
icon: lucide/route
description: How spectrafit-solver's LmProblem front-end minimizes weighted residuals, plus the post-fit chi2/DOF/AIC/BIC/covariance statistics it reports.
tags:
  - Uncertainty
  - Solvers
  - Rust
---

# Solver

`LmProblem<'a>` (`crates/spectrafit-solver/src/lm_problem.rs` — a crate-private
module, so this type is not importable from outside `spectrafit-solver`)
implements `LeastSquaresProblem<f64, Dyn, Dyn>` from the `levenberg-marquardt`
crate. It borrows (does not own) `&'a CompiledGraph` and `&'a
[MeasurementSpec]`, plus
per-iteration scratch state (`node_param_bufs`, `free_to_node_param`,
cached `x_concat`/`y_concat`). This is one of several strategy front-ends
`spectrafit-solver` dispatches to — ten in all (`Solver` in
`crates/spectrafit-solver/src/dispatch.rs`): `lm`/`lm-legacy`/`trf`/`geodesic`/
`dogleg`/`newton-cg`/`irls`/`global` (differential evolution)/`varpro`/`auto`
— LM is the default and `auto` picks VarPro vs. the LM
family from the graph shape.

This page describes how the solver front-end works. For *which* solver to reach
for on a given model or dataset, see
[Choosing a Solver](../how-to/choosing-a-solver.md).

**Residual:** $r_i = (y_i - f(x_i)) / \sigma_i$

**Jacobian:** $\partial r_i / \partial p_j = -(\partial f / \partial p_j) / \sigma_i$

## Post-fit statistics

!!! note "chi2 vs. the weighted residual the solver minimizes"

    The *reported* `chi2` below is a fresh unweighted sum-of-squares — distinct
    from the weighted residual `r_i` the solver itself minimizes above — kept
    comparable across backends regardless of how each one weights internally.
    AIC / BIC are derived from a proper Gaussian-deviance term, not raw `chi2`
    directly (an earlier "raw chi2 as deviance" form put spectrafit on a
    different scale than the lmfit/jax oracles and was deliberately replaced).
    Covariance has two paths depending on whether per-point `sigma` was supplied.

    `chi2_reduced` below inherits the same unweighted `chi2` and is **not**
    divided by the per-point measurement variance `sigma_i^2`, even when
    `sigma` was supplied and used to weight the fit — see
    [Sigma-Weighted Fitting](../tutorials/gallery/weighted_fitting.md). The textbook
    reduced-chi-squared statistic gets its "close to 1 indicates a good fit"
    reading only from that division; without it, `chi2_reduced` here is a
    cross-backend-comparable mean squared residual in the data's own units, not
    a test of the fit against known measurement noise.

$$
\chi^2 = \sum_i (y_i - f(x_i))^2 \quad \text{(unweighted, not } \sum_i r_i^2\text{)}
$$

**Degrees of freedom (DOF)** is the point count less the free-parameter count:

$$
\mathrm{DOF} = N_{\text{points}} - N_{\text{free}}
\qquad
\chi^2_{\text{reduced}} = \chi^2 / \mathrm{DOF}
$$

$$
\text{neg2\_log\_l} = N_{\text{points}} \ln(\chi^2 / N_{\text{points}}) \quad \text{(Gaussian deviance term)}
$$

$$
\mathrm{AIC} = \text{neg2\_log\_l} + 2 N_{\text{free}}
\qquad
\mathrm{BIC} = \text{neg2\_log\_l} + N_{\text{free}} \ln(N_{\text{points}})
$$

$$
R^2 = 1 - \chi^2 \Big/ \sum_i (y_i - \bar{y})^2
$$

$$
\mathrm{cov}\ (\sigma \text{ provided}) = (J_w^T J_w)^{-1}, \quad J_w[i,:] = J[i,:] / \sigma_i
$$

$$
\mathrm{cov}\ (\text{no } \sigma \text{ supplied}) = (J^T J)^{-1} \cdot (\chi^2 / \mathrm{DOF}) \quad \text{(scale-from-residuals estimate)}
$$

$$
\mathrm{stderr}[j] = \sqrt{\mathrm{cov}[j,j]}
$$

For multi-dataset global fits: $\mathrm{DOF} = \sum_d N_d - N_{\text{free\_shared}}$.

!!! warning "What these statistics assume, and what they are not"

    Every formula above is inference about the fit only under the assumption
    that the residuals are independent and normally distributed around the
    model with the stated (or estimated) `sigma` — correlated baseline noise,
    non-Gaussian detector statistics, or a misspecified model all break that
    assumption silently; nothing here checks it for you.

    **AIC/BIC compare models fit to the *same* data** (same `N_points`, same
    weighting) among *plausible* candidates — they are not a general "lower is
    always better" score, and not a substitute for checking whether a
    component belongs in the model at all. This library's own case study
    (`manuscript/examples/fecl4/fig_fecl4_case_study.py`) found the trap
    directly: a spectral shoulder seeded from a guess rather than the
    spectroscopy was *rejected* by BIC, then accepted by the same criterion
    once given a spectroscopically-motivated seed and the same data — an
    information criterion scores the optimum a solver actually reached, not
    the model in the abstract, so a bad seed or a solver stuck in a local
    minimum can make a real component look statistically unnecessary. Treat
    AIC/BIC here as an ablation check on a component list you already trust
    from the physics, not as an automatic peak-count selector.

    `stderr`/`cov` can be `None` rather than a number when the Jacobian is
    empty, rank-deficient, or otherwise ill-conditioned (typically
    overlapping/redundant peaks, or a parameter that barely moves the model)
    — see [Confidence Intervals](../tutorials/gallery/confidence_intervals.md)
    for what to check before building a confidence interval (CI) from it.

See [Multi-Dataset & Multi-Dimensional Fitting](../contributor-guide/architecture.md#multi-dataset-multi-dimensional-fitting).

## Next steps

- **See these statistics validated against certified values** — [NIST StRD Validation](nist-validation.md)
  checks the LM solver's output against NIST's certified reference values.
- **Look up the Python-facing result fields** — [Python: core API](../reference/python/core-api.md#result-types)
  documents `FitResult`, the object these formulas actually populate.
