"""Rust <-> Python schema and API-surface parity (Unit U4).

This module enforces that every Pydantic model in :mod:`spectrafit_core`
round-trips field-for-field through the Rust serde boundary exposed by the
``spectrafit_core._core`` extension module, and that the Python high-level API
surface matches the Rust capability set.

Round-trip strategy
-------------------
``_core`` does not expose a generic ``serialize``/``deserialize`` for each type,
so parity is exercised through the *real* boundary functions:

* **Input models** (``Parameter``, ``ModelNodeSpec``, ``FitGraph``,
  ``MeasurementData``, ``FitOptions``, ``ExprEdge``) are serialised by Pydantic
  and deserialised by Rust serde inside ``fit`` / ``evaluate``.  A missing or
  renamed field would surface as a ``ValueError`` from the Rust JSON parser.
* **Output models** (``FitResult``, ``ParameterResult``, ``DatasetSlice``) are
  produced by Rust serde and parsed by Pydantic.  ``extra="forbid"`` on the
  Python side means any unexpected Rust field would raise a
  ``ValidationError``; any missing required field likewise fails.

Any *intentional* asymmetry (e.g. ``±inf`` <-> ``null``) is documented in
``docs/PARITY.md`` and asserted positively here.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

import spectrafit_core as sc
from spectrafit_core import (
    DatasetSlice,
    ExprEdge,
    FitGraph,
    FitOptions,
    FitResult,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    ParameterResult,
    fit,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _gaussian_node(node_id: str = "g1", center: float = 0.0) -> ModelNodeSpec:
    """Build a canonical Gaussian node (amplitude/center/sigma per MODELS.md)."""
    return ModelNodeSpec(
        id=node_id,
        model_type=ModelType.GAUSSIAN,
        parameters={
            "amplitude": Parameter(value=1.0, min=0.0),
            "center": Parameter(value=center),
            "sigma": Parameter(value=1.0, min=1e-6),
        },
    )


def _gaussian_graph() -> FitGraph:
    return FitGraph(nodes=[_gaussian_node()])


def _gaussian_data() -> MeasurementData:
    x = np.linspace(-3.0, 3.0, 64)
    y = np.exp(-(x**2) / 2.0)
    return MeasurementData(x=x.tolist(), y=y.tolist())


def _run_fit() -> FitResult:
    return fit(_gaussian_graph(), _gaussian_data())


# ---------------------------------------------------------------------------
# Input-side round-trips: Pydantic JSON -> Rust serde (inside fit/evaluate)
# ---------------------------------------------------------------------------


def test_parameter_min_max_inf_serialises_as_null() -> None:
    """Parameter serialises ±inf bounds as JSON null (Rust ser_bound contract)."""
    payload = json.loads(Parameter(value=1.0).model_dump_json())
    assert payload["min"] is None
    assert payload["max"] is None
    assert payload["vary"] is True
    # Field set must match the Rust ParameterSpec field set exactly.
    assert set(payload) == {"value", "min", "max", "vary", "expr", "scale"}


def test_parameter_null_bounds_deserialise_to_inf() -> None:
    """Round-trip: Rust-style null bounds parse back to ±inf in Python."""
    js = '{"value":2.0,"min":null,"max":null,"vary":true,"expr":null,"scale":null}'
    p = Parameter.model_validate_json(js)
    assert p.min == float("-inf")
    assert p.max == float("inf")


def test_fit_graph_accepted_by_rust_boundary() -> None:
    """FitGraph + ModelNodeSpec + Parameter deserialise cleanly in Rust serde."""
    result = _run_fit()
    assert result.success is True
    assert set(result.parameters) == {"g1.amplitude", "g1.center", "g1.sigma"}


def test_measurement_and_options_accepted_by_rust_boundary() -> None:
    """MeasurementData + FitOptions cross the boundary without field drift."""
    opts = FitOptions(solver="lm", max_iterations=100, tolerance=1e-8)
    result = fit(_gaussian_graph(), _gaussian_data(), opts)
    assert result.success is True


def test_model_type_enum_parity() -> None:
    """Python ``ModelType`` is pinned to the Rust canonical model set.

    The Rust side exposes its single source of truth — the
    ``model_manifest!``-generated ``ModelTypeStr::ALL`` — via
    ``_core.model_type_wire_strings()``. Asserting the Python enum's values equal
    that set (rather than a hand-maintained list duplicated here) means adding a
    model to the Rust manifest forces the Python enum to follow, or THIS test
    fails — there is no longer a separate Python-side wire list to drift.
    """
    import spectrafit_core._core as core

    # `_core` is a compiled PyO3 extension with no type stubs, so the static
    # checker cannot see this function — the test itself is what verifies it.
    rust_wire = set(core.model_type_wire_strings())  # ty: ignore[unresolved-attribute]
    python_wire = {m.value for m in ModelType}
    assert python_wire == rust_wire, (
        "ModelType drift between Python and Rust (the manifest is the source):\n"
        f"  only in Python: {sorted(python_wire - rust_wire)}\n"
        f"  only in Rust:   {sorted(rust_wire - python_wire)}"
    )


def test_expr_edge_reaches_rust_and_is_applied() -> None:
    """ExprEdge fields round-trip into Rust, which now applies the tie.

    Expression edges are implemented (crates/spectrafit-graph/src/expr.rs:
    tied-parameter planning + cycle detection). A successful fit proves the
    edge deserialised across the boundary, and the enforced tie is asserted
    positively: ``g2.center`` is held at ``g1.center + 1`` at the solution
    (a field mismatch would instead raise a JSON parse error before the
    engine is reached).
    """
    graph = FitGraph(
        nodes=[_gaussian_node("g1", 0.0), _gaussian_node("g2", 1.0)],
        expr_edges=[
            ExprEdge(
                target_node="g2",
                target_param="center",
                expression="g1.center + 1",
            )
        ],
    )
    result = fit(graph, _gaussian_data())
    assert result.success is True
    g1_center = result.parameters["g1.center"].value
    g2_center = result.parameters["g2.center"].value
    assert g2_center == pytest.approx(g1_center + 1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Output-side round-trips: Rust serde JSON -> Pydantic (extra="forbid")
# ---------------------------------------------------------------------------


def test_fit_result_field_set_matches_rust() -> None:
    """Rust FitResultSpec JSON populates exactly the Python FitResult fields."""
    result = _run_fit()
    expected = {
        "schema_version",
        "parameters",
        "covariance",
        "covariance_param_order",
        "chi2",
        "reduced_chi2",
        "r_squared",
        "dof",
        "aic",
        "bic",
        "n_iter",
        "n_func_evals",
        "n_jac_evals",
        "success",
        "message",
        "best_fit",
        "residuals",
        "init_fit",
        "components",
        "dataset_slices",
        "condition_number",
        "n_de_generations",
        "cost_history",
        "gradient_norm_history",
        "params_history",
    }
    assert set(result.model_dump().keys()) == expected


def test_parameter_result_field_set_matches_rust() -> None:
    """ParameterResult carries exactly the Rust ParameterResultSpec fields."""
    pr = _run_fit().parameters["g1.amplitude"]
    assert set(pr.model_dump().keys()) == {
        "value",
        "min",
        "max",
        "vary",
        "expr",
        "scale",
        "name",
        "stderr",
    }
    assert pr.name == "g1.amplitude"


def test_fit_result_pydantic_roundtrip_is_lossless() -> None:
    """FitResult -> JSON -> FitResult preserves every scalar field."""
    result = _run_fit()
    restored = FitResult.model_validate_json(result.model_dump_json())
    assert restored.success == result.success
    assert restored.message == result.message
    assert restored.chi2 == result.chi2
    assert restored.dof == result.dof
    assert restored.parameters.keys() == result.parameters.keys()
    for key, pr in result.parameters.items():
        assert restored.parameters[key].value == pr.value


def test_dataset_slice_parity_for_multi_dataset_fit() -> None:
    """Multi-dataset fits emit Rust DatasetSliceSpec -> Python DatasetSlice."""
    data = _gaussian_data()
    x_flat: list[float] = [
        float(row[0]) for row in data.x
    ]  # ty: ignore  # data.x is (N,D) post-validation
    other = MeasurementData(
        x=[[v] for v in x_flat],
        y=[v * 0.9 for v in data.y],
    )
    result = fit(_gaussian_graph(), [data, other])
    assert result.dataset_slices is not None
    assert len(result.dataset_slices) == 2
    a_slice = result.dataset_slices[0]
    assert isinstance(a_slice, DatasetSlice)
    assert set(a_slice.model_dump().keys()) == {
        "label",
        "n_points",
        "best_fit",
        "residuals",
        "chi2",
    }


def test_result_min_max_bounds_round_trip_finite() -> None:
    """Finite bounds survive the Rust ParameterResultSpec serialise step."""
    result = fit(_gaussian_graph(), _gaussian_data())
    # amplitude has min=0.0 (finite, vary) — must come back finite, not null.
    amp = result.parameters["g1.amplitude"]
    assert amp.min == 0.0


# ---------------------------------------------------------------------------
# API-surface parity: Python high-level names <-> Rust capability set
# ---------------------------------------------------------------------------


def test_core_extension_exposes_expected_capabilities() -> None:
    """The Rust _core module exposes exactly the documented capability set."""
    import spectrafit_core._core as core

    core_fns = {name for name in dir(core) if not name.startswith("_")}
    assert core_fns == {
        "fit",
        "fit_arrays",
        "fit_arrays_numpy",
        "evaluate",
        "evaluate_components",
        # Canonical model-type enumerator: exposes the manifest-generated
        # ModelTypeStr::ALL so the Python ModelType enum is pinned to the single
        # Rust source (see test_model_type_enum_parity).
        "model_type_wire_strings",
    }


def test_python_public_api_matches_capabilities() -> None:
    """The Python public API surfaces the fit/evaluate/graph capability set."""
    # High-level callables that map onto Rust capabilities.
    assert {"fit", "fit_fast", "evaluate", "evaluate_components"} <= set(sc.__all__)
    # Graph carries the evaluate / evaluate_components methods.
    assert hasattr(FitGraph, "eval")
    assert hasattr(FitGraph, "eval_components")
    # Every exported name is importable from the package root.
    for name in sc.__all__:
        assert hasattr(sc, name), f"missing public export: {name}"


def test_no_unfit_drift_is_silently_introduced() -> None:
    """Guard: Python models forbid extras, so unknown Rust fields fail loudly.

    This documents the contract that protects the round-trips above — if a
    future Rust field is added without a Python counterpart, output parsing
    raises rather than silently dropping data.
    """
    for model in (
        Parameter,
        ParameterResult,
        FitResult,
        DatasetSlice,
        MeasurementData,
        FitOptions,
    ):
        assert model.model_config.get("extra") == "forbid", (
            f"{model.__name__} must forbid extras to detect Rust drift"
        )
