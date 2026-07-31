"""Joint fit of four 2-D maps sharing a peak center and both widths.

Four 2-D ``gaussian2d`` spectra (think: four spatial maps recorded under
different conditions) differ only in amplitude — the underlying peak sits at
the same location with the same widths in every map. Rather than fitting each
map independently and hoping the four recovered centers/widths agree, we fit
all four jointly with :class:`~spectrafit_core.GlobalFitGraph`: the peak is a
*local* node replicated once per map (``n_slices=4``), and
``shared_local_params=["center_x", "center_y", "sigma_x", "sigma_y"]`` ties
those four parameters together with a hard constraint (an ``ExprEdge``) across
all replicas. Only ``amplitude`` stays free per map. The shared shape
parameters are then constrained by *all four maps at once* (4 x 400 = 1600
data points, but only 4 shared + 4 per-map-amplitude = 8 free parameters),
giving a far more precise estimate than any single map could on its own.

Companion to ``multi_dataset_1d.py`` (two 1-D peaks sharing width instead of
four 2-D maps sharing center + width). See ``docs/tutorials/gallery/
multi_dataset.md`` for the full narrative and caveats.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from _plotting import plot_fit, savefig
from spectrafit_core import (
    GlobalFitGraph,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
)


def main() -> None:
    """Build four shared-shape 2-D maps, fit them jointly, and plot line-outs."""
    # ------------------------------------------------------------------
    # Build a 20x20 coordinate grid shared by all four maps.
    # ------------------------------------------------------------------
    nx = ny = 20
    gx = np.linspace(-5.0, 5.0, nx)
    gy = np.linspace(-5.0, 5.0, ny)
    xx, yy = np.meshgrid(gx, gy)
    coords = np.column_stack([xx.ravel(), yy.ravel()])

    # Ground-truth shared shape; only amplitude varies across the four maps.
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

    # ------------------------------------------------------------------
    # GlobalFitGraph with no global_nodes — the peak is a local node
    # replicated once per map. shared_local_params ties center_x, center_y,
    # sigma_x, sigma_y across all four replicas; amplitude stays free.
    # ------------------------------------------------------------------
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

    graph = GlobalFitGraph(
        global_nodes=[],
        local_nodes=[peak()],
        n_slices=len(datasets),
        shared_local_params=["center_x", "center_y", "sigma_x", "sigma_y"],
    )
    result = graph.fit(datasets)
    p = {k: v.value for k, v in result.parameters.items()}

    # ------------------------------------------------------------------
    # Inspect the result.
    # ------------------------------------------------------------------
    print(f"Success: {result.success}")
    print(f"R²:      {result.r_squared:.6f}")
    print()
    print("Recovered shared params (all four maps contribute):")
    print(f"  center_x = {p['pk_s0.center_x']:.4f}  (true {cx})")
    print(f"  center_y = {p['pk_s0.center_y']:.4f}  (true {cy})")
    print(f"  sigma_x  = {p['pk_s0.sigma_x']:.4f}  (true {sx})")
    print(f"  sigma_y  = {p['pk_s0.sigma_y']:.4f}  (true {sy})")
    print()
    print("Per-map amplitudes:")
    for i, a_true in enumerate(amps_true):
        print(
            f"  slice {i}: amplitude = {p[f'pk_s{i}.amplitude']:.4f}  (true {a_true})"
        )
    print()
    print("Tie drift across slices (must be 0.0):")
    for param in ["center_x", "center_y", "sigma_x", "sigma_y"]:
        drift = max(
            abs(p[f"pk_s{i}.{param}"] - p["pk_s0." + param])
            for i in range(1, len(datasets))
        )
        print(f"  {param}: {drift:.2e}")

    # ------------------------------------------------------------------
    # Plot: one subplot per map (2x2 small multiples). `plot_fit` only ever
    # draws a 2-D (x, y) curve, so each 20x20 map is first sliced down to a
    # 1-D line-out along x at the row nearest the shared, fitted center_y
    # (both for the raw data and for the joint fit's `best_fit`, which
    # `result.dataset_slices` returns flattened in the same row-major order
    # as the input grid).
    # ------------------------------------------------------------------
    assert result.dataset_slices is not None
    row = int(np.argmin(np.abs(gy - p["pk_s0.center_y"])))

    fig, axes = plt.subplots(2, 2, figsize=(10.0, 8.0), sharex=True, sharey=True)
    for i, (ds, sl, ax) in enumerate(
        zip(datasets, result.dataset_slices, axes.ravel())
    ):
        y_data = np.asarray(ds.y).reshape(xx.shape)[row, :]
        y_fit = np.asarray(sl.best_fit).reshape(xx.shape)[row, :]
        plot_fit(
            gx,
            y_data,
            y_fit,
            title=f"map {i}  (true amplitude={amps_true[i]})  y≈{gy[row]:.2f}",
            ax=ax,
        )
    fig.suptitle(
        "Joint fit: four 2-D maps sharing center + width (line-out at y≈center_y)"
    )
    fig.tight_layout()
    out_path = savefig(fig, "multi_dataset_2d")
    print(f"\nSaved figure to {out_path}")


if __name__ == "__main__":
    main()
