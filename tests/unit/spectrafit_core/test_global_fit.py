"""Phase 8 — test_global_fit.py

Tests for multi-dataset (global) fitting.
"""

from __future__ import annotations

import numpy as np
import pytest

from spectrafit_core import (
    FitGraph,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    fit,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gaussian_y(x: np.ndarray, A: float, c: float, sigma: float) -> np.ndarray:
    return A * np.exp(-0.5 * ((x - c) / sigma) ** 2)


def _make_gaussian_graph() -> FitGraph:
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="g",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=1.0),
                    "center": Parameter(value=0.0),
                    "sigma": Parameter(value=1.0, min=1e-3),
                },
            )
        ]
    )


# ---------------------------------------------------------------------------
# Two identical datasets — basic global fit
# ---------------------------------------------------------------------------


def test_global_fit_two_identical_datasets_best_fit_length() -> None:
    """Combined best_fit length == n_points_1 + n_points_2."""
    x = np.linspace(-2.0, 2.0, 20)
    y = _gaussian_y(x, 1.0, 0.0, 1.0)

    data1 = MeasurementData(x=x.tolist(), y=y.tolist())
    data2 = MeasurementData(x=x.tolist(), y=y.tolist())

    graph = _make_gaussian_graph()
    result = fit(graph, [data1, data2])

    assert len(result.best_fit) == len(x) * 2


def test_global_fit_two_datasets_recovers_params() -> None:
    """Global fit on two copies of noiseless Gaussian should converge."""
    A_true, c_true, s_true = 3.0, 0.5, 0.8
    x = np.linspace(-3.0, 4.0, 40)
    y = _gaussian_y(x, A_true, c_true, s_true)

    data1 = MeasurementData(x=x.tolist(), y=y.tolist())
    data2 = MeasurementData(x=x.tolist(), y=y.tolist())

    graph = FitGraph(
        nodes=[
            ModelNodeSpec(
                id="g",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=2.0),
                    "center": Parameter(value=0.0),
                    "sigma": Parameter(value=0.5, min=1e-3),
                },
            )
        ]
    )
    result = fit(graph, [data1, data2])

    assert result.success is True
    assert result.params["g.amplitude"].value == pytest.approx(A_true, rel=0.01)
    assert result.params["g.center"].value == pytest.approx(c_true, rel=0.02)
    assert result.params["g.sigma"].value == pytest.approx(s_true, rel=0.02)


def test_global_fit_dataset_slices_populated() -> None:
    """Multi-dataset fit populates dataset_slices (not None)."""
    x = np.linspace(-2.0, 2.0, 10)
    y = _gaussian_y(x, 1.0, 0.0, 1.0)

    data1 = MeasurementData(x=x.tolist(), y=y.tolist())
    data2 = MeasurementData(x=x.tolist(), y=y.tolist())

    graph = _make_gaussian_graph()
    result = fit(graph, [data1, data2])

    assert result.dataset_slices is not None
    assert len(result.dataset_slices) == 2


def test_global_fit_dataset_slices_indexing() -> None:
    """dataset_slices[i].n_points equals the size of each individual dataset."""
    x1 = np.linspace(-2.0, 2.0, 15)
    x2 = np.linspace(-1.0, 1.0, 10)
    y1 = _gaussian_y(x1, 1.0, 0.0, 1.0)
    y2 = _gaussian_y(x2, 1.0, 0.0, 1.0)

    data1 = MeasurementData(x=x1.tolist(), y=y1.tolist())
    data2 = MeasurementData(x=x2.tolist(), y=y2.tolist())

    graph = _make_gaussian_graph()
    result = fit(graph, [data1, data2])

    assert result.dataset_slices is not None
    assert result.dataset_slices[0].n_points == len(x1)
    assert result.dataset_slices[1].n_points == len(x2)


def test_global_fit_dataset_slices_best_fit_concat_matches() -> None:
    """Concatenation of per-slice best_fit == overall best_fit."""
    x1 = np.linspace(-2.0, 2.0, 12)
    x2 = np.linspace(-1.0, 1.0, 8)
    y1 = _gaussian_y(x1, 1.0, 0.0, 1.0)
    y2 = _gaussian_y(x2, 1.0, 0.0, 1.0)

    data1 = MeasurementData(x=x1.tolist(), y=y1.tolist())
    data2 = MeasurementData(x=x2.tolist(), y=y2.tolist())

    graph = _make_gaussian_graph()
    result = fit(graph, [data1, data2])

    assert result.dataset_slices is not None
    concatenated = result.dataset_slices[0].best_fit + result.dataset_slices[1].best_fit
    np.testing.assert_allclose(concatenated, result.best_fit, atol=1e-12)


def test_single_dataset_dataset_slices_is_none() -> None:
    """Single dataset → dataset_slices is None."""
    x = np.linspace(-2.0, 2.0, 10)
    y = _gaussian_y(x, 1.0, 0.0, 1.0)
    data = MeasurementData(x=x.tolist(), y=y.tolist())
    graph = _make_gaussian_graph()
    result = fit(graph, data)
    assert result.dataset_slices is None


def test_global_fit_graph_simultaneous_shared_peak_local_offsets() -> None:
    """GlobalFitGraph.fit does a single joint solve: a shared (global) peak plus
    per-dataset local offsets, where each local node only affects its dataset."""
    from spectrafit_core import GlobalFitGraph

    x = np.linspace(0.0, 10.0, 120)
    peak = _gaussian_y(x, 3.0, 5.0, 0.8)
    off0, off1 = 1.0, -0.5
    rng = np.random.default_rng(0)
    d0 = MeasurementData(
        x=x.tolist(), y=(peak + off0 + rng.normal(0, 0.01, x.size)).tolist()
    )
    d1 = MeasurementData(
        x=x.tolist(), y=(peak + off1 + rng.normal(0, 0.01, x.size)).tolist()
    )

    g = GlobalFitGraph(
        global_nodes=[
            ModelNodeSpec(
                id="peak",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=1.0, min=0.0),
                    "center": Parameter(value=4.0),
                    "sigma": Parameter(value=1.0, min=1e-6),
                },
            )
        ],
        local_nodes=[
            ModelNodeSpec(
                id="bg",
                model_type=ModelType.CONSTANT,
                parameters={"c": Parameter(value=0.0)},
            )
        ],
        n_slices=2,
    )
    r = g.fit([d0, d1])
    p = r.parameters
    assert r.success
    # Shared peak recovered from the joint fit.
    assert p["peak.center"].value == pytest.approx(5.0, abs=0.05)
    assert p["peak.amplitude"].value == pytest.approx(3.0, abs=0.05)
    # Each local offset is recovered independently — proving the local node only
    # contributes to its own dataset (otherwise both would converge to the mean).
    assert p["bg_s0.c"].value == pytest.approx(off0, abs=0.05)
    assert p["bg_s1.c"].value == pytest.approx(off1, abs=0.05)
    assert r.dataset_slices is not None and len(r.dataset_slices) == 2


def test_global_fit_graph_shared_local_param_across_slices() -> None:
    """Per-parameter sharing: a local peak with per-dataset amplitude/center but
    a sigma tied (shared) across slices — the lmfit fit_multi_datasets pattern."""
    from spectrafit_core import GlobalFitGraph

    x = np.linspace(0.0, 10.0, 150)
    shared_sigma = 0.5
    truth = [(2.0, 3.0), (3.5, 6.0)]  # (amplitude, center) per dataset
    rng = np.random.default_rng(0)
    ds = [
        MeasurementData(
            x=x.tolist(),
            y=(
                _gaussian_y(x, a, c, shared_sigma) + rng.normal(0, 0.01, x.size)
            ).tolist(),
        )
        for a, c in truth
    ]

    peak = ModelNodeSpec(
        id="pk",
        model_type=ModelType.GAUSSIAN,
        parameters={
            "amplitude": Parameter(value=1.0, min=0.0),
            "center": Parameter(value=5.0),
            "sigma": Parameter(value=1.0, min=1e-6),
        },
    )
    g = GlobalFitGraph(
        global_nodes=[],
        local_nodes=[peak],
        n_slices=2,
        shared_local_params=["sigma"],
    )
    r = g.fit(ds)
    p = r.parameters
    assert r.success
    # Per-dataset amplitude/center recovered independently.
    assert p["pk_s0.center"].value == pytest.approx(3.0, abs=0.05)
    assert p["pk_s1.center"].value == pytest.approx(6.0, abs=0.05)
    assert p["pk_s0.amplitude"].value == pytest.approx(2.0, abs=0.05)
    assert p["pk_s1.amplitude"].value == pytest.approx(3.5, abs=0.05)
    # Sigma is tied across slices (identical) and recovered.
    assert p["pk_s0.sigma"].value == pytest.approx(p["pk_s1.sigma"].value, abs=1e-9)
    assert p["pk_s0.sigma"].value == pytest.approx(shared_sigma, abs=0.02)


def test_global_fit_graph_shared_local_params_per_node_dict() -> None:
    """Per-node shared_local_params (dict form) ties only the named node's param."""
    from spectrafit_core import GlobalFitGraph

    x = np.linspace(0.0, 10.0, 150)
    shared_sigma = 0.5
    truth = [(2.0, 3.0), (3.5, 6.0)]
    rng = np.random.default_rng(1)
    ds = [
        MeasurementData(
            x=x.tolist(),
            y=(
                _gaussian_y(x, a, c, shared_sigma) + rng.normal(0, 0.01, x.size)
            ).tolist(),
        )
        for a, c in truth
    ]
    peak = ModelNodeSpec(
        id="pk",
        model_type=ModelType.GAUSSIAN,
        parameters={
            "amplitude": Parameter(value=1.0, min=0.0),
            "center": Parameter(value=5.0),
            "sigma": Parameter(value=1.0, min=1e-6),
        },
    )
    # dict form: tie sigma for "pk" specifically.
    g = GlobalFitGraph(
        global_nodes=[],
        local_nodes=[peak],
        n_slices=2,
        shared_local_params={"pk": ["sigma"]},
    )
    # to_fit_graph emits exactly one tie (pk_s1.sigma → pk_s0.sigma).
    flat = g.to_fit_graph()
    assert len(flat.expr_edges) == 1
    assert flat.expr_edges[0].target_node == "pk_s1"
    assert flat.expr_edges[0].target_param == "sigma"

    r = g.fit(ds)
    p = r.parameters
    assert r.success
    assert p["pk_s0.sigma"].value == pytest.approx(p["pk_s1.sigma"].value, abs=1e-9)
    assert p["pk_s0.center"].value == pytest.approx(3.0, abs=0.05)
    assert p["pk_s1.center"].value == pytest.approx(6.0, abs=0.05)


# ---------------------------------------------------------------------------
# fit_all_slices — staged Stage 1 (joint globals) + Stage 2 (per-slice locals)
#
# Covers `python/spectrafit_core/graph.py` lines 296–383, the previously-uncovered
# contiguous block that drove the per-module coverage floor down to 65 %.
# ---------------------------------------------------------------------------


def test_fit_all_slices_validates_dataset_count() -> None:
    """`fit_all_slices` must raise `ValueError` when len(datasets) != n_slices.

    Anti-regression for the dispatch guard at graph.py:325-329. The bench's
    time-resolved panel relies on this check so a mismatched recording
    surfaces as a clean error instead of a silent slice-index off-by-one
    deep inside the per-slice loop.
    """
    from spectrafit_core import GlobalFitGraph

    g = GlobalFitGraph(
        global_nodes=[],
        local_nodes=[
            ModelNodeSpec(
                id="bg",
                model_type=ModelType.CONSTANT,
                parameters={"c": Parameter(value=0.0)},
            )
        ],
        n_slices=3,
    )
    x = np.linspace(0.0, 1.0, 20)
    d = MeasurementData(x=x.tolist(), y=np.zeros_like(x).tolist())
    with pytest.raises(ValueError, match="expects 3 datasets, got 2"):
        g.fit_all_slices([d, d])


def test_fit_all_slices_with_globals_returns_per_slice_results() -> None:
    """Stage 1 (joint global solve) → Stage 2 (per-slice local refinement).

    Confirms the staged strategy returns one `FitResult` per slice, in dataset
    order, with the global peak's parameters consistent across slices (because
    Stage 2 fixes them) and the local offset recovered per-slice (because the
    locals are replicated and free per dataset).
    """
    from spectrafit_core import GlobalFitGraph

    x = np.linspace(0.0, 10.0, 120)
    peak = _gaussian_y(x, 3.0, 5.0, 0.8)
    off0, off1 = 1.0, -0.5
    rng = np.random.default_rng(7)
    d0 = MeasurementData(
        x=x.tolist(), y=(peak + off0 + rng.normal(0, 0.01, x.size)).tolist()
    )
    d1 = MeasurementData(
        x=x.tolist(), y=(peak + off1 + rng.normal(0, 0.01, x.size)).tolist()
    )

    g = GlobalFitGraph(
        global_nodes=[
            ModelNodeSpec(
                id="peak",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=1.0, min=0.0),
                    "center": Parameter(value=4.0),
                    "sigma": Parameter(value=1.0, min=1e-6),
                },
            )
        ],
        local_nodes=[
            ModelNodeSpec(
                id="bg",
                model_type=ModelType.CONSTANT,
                parameters={"c": Parameter(value=0.0)},
            )
        ],
        n_slices=2,
    )
    results = g.fit_all_slices([d0, d1])

    # One FitResult per slice, in dataset order.
    assert len(results) == 2
    for r in results:
        assert r.success

    # Stage 2 fixes the global params at their Stage 1 values, so every slice
    # reports the same converged peak.center / peak.amplitude / peak.sigma.
    center_values = {round(r.parameters["peak.center"].value, 4) for r in results}
    assert len(center_values) == 1, (
        f"global peak.center should be identical across slices, got {center_values}"
    )

    # Locals are replicated per slice (id suffix `_s{i}`); each slice recovers
    # an independent offset. Tolerance is looser than the joint-fit test
    # (`test_global_fit_graph_simultaneous_shared_peak_local_offsets`) because
    # Stage 2 fixes globals at Stage 1's values and only varies the locals,
    # so any Stage-1 imprecision in the global peak propagates as offset
    # drift; the key property is that the two slices RECOVER DIFFERENT
    # offsets in the right direction — proving locals don't bleed across.
    bg0 = results[0].parameters["bg_s0.c"].value
    bg1 = results[1].parameters["bg_s1.c"].value
    assert bg0 > bg1, (
        f"slice 0 ({off0}) should recover higher offset than slice 1 ({off1}); got bg0={bg0:.3f}, bg1={bg1:.3f}"
    )
    assert bg0 == pytest.approx(off0, abs=0.2)
    assert bg1 == pytest.approx(off1, abs=0.2)


def test_fit_all_slices_without_globals_skips_stage_one() -> None:
    """`global_nodes = []` short-circuits Stage 1; only per-slice fits run.

    Anti-regression for the `if self.global_nodes:` branch at graph.py:336 —
    the empty-globals path landed uncovered. With locals-only, each slice is
    fit independently and returns its own per-slice parameters; no global
    parameters appear.
    """
    from spectrafit_core import GlobalFitGraph

    x = np.linspace(0.0, 10.0, 60)
    # Two unrelated single-peak datasets — no shared structure to globalize.
    d0 = MeasurementData(x=x.tolist(), y=_gaussian_y(x, 2.0, 3.0, 0.5).tolist())
    d1 = MeasurementData(x=x.tolist(), y=_gaussian_y(x, 4.0, 7.0, 0.5).tolist())

    g = GlobalFitGraph(
        global_nodes=[],
        local_nodes=[
            ModelNodeSpec(
                id="pk",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=1.0, min=0.0),
                    "center": Parameter(value=5.0),
                    "sigma": Parameter(value=0.5, min=1e-3),
                },
            )
        ],
        n_slices=2,
    )
    results = g.fit_all_slices([d0, d1])
    assert len(results) == 2
    # No global params should appear (we passed an empty global_nodes list).
    for r in results:
        for key in r.parameters:
            assert not key.startswith("peak."), (
                f"unexpected global-style param key on locals-only fit: {key}"
            )
    # Local replicas reach the per-slice ground truth.
    assert results[0].parameters["pk_s0.center"].value == pytest.approx(3.0, abs=0.05)
    assert results[1].parameters["pk_s1.center"].value == pytest.approx(7.0, abs=0.05)


def test_global_fit_several_2d_spectra_shared_model_recovers_and_ties() -> None:
    """Regression guard: several *different* 2-D spectra sharing one model fit jointly.

    Guards the general (2-D, several-spectra) form of SP-3 — one representative
    seeded geometry: four ``gaussian2d`` maps sharing peak center/width (global
    analysis) with per-slice amplitudes, all recovered by one simultaneous solve.
    A single seeded instance; not a sweep that proves generality across all
    problem sizes, model families, or noise regimes.

    Asserts (a) the shared params are recovered toward truth, (b) each slice's
    amplitude is recovered, and (c) the shared params are *identical* across every
    slice (the engine enforces each tie as a hard constraint within the solve).
    """
    import numpy as np

    from spectrafit_core.data import MeasurementData
    from spectrafit_core.graph import GlobalFitGraph
    from spectrafit_core.models import ModelNodeSpec, ModelType
    from spectrafit_core.parameters import Parameter

    nx = ny = 20
    gx = np.linspace(-5.0, 5.0, nx)
    gy = np.linspace(-5.0, 5.0, ny)
    xx, yy = np.meshgrid(gx, gy)
    coords = np.column_stack([xx.ravel(), yy.ravel()])
    cx, cy, sx, sy = -1.0, 1.5, 1.2, 0.9
    amps_true = [6.0, 4.0, 2.5, 5.0]  # four DIFFERENT 2-D spectra
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

    assert result.success
    # (a) shared params recovered toward truth
    assert abs(p["pk_s0.center_x"] - cx) < 0.05
    assert abs(p["pk_s0.center_y"] - cy) < 0.05
    assert abs(p["pk_s0.sigma_x"] - sx) < 0.05
    assert abs(p["pk_s0.sigma_y"] - sy) < 0.05
    # (b) each slice's amplitude recovered
    for i, a in enumerate(amps_true):
        assert abs(p[f"pk_s{i}.amplitude"] - a) < 0.1
    # (c) shared params identical across every slice (tie holds exactly)
    for i in range(1, len(datasets)):
        assert p[f"pk_s{i}.center_x"] == p["pk_s0.center_x"]
        assert p[f"pk_s{i}.center_y"] == p["pk_s0.center_y"]
        assert p[f"pk_s{i}.sigma_x"] == p["pk_s0.sigma_x"]
        assert p[f"pk_s{i}.sigma_y"] == p["pk_s0.sigma_y"]
