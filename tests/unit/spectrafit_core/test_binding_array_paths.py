"""Coverage for the zero-copy numpy array paths in ``crates/spectrafit-core/src/lib.rs``.

These tests target three groups of previously-uncovered branches in the PyO3
binding shim (Task A of the binding-coverage follow-up):

* ``fit_arrays_numpy`` — the whole `#[pyfunction]` was never exercised by
  ``tests/unit/spectrafit_core`` before this file. ``spectrafit_core.fit_fast``
  (``python/spectrafit_core/fit.py``) is its only public-API caller, so the
  happy-path tests go through ``fit_fast`` (single dataset, global/multi-dataset,
  and 2-D x); the extension is also called directly to pin the raw binding
  contract (compact JSON strips the per-point arrays, the ndarray carries the
  fitted curve), its own JSON-decoding error branches, and — with a corrupted
  point fit twice under uniform vs. heavily down-weighted sigma — that the
  ``sigma`` argument is actually honoured by the solver, not merely accepted.
* ``split_array_datasets`` edge branches: the ``checked_mul`` overflow guard
  on ``n_total * n_dims`` and the "sigma slice out of bounds" guard, neither
  of which the size-mismatch tests in ``test_core_error_paths.py`` reach.
  ``split_array_datasets`` is a single private helper shared by
  ``fit_arrays`` and ``fit_arrays_numpy``, so exercising these guards through
  either entrypoint hits the identical Rust lines; this file owns both guards
  (via ``fit_arrays_numpy``, since this file already owns that entrypoint's
  coverage) and ``test_binding_edge_paths.py`` does not repeat them.
* ``transpose_x_for_solver`` branches reachable only through the JSON ``fit()``
  entrypoint: the empty-dataset no-op, the empty-coordinate-row rejection, and
  the ragged-x rejection. This file owns all three (the "array/shape/transpose/
  split paths" scope); ``test_binding_edge_paths.py`` does not repeat them —
  its own JSON-``fit()`` coverage is limited to the distinct success path.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from spectrafit_core import (
    FitGraph,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    _core,
    fit_fast,
)

# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _gaussian_y(x: np.ndarray, amplitude: float, center: float, sigma: float) -> np.ndarray:
    return amplitude * np.exp(-0.5 * ((x - center) / sigma) ** 2)


def _gaussian_graph(node_id: str = "g", amplitude: float = 1.0, center: float = 0.0) -> FitGraph:
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id=node_id,
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=amplitude),
                    "center": Parameter(value=center),
                    "sigma": Parameter(value=0.5, min=1e-3),
                },
            ),
        ],
    )


def _gaussian2d_graph() -> FitGraph:
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="g2",
                model_type=ModelType.GAUSSIAN2D,
                parameters={
                    "amplitude": Parameter(value=2.0),
                    "center_x": Parameter(value=0.3),
                    "center_y": Parameter(value=-0.6),
                    "sigma_x": Parameter(value=0.8, min=1e-3),
                    "sigma_y": Parameter(value=1.1, min=1e-3),
                },
            ),
        ],
    )


def _gaussian_graph_json(node_id: str = "g") -> str:
    return json.dumps(
        {
            "schema_version": "0.1",
            "nodes": [
                {
                    "id": node_id,
                    "model_type": "gaussian",
                    "parameters": {
                        "amplitude": {
                            "value": 1.0,
                            "min": None,
                            "max": None,
                            "vary": True,
                            "expr": None,
                            "scale": None,
                        },
                        "center": {
                            "value": 0.0,
                            "min": None,
                            "max": None,
                            "vary": True,
                            "expr": None,
                            "scale": None,
                        },
                        "sigma": {
                            "value": 1.0,
                            "min": 0.0,
                            "max": None,
                            "vary": True,
                            "expr": None,
                            "scale": None,
                        },
                    },
                },
            ],
            "expr_edges": [],
        },
    )


def _options_json() -> str:
    return json.dumps(
        {
            "schema_version": "0.1",
            "solver": "lm",
            "max_iterations": 50,
            "tolerance": 1e-8,
        },
    )


def _single_data_json(x_vals: list[list[float]], y_vals: list[float]) -> str:
    return json.dumps(
        {
            "schema_version": "0.1",
            "x": x_vals,
            "y": y_vals,
            "sigma": None,
            "label": None,
        },
    )


# ---------------------------------------------------------------------------
# fit_arrays_numpy — happy paths, reached through the public `fit_fast` API
# (python/spectrafit_core/fit.py:241 is the only caller of `core.fit_arrays_numpy`).
# ---------------------------------------------------------------------------


def test_fit_fast_single_dataset_recovers_params_and_returns_ndarray() -> None:
    """`fit_fast` on one dataset recovers truth and returns the curve as an ndarray."""
    a_true, c_true, s_true = 2.4, 0.3, 0.6
    x = np.linspace(-3.0, 3.0, 60)
    y = _gaussian_y(x, a_true, c_true, s_true)

    result, best_fit = fit_fast(
        _gaussian_graph(amplitude=1.8, center=0.0),
        MeasurementData(x=x.tolist(), y=y.tolist()),
    )

    assert result.success is True
    assert isinstance(best_fit, np.ndarray)
    assert best_fit.dtype == np.float64
    assert best_fit.shape == (60,)
    # The compact result strips the per-point arrays — the caller must use
    # the returned ndarray instead.
    assert result.best_fit == []
    assert result.params["g.amplitude"].value == pytest.approx(a_true, rel=0.02)
    assert result.params["g.center"].value == pytest.approx(c_true, rel=0.05)
    assert result.params["g.sigma"].value == pytest.approx(s_true, rel=0.05)


def test_fit_fast_global_multi_dataset_concatenates_curve() -> None:
    """`fit_fast` on a list of datasets (global fit) hits the multi-dataset split loop."""
    a_true, c_true, s_true = 1.7, -0.4, 0.9
    x1 = np.linspace(-3.0, 3.0, 25)
    x2 = np.linspace(-2.5, 2.5, 15)
    y1 = _gaussian_y(x1, a_true, c_true, s_true)
    y2 = _gaussian_y(x2, a_true, c_true, s_true)

    data = [
        MeasurementData(x=x1.tolist(), y=y1.tolist()),
        MeasurementData(x=x2.tolist(), y=y2.tolist()),
    ]
    result, best_fit = fit_fast(_gaussian_graph(amplitude=1.2, center=-0.1), data)

    assert result.success is True
    assert best_fit.shape == (len(x1) + len(x2),)
    assert result.dataset_slices is None, "fit_fast strips dataset_slices from the compact result"
    assert result.params["g.amplitude"].value == pytest.approx(a_true, rel=0.02)
    assert result.params["g.sigma"].value == pytest.approx(s_true, rel=0.05)


def test_fit_fast_2d_x_reshapes_and_recovers_params() -> None:
    """`fit_fast` with 2-D x exercises the `n_dims == 2` stride/reshape path."""
    a_true, cx_true, cy_true = 3.0, 0.5, -1.0
    sx_true, sy_true = 1.0, 1.5
    xs = np.linspace(-2.0, 2.0, 6)
    ys = np.linspace(-3.0, 1.0, 6)
    coords = [[x, y] for x in xs for y in ys]
    values = [
        a_true
        * np.exp(
            -((x - cx_true) ** 2) / (2.0 * sx_true**2) - ((y - cy_true) ** 2) / (2.0 * sy_true**2),
        )
        for x, y in coords
    ]
    data = MeasurementData(x=coords, y=values)

    result, best_fit = fit_fast(_gaussian2d_graph(), data)

    assert result.success is True
    assert best_fit.shape == (len(coords),)
    assert result.params["g2.amplitude"].value == pytest.approx(a_true, rel=0.02)
    assert result.params["g2.center_x"].value == pytest.approx(cx_true, abs=0.05)
    assert result.params["g2.center_y"].value == pytest.approx(cy_true, abs=0.05)


# ---------------------------------------------------------------------------
# fit_arrays_numpy — direct extension calls (raw binding contract + its own
# JSON-decoding error branches).
# ---------------------------------------------------------------------------


def test_core_fit_arrays_numpy_direct_call_strips_arrays_from_json() -> None:
    """Direct `_core.fit_arrays_numpy` call: compact JSON omits per-point arrays."""
    x = np.linspace(-2.0, 2.0, 12)
    y = _gaussian_y(x, 2.0, 0.1, 0.6)

    compact_json, best_fit_array = _core.fit_arrays_numpy(
        _gaussian_graph_json("g"),
        x,
        y,
        None,
        [12],
        1,
        _options_json(),
    )
    payload = json.loads(compact_json)

    assert payload["success"] is True
    assert payload["best_fit"] == []
    assert payload["residuals"] == []
    assert payload["init_fit"] == []
    assert payload["components"] == {}
    assert payload["dataset_slices"] is None
    assert isinstance(best_fit_array, np.ndarray)
    assert best_fit_array.shape == (12,)
    assert best_fit_array.dtype == np.float64


def test_core_fit_arrays_numpy_direct_call_with_sigma_weights() -> None:
    """Direct call proves ``sigma`` is honoured, not merely accepted.

    One point is corrupted with a large additive outlier. The same corrupted
    data is fit twice through the identical ``_core.fit_arrays_numpy`` call —
    once with uniform sigma (the outlier drags the fit off-truth) and once
    with a hugely inflated sigma on only the corrupted point (down-weighting
    its residual to near zero). A regression that silently ignores the
    ``sigma`` argument would make both calls converge to the same biased
    optimum; instead the weighted fit must recover amplitude/center/sigma
    markedly closer to the true values, with a comfortable margin, and the
    reported chi-square must differ between the two runs.
    """
    a_true, c_true, s_true = 1.5, 0.0, 0.6
    n_points = 13
    x = np.linspace(-3.0, 3.0, n_points)
    y_corrupted = _gaussian_y(x, a_true, c_true, s_true)
    outlier_index = 9  # x[9] == 1.5, where the true signal is small (~0.066).
    y_corrupted[outlier_index] += 4.0  # large, deterministic spike — no RNG.

    sigma_uniform = np.full(n_points, 1.0)
    sigma_weighted = sigma_uniform.copy()
    sigma_weighted[outlier_index] = 1.0e4  # effectively zeroes its residual weight.

    uniform_json, uniform_best_fit = _core.fit_arrays_numpy(
        _gaussian_graph_json("g"),
        x,
        y_corrupted,
        sigma_uniform,
        [n_points],
        1,
        _options_json(),
    )
    weighted_json, weighted_best_fit = _core.fit_arrays_numpy(
        _gaussian_graph_json("g"),
        x,
        y_corrupted,
        sigma_weighted,
        [n_points],
        1,
        _options_json(),
    )
    uniform = json.loads(uniform_json)
    weighted = json.loads(weighted_json)

    assert uniform["success"] is True
    assert weighted["success"] is True
    assert uniform_best_fit.shape == (n_points,)
    assert weighted_best_fit.shape == (n_points,)

    amp_err_uniform = abs(uniform["parameters"]["g.amplitude"]["value"] - a_true)
    amp_err_weighted = abs(weighted["parameters"]["g.amplitude"]["value"] - a_true)
    center_err_uniform = abs(uniform["parameters"]["g.center"]["value"] - c_true)
    center_err_weighted = abs(weighted["parameters"]["g.center"]["value"] - c_true)
    sigma_err_uniform = abs(uniform["parameters"]["g.sigma"]["value"] - s_true)
    sigma_err_weighted = abs(weighted["parameters"]["g.sigma"]["value"] - s_true)

    # Down-weighting the outlier recovers the true parameters almost exactly.
    assert amp_err_weighted < 0.05
    assert center_err_weighted < 0.05
    assert sigma_err_weighted < 0.05
    # Ignoring sigma (uniform weighting) leaves the outlier's pull visible.
    assert amp_err_uniform > 0.15
    assert center_err_uniform > 0.3
    assert sigma_err_uniform > 0.2
    # Require a clear margin, not just the right direction.
    assert amp_err_weighted < amp_err_uniform / 3
    assert center_err_weighted < center_err_uniform / 3
    assert sigma_err_weighted < sigma_err_uniform / 3

    # sigma also visibly changes the reported fit-quality metric.
    assert uniform["chi2"] != pytest.approx(weighted["chi2"])


def test_core_fit_arrays_numpy_rejects_invalid_graph_json() -> None:
    """`graph_json` deserialisation failure in `fit_arrays_numpy` raises ValueError."""
    x = np.zeros(3, dtype=np.float64)
    y = np.zeros(3, dtype=np.float64)
    with pytest.raises(ValueError, match="JSON parse error"):
        _core.fit_arrays_numpy("{not valid json", x, y, None, [3], 1, _options_json())


def test_core_fit_arrays_numpy_rejects_invalid_options_json() -> None:
    """`options_json` deserialisation failure in `fit_arrays_numpy` raises ValueError."""
    x = np.zeros(3, dtype=np.float64)
    y = np.zeros(3, dtype=np.float64)
    with pytest.raises(ValueError, match="JSON parse error"):
        _core.fit_arrays_numpy(
            _gaussian_graph_json("g"),
            x,
            y,
            None,
            [3],
            1,
            "{not valid options",
        )


# ---------------------------------------------------------------------------
# split_array_datasets — edge branches not reached by the size-mismatch tests
# in test_core_error_paths.py: the checked_mul overflow guard and the sigma
# out-of-bounds guard. Exercised through `fit_arrays_numpy` since this file
# owns that entrypoint's coverage.
# ---------------------------------------------------------------------------


def test_fit_arrays_numpy_rejects_dataset_sizes_x_overflow() -> None:
    """`n_total * n_dims` overflowing `usize` must raise the explicit overflow error.

    `dataset_sizes = [2]` and `len(y) = 2` pass the sum check; an adversarially
    large `n_dims` then overflows `usize` in the subsequent `checked_mul`
    (``crates/spectrafit-core/src/lib.rs`` ``split_array_datasets``), which must
    surface as a clean ``ValueError`` rather than silently wrapping.
    """
    x = np.zeros(2, dtype=np.float64)
    y = np.zeros(2, dtype=np.float64)
    huge_n_dims = 2**63  # 2 * 2**63 overflows a 64-bit usize.
    with pytest.raises(ValueError, match=r"n_total \* n_dims overflows usize"):
        _core.fit_arrays_numpy(
            _gaussian_graph_json("g"),
            x,
            y,
            None,
            [2],
            huge_n_dims,
            _options_json(),
        )


def test_fit_arrays_numpy_rejects_sigma_shorter_than_y() -> None:
    """A `sigma` array shorter than `y` trips the "sigma slice out of bounds" guard.

    `dataset_sizes`/`x`/`y` are all self-consistent (5 points, 1-D), so only the
    sigma slice — which has no length precondition of its own — goes
    out-of-bounds when `split_array_datasets` tries to slice
    `point_offset..point_offset + size` out of a too-short sigma buffer.
    """
    x = np.linspace(0.0, 1.0, 5, dtype=np.float64)
    y = np.zeros(5, dtype=np.float64)
    sigma = np.ones(3, dtype=np.float64)  # shorter than y (5 points).
    with pytest.raises(ValueError, match="sigma slice out of bounds"):
        _core.fit_arrays_numpy(
            _gaussian_graph_json("g"),
            x,
            y,
            sigma,
            [5],
            1,
            _options_json(),
        )


# ---------------------------------------------------------------------------
# transpose_x_for_solver — reachable only through the JSON `_core.fit()`
# entrypoint (`fit_arrays`/`fit_arrays_numpy` build their `MeasurementSpec`s
# through `split_array_datasets`, which reshapes directly and never calls
# `transpose_x_for_solver`).
# ---------------------------------------------------------------------------


def test_core_fit_json_path_empty_dataset_x_is_noop() -> None:
    """An entirely empty dataset (`x = []`, `y = []`) hits the early-return no-op.

    `transpose_x_for_solver` returns the spec unchanged when `spec.x.is_empty()`
    (line 140) rather than indexing `spec.x[0]`; the solver then runs on zero
    points and completes (with `success = False`) instead of raising or panicking.
    """
    data_j = _single_data_json(x_vals=[], y_vals=[])
    result_json = _core.fit(_gaussian_graph_json("g"), data_j, _options_json())
    payload = json.loads(result_json)

    assert payload["success"] is False
    assert payload["best_fit"] == []


def test_core_fit_json_path_rejects_empty_coordinate_row() -> None:
    """A single x point with zero coordinates (`x = [[]]`) must raise a clear error."""
    data_j = _single_data_json(x_vals=[[]], y_vals=[0.0])
    with pytest.raises(
        ValueError,
        match=r"fit\(\) received an x point with no coordinates \(empty row\)",
    ):
        _core.fit(_gaussian_graph_json("g"), data_j, _options_json())


def test_core_fit_json_path_rejects_ragged_x() -> None:
    """Points with differing coordinate counts must raise a ragged-x error.

    Point 0 has 1 coordinate, point 1 has 2 — `transpose_x_for_solver` must
    reject this rather than silently zero-padding the short row.
    """
    data_j = _single_data_json(x_vals=[[0.0], [1.0, 2.0]], y_vals=[0.0, 0.0])
    with pytest.raises(
        ValueError,
        match=r"fit\(\) received ragged x: point 0 has 1 coordinate\(s\) but point 1 has 2",
    ):
        _core.fit(_gaussian_graph_json("g"), data_j, _options_json())
