---
icon: lucide/route
---

# Solver

`spectrafit-solver::problem::LmProblem<'a>` implements
`LeastSquaresProblem<f64, Dyn, Dyn>` from the `levenberg-marquardt` crate. It
borrows (does not own) `&'a CompiledGraph` and `&'a [MeasurementSpec]`, plus
per-iteration scratch state (`node_param_bufs`, `free_to_node_param`,
cached `x_concat`/`y_concat`). This is one of several strategy front-ends
`spectrafit-solver` dispatches to (`lm`/`lm-legacy`/`trf`/`irls`/`global`
(differential evolution)/`varpro`/`geodesic`) — LM is the default.

**Residual:** $r_i = (y_i - f(x_i)) / \sigma_i$

**Jacobian:** $\partial r_i / \partial p_j = -(\partial f / \partial p_j) / \sigma_i$

## Post-fit statistics

The *reported* `chi2` below is a fresh unweighted sum-of-squares — distinct
from the weighted residual `r_i` the solver itself minimizes above — kept
comparable across backends regardless of how each one weights internally.
AIC/BIC are derived from a proper Gaussian-deviance term, not raw `chi2`
directly (an earlier "raw chi2 as deviance" form put spectrafit on a
different scale than the lmfit/jax oracles and was deliberately replaced).
Covariance has two paths depending on whether per-point `sigma` was supplied.

$$
\chi^2 = \sum_i (y_i - f(x_i))^2 \quad \text{(unweighted, not } \sum_i r_i^2\text{)}
$$

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

See [Multi-Dataset & Multi-Dimensional Fitting](../contributor-guide/architecture.md#multi-dataset-multi-dimensional-fitting).
