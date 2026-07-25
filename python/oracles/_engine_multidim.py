"""N-dimensional (SP-2) and shared-model multi-spectrum global-fit (SP-3) showcases.

Split out of ``oracles.engine`` (G27): these four functions are a self-contained
cluster — they depend on no other engine helper and on no engine module constant,
only on numpy, the frozen contract types, and a real ``spectrafit_core`` solve
(the subject). ``engine`` re-imports ``_multidim`` and ``_global_fit`` so existing
``from oracles.engine import _multidim`` / ``_global_fit`` paths (and the
showcase-recovery tests) keep working unchanged.
"""

from __future__ import annotations

import numpy as np

from oracles.bench_contract import (
    GlobalFit,
    GlobalFitSlice,
    MultiDim,
    NdPeak,
    PeakTrace,
    Projection,
)


def _multidim() -> MultiDim:
    """A *genuinely fitted* N-dimensional (3-D) example (SP-2).

    A synthetic 3-D Gaussian is planted, sampled with noise, then **recovered by a
    real least-squares solve** with the parametric ``gaussian_nd`` kernel — the
    dimensionality D=3 is inferred from the node's indexed ``center_0/1/2``
    parameters — from a perturbed start. ``peaks`` are spectrafit's *fitted*
    parameters (not the planted truth) and ``r_squared`` the recovery quality.

    spectrafit-core is the **subject**: a real spectrafit ≥3-D solve, not the
    scipy oracle. Full 3-D obs/model grids do not scale past 2-D, so they are not
    stored; ``projections`` carries a 2-D marginal slice of the fitted model.
    """
    from spectrafit_core.data import MeasurementData
    from spectrafit_core.fit import fit as sf_fit
    from spectrafit_core.graph import FitGraph
    from spectrafit_core.models import ModelType
    from spectrafit_core.parameters import Parameter

    n = 14
    axes = [np.linspace(-5.0, 5.0, n) for _ in range(3)]
    xx, yy, zz = np.meshgrid(*axes, indexing="ij")
    coords = np.column_stack([xx.ravel(), yy.ravel(), zz.ravel()])

    amp_t, c_t, s_t = 6.0, (-1.5, 1.0, 0.5), (1.6, 2.1, 1.2)
    rng = np.random.default_rng(7)
    obs = amp_t * np.exp(
        -((xx - c_t[0]) ** 2) / (2 * s_t[0] ** 2)
        - ((yy - c_t[1]) ** 2) / (2 * s_t[1] ** 2)
        - ((zz - c_t[2]) ** 2) / (2 * s_t[2] ** 2)
    ) + rng.normal(0.0, 0.05, xx.shape)

    node = {
        "id": "g",
        "model_type": ModelType.GAUSSIAN_ND,
        "parameters": {
            "amplitude": Parameter(value=amp_t * 1.1),
            **{f"center_{i}": Parameter(value=c_t[i] + 0.3) for i in range(3)},
            **{f"sigma_{i}": Parameter(value=1.0, min=1e-3) for i in range(3)},
        },
    }
    result = sf_fit(
        FitGraph.model_validate({"nodes": [node]}),
        MeasurementData(x=coords.tolist(), y=obs.ravel().tolist()),
    )
    p = {key: val.value for key, val in result.parameters.items()}
    peak = NdPeak(
        amplitude=p["g.amplitude"],
        center=[p[f"g.center_{i}"] for i in range(3)],
        sigma=[p[f"g.sigma_{i}"] for i in range(3)],
    )
    # 2-D marginal: the fitted model sliced at the central z index → an (x, y) map.
    model = np.asarray(result.best_fit, dtype=float).reshape(n, n, n)
    mid = n // 2
    proj = Projection(labels=("x", "y"), matrix=model[:, :, mid][::2, ::2].tolist())
    return MultiDim(
        n_dims=3,
        shape=[n, n, n],
        n_points=int(coords.shape[0]),
        r_squared=float(result.r_squared),
        peaks=[peak],
        projections=[proj],
        source="spectrafit-core",
    )


def _build_global_fit_datasets(
    x: np.ndarray,
    a0_t: np.ndarray,
    a1_t: np.ndarray,
    c0: float,
    s0: float,
    c1: float,
    s1: float,
    noise: float,
    rng: np.random.Generator,
) -> tuple[list, list[np.ndarray]]:
    """Synthesize multi-dataset slices for the shared-model multi-spectrum global fit demo."""
    from spectrafit_core.data import MeasurementData

    def _g(xv: np.ndarray, a: float, c: float, s: float) -> np.ndarray:
        return a * np.exp(-0.5 * ((xv - c) / s) ** 2)

    datasets, obs_slices = [], []
    n_pts = len(x)
    for i in range(len(a0_t)):
        y = (
            _g(x, a0_t[i], c0, s0)
            + _g(x, a1_t[i], c1, s1)
            + rng.normal(0, noise, n_pts)
        )
        obs_slices.append(y)
        datasets.append(MeasurementData(x=[[xi] for xi in x.tolist()], y=y.tolist()))
    return datasets, obs_slices


def _assemble_global_fit(
    x: np.ndarray,
    dataset_axis: np.ndarray,
    obs_slices: list[np.ndarray],
    amp0: list[float],
    amp1: list[float],
    cen0: float,
    sig0: float,
    cen1: float,
    sig1: float,
) -> GlobalFit:
    """Assemble the GlobalFit contract from recovered shared-model multi-spectrum fit parameters."""

    def _g(xv: np.ndarray, a: float, c: float, s: float) -> np.ndarray:
        return a * np.exp(-0.5 * ((xv - c) / s) ** 2)

    n_slices = len(dataset_axis)
    slices = [
        GlobalFitSlice(
            coord=float(dataset_axis[i]),
            obs=obs_slices[i].tolist(),
            model=(_g(x, amp0[i], cen0, sig0) + _g(x, amp1[i], cen1, sig1)).tolist(),
        )
        for i in range(n_slices)
    ]
    traces = [
        PeakTrace(
            label="peak A",
            center=float(cen0),
            sigma=float(sig0),
            amplitude=[float(a) for a in amp0],
        ),
        PeakTrace(
            label="peak B",
            center=float(cen1),
            sigma=float(sig1),
            amplitude=[float(a) for a in amp1],
        ),
    ]
    return GlobalFit(
        x=x.tolist(),
        dataset_axis=[float(t) for t in dataset_axis],
        slices=slices,
        traces=traces,
        source="spectrafit-core",
    )


def _global_fit() -> GlobalFit:
    """Shared-model multi-spectrum joint global fit as ONE DAG solve.

    ``n_slices`` 1-D spectra share two peak centers/widths (global analysis via
    :class:`GlobalFitGraph` with ``shared_local_params=["center","sigma"]``) while each
    dataset slice's amplitudes vary — peak A decays, peak B rises along the axis.
    spectrafit fits every slice *simultaneously*; ``traces`` are the recovered per-peak
    amplitude traces and each ``slice`` carries its observed + jointly-fitted curve on
    the shared ``x`` grid.
    """
    from spectrafit_core.graph import GlobalFitGraph
    from spectrafit_core.models import ModelNodeSpec, ModelType
    from spectrafit_core.parameters import Parameter

    n_pts, n_slices = 120, 12
    x = np.linspace(-6.0, 6.0, n_pts)
    dataset_axis = np.linspace(0.0, 11.0, n_slices)
    c0, s0, c1, s1 = -1.8, 0.9, 2.0, 1.1
    rng = np.random.default_rng(11)
    a0_t = 5.0 * np.exp(-dataset_axis / 4.0)  # peak A decays
    a1_t = 4.0 * (1.0 - np.exp(-dataset_axis / 3.0))  # peak B rises

    datasets, obs_slices = _build_global_fit_datasets(
        x, a0_t, a1_t, c0, s0, c1, s1, 0.04, rng
    )

    def _peak(nid: str, a: float, c: float, s: float) -> ModelNodeSpec:
        return ModelNodeSpec(
            id=nid,
            model_type=ModelType.GAUSSIAN,
            parameters={
                "amplitude": Parameter(value=a, min=0.0),
                "center": Parameter(value=c, min=-6.0, max=6.0),
                "sigma": Parameter(value=s, min=0.1, max=5.0),
            },
        )

    gfg = GlobalFitGraph(
        global_nodes=[],
        local_nodes=[_peak("p0", 4.0, c0, s0), _peak("p1", 1.0, c1, s1)],
        n_slices=n_slices,
        shared_local_params=["center", "sigma"],
    )
    result = gfg.fit(datasets)
    p = {key: val.value for key, val in result.parameters.items()}
    amp0 = [p[f"p0_s{i}.amplitude"] for i in range(n_slices)]
    amp1 = [p[f"p1_s{i}.amplitude"] for i in range(n_slices)]
    return _assemble_global_fit(
        x,
        dataset_axis,
        obs_slices,
        amp0,
        amp1,
        p["p0_s0.center"],
        p["p0_s0.sigma"],
        p["p1_s0.center"],
        p["p1_s0.sigma"],
    )
