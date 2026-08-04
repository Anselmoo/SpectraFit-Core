---
icon: lucide/play
---

# Quickstart

Fit a single Gaussian peak to synthetic data in a few lines. This example
uses only the public `spectrafit_core` API: the `gaussian()` node factory,
`compose()` to build a `FitGraph`, `MeasurementData` for the input, and
`fit()` to run the solver.

```python
import numpy as np
from spectrafit_core import MeasurementData, compose, fit, gaussian

# Synthetic "measured" data: a Gaussian peak plus a little noise.
x = np.linspace(-5, 5, 200)
y = 3.0 * np.exp(-0.5 * ((x - 0.5) / 1.2) ** 2) + np.random.default_rng(0).normal(
    0, 0.05, x.size
)

# Build the model graph: one Gaussian node with initial guesses.
graph = compose([gaussian("peak1", amplitude=1.0, center=0.0, sigma=1.0)]).build()

# Run the fit.
result = fit(graph, MeasurementData(x=x.tolist(), y=y.tolist()))

print(result.parameters)  # fitted amplitude/center/sigma, keyed "peak1.<param>"
print(result.r_squared)  # goodness of fit
```

`fit()` returns a `FitResult` with the fitted parameters, uncertainties, and
goodness-of-fit statistics (`r_squared`, `chi2`, `reduced_chi2`, `aic`, `bic`,
…). For a variant that also returns the best-fit curve directly as a NumPy
array (skipping JSON round-tripping of per-point arrays), use `fit_fast()`
instead of `fit()`.

## Next steps

This example is deliberately minimal — one peak, default solver, no bounds
or ties. For multi-peak fits, bounds, shared/tied parameters, alternative
solvers, and 2D/N-D data, see the [tutorial gallery](../tutorials/gallery/index.md).
