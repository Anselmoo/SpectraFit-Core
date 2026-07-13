import math

import pytest
from pydantic import ValidationError

from spectrafit_core import (
    FitGraph,
    FitOptions,
    FitResult,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    _core,
    fit,
)


def _gaussian_graph_json() -> str:
    """One-component gaussian graph as JSON for direct ``_core`` FFI probing."""
    node = ModelNodeSpec(
        id="p",
        model_type=ModelType.GAUSSIAN,
        parameters={
            "amplitude": Parameter(value=1.0),
            "center": Parameter(value=0.0),
            "sigma": Parameter(value=1.0, min=0.0),
        },
    )
    return FitGraph(nodes=[node]).model_dump_json()


def test_evaluate_rejects_empty_coordinate_rows() -> None:
    """Ragged/empty x rows must raise ValueError, not silently fabricate x=0.0.

    Previously ``flatten_x`` used ``row.first().unwrap_or(&0.0)``, so a point
    with no coordinates (``x=[[], []]``) silently became ``x=0.0`` and the
    evaluator returned the curve at 0 — a wrong answer with no error. The clean
    FFI boundary must reject malformed input with a descriptive ValueError.
    """
    g = _gaussian_graph_json()
    params = '{"p.amplitude":1.0,"p.center":0.0,"p.sigma":1.0}'
    # x has two points, each with zero coordinates — malformed.
    data = MeasurementData(x=[[], []], y=[1.0, 2.0]).model_dump_json()
    with pytest.raises(ValueError):
        _core.evaluate(g, params, data)


def test_fit_arrays_rejects_zero_ndims() -> None:
    """fit_arrays with n_dims=0 returns a clean ValueError (not a panic)."""
    import numpy as np

    g = _gaussian_graph_json()
    o = FitOptions().model_dump_json()
    with pytest.raises(ValueError):
        _core.fit_arrays(
            g,
            np.array([0.0], dtype=float),
            np.array([1.0], dtype=float),
            None,
            [1],
            0,
            o,
        )


def test_fit_arrays_rejects_size_mismatch() -> None:
    """fit_arrays with dataset_sizes not summing to len(y) raises ValueError."""
    import numpy as np

    g = _gaussian_graph_json()
    o = FitOptions().model_dump_json()
    with pytest.raises(ValueError):
        _core.fit_arrays(
            g,
            np.array([0.0, 1.0], dtype=float),
            np.array([1.0, 1.0], dtype=float),
            None,
            [3],  # sum 3 != len(y) 2
            1,
            o,
        )


def test_fit_smoke_crosses_python_rust_json_boundary() -> None:
    graph = FitGraph(
        nodes=[
            ModelNodeSpec(
                id="peak",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=1.0),
                    "center": Parameter(value=0.0),
                    "sigma": Parameter(value=1.0, min=0.0),
                },
            )
        ]
    )
    data = MeasurementData(
        x=[0.0, 1.0, 2.0],
        y=[1.0, 0.5, 0.25],
        sigma=[1.0, 1.0, 1.0],
        label="smoke",
    )
    options = FitOptions(max_iterations=1, tolerance=1e-6)

    result = fit(graph, data, options)

    assert isinstance(result, FitResult)
    assert result.schema_version == "0.1"
    assert set(result.params) == {"peak.amplitude", "peak.center", "peak.sigma"}
    # Smoke test: max_iterations=1 so this is a single LM step, not a converged
    # fit. The faer trust-region core takes a deterministic first step to ~1.84
    # from the 1.0 start; assert the boundary round-trips a sane finite value
    # rather than baking in a solver-specific step magnitude.
    amp = result.params["peak.amplitude"].value
    assert isinstance(amp, float)
    assert 0.0 < amp < 10.0
    assert result.params["peak.sigma"].min == 0.0
    assert result.n_iter >= 0  # LM may converge in 0 iterations on trivial data
    assert isinstance(result.success, bool)
    assert isinstance(result.message, str)
    assert len(result.best_fit) == data.n_points
    assert len(result.residuals) == data.n_points
    assert len(result.init_fit) == data.n_points
    assert set(result.components) == {"peak"}
    assert len(result.components["peak"]) == data.n_points
    assert result.dataset_slices is None


# --- Input-boundary finite guard (Invariant: values crossing the FFI must be
# finite, or fail fast — NaN/inf must never reach the Rust solver silently) ---


def test_measurement_data_rejects_nonfinite_y() -> None:
    """A NaN observation is rejected at the boundary, not silently fit to NaN."""
    with pytest.raises(ValidationError, match="finite"):
        MeasurementData(x=[0.0, 1.0, 2.0], y=[1.0, math.nan, 0.25])


def test_measurement_data_rejects_inf_x() -> None:
    """An infinite coordinate is rejected at the boundary."""
    with pytest.raises(ValidationError, match="finite"):
        MeasurementData(x=[0.0, math.inf, 2.0], y=[1.0, 0.5, 0.25])


def test_measurement_data_rejects_nonfinite_sigma() -> None:
    """A non-finite weight is rejected at the boundary."""
    with pytest.raises(ValidationError, match="finite"):
        MeasurementData(
            x=[0.0, 1.0, 2.0], y=[1.0, 0.5, 0.25], sigma=[1.0, math.inf, 1.0]
        )


# --- Data-coercion edge cases (shape, emptiness, extreme-but-finite) ---


def test_measurement_data_accepts_single_point() -> None:
    """A single-point dataset (n_points=1) is valid."""
    data = MeasurementData(x=[1.0], y=[1.0])
    assert data.n_points == 1


def test_measurement_data_accepts_empty_dataset() -> None:
    """An empty dataset (n_points=0) is valid — no minimum-length guard exists."""
    data = MeasurementData(x=[], y=[])
    assert data.n_points == 0


def test_measurement_data_rejects_3d_x() -> None:
    """A 3-D x array is rejected (only 1-D and 2-D are accepted)."""
    import numpy as np

    with pytest.raises(ValidationError):
        MeasurementData(x=np.zeros((2, 2, 2)), y=[1.0, 2.0, 3.0, 4.0])  # type: ignore


def test_measurement_data_rejects_ragged_2d_x() -> None:
    """Ragged rows (rows of different lengths) cannot be coerced to float64."""
    with pytest.raises(ValidationError):
        MeasurementData(x=[[1.0, 2.0], [3.0]], y=[1.0, 2.0])


def test_measurement_data_accepts_extreme_finite_coordinates() -> None:
    """Extreme but finite coordinates (1e300) pass the finite guard."""
    import numpy as np
    from typing import cast

    data = MeasurementData(x=[1e300, -1e300], y=[1.0, 2.0])
    assert data.n_points == 2
    x_matrix = cast(list[list[float]], data.x)
    assert np.isfinite(x_matrix[0][0])
