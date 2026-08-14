---
icon: lucide/play
description: Fitting a single Gaussian peak to synthetic data in a few lines, using only the public compose/MeasurementData/fit API.
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

## Expected output

The noise is drawn from a seeded generator (`default_rng(0)`), so this example
is deterministic — you should see these numbers exactly:

```text
{'peak1.sigma': ParameterResult(value=1.2024163241228947, min=-inf, max=inf, vary=True,
                                expr=None, scale=None, name='peak1.sigma',
                                stderr=0.004211511681961483),
 'peak1.amplitude': ParameterResult(value=2.997594452290324, ...,
                                stderr=0.00909249987508253),
 'peak1.center': ParameterResult(value=0.49756589193680784, ...,
                                stderr=0.004211469158787863)}
0.9979075074894731
```

The fit is worth reading against the data it was given. The synthetic peak was
built with amplitude 3.0, centre 0.5 and sigma 1.2, and the solver recovers
2.9976, 0.4976 and 1.2024 from initial guesses of 1.0, 0.0 and 1.0 — each within
about one standard error of the truth, in 7 iterations. The remaining difference
is the noise, not the solver: r² = 0.9979 against data carrying 0.05 of added
noise on a peak of height 3.

Every parameter comes back as a `ParameterResult` rather than a bare float, so
the bounds (`min`/`max`), whether it was fitted or held (`vary`), any tie
(`expr`), and its standard error travel with the value.

`fit()` returns a `FitResult` with the fitted parameters, uncertainties, and
goodness-of-fit statistics (`r_squared`, `chi2`, `reduced_chi2`, `aic`, `bic`,
…). For a variant that also returns the best-fit curve directly as a NumPy
array (skipping JSON round-tripping of per-point arrays), use `fit_fast()`
instead of `fit()`.

## Next steps

This example is deliberately minimal — one peak, default solver, no bounds
or ties. For multi-peak fits, bounds, shared/tied parameters, alternative
solvers, and 2D/N-D data, see the [tutorial gallery](../tutorials/gallery/index.md).
