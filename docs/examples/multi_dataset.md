# Multi-Dataset Joint Fitting

## Context

**When to use this pattern.** You have N related spectra that share one identical
model, want to enforce that some parameters are globally identical across all datasets,
keep others free per dataset, and solve them all at once. One simultaneous joint solve
is strictly better than N independent fits: shared parameters are constrained by
*all* data points at once, giving a more precise estimate and ensuring consistency.

Typical use cases: temperature-dependent measurements sharing a peak position; a
series of samples sharing a calibrated instrument response; spatial maps sharing
center and width but varying amplitude per location.

**Contrast with `docs/examples/shared_params.md`** (which ties parameters across
*peaks within one spectrum*; this file ties parameters across *datasets*).

> **Scope of these examples.** All examples below are **synthetic and illustrative**:
> each uses a single seeded geometry (one model type, one grid size, one noise level,
> one random seed) chosen to demonstrate the mechanism, not to characterise accuracy
> across problem sizes, model families, or noise regimes. They show that the joint
> solve runs and that the shared-parameter ties are enforced within a solve. They are
> not measured data and are not a sweep that proves general accuracy.
>
> **Benchmark UI status.** The corresponding `global_fit` contract field is currently
> not rendered in the production web UI (classified `ignored: cut`). The capability
> lives in the fitting engine (`GlobalFitGraph`) and is exercised by tests; the
> benchmark showcase field exists but has no UI panel yet.

## 1-D example: local peaks with a shared line width

Two Gaussian peaks are recorded at different positions and amplitudes, but the
instrument's line-broadening function is known to be identical across measurements
(shared `sigma`). We fit both datasets jointly and recover the per-dataset amplitude
and center while the shared `sigma` is constrained by all data.

```python
import numpy as np
from spectrafit_core import (
    GlobalFitGraph,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
)

x = np.linspace(0.0, 10.0, 150)
shared_sigma = 0.5
truth = [(2.0, 3.0), (3.5, 6.0)]  # (amplitude, center) per dataset
rng = np.random.default_rng(0)

datasets = [
    MeasurementData(
        x=x.tolist(),
        y=(
            a * np.exp(-0.5 * ((x - c) / shared_sigma) ** 2)
            + rng.normal(0, 0.01, x.size)
        ).tolist(),
    )
    for a, c in truth
]

# GlobalFitGraph with no global_nodes — the peak is a local node replicated
# once per dataset.  shared_local_params="sigma" means sigma is tied (identical)
# across all dataset replicas while amplitude and center vary freely per dataset.
graph = GlobalFitGraph(
    global_nodes=[],
    local_nodes=[
        ModelNodeSpec(
            id="pk",
            model_type=ModelType.GAUSSIAN,
            parameters={
                "amplitude": Parameter(value=1.0, min=0.0),
                "center": Parameter(value=5.0),
                "sigma": Parameter(value=1.0, min=1e-6),
            },
        )
    ],
    n_slices=2,
    shared_local_params=["sigma"],
)

result = graph.fit(datasets)
p = result.parameters

print(f"Success: {result.success}")
print(f"R²:      {result.r_squared:.6f}")
print()
print("Per-dataset amplitude and center:")
for i, (a_true, c_true) in enumerate(truth):
    print(
        f"  slice {i}: amplitude = {p[f'pk_s{i}.amplitude'].value:.4f} (true {a_true})"
        f"  center = {p[f'pk_s{i}.center'].value:.4f} (true {c_true})"
    )
print()
print("Shared sigma (identical across slices):")
print(f"  pk_s0.sigma = {p['pk_s0.sigma'].value:.6f}")
print(f"  pk_s1.sigma = {p['pk_s1.sigma'].value:.6f}")
print(f"  Tie drift   = {abs(p['pk_s0.sigma'].value - p['pk_s1.sigma'].value):.2e}")
```

### What just happened

1. **Local nodes, shared params** — `local_nodes` are replicated once per dataset
   (here: `pk_s0` and `pk_s1`). By default every replica's parameters are
   independent. `shared_local_params=["sigma"]` adds an `ExprEdge` tie so
   `pk_s1.sigma` is constrained to equal `pk_s0.sigma`, reducing the degrees of
   freedom by one.

2. **Joint solve** — `graph.fit(datasets)` concatenates the residuals of both
   datasets into one vector and minimizes a single objective. Both datasets
   contribute to `sigma`'s estimate; per-dataset amplitude and center vary freely.

3. **Tie holds exactly within this solve** — the reported drift is 0.0 (machine
   precision). The engine enforces each shared-parameter tie as a hard constraint
   (an `ExprEdge`) so that, within a given fit, the tied parameters take an
   identical value throughout the solve. This is how the constraint is implemented,
   not a claim about all possible problem geometries or solvers.

## 2-D multi-spectrum example: four different maps sharing center and width

An illustrative 2-D multi-spectrum case (synthetic, one geometry): N 2-D
`gaussian2d` spectra that differ only in amplitude are fitted jointly. The shared
peak center and widths are constrained by *all four maps at once*; each map
contributes its own amplitude. This demonstrates the mechanism (SP-3) in one
representative seeded instance — not a sweep across geometries or noise levels.

```python
import numpy as np
from spectrafit_core import (
    GlobalFitGraph,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
)

# Build a 20×20 coordinate grid
nx = ny = 20
gx = np.linspace(-5.0, 5.0, nx)
gy = np.linspace(-5.0, 5.0, ny)
xx, yy = np.meshgrid(gx, gy)
coords = np.column_stack([xx.ravel(), yy.ravel()])

# Ground-truth shared shape; only amplitude varies across the four spectra
cx, cy, sx, sy = -1.0, 1.5, 1.2, 0.9
amps_true = [6.0, 4.0, 2.5, 5.0]
rng = np.random.default_rng(3)


def g2d(a: float) -> np.ndarray:
    return a * np.exp(-0.5 * (((xx - cx) / sx) ** 2 + ((yy - cy) / sy) ** 2))


datasets = [
    MeasurementData(
        x=coords.tolist(),
        y=(g2d(a) + rng.normal(0.0, 0.05, xx.shape)).ravel().tolist(),
    )
    for a in amps_true
]


def peak() -> ModelNodeSpec:
    return ModelNodeSpec(
        id="pk",
        model_type=ModelType.GAUSSIAN2D,
        parameters={
            "amplitude": Parameter(value=3.0, min=0.0),
            "center_x": Parameter(value=-0.5),
            "center_y": Parameter(value=1.0),
            "sigma_x": Parameter(value=1.0, min=0.1),
            "sigma_y": Parameter(value=1.0, min=0.1),
        },
    )


gfg = GlobalFitGraph(
    global_nodes=[],
    local_nodes=[peak()],
    n_slices=len(datasets),
    shared_local_params=["center_x", "center_y", "sigma_x", "sigma_y"],
)
result = gfg.fit(datasets)
p = {k: v.value for k, v in result.parameters.items()}

print(f"Success: {result.success}")
print(f"R²:      {result.r_squared:.6f}")
print()
print("Recovered shared params (all four maps contribute):")
print(f"  center_x = {p['pk_s0.center_x']:.4f}  (true {cx})")
print(f"  center_y = {p['pk_s0.center_y']:.4f}  (true {cy})")
print(f"  sigma_x  = {p['pk_s0.sigma_x']:.4f}  (true {sx})")
print(f"  sigma_y  = {p['pk_s0.sigma_y']:.4f}  (true {sy})")
print()
print("Per-slice amplitudes:")
for i, a_true in enumerate(amps_true):
    print(f"  slice {i}: amplitude = {p[f'pk_s{i}.amplitude']:.4f}  (true {a_true})")
print()
print("Tie drift across slices (must be 0.0):")
for param in ["center_x", "center_y", "sigma_x", "sigma_y"]:
    drift = max(
        abs(p[f"pk_s{i}.{param}"] - p["pk_s0." + param])
        for i in range(1, len(datasets))
    )
    print(f"  {param}: {drift:.2e}")
```

### What just happened

1. **Four 2-D spectra** — each is a 20×20 `gaussian2d` map with the same peak
   center and widths but a different amplitude. The true parameters are
   `center_x = −1.0`, `center_y = 1.5`, `sigma_x = 1.2`, `sigma_y = 0.9`.

2. **Shared shape, free amplitude** — `shared_local_params` ties
   `center_x`, `center_y`, `sigma_x`, `sigma_y` across all four dataset replicas.
   Each replica's `amplitude` remains free.

3. **One joint solve** — the optimizer minimizes a residual vector of length
   4 × 400 = 1600 data points simultaneously, with 4 (shared shape) + 4
   (per-slice amplitudes) = 8 free parameters.

4. **Tie drift is 0.0 in this run** — within this solve the shared parameters are
   identical across slices (not approximately equal), because the engine enforces
   each tie as a hard constraint (`ExprEdge`), not a soft penalty. The printed
   drift of 0.0 is a property of how the constraint is implemented, reported for
   the specific geometry shown above.

## Honest naming note

This capability was previously misnamed `time_resolved` in the benchmark contract.
That name implied a time axis, but the mechanism is a general shared-model
multi-spectrum joint fit: time is just one incidental axis interpretation. The
contract field was renamed `global_fit` (classes `GlobalFit` / `GlobalFitSlice`,
axis fields `dataset_axis` / `coord` / `axis_label`) in schema version 1.6.

## See also

- **Related examples**: `docs/examples/fitting.md` (single dataset, single peak),
  `docs/examples/shared_params.md` (per-peak parameter ties within one spectrum),
  `docs/examples/3d_fitting.md` (2-D Gaussian maps).
- **Test reference**:
  `tests/unit/spectrafit_core/test_global_fit.py::test_global_fit_graph_shared_local_param_across_slices`
  (1-D shared sigma),
  `tests/unit/spectrafit_core/test_global_fit.py::test_global_fit_several_2d_spectra_shared_model_recovers_and_ties`
  (2-D multi-spectrum proof).
- **API docs**: `GlobalFitGraph`, `GlobalFitGraph.fit`, `GlobalFitGraph.fit_all_slices`.
