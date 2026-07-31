"""Joint fit of two 1-D peaks sharing one line-broadening parameter.

Two Gaussian peaks are recorded at different positions and amplitudes, but the
instrument's line-broadening function is known to be identical across the two
measurements (shared ``sigma``). Instead of fitting each dataset on its own —
which would let the two independent line widths drift apart and would let each
fit see only half the evidence for ``sigma`` — we fit both datasets in a single
joint solve via :class:`~spectrafit_core.GlobalFitGraph`. The two peaks are
modeled as *local* replicas of one node (``local_nodes``, one replica per
dataset), and ``shared_local_params=["sigma"]`` ties the replicas' ``sigma``
together with a hard constraint (an ``ExprEdge``) for the duration of the
solve. Amplitude and center stay free per dataset; sigma is constrained by
*all* data points from *both* datasets at once.

Companion to ``multi_dataset_2d.py`` (four 2-D maps sharing center + width
instead of two 1-D peaks sharing width). See ``docs/tutorials/gallery/
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
    """Build two shared-width datasets, fit them jointly, and plot the result."""
    # ------------------------------------------------------------------
    # Synthesize two datasets: same shared sigma, different amplitude/center.
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # GlobalFitGraph with no global_nodes — the peak is a local node
    # replicated once per dataset. shared_local_params=["sigma"] means sigma
    # is tied (identical) across all dataset replicas while amplitude and
    # center vary freely per dataset.
    # ------------------------------------------------------------------
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
        n_slices=len(datasets),
        shared_local_params=["sigma"],
    )

    result = graph.fit(datasets)
    p = result.parameters

    # ------------------------------------------------------------------
    # Inspect the result.
    # ------------------------------------------------------------------
    print(f"Success: {result.success}")
    print(f"R²:      {result.r_squared:.6f}")
    print()
    print("Per-dataset amplitude and center:")
    for i, (a_true, c_true) in enumerate(truth):
        print(
            f"  slice {i}: amplitude = {p[f'pk_s{i}.amplitude'].value:.4f}"
            f" (true {a_true})"
            f"  center = {p[f'pk_s{i}.center'].value:.4f} (true {c_true})"
        )
    print()
    print("Shared sigma (identical across slices):")
    for i in range(len(datasets)):
        print(f"  pk_s{i}.sigma = {p[f'pk_s{i}.sigma'].value:.6f}")
    drift = abs(p["pk_s0.sigma"].value - p["pk_s1.sigma"].value)
    print(f"  Tie drift     = {drift:.2e}")

    # ------------------------------------------------------------------
    # Plot: one subplot per dataset (small multiples), each showing the raw
    # data overlaid with its jointly-fitted curve. `result.dataset_slices`
    # carries the per-dataset `best_fit` array in the same x-order as the
    # input, so no re-evaluation of the graph is needed.
    # ------------------------------------------------------------------
    assert result.dataset_slices is not None
    fig, axes = plt.subplots(1, len(datasets), figsize=(11.0, 4.5), sharey=True)
    for i, (ds, sl, ax) in enumerate(zip(datasets, result.dataset_slices, axes)):
        a_true, c_true = truth[i]
        plot_fit(
            ds.x,
            ds.y,
            sl.best_fit,
            title=f"dataset {i}  (true a={a_true}, c={c_true})",
            ax=ax,
        )
    fig.suptitle("Joint fit: two 1-D peaks sharing one line width (sigma)")
    fig.tight_layout()
    out_path = savefig(fig, "multi_dataset_1d")
    print(f"\nSaved figure to {out_path}")


if __name__ == "__main__":
    main()
