"""Top-level :func:`fit` entry point bridging Python contracts to the engine."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import cast

import numpy as np
from numpy.typing import NDArray

from .data import MeasurementData, MeasurementInput, normalize_measurement_input
from .graph import FitGraph
from .options import FitOptions
from .result import FitResult


# ---------------------------------------------------------------------------
# Private phase helpers
# ---------------------------------------------------------------------------


def _phase_validate_graph_options(
    graph: FitGraph,
    options: FitOptions | None,
) -> tuple[FitGraph, FitOptions]:
    """Validate and coerce graph + options; returns validated instances."""
    return FitGraph.model_validate(graph), FitOptions.model_validate(
        options or FitOptions()
    )


def _phase_prepare_arrays(
    data: MeasurementInput,
) -> tuple[
    NDArray[np.float64], NDArray[np.float64], NDArray[np.float64] | None, list[int], int
]:
    """Normalise measurement input and build flat numpy arrays for the Rust executor.

    Returns:
        ``(x_arr, y_arr, sigma_arr, sizes, n_dims)`` where *sigma_arr* is
        ``None`` when no dataset supplies uncertainties.
    """
    normalised = normalize_measurement_input(data)
    datasets: list[MeasurementData] = (
        [normalised] if isinstance(normalised, MeasurementData) else normalised
    )

    # N-D ready (SP-2): the executor strides the flat x buffer by n_dims and
    # reshapes each per-dataset chunk to dims × points, so any n_dims ≥ 1 flows
    # through end-to-end (1-D and 2-D use fixed kernels; ≥3-D uses the parametric
    # `gaussian_nd` kernel, whose dimensionality the Rust compiler infers from the
    # node's indexed `center_<i>` parameters).
    # ds.x is normalised to a list[list[float]] (N, D) matrix by MeasurementData._validate_x.
    # Cast to guarantee type safety for len/list operations below.
    datasets_with_typed_x: list[tuple[MeasurementData, list[list[float]]]] = [
        (ds, cast(list[list[float]], ds.x)) for ds in datasets
    ]
    n_dims = max(
        (len(row) for _ds, x in datasets_with_typed_x for row in x),
        default=1,
    )

    # Build flat numpy arrays — eliminates JSON serialisation of measurement
    # data, which scales O(n) and was the dominant bottleneck for large arrays.
    # x is laid out point-major (stride == n_dims): point i occupies the slice
    # x[i*n_dims : (i+1)*n_dims], which the Rust executor reshapes to dims ×
    # points per dataset.  Short rows are padded to n_dims so the stride holds.
    x_parts = [
        np.asarray(
            [c for row in x for c in (list(row) + [0.0] * (n_dims - len(row)))],
            dtype=np.float64,
        )
        for _ds, x in datasets_with_typed_x
    ]
    y_parts = [np.asarray(ds.y, dtype=np.float64) for ds in datasets]
    has_sigma = any(ds.sigma is not None for ds in datasets)
    sigma_parts = [
        np.asarray(ds.sigma, dtype=np.float64)
        if ds.sigma is not None
        else np.ones(len(ds.y), dtype=np.float64)
        for ds in datasets
    ]

    x_arr = np.concatenate(x_parts)
    y_arr = np.concatenate(y_parts)
    sigma_arr = np.concatenate(sigma_parts) if has_sigma else None
    sizes = [len(ds.y) for ds in datasets]
    return x_arr, y_arr, sigma_arr, sizes, n_dims


def _phase_load_core() -> ModuleType:
    """Import and return the compiled ``spectrafit_core._core`` extension."""
    return import_module("spectrafit_core._core")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fit(
    graph: FitGraph, data: MeasurementInput, options: FitOptions | None = None
) -> FitResult:
    """Run a Levenberg-Marquardt fit and return the result.

    Args:
        graph: Model topology as a ``FitGraph``.  ``expr_edges`` and
            per-parameter ``Parameter.expr`` (both equivalent constraint
            surfaces) are supported and evaluated per solver iteration by
            the engine.
        data: One or more ``MeasurementData`` datasets.  All datasets must
            share the same number of x-dimensions.  1-D, 2-D, and N-D x are
            accepted (≥3-D is fit by the parametric ``gaussian_nd`` kernel).
        options: Solver configuration; defaults to ``FitOptions()``.

    Returns:
        A ``FitResult`` with fitted parameters, uncertainties, and
        goodness-of-fit statistics.

    Raises:
        ValueError: If data dimensions are inconsistent.

    """
    validated_graph, validated_options = _phase_validate_graph_options(graph, options)
    core = _phase_load_core()
    x_arr, y_arr, sigma_arr, sizes, n_dims = _phase_prepare_arrays(data)

    result_json = core.fit_arrays(
        validated_graph.model_dump_json(),
        x_arr,
        y_arr,
        sigma_arr,
        sizes,
        n_dims,
        validated_options.model_dump_json(),
    )
    return FitResult.model_validate_json(result_json)


def fit_fast(
    graph: FitGraph, data: MeasurementInput, options: FitOptions | None = None
) -> tuple[FitResult, np.ndarray]:
    """Run a fit and return both the result and the best-fit curve as a NumPy array.

    Identical to :func:`fit` but avoids JSON-serialising the per-point arrays
    (best_fit, residuals, init_fit, components).  The best-fit curve is returned
    directly as the second element of the tuple, saving ~2 ms per call on typical
    spectra (~500 points).  The ``FitResult.best_fit`` field will be empty —
    use the returned array instead.

    Args:
        graph: Model topology as a ``FitGraph``.  ``expr_edges`` and
            per-parameter ``Parameter.expr`` are both supported.
        data: One or more ``MeasurementData`` datasets.
        options: Solver configuration; defaults to ``FitOptions()``.

    Returns:
        Tuple of ``(FitResult, best_fit_array)`` where ``best_fit_array`` is a
        1-D float64 NumPy array of length ``n_data_points``.

    Raises:
        ValueError: If data dimensions are inconsistent.

    """
    validated_graph, validated_options = _phase_validate_graph_options(graph, options)
    core = _phase_load_core()
    x_arr, y_arr, sigma_arr, sizes, n_dims = _phase_prepare_arrays(data)

    compact_json, best_fit_arr = core.fit_arrays_numpy(
        validated_graph.model_dump_json(),
        x_arr,
        y_arr,
        sigma_arr,
        sizes,
        n_dims,
        validated_options.model_dump_json(),
    )
    return FitResult.model_validate_json(compact_json), best_fit_arr
