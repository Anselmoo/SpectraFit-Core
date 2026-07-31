"""Fit a single Gaussian peak plus a constant background, then plot the result.

The simplest possible spectrafit_core workflow: one peak node, one background
node, a single dataset. See ``fitting.md`` for the narrative walkthrough.
"""

import numpy as np
from _plotting import plot_fit, savefig
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

# Print fitted parameters with their estimated standard error (1σ).
for param_name, param in sorted(result.parameters.items()):
    print(f"{param_name:15s} = {param.value:8.4f} ± {param.stderr:8.4f}")
print()

# Show fit quality: residuals summary.
residuals = np.array(result.residuals)
print(f"Residual RMS:   {np.sqrt(np.mean(residuals**2)):.6f}")
print(f"Residual range: [{np.min(residuals):.6f}, {np.max(residuals):.6f}]")

if __name__ == "__main__":
    # Plot data + fitted curve with a residuals subplot below.
    best_fit = np.array(result.best_fit)
    fit_residuals = y - best_fit
    fig, ax = plot_fit(
        x,
        y,
        best_fit,
        residuals=fit_residuals,
        title="Single-dataset Gaussian fit",
    )
    savefig(fig, "fitting")
