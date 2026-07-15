"""Phase 8 — test_evaluate.py

Tests for standalone evaluate() and evaluate_components() — exercising both
the FitGraph Python wrapper and the _core boundary layer directly.
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
    evaluate,
    evaluate_components,
)
import spectrafit_core._core as _core


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
                            "value": 3.0,
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
                }
            ],
            "expr_edges": [],
        }
    )


def _params_json(node_id: str, amplitude: float, center: float, sigma: float) -> str:
    return json.dumps(
        {
            f"{node_id}.amplitude": amplitude,
            f"{node_id}.center": center,
            f"{node_id}.sigma": sigma,
        }
    )


def _data_json(x_vals: list[float]) -> str:
    return json.dumps(
        {
            "schema_version": "0.1",
            "x": [[v] for v in x_vals],
            "y": [0.0] * len(x_vals),
            "sigma": None,
            "label": None,
        }
    )


# ---------------------------------------------------------------------------
# _core boundary tests (direct JSON strings)
# ---------------------------------------------------------------------------


def test_core_evaluate_gaussian_at_center() -> None:
    """Gaussian at center x==center should equal amplitude."""
    graph_j = _gaussian_graph_json("g")
    params_j = _params_json("g", amplitude=3.0, center=2.0, sigma=1.0)
    data_j = _data_json([2.0])
    result = json.loads(_core.evaluate(graph_j, params_j, data_j))
    assert result[0] == pytest.approx(3.0, abs=1e-6)


def test_core_evaluate_lorentzian_at_center() -> None:
    """Lorentzian at center x==center should equal amplitude."""
    graph_j = json.dumps(
        {
            "schema_version": "0.1",
            "nodes": [
                {
                    "id": "l",
                    "model_type": "lorentzian",
                    "parameters": {
                        "amplitude": {
                            "value": 2.5,
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
                            "min": None,
                            "max": None,
                            "vary": True,
                            "expr": None,
                            "scale": None,
                        },
                    },
                }
            ],
            "expr_edges": [],
        }
    )
    params_j = json.dumps({"l.amplitude": 2.5, "l.center": 1.0, "l.sigma": 0.5})
    data_j = _data_json([1.0])
    result = json.loads(_core.evaluate(graph_j, params_j, data_j))
    assert result[0] == pytest.approx(2.5, abs=1e-6)


def test_core_evaluate_components_keys() -> None:
    graph_j = _gaussian_graph_json("peak")
    params_j = _params_json("peak", amplitude=1.0, center=0.0, sigma=1.0)
    data_j = _data_json([0.0, 1.0, 2.0])
    result = json.loads(_core.evaluate_components(graph_j, params_j, data_j))
    assert "peak" in result
    assert len(result["peak"]) == 3


def test_core_unknown_param_raises_value_error() -> None:
    graph_j = _gaussian_graph_json("g")
    # provide params for a completely different node id
    params_j = json.dumps(
        {"wrong.amplitude": 1.0, "wrong.center": 0.0, "wrong.sigma": 1.0}
    )
    data_j = _data_json([0.0])
    with pytest.raises(ValueError):
        _core.evaluate(graph_j, params_j, data_j)


# ---------------------------------------------------------------------------
# FitGraph Python wrapper tests
# ---------------------------------------------------------------------------


def _make_gaussian_graph(node_id: str = "g") -> FitGraph:
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id=node_id,
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=4.0),
                    "center": Parameter(value=1.0),
                    "sigma": Parameter(value=0.5, min=0.0),
                },
            )
        ]
    )


def _make_data(x_vals: list[float]) -> MeasurementData:
    return MeasurementData(x=[[value] for value in x_vals], y=[0.0] * len(x_vals))


def test_fitgraph_eval_gaussian_at_center() -> None:
    graph = _make_gaussian_graph("g")
    data = _make_data([1.0])
    # params as flat dict {node.param: value}
    params = {"g.amplitude": 4.0, "g.center": 1.0, "g.sigma": 0.5}
    result = graph.eval(params, data)
    assert result[0] == pytest.approx(4.0, abs=1e-6)


def test_fitgraph_eval_two_node_sum() -> None:
    """Gaussian + Constant: evaluate should return component sum."""
    graph = FitGraph(
        nodes=[
            ModelNodeSpec(
                id="peak",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=2.0),
                    "center": Parameter(value=0.0),
                    "sigma": Parameter(value=1.0, min=0.0),
                },
            ),
            ModelNodeSpec(
                id="bg",
                model_type=ModelType.CONSTANT,
                parameters={
                    "c": Parameter(value=1.5),
                },
            ),
        ]
    )
    data = _make_data([0.0, 1.0, 2.0])
    params = {
        "peak.amplitude": 2.0,
        "peak.center": 0.0,
        "peak.sigma": 1.0,
        "bg.c": 1.5,
    }
    total = graph.eval(params, data)
    comps = graph.eval_components(params, data)

    # Component sum should equal total
    for i in range(len(data.y)):
        assert comps["peak"][i] + comps["bg"][i] == pytest.approx(total[i], abs=1e-10)


def test_eval_components_sum_equals_evaluate() -> None:
    """eval_components values must sum to evaluate result (multi-node)."""
    graph = FitGraph(
        nodes=[
            ModelNodeSpec(
                id="g1",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=3.0),
                    "center": Parameter(value=-1.0),
                    "sigma": Parameter(value=0.8, min=0.0),
                },
            ),
            ModelNodeSpec(
                id="g2",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=2.0),
                    "center": Parameter(value=1.0),
                    "sigma": Parameter(value=0.6, min=0.0),
                },
            ),
        ]
    )
    x = np.linspace(-3.0, 3.0, 15).tolist()
    data = _make_data(x)
    params = {
        "g1.amplitude": 3.0,
        "g1.center": -1.0,
        "g1.sigma": 0.8,
        "g2.amplitude": 2.0,
        "g2.center": 1.0,
        "g2.sigma": 0.6,
    }
    total = graph.eval(params, data)
    comps = graph.eval_components(params, data)

    component_sum = np.asarray(comps["g1"]) + np.asarray(comps["g2"])
    np.testing.assert_allclose(component_sum, total, atol=1e-10)


def test_top_level_evaluate_exports_match_graph_methods() -> None:
    """Top-level evaluate helpers should match FitGraph method behavior."""
    graph = _make_gaussian_graph("g")
    data = _make_data([0.0, 1.0, 2.0])
    params = {"g.amplitude": 4.0, "g.center": 1.0, "g.sigma": 0.5}

    total_a = graph.eval(params, data)
    total_b = evaluate(graph, params, data)
    np.testing.assert_allclose(total_a, total_b, atol=1e-12)

    comps_a = graph.eval_components(params, data)
    comps_b = evaluate_components(graph, params, data)
    assert comps_a.keys() == comps_b.keys()
    for key in comps_a:
        np.testing.assert_allclose(comps_a[key], comps_b[key], atol=1e-12)
