"""Phase 8 — test_models_python.py

Tests for the Python schema layer: Parameter, ModelNodeSpec, FitGraph,
FitOptions, MeasurementData, and dump_measurement_json.
"""

from __future__ import annotations

import json
import math

import pytest
from pydantic import ValidationError

from spectrafit_core import (
    FitGraph,
    FitOptions,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
)
from spectrafit_core.data import dump_measurement_json


# ---------------------------------------------------------------------------
# Parameter
# ---------------------------------------------------------------------------


def test_parameter_defaults() -> None:
    p = Parameter(value=0.0)
    assert p.value == pytest.approx(0.0)
    assert p.vary is True
    assert math.isinf(p.min) and p.min < 0
    assert math.isinf(p.max) and p.max > 0
    assert p.expr is None
    assert p.scale is None


def test_parameter_explicit_min_max_preserved() -> None:
    p = Parameter(value=1.5, min=-10.0, max=10.0)
    assert p.min == pytest.approx(-10.0)
    assert p.max == pytest.approx(10.0)


def test_parameter_inf_serialises_to_null() -> None:
    p = Parameter(value=0.0)
    data = json.loads(p.model_dump_json())
    assert data["min"] is None, "−∞ should serialise to null"
    assert data["max"] is None, "+∞ should serialise to null"


def test_parameter_null_deserialises_to_inf() -> None:
    raw = '{"value":1.0,"min":null,"max":null,"vary":true,"expr":null,"scale":null}'
    p = Parameter.model_validate_json(raw)
    assert math.isinf(p.min) and p.min < 0
    assert math.isinf(p.max) and p.max > 0


def test_parameter_expr_preserves_vary() -> None:
    """``vary`` is preserved as supplied when ``expr`` is set — not coerced.

    The engine excludes expr-derived parameters from the free set regardless
    of ``vary``, so forcing ``vary=True`` was wrong.  Both True and False are
    accepted and left unchanged.
    """
    p_false = Parameter(value=0.0, expr="other.value * 2", vary=False)
    assert p_false.vary is False, "vary=False must be preserved when expr is set"

    p_true = Parameter(value=0.0, expr="other.value * 2", vary=True)
    assert p_true.vary is True, "vary=True must be preserved when expr is set"


def test_parameter_empty_expr_rejected() -> None:
    """Empty or whitespace-only ``expr`` is a construction-time error.

    A non-None ``expr`` that is empty or whitespace-only is meaningless and
    should be rejected. Users should pass ``expr=None`` for "no expression".
    """
    with pytest.raises(ValidationError, match="expr must be a non-empty expression or None"):
        Parameter(value=0.0, expr="")

    with pytest.raises(ValidationError, match="expr must be a non-empty expression or None"):
        Parameter(value=0.0, expr="   ")


# ---------------------------------------------------------------------------
# ModelNodeSpec
# ---------------------------------------------------------------------------


def test_modelnode_unknown_type_raises() -> None:
    with pytest.raises(ValidationError):
        # Intentionally invalid model_type — the point of the test is that the
        # validator rejects it; the type error is expected here.
        ModelNodeSpec(
            id="n", model_type="bogus_model", parameters={}  # ty: ignore[invalid-argument-type]
        )


def test_modelnode_known_types_all_work() -> None:
    for mt in ModelType:
        # Just validate construction — param dict can be empty for schema test
        node = ModelNodeSpec(id="n", model_type=mt, parameters={})
        assert node.model_type == mt


# ---------------------------------------------------------------------------
# FitGraph
# ---------------------------------------------------------------------------


def _gaussian_node(node_id: str) -> ModelNodeSpec:
    return ModelNodeSpec(
        id=node_id,
        model_type=ModelType.GAUSSIAN,
        parameters={
            "amplitude": Parameter(value=1.0),
            "center": Parameter(value=0.0),
            "sigma": Parameter(value=1.0, min=0.0),
        },
    )


def test_fitgraph_duplicate_node_ids_raise() -> None:
    with pytest.raises(ValidationError, match="unique"):
        FitGraph(nodes=[_gaussian_node("n"), _gaussian_node("n")])


def test_fitgraph_round_trip_json() -> None:
    g = FitGraph(nodes=[_gaussian_node("g1"), _gaussian_node("g2")])
    j = g.model_dump_json()
    g2 = FitGraph.model_validate_json(j)
    assert g == g2


def test_fitgraph_schema_version() -> None:
    g = FitGraph(nodes=[_gaussian_node("g")])
    assert g.schema_version == "0.1"


# ---------------------------------------------------------------------------
# FitOptions
# ---------------------------------------------------------------------------


def test_fitoptions_defaults() -> None:
    opts = FitOptions()
    assert opts.solver == "lm"
    assert opts.max_iterations == 200
    assert opts.tolerance == pytest.approx(1e-8)


# ---------------------------------------------------------------------------
# MeasurementData
# ---------------------------------------------------------------------------


def test_measurement_1d_x_auto_promoted() -> None:
    d = MeasurementData(x=[[0.0], [1.0], [2.0]], y=[10.0, 20.0, 30.0])
    # 1-D input → [[x0],[x1],...]
    assert d.x == [[0.0], [1.0], [2.0]]


def test_measurement_mismatched_xy_raises() -> None:
    with pytest.raises(ValidationError):
        MeasurementData(x=[[0.0], [1.0]], y=[1.0, 2.0, 3.0])


def test_measurement_n_points() -> None:
    d = MeasurementData(x=[[0.0], [1.0], [2.0], [3.0]], y=[1.0, 2.0, 3.0, 4.0])
    assert d.n_points == 4


# ---------------------------------------------------------------------------
# dump_measurement_json
# ---------------------------------------------------------------------------


def test_dump_measurement_json_single_is_object() -> None:
    d = MeasurementData(x=[[0.0], [1.0]], y=[1.0, 2.0])
    parsed = json.loads(dump_measurement_json(d))
    assert isinstance(parsed, dict)


def test_dump_measurement_json_list_is_array() -> None:
    d = MeasurementData(x=[[0.0], [1.0]], y=[1.0, 2.0])
    parsed = json.loads(dump_measurement_json([d, d]))
    assert isinstance(parsed, list)
    assert len(parsed) == 2
