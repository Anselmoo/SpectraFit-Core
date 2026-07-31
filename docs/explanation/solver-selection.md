# Solver

`spectrafit-solver::problem::LmProblem<'a>` implements
`LeastSquaresProblem<f64, Dyn, Dyn>` from the `levenberg-marquardt` crate. It
borrows (does not own) `&'a CompiledGraph` and `&'a [MeasurementSpec]`, plus
per-iteration scratch state (`node_param_bufs`, `free_to_node_param`,
cached `x_concat`/`y_concat`). This is one of several strategy front-ends
`spectrafit-solver` dispatches to (`lm`/`lm-legacy`/`trf`/`irls`/`global`
(differential evolution)/`varpro`/`geodesic`) — LM is the default.

Residual:   `r_i = (y_i - f(x_i)) / sigma_i`
Jacobian:   `dr_i/dp_j = -(df/dp_j) / sigma_i`

## Post-fit statistics

The *reported* `chi2` below is a fresh unweighted sum-of-squares — distinct
from the weighted residual `r_i` the solver itself minimizes above — kept
comparable across backends regardless of how each one weights internally.
AIC/BIC are derived from a proper Gaussian-deviance term, not raw `chi2`
directly (an earlier "raw chi2 as deviance" form put spectrafit on a
different scale than the lmfit/jax oracles and was deliberately replaced).
Covariance has two paths depending on whether per-point `sigma` was supplied.

```
chi2          = sum((y_i - f(x_i))^2)                 # unweighted, NOT sum(r_i^2)
DOF           = N_points - N_free
reduced_chi2  = chi2 / DOF
neg2_log_l    = N_points * ln(chi2 / N_points)         # Gaussian deviance term
AIC           = neg2_log_l + 2 * N_free
BIC           = neg2_log_l + N_free * ln(N_points)
r_squared     = 1 - chi2 / sum((y_i - y_mean)^2)

cov (sigma provided)     = (J_w^T J_w)^{-1}            # J_w[i,:] = J[i,:] / sigma_i
cov (no sigma supplied)  = (J^T J)^{-1} * (chi2 / DOF) # scale-from-residuals estimate
stderr[j]     = sqrt(cov[j,j])
```

For multi-dataset global fits: `DOF = sum_d(N_d) - N_free_shared`.

See **Multi-Dataset & Multi-Dimensional Fitting** below.
