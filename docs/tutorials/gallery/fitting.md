---
icon: lucide/chart-line
---

# Single-Dataset Fitting

## Context

**When to use this pattern.** You have a single measurement (x, y data) and want to fit it with one or more peak models. This is the simplest spectroscopy workflow: create a `FitGraph` with one or more peak nodes, pass your measured data, and extract the fitted parameters. The result includes the fitted curve, goodness-of-fit metrics (R², χ²), and uncertainty estimates.

## Quick example

```python
--8<-- "fitting.py:data"
```

```python
--8<-- "fitting.py:build_graph"
```

```python
--8<-- "fitting.py:fit_execution"
```

```python
--8<-- "fitting.py:result_inspection"
```

![Single-dataset Gaussian fit with residuals subplot](_static/fitting.png)

## What just happened

1. **Data creation** — we synthesized x, y values (100 points) with a 2.0-amplitude Gaussian centered at 0.5, a 0.1 constant background, and Gaussian noise.

2. **Graph definition** — we built a `FitGraph` with two nodes:
    - `peak`: a Gaussian with initial guesses (amplitude=1.5, center=0, sigma=0.5).
    - `bg`: a constant with initial guess 0.

    The `sigma` parameter has a lower bound `min=1e-3` to prevent the optimizer from driving it to zero.

3. **Fit execution** — `fit(graph, data)` invokes the Levenberg-Marquardt solver (default), which iteratively adjusts parameters to minimize the residuals until convergence.

4. **Result inspection** — we read:
    - **`success`** — True if the solver converged.
    - **`r_squared`** — the coefficient of determination (aim for > 0.99 on good data).
    - **`chi2`** — the sum of squared residuals.
    - **`parameters`** — dict of fitted parameters with `value` (point estimate) and `stderr` (estimated standard error, 1σ — the square root of the covariance diagonal, not a confidence-interval half-width).
    - **`residuals`** — the observed minus fitted values; their RMS and range tell you about noise level and systematic errors.

## See also

- **Related examples**: [`shared_params.md`](shared_params.md) (tied parameters), [`multi_dataset.md`](multi_dataset.md) (joint multi-dataset fits).
- **Test reference**: `tests/unit/spectrafit_core/test_fit.py::test_single_gaussian_recovery` (noiseless Gaussian), `tests/unit/spectrafit_core/test_fit.py::test_components_sum_equals_best_fit` (peak + background decomposition).
- **API docs**: `FitGraph`, `ModelNodeSpec`, `ModelType`, `Parameter`, `MeasurementData`, `FitResult`.
