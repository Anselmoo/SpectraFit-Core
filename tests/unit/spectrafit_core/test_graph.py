"""Phase 8 — test_graph.py

Tests for single-node and multi-node DAG compilation and evaluation.
"""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from spectrafit_core import (
    FitGraph,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
)
from spectrafit_core.graph import ExprEdge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gaussian_node(
    node_id: str, amplitude: float = 1.0, center: float = 0.0, sigma: float = 1.0
) -> ModelNodeSpec:
    return ModelNodeSpec(
        id=node_id,
        model_type=ModelType.GAUSSIAN,
        parameters={
            "amplitude": Parameter(value=amplitude),
            "center": Parameter(value=center),
            "sigma": Parameter(value=sigma, min=1e-3),
        },
    )


def _const_node(node_id: str, c: float = 0.0) -> ModelNodeSpec:
    return ModelNodeSpec(
        id=node_id,
        model_type=ModelType.CONSTANT,
        parameters={
            "c": Parameter(value=c),
        },
    )


def _make_data(x_vals: list[float]) -> MeasurementData:
    return MeasurementData(x=x_vals, y=[0.0] * len(x_vals))


# ---------------------------------------------------------------------------
# Single-node compilation & evaluation
# ---------------------------------------------------------------------------


def test_single_node_graph_compiles() -> None:
    """FitGraph with a single node compiles without error."""
    g = FitGraph(nodes=[_gaussian_node("g")])
    compiled = g.compile()
    assert compiled is g  # compile() returns self in the Python layer


def test_single_node_eval_returns_correct_length() -> None:
    g = FitGraph(nodes=[_gaussian_node("g")])
    data = _make_data([0.0, 1.0, 2.0])
    result = g.eval({"g.amplitude": 1.0, "g.center": 0.0, "g.sigma": 1.0}, data)
    assert len(result) == 3


def test_single_node_gaussian_eval_at_center() -> None:
    A, c, sigma = 2.5, 1.0, 0.5
    g = FitGraph(nodes=[_gaussian_node("g", amplitude=A, center=c, sigma=sigma)])
    data = _make_data([c])
    result = g.eval({"g.amplitude": A, "g.center": c, "g.sigma": sigma}, data)
    assert result[0] == pytest.approx(A, abs=1e-9)


def test_single_node_eval_components_keys() -> None:
    g = FitGraph(nodes=[_gaussian_node("peak")])
    data = _make_data([0.0, 1.0])
    comps = g.eval_components(
        {"peak.amplitude": 1.0, "peak.center": 0.0, "peak.sigma": 1.0}, data
    )
    assert "peak" in comps
    assert len(comps["peak"]) == 2


# ---------------------------------------------------------------------------
# Multi-node DAG evaluation
# ---------------------------------------------------------------------------


def test_two_node_graph_sum_of_components() -> None:
    """Sum of two Gaussian components equals evaluate() output."""
    g = FitGraph(nodes=[_gaussian_node("g1"), _gaussian_node("g2")])
    x = np.linspace(-3.0, 3.0, 20).tolist()
    data = _make_data(x)
    params = {
        "g1.amplitude": 2.0,
        "g1.center": -1.0,
        "g1.sigma": 0.5,
        "g2.amplitude": 1.5,
        "g2.center": 1.0,
        "g2.sigma": 0.8,
    }
    total = g.eval(params, data)
    comps = g.eval_components(params, data)

    sum_components = np.asarray(comps["g1"]) + np.asarray(comps["g2"])
    np.testing.assert_allclose(sum_components, total, atol=1e-10)


def test_gaussian_plus_constant_eval() -> None:
    """Gaussian + Constant eval equals element-wise sum."""
    g = FitGraph(nodes=[_gaussian_node("peak"), _const_node("bg", c=0.5)])
    data = _make_data([0.0, 1.0, 2.0])
    params = {
        "peak.amplitude": 3.0,
        "peak.center": 0.0,
        "peak.sigma": 1.0,
        "bg.c": 0.5,
    }
    total = g.eval(params, data)
    comps = g.eval_components(params, data)

    for i in range(3):
        assert comps["peak"][i] + comps["bg"][i] == pytest.approx(total[i], abs=1e-10)


def test_three_node_sum() -> None:
    """Three-node graph: sum of all components equals total."""
    g = FitGraph(
        nodes=[
            _gaussian_node("g1", amplitude=2.0, center=-2.0, sigma=0.5),
            _gaussian_node("g2", amplitude=3.0, center=0.0, sigma=0.8),
            _const_node("bg", c=1.0),
        ]
    )
    x = np.linspace(-5.0, 5.0, 25).tolist()
    data = _make_data(x)
    params = {
        "g1.amplitude": 2.0,
        "g1.center": -2.0,
        "g1.sigma": 0.5,
        "g2.amplitude": 3.0,
        "g2.center": 0.0,
        "g2.sigma": 0.8,
        "bg.c": 1.0,
    }
    total = g.eval(params, data)
    comps = g.eval_components(params, data)

    component_sum = (
        np.asarray(comps["g1"]) + np.asarray(comps["g2"]) + np.asarray(comps["bg"])
    )
    np.testing.assert_allclose(component_sum, total, atol=1e-10)


# ---------------------------------------------------------------------------
# Validation: duplicate node ids, unknown nodes in edges
# ---------------------------------------------------------------------------


def test_duplicate_node_ids_raise() -> None:
    with pytest.raises(ValidationError):
        FitGraph(nodes=[_gaussian_node("n"), _gaussian_node("n")])


def test_expr_edge_with_unknown_target_raises() -> None:
    with pytest.raises(ValidationError):
        FitGraph(
            nodes=[_gaussian_node("g")],
            expr_edges=[
                ExprEdge(
                    target_node="nonexistent",
                    target_param="amplitude",
                    expression="g.amplitude * 0.5",
                )
            ],
        )


def test_expr_edge_with_unknown_source_in_expression_raises() -> None:
    with pytest.raises(ValidationError):
        FitGraph(
            nodes=[_gaussian_node("g")],
            expr_edges=[
                ExprEdge(
                    target_node="g",
                    target_param="amplitude",
                    expression="bogus.amplitude * 0.5",
                )
            ],
        )


# ---------------------------------------------------------------------------
# FitGraph schema_version and JSON round-trip
# ---------------------------------------------------------------------------


def test_fitgraph_schema_version() -> None:
    g = FitGraph(nodes=[_gaussian_node("g")])
    assert g.schema_version == "0.1"


def test_fitgraph_empty_expr_edges_by_default() -> None:
    g = FitGraph(nodes=[_gaussian_node("g")])
    assert g.expr_edges == []


def test_fitgraph_json_round_trip() -> None:
    g = FitGraph(
        nodes=[_gaussian_node("g1"), _const_node("bg")],
    )
    j = g.model_dump_json()
    g2 = FitGraph.model_validate_json(j)
    assert g == g2
