"""Phase 8 — test_fit.py

End-to-end tests for the fit() function.
"""

from __future__ import annotations

import numpy as np
import pytest

from spectrafit_core import (
    ExprEdge,
    FitGraph,
    FitOptions,
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


# ---------------------------------------------------------------------------
# Single Gaussian recovery
# ---------------------------------------------------------------------------


def test_single_gaussian_recovery() -> None:
    """Fit recovers noiseless Gaussian to <1 % of true values."""
    A_true, c_true, s_true = 5.0, 2.0, 0.5
    x = np.linspace(-1.0, 5.0, 50)
    y = _gaussian_y(x, A_true, c_true, s_true)

    graph = FitGraph(
        nodes=[
            ModelNodeSpec(
                id="peak",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=4.0),
                    "center": Parameter(value=1.8),
                    "sigma": Parameter(value=0.6, min=1e-3),
                },
            )
        ]
    )
    data = MeasurementData(x=x.tolist(), y=y.tolist())
    result = fit(graph, data)

    assert result.success is True
    assert result.chi2 < 1e-8
    assert result.r_squared > 0.9999

    assert result.params["peak.amplitude"].value == pytest.approx(A_true, rel=0.01)
    assert result.params["peak.center"].value == pytest.approx(c_true, rel=0.01)
    assert result.params["peak.sigma"].value == pytest.approx(s_true, rel=0.01)


def test_result_params_keys_format() -> None:
    """Parameter keys must be 'node.param' format."""
    graph = FitGraph(
        nodes=[
            ModelNodeSpec(
                id="pk",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=1.0),
                    "center": Parameter(value=0.0),
                    "sigma": Parameter(value=1.0, min=1e-3),
                },
            )
        ]
    )
    data = MeasurementData(x=[0.0, 1.0, 2.0], y=[1.0, 0.5, 0.1])
    result = fit(graph, data)

    for key in result.params:
        assert "." in key, f"param key {key!r} should contain '.'"
        node_id, param_name = key.split(".", 1)
        assert node_id == "pk"
        assert param_name in ("amplitude", "center", "sigma")


# ---------------------------------------------------------------------------
# Fixed parameter
# ---------------------------------------------------------------------------


def test_fixed_center_unchanged() -> None:
    """A fixed (vary=False) center must not change after fitting."""
    x = np.linspace(-3.0, 3.0, 40)
    y = _gaussian_y(x, 2.0, 0.5, 0.8)

    graph = FitGraph(
        nodes=[
            ModelNodeSpec(
                id="g",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=2.0),
                    "center": Parameter(value=0.5, vary=False),
                    "sigma": Parameter(value=0.8, min=1e-3),
                },
            )
        ]
    )
    data = MeasurementData(x=x.tolist(), y=y.tolist())
    result = fit(graph, data)

    assert result.params["g.center"].value == pytest.approx(0.5, abs=1e-12)


# ---------------------------------------------------------------------------
# Constant model
# ---------------------------------------------------------------------------


def test_constant_model_recovery() -> None:
    """Constant model should recover c ≈ 3.0 from flat data."""
    x = np.linspace(0.0, 5.0, 20)
    y = np.full_like(x, 3.0)

    graph = FitGraph(
        nodes=[
            ModelNodeSpec(
                id="bg",
                model_type=ModelType.CONSTANT,
                parameters={
                    "c": Parameter(value=1.0),
                },
            )
        ]
    )
    data = MeasurementData(x=x.tolist(), y=y.tolist())
    result = fit(graph, data)

    assert result.params["bg.c"].value == pytest.approx(3.0, abs=1e-4)


# ---------------------------------------------------------------------------
# init_fit, components, dataset_slices
# ---------------------------------------------------------------------------


def test_init_fit_length_and_differs_from_best_fit() -> None:
    """init_fit should have same length as data and differ from best_fit."""
    x = np.linspace(-2.0, 2.0, 25)
    y = _gaussian_y(x, 5.0, 1.0, 0.5)

    graph = FitGraph(
        nodes=[
            ModelNodeSpec(
                id="g",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=1.0),  # far from truth
                    "center": Parameter(value=0.0),  # off-center
                    "sigma": Parameter(value=0.1, min=1e-3),  # far from truth
                },
            )
        ]
    )
    data = MeasurementData(x=x.tolist(), y=y.tolist())
    result = fit(graph, data)

    assert len(result.init_fit) == len(x)
    # init_fit was evaluated at very different params, so differs from best_fit
    assert result.init_fit != result.best_fit


def test_components_sum_equals_best_fit() -> None:
    """Sum of all components must equal best_fit at each point."""
    x = np.linspace(-3.0, 3.0, 30)
    y = _gaussian_y(x, 2.0, 0.0, 1.0) + 0.5  # gaussian + constant

    graph = FitGraph(
        nodes=[
            ModelNodeSpec(
                id="peak",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=2.0),
                    "center": Parameter(value=0.0),
                    "sigma": Parameter(value=1.0, min=1e-3),
                },
            ),
            ModelNodeSpec(
                id="bg",
                model_type=ModelType.CONSTANT,
                parameters={
                    "c": Parameter(value=0.5),
                },
            ),
        ]
    )
    data = MeasurementData(x=x.tolist(), y=y.tolist())
    result = fit(graph, data)

    comp_sum = np.asarray(result.components["peak"]) + np.asarray(
        result.components["bg"]
    )
    np.testing.assert_allclose(comp_sum, result.best_fit, atol=1e-10)


def test_dataset_slices_none_for_single_dataset() -> None:
    """Single dataset → dataset_slices should be None."""
    graph = FitGraph(
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
    data = MeasurementData(x=[0.0, 1.0, 2.0], y=[1.0, 0.5, 0.1])
    result = fit(graph, data)
    assert result.dataset_slices is None


def test_schema_version_in_result() -> None:
    """result.schema_version should be '0.1'."""
    graph = FitGraph(
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
    data = MeasurementData(x=[0.0, 1.0, 2.0], y=[1.0, 0.5, 0.1])
    result = fit(graph, data)
    assert result.schema_version == "0.1"


# ---------------------------------------------------------------------------
# FitOptions — max_iterations=1 does not crash
# ---------------------------------------------------------------------------


def test_max_iterations_one_does_not_crash() -> None:
    """FitOptions(max_iterations=1) should return a result without error."""
    graph = FitGraph(
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
    data = MeasurementData(x=[0.0, 1.0, 2.0], y=[1.0, 0.5, 0.1])
    opts = FitOptions(max_iterations=1)
    result = fit(graph, data, opts)
    # Just verify it doesn't raise and produces a FitResult
    assert len(result.best_fit) == 3
    assert isinstance(result.success, bool)


# ---------------------------------------------------------------------------
# Error-path tests
# ---------------------------------------------------------------------------


def test_fit_accepts_expr_edges() -> None:
    """fit() with expr_edges solves the tie (bg.sigma == peak.sigma) end-to-end."""
    graph = FitGraph(
        nodes=[
            ModelNodeSpec(
                id="peak",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=1.0),
                    "center": Parameter(value=0.0),
                    "sigma": Parameter(value=1.0, min=1e-3),
                },
            ),
            ModelNodeSpec(
                id="bg",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=0.5),
                    "center": Parameter(value=1.0),
                    "sigma": Parameter(value=1.0, min=1e-3),
                },
            ),
        ],
        expr_edges=[
            ExprEdge(
                target_node="bg",
                target_param="sigma",
                expression="peak.sigma",
            )
        ],
    )
    data = MeasurementData(x=[0.0, 1.0, 2.0], y=[1.0, 0.5, 0.1])
    # No longer raises: expr_edges are evaluated per iteration by the engine.
    result = fit(graph, data)
    assert isinstance(result.success, bool)
    # The tie holds in the output: bg.sigma == peak.sigma.
    bg_sigma = result.parameters["bg.sigma"].value
    peak_sigma = result.parameters["peak.sigma"].value
    assert bg_sigma == pytest.approx(peak_sigma, rel=1e-9)


def test_fit_honors_parameter_expr() -> None:
    """fit() with Parameter.expr derives the tied param each iteration.

    Two Gaussians share the same ``sigma`` via ``g2.sigma.expr = 'g1.sigma'``.
    The tie is expressed *purely* through ``Parameter.expr`` — no ``ExprEdge``
    entry is present in ``expr_edges``.  The recovered ``g2.sigma`` must match
    ``g1.sigma`` at the converged solution (not stay at its initial placeholder).
    """
    s_true = 0.5
    x = np.linspace(-3.0, 3.0, 80)
    # Symmetric twin Gaussians — equal amplitude and sigma, opposite centers.
    y = np.exp(-0.5 * ((x + 1.0) / s_true) ** 2) * 3.0 + np.exp(
        -0.5 * ((x - 1.0) / s_true) ** 2
    ) * 3.0

    graph = FitGraph(
        nodes=[
            ModelNodeSpec(
                id="g1",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=2.5),
                    "center": Parameter(value=-0.8),
                    "sigma": Parameter(value=0.4, min=1e-3),
                },
            ),
            ModelNodeSpec(
                id="g2",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=2.5),
                    "center": Parameter(value=0.8),
                    # expr-only tie — no ExprEdge; vary=False means not free
                    "sigma": Parameter(value=0.4, min=1e-3, expr="g1.sigma", vary=False),
                },
            ),
        ]
        # expr_edges intentionally empty — the tie lives in Parameter.expr only
    )
    data = MeasurementData(x=x.tolist(), y=y.tolist())
    result = fit(graph, data)

    assert result.success is True
    g1_sigma = result.parameters["g1.sigma"].value
    g2_sigma = result.parameters["g2.sigma"].value

    # Primary assertion: tied param must equal the free source at convergence.
    assert g2_sigma == pytest.approx(g1_sigma, rel=1e-9), (
        f"g2.sigma ({g2_sigma}) must equal g1.sigma ({g1_sigma}) — "
        "Parameter.expr tie was not honored."
    )
    # Secondary assertion: the free sigma must recover the ground truth.
    assert g1_sigma == pytest.approx(s_true, rel=0.02), (
        f"g1.sigma ({g1_sigma}) should recover ground-truth {s_true}."
    )


def test_fit_accepts_3d_data_with_gaussian_nd() -> None:
    """fit() no longer rejects n_dims > 2 (SP-2): a 3-D gaussian_nd graph fits.

    The old ``NotImplementedError`` guard at ``n_dims > 2`` is gone; the
    parametric ``gaussian_nd`` kernel handles ≥3-D, with D inferred from the
    node's indexed ``center_<i>`` parameters. (Full parameter recovery is
    asserted in ``test_fit_nd.py``; here we pin only that the guard is lifted.)
    """
    g = np.linspace(-2.0, 2.0, 6)
    xx, yy, zz = np.meshgrid(g, g, g)
    coords = np.column_stack([xx.ravel(), yy.ravel(), zz.ravel()])
    truth_y = 3.0 * np.exp(
        -(coords[:, 0] ** 2) / 2.0
        - (coords[:, 1] ** 2) / 2.0
        - (coords[:, 2] ** 2) / 2.0
    )
    graph = FitGraph(
        nodes=[
            ModelNodeSpec(
                id="g",
                model_type=ModelType.GAUSSIAN_ND,
                parameters={
                    "amplitude": Parameter(value=2.0),
                    "center_0": Parameter(value=0.2),
                    "center_1": Parameter(value=0.0),
                    "center_2": Parameter(value=-0.1),
                    "sigma_0": Parameter(value=1.0, min=1e-3),
                    "sigma_1": Parameter(value=1.0, min=1e-3),
                    "sigma_2": Parameter(value=1.0, min=1e-3),
                },
            )
        ]
    )
    result = fit(graph, MeasurementData(x=coords.tolist(), y=truth_y.tolist()))
    assert result.success


def test_fit_accepts_2d_data() -> None:
    """fit() accepts n_dims == 2 data with a Gaussian2D node and recovers params.

    The n_dims==2 guard forwards the point-major x buffer to the executor's
    strided path and the solver recovers the 2-D Gaussian parameters. (2-D fitting
    has landed — see test_fit_2d.py — so this is a real passing test, not xfail.)
    """
    graph = FitGraph(
        nodes=[
            ModelNodeSpec(
                id="g2",
                model_type=ModelType.GAUSSIAN2D,
                parameters={
                    "amplitude": Parameter(value=3.0),
                    "center_x": Parameter(value=0.5),
                    "center_y": Parameter(value=-1.0),
                    "sigma_x": Parameter(value=1.0, min=1e-3),
                    "sigma_y": Parameter(value=1.5, min=1e-3),
                },
            )
        ]
    )
    # 5x5 grid of (x, y) coordinates, point-major.
    xs = np.linspace(-2.0, 2.0, 5)
    ys = np.linspace(-3.0, 1.0, 5)
    coords = [[x, y] for x in xs for y in ys]
    values = [
        3.0 * np.exp(-((x - 0.5) ** 2) / 2.0 - ((y + 1.0) ** 2) / (2.0 * 1.5**2))
        for x, y in coords
    ]
    data = MeasurementData(x=coords, y=values)
    result = fit(graph, data)
    assert result.params["g2.amplitude"].value == pytest.approx(3.0, abs=1e-2)


def test_fit_unknown_solver_falls_back_to_lm() -> None:
    """Unknown solver strings fall back to LM without raising."""
    graph = FitGraph(
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
    data = MeasurementData(x=[0.0, 1.0, 2.0], y=[1.0, 0.5, 0.1])
    opts = FitOptions(solver="not_a_real_solver")
    result = fit(graph, data, opts)
    assert len(result.best_fit) == 3
