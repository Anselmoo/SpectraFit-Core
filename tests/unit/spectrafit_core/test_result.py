"""Phase 8 — test_result.py

Tests for FitResult schema, serialisation, and properties.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from spectrafit_core import (
    FitGraph,
    FitResult,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    fit,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_gaussian_graph(node_id: str = "g") -> FitGraph:
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id=node_id,
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=2.0),
                    "center": Parameter(value=0.0),
                    "sigma": Parameter(value=1.0, min=1e-3),
                },
            )
        ]
    )


def _basic_fit() -> FitResult:
    x = np.linspace(-3.0, 3.0, 30)
    y = 2.0 * np.exp(-0.5 * x**2)
    data = MeasurementData(x=x.tolist(), y=y.tolist())
    return fit(_make_gaussian_graph(), data)


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------


def test_fitresult_accepts_fit_json() -> None:
    """FitResult.model_validate_json() must accept JSON produced by _core.fit."""
    result = _basic_fit()
    # If we get here without ValidationError the test passes.
    assert isinstance(result, FitResult)


def test_fitresult_json_round_trip_preserves_all_fields() -> None:
    result = _basic_fit()
    json_str = result.model_dump_json()
    result2 = FitResult.model_validate_json(json_str)

    assert result2.schema_version == result.schema_version
    assert result2.chi2 == pytest.approx(result.chi2)
    assert result2.r_squared == pytest.approx(result.r_squared)
    assert result2.dof == result.dof
    assert result2.success == result.success
    assert result2.message == result.message
    assert result2.n_iter == result.n_iter
    assert result2.best_fit == pytest.approx(result.best_fit)
    assert result2.residuals == pytest.approx(result.residuals)
    assert result2.init_fit == pytest.approx(result.init_fit)
    assert set(result2.params.keys()) == set(result.params.keys())
    assert result2.dataset_slices == result.dataset_slices


# ---------------------------------------------------------------------------
# params alias
# ---------------------------------------------------------------------------


def test_params_is_alias_for_parameters() -> None:
    result = _basic_fit()
    assert result.params is result.parameters


# ---------------------------------------------------------------------------
# ParameterResult.stderr
# ---------------------------------------------------------------------------


def test_stderr_is_float_for_free_params() -> None:
    result = _basic_fit()
    for name, pr in result.params.items():
        if pr.vary and pr.expr is None:
            # Free params should have stderr after a successful fit
            assert pr.stderr is not None, f"Expected stderr for free param {name}"
            assert isinstance(pr.stderr, float)


def test_stderr_is_none_for_fixed_param() -> None:
    x = np.linspace(-3.0, 3.0, 30)
    y = 2.0 * np.exp(-0.5 * x**2)
    graph = FitGraph(
        nodes=[
            ModelNodeSpec(
                id="g",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=2.0),
                    "center": Parameter(value=0.0, vary=False),  # fixed
                    "sigma": Parameter(value=1.0, min=1e-3),
                },
            )
        ]
    )
    data = MeasurementData(x=x.tolist(), y=y.tolist())
    result = fit(graph, data)

    center = result.params["g.center"]
    assert center.vary is False
    assert center.stderr is None


# ---------------------------------------------------------------------------
# covariance shape
# ---------------------------------------------------------------------------


def test_covariance_shape() -> None:
    """Covariance is n_free × n_free when present."""
    result = _basic_fit()
    n_free = sum(1 for p in result.params.values() if p.vary and p.expr is None)
    if result.covariance is not None:
        cov = result.covariance
        assert len(cov) == n_free
        for row in cov:
            assert len(row) == n_free


# ---------------------------------------------------------------------------
# dof = n_points - n_free_params
# ---------------------------------------------------------------------------


def test_dof_equals_n_points_minus_free_params() -> None:
    n_points = 30
    x = np.linspace(-3.0, 3.0, n_points)
    y = 2.0 * np.exp(-0.5 * x**2)
    data = MeasurementData(x=x.tolist(), y=y.tolist())
    result = fit(_make_gaussian_graph(), data)

    n_free = sum(1 for p in result.params.values() if p.vary and p.expr is None)
    assert result.dof == n_points - n_free


# ---------------------------------------------------------------------------
# schema_version
# ---------------------------------------------------------------------------


def test_schema_version_is_0_1() -> None:
    result = _basic_fit()
    assert result.schema_version == "0.1"


# ---------------------------------------------------------------------------
# best_fit / residuals length
# ---------------------------------------------------------------------------


def test_best_fit_and_residuals_length() -> None:
    n = 20
    x = np.linspace(-2.0, 2.0, n)
    y = np.exp(-0.5 * x**2)
    data = MeasurementData(x=x.tolist(), y=y.tolist())
    result = fit(_make_gaussian_graph(), data)

    assert len(result.best_fit) == n
    assert len(result.residuals) == n
    assert len(result.init_fit) == n


# ---------------------------------------------------------------------------
# condition_number (U3): schema parity + back-compat
# ---------------------------------------------------------------------------


def test_condition_number_field_exists_and_defaults_none() -> None:
    """The new field exists on the model and defaults to None."""
    assert "condition_number" in FitResult.model_fields
    assert FitResult().condition_number is None


def test_condition_number_back_compat_legacy_json() -> None:
    """Legacy JSON without ``condition_number`` deserialises to None."""
    legacy = (
        '{"schema_version":"0.1","parameters":{},"covariance":null,'
        '"chi2":0.0,"reduced_chi2":0.0,"r_squared":1.0,"dof":1,'
        '"aic":0.0,"bic":0.0,"n_iter":0,"success":true,"message":"converged",'
        '"best_fit":[],"residuals":[],"init_fit":[],"components":{}}'
    )
    result = FitResult.model_validate_json(legacy)
    assert result.condition_number is None


def test_condition_number_round_trips_when_present() -> None:
    """A populated ``condition_number`` survives a JSON round-trip."""
    result = FitResult(condition_number=12.5)
    result2 = FitResult.model_validate_json(result.model_dump_json())
    assert result2.condition_number == pytest.approx(12.5)


def test_fit_reports_condition_number() -> None:
    """A successful LM fit reports a finite condition number (>= 1).

    The Rust LM path computes ``condition_number`` from the SVD of ``JᵀJ`` at
    the solution and the value crosses the PyO3 boundary, so a well-conditioned
    Gaussian fit must surface a finite, >= 1 value. (Per-parameter ``scale``
    wiring is still TDD-red; see the Rust ``parameter_scale_changes_*`` test.)
    """
    result = _basic_fit()
    assert result.condition_number is not None
    assert math.isfinite(result.condition_number)
    assert result.condition_number >= 1.0
