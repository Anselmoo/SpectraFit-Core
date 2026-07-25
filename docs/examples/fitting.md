# Single-Dataset Fitting

## Context

**When to use this pattern.** You have a single measurement (x, y data) and want to fit it with one or more peak models. This is the simplest spectroscopy workflow: create a `FitGraph` with one or more peak nodes, pass your measured data, and extract the fitted parameters. The result includes the fitted curve, goodness-of-fit metrics (R², χ²), and uncertainty estimates.

## Quick example

```python
import numpy as np
from spectrafit_core import (
    FitGraph,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    fit,
)

# Synthesize example data: a single Gaussian peak in noisy background.
rng = np.random.default_rng(42)
x = np.linspace(-3, 3, 100)
peak = 2.0 * np.exp(-0.5 * ((x - 0.5) / 0.8) ** 2)
background = 0.1
noise = rng.normal(0, 0.05, len(x))
y = peak + background + noise

# Build a FitGraph: one Gaussian peak + one constant background.
graph = FitGraph(
    nodes=[
        ModelNodeSpec(
            id="peak",
            model_type=ModelType.GAUSSIAN,
            parameters={
                "amplitude": Parameter(value=1.5),
                "center": Parameter(value=0.0),
                "sigma": Parameter(value=0.5, min=1e-3),
            },
        ),
        ModelNodeSpec(
            id="bg",
            model_type=ModelType.CONSTANT,
            parameters={
                "c": Parameter(value=0.0),
            },
        ),
    ]
)

# Prepare measurement data.
data = MeasurementData(x=x.tolist(), y=y.tolist())

# Fit!
result = fit(graph, data)

# Inspect the result.
print(f"Success: {result.success}")
print(f"R²: {result.r_squared:.6f}")
print(f"χ²: {result.chi2:.6f}")
print()

# Print fitted parameters with 95 % confidence intervals.
for param_name, param in sorted(result.parameters.items()):
    print(f"{param_name:15s} = {param.value:8.4f} ± {param.stderr:8.4f}")
print()

# Show fit quality: residuals summary.
residuals = np.array(result.residuals)
print(f"Residual RMS:   {np.sqrt(np.mean(residuals**2)):.6f}")
print(f"Residual range: [{np.min(residuals):.6f}, {np.max(residuals):.6f}]")
```

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
   - **`parameters`** — dict of fitted parameters with `value` (point estimate) and `stderr` (95 % CI half-width).
   - **`residuals`** — the observed minus fitted values; their RMS and range tell you about noise level and systematic errors.

## See also

- **Related examples**: `docs/examples/shared_params.md` (tied parameters), `docs/examples/multi_dataset.md` (joint multi-dataset fits).
- **Test reference**: `tests/test_fit.py::test_single_gaussian_recovery` (noiseless Gaussian), `tests/test_fit.py::test_components_sum_equals_best_fit` (peak + background decomposition).
- **API docs**: `FitGraph`, `ModelNodeSpec`, `ModelType`, `Parameter`, `MeasurementData`, `FitResult`.
