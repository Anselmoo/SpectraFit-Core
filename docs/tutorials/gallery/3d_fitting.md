# N-Dimensional (≥3-D) Fitting

!!! warning "Synthetic examples"
    All examples below are **synthetic and illustrative** — a single seeded
    geometry each, chosen to demonstrate the mechanism, not measured data and not a
    sweep that proves accuracy across all problem sizes, models, or noise levels.

## Context

**When to use this pattern.** You have a genuinely N-dimensional dataset — spectral
intensity over `(x, y, z)` coordinates, or `(kx, ky, kz, energy)` — and you want to
fit **one model jointly across all dimensions** (e.g. a trivariate Gaussian). As of
SP-2, spectrafit fits this **natively**: the parametric `gaussian_nd` kernel handles
any dimensionality `D`, and the dimensionality is **inferred** from the node's indexed
`center_<i>` parameters. No `MeasurementData3D` class is needed — a D-dimensional
point is just a coordinate row of length `D`.

!!! note "Shared-model global fit"
    If instead you have *several datasets sharing one model* (e.g. spectra at different
    conditions, each with its own amplitude but a shared peak shape), that is a
    **shared-model global fit** — use `GlobalFitGraph`; see the "Stacked slices"
    alternative below and [`multi_dataset.md`](multi_dataset.md).

## Native N-D example — one 3-D Gaussian

```python
--8<-- "3d_fitting.py"
```

## Arbitrary N (demonstrated at 3-D and 5-D)

`gaussian_nd` is not capped at 3-D. Give it `center_0..center_4` / `sigma_0..sigma_4`
and a 5-D coordinate grid, and it fits a 5-D Gaussian the same way — the kernel and the
solver are *structurally* dimensionality-general (the kernel sums over all `D` axes; the
executor strides by `D`), so there is no dimension-specific code path that caps `N`.
That structural generality is **demonstrated at 3-D and 5-D** by the Rust solver tests
(`run_gaussian_nd_recovery` at `d=3` and `d=5`); higher `N` follows from the same code
path but is not separately accuracy-tested here. The only practical limit is that an
N-D grid has `points = size**N`, so keep per-axis resolution modest at high `N`.

## What just happened

1. **Data** — a synthetic 3-D Gaussian sampled with light noise (σ=0.05).
2. **Graph** — a single `gaussian_nd` node. Its parameters are **indexed**
   (`center_0..center_{D-1}`, `sigma_0..sigma_{D-1}`, plus `amplitude`); the compiler
   counts the `center_<i>` parameters to infer `D=3` and validates the full
   `1 + 2D` set is present (a missing `center_i` raises a clear error).
3. **Fit** — one simultaneous least-squares solve over all 512 points. The executor
   strides the flat coordinate buffer by `D`, and the analytic Jacobian covers every
   axis. The planted center/σ are recovered to within a few percent.

## Performance note

The N-D path evaluates the model **per point** (the optimized batched fast-path is
1-D-only), so very large N-D grids (`size**N` points) are heavier than a 1-D fit of
the same point count. For volumetric data, keep the per-axis resolution modest, or
down-sample before fitting.

## Alternative — stacked slices (different parameters per slice)

If your "third dimension" is really an **index over datasets that share a model but
differ per slice** (e.g. a Gaussian whose amplitude changes from slice to slice while
center/σ stay fixed), that is a *shared-model global fit*, not a single N-D kernel.
Use `GlobalFitGraph` with `shared_local_params`:

```python
import numpy as np
from spectrafit_core import GlobalFitGraph, MeasurementData, ModelNodeSpec, ModelType, Parameter

x = np.linspace(-1, 4, 120)
amps_true = [1.5, 2.5, 1.8]  # one per slice
rng = np.random.default_rng(42)
datasets = [
    MeasurementData(
        x=[[xi] for xi in x.tolist()],
        y=(a * np.exp(-0.5 * ((x - 1.5) / 0.5) ** 2) + rng.normal(0, 0.025, len(x))).tolist(),
    )
    for a in amps_true
]
graph = GlobalFitGraph(
    global_nodes=[],
    local_nodes=[ModelNodeSpec(
        id="peak", model_type=ModelType.GAUSSIAN,
        parameters={"amplitude": Parameter(value=2.0),
                    "center": Parameter(value=1.5),
                    "sigma": Parameter(value=0.5, min=1e-6)},
    )],
    n_slices=len(amps_true),
    shared_local_params=["center", "sigma"],  # shared shape; amplitude stays per-slice
)
result = graph.fit(datasets)
print("shared center:", result.parameters["peak_s0.center"].value)
for i in range(len(amps_true)):
    print(f"  slice {i} amplitude:", result.parameters[f"peak_s{i}.amplitude"].value)
```

The two patterns answer different questions: **native N-D** fits *one* model over an
N-dimensional coordinate space; **stacked slices** fits *one shared model* across many
lower-dimensional datasets with per-slice free parameters.

## See also

- **Related examples**: [`multi_dataset.md`](multi_dataset.md) (shared-model multi-spectrum
  global fit), [`shared_params.md`](shared_params.md) (tied parameters within one spectrum),
  [`fitting.md`](fitting.md) (single-dataset fit).
- **Test reference**: `tests/unit/spectrafit_core/test_fit_nd.py` (native 3-D `gaussian_nd`
  round-trip), `tests/unit/spectrafit_core/test_global_fit.py` (GlobalFitGraph).
- **API docs**: `ModelType.GAUSSIAN_ND`, `FitGraph`, `GlobalFitGraph`.
