# Shared Parameters Across Peaks

## Context

**When to use this pattern.** You have multiple peaks in a single spectrum and want to enforce that some parameters are identical across peaks. For example, two Lorentzian peaks that must share the same line width (σ), or three multiplet lines with identical broadening.

There are **two equivalent ways** to express a parameter tie — choose whichever reads most naturally in your code:

| Surface | How to declare | When to use |
|---|---|---|
| `ExprEdge` (graph-level) | Add an `ExprEdge` to `FitGraph.expr_edges` | When building or composing graphs programmatically; best for complex, multi-edge topologies. |
| `Parameter.expr` (per-param) | Set `expr="source_node.param"` on the target `Parameter` | When building a node inline and the tie is a simple identity; no separate edge list needed. |

Both surfaces compile to the **same** dependency-ordered tied-plan, so the fit result is **numerically identical** regardless of which surface you use. The LM-family solvers (`lm`, `trf`, `geodesic`, `dogleg`, `newton-cg`, `irls`) apply the tied-plan on every iteration. The `global` (differential-evolution) solver searches with the tied parameters held at their seed values and then applies the tie in its post-search LM refinement, so its **final result** is tie-correct. (`solver="varpro"` does not fit tied graphs at all — it rejects them; see MODELS.md.) Setting the same target parameter via **both** surfaces simultaneously raises a `DuplicateExprTarget` error.

## Quick example — using ExprEdge (graph-level)

```python
import numpy as np
from spectrafit_core import (
    ExprEdge,
    FitGraph,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    fit,
)

# Synthesize example data: two Gaussians with identical sigma (0.6),
# but different amplitudes and centers.
rng = np.random.default_rng(42)
x = np.linspace(-2, 4, 120)
sigma_true = 0.6
peak1 = 3.0 * np.exp(-0.5 * ((x - 0.0) / sigma_true) ** 2)
peak2 = 2.0 * np.exp(-0.5 * ((x - 2.5) / sigma_true) ** 2)
noise = rng.normal(0, 0.05, len(x))
y = peak1 + peak2 + noise

# Build a FitGraph with two Gaussian peaks and ONE ExprEdge tie:
# peak2.sigma = peak1.sigma (they must be identical).
graph = FitGraph(
    nodes=[
        ModelNodeSpec(
            id="peak1",
            model_type=ModelType.GAUSSIAN,
            parameters={
                "amplitude": Parameter(value=2.5),
                "center": Parameter(value=0.5),
                "sigma": Parameter(value=0.5, min=1e-3),
            },
        ),
        ModelNodeSpec(
            id="peak2",
            model_type=ModelType.GAUSSIAN,
            parameters={
                "amplitude": Parameter(value=2.0),
                "center": Parameter(value=2.0),
                "sigma": Parameter(value=0.5, min=1e-3),
            },
        ),
    ],
    expr_edges=[
        ExprEdge(
            target_node="peak2",
            target_param="sigma",
            expression="peak1.sigma",
        )
    ],
)

# Prepare measurement data.
data = MeasurementData(x=x.tolist(), y=y.tolist())

# Fit!
result = fit(graph, data)

# Inspect the result.
print(f"Success: {result.success}")
print(f"R²: {result.r_squared:.6f}")
print()

# Print parameters.
print("Fitted parameters:")
for param_name, param in sorted(result.parameters.items()):
    stderr_str = f"{param.stderr:8.4f}" if param.stderr is not None else "    tied"
    print(f"{param_name:20s} = {param.value:8.4f} ± {stderr_str}")
print()

# Verify the tie holds: sigma values must be identical.
sigma1 = result.parameters["peak1.sigma"].value
sigma2 = result.parameters["peak2.sigma"].value
print(f"Tie verification:")
print(f"  peak1.sigma = {sigma1:.8f}")
print(f"  peak2.sigma = {sigma2:.8f}")
print(f"  Difference  = {abs(sigma1 - sigma2):.2e}")
```

## What just happened

1. **Data creation** — we synthesized two overlapping Gaussians: peak1 at center=0 with amplitude=3, peak2 at center=2.5 with amplitude=2, both with σ=0.6.

2. **Graph definition** — we built a `FitGraph` with two `GAUSSIAN` nodes, plus one `ExprEdge`:
   - `expr_edges[0]` ties `peak2.sigma` to `peak1.sigma`, meaning throughout the fit, `peak2.sigma` is automatically updated to match `peak1.sigma`.
   - This reduces the degrees of freedom by 1 (peak1.sigma is a free variable; peak2.sigma is dependent).

3. **Fit execution** — the optimizer adjusts the 5 free variables (peak1 amplitude, center, sigma; peak2 amplitude, center) and the tie constraint is enforced at each iteration.

4. **Result inspection** — the `parameters` dict includes both `peak1.sigma` and `peak2.sigma`, but they are **numerically identical** because the tie is enforced. In the output above, both report ~0.6 (the true value).

5. **Tie verification** — we confirm that the difference between `peak1.sigma` and `peak2.sigma` is negligible (< 1e-14 machine epsilon).

## Equivalent form — using Parameter.expr (per-parameter)

The same tie can be declared entirely inside the target `Parameter` itself, without adding an `ExprEdge` to the graph. The fit result is numerically identical.

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

rng = np.random.default_rng(42)
x = np.linspace(-2, 4, 120)
sigma_true = 0.6
peak1 = 3.0 * np.exp(-0.5 * ((x - 0.0) / sigma_true) ** 2)
peak2 = 2.0 * np.exp(-0.5 * ((x - 2.5) / sigma_true) ** 2)
noise = rng.normal(0, 0.05, len(x))
y = peak1 + peak2 + noise

# Same tie — expressed via Parameter.expr on peak2.sigma.
# No ExprEdge is needed; the expr_edges list stays empty.
graph = FitGraph(
    nodes=[
        ModelNodeSpec(
            id="peak1",
            model_type=ModelType.GAUSSIAN,
            parameters={
                "amplitude": Parameter(value=2.5),
                "center": Parameter(value=0.5),
                "sigma": Parameter(value=0.5, min=1e-3),
            },
        ),
        ModelNodeSpec(
            id="peak2",
            model_type=ModelType.GAUSSIAN,
            parameters={
                "amplitude": Parameter(value=2.0),
                "center": Parameter(value=2.0),
                # Tie declared inline: peak2.sigma is derived from peak1.sigma.
                # vary=False is conventional; the engine excludes expr params
                # from the free set regardless of vary.
                "sigma": Parameter(value=0.5, min=1e-3, expr="peak1.sigma", vary=False),
            },
        ),
    ],
    # expr_edges intentionally empty — the tie lives in Parameter.expr only.
)

data = MeasurementData(x=x.tolist(), y=y.tolist())
result = fit(graph, data)

sigma1 = result.parameters["peak1.sigma"].value
sigma2 = result.parameters["peak2.sigma"].value
print(f"peak1.sigma = {sigma1:.8f}")
print(f"peak2.sigma = {sigma2:.8f}")
print(f"Difference  = {abs(sigma1 - sigma2):.2e}")
# → Difference is < 1e-14 (machine epsilon) — identical to the ExprEdge form.
```

## Equivalence guarantee

`ExprEdge` and `Parameter.expr` are two syntax forms for the same constraint: both are compiled into the same dependency-ordered tied-plan that the solver evaluates on every iteration. The parity test `tests/parity/test_param_expr_surface_parity.py::test_param_expr_matches_expr_edge` asserts that recovered parameters and chi² agree to `rel=1e-6` across the two surfaces.

**Do not use both at once.** Targeting the same parameter with both a `Parameter.expr` and a matching `ExprEdge` raises a `DuplicateExprTarget` error at compilation time.

## See also

- **Related examples**: `docs/examples/fitting.md` (basic single-fit), `docs/examples/multi_dataset.md` (per-slice shared parameters).
- **Test reference**: `tests/unit/spectrafit_core/test_fit.py::test_fit_accepts_expr_edges` (ExprEdge end-to-end), `tests/unit/spectrafit_core/test_fit.py::test_fit_honors_parameter_expr` (Parameter.expr end-to-end), `tests/parity/test_param_expr_surface_parity.py::test_param_expr_matches_expr_edge` (equivalence invariant).
- **API docs**: `ExprEdge`, `FitGraph`, `Parameter`.
