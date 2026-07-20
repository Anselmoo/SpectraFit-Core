from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from numpy.typing import NDArray
    import numpy as np

def fit(graph_json: str, data_json: str, options_json: str) -> str:
    """Run a full Levenberg-Marquardt fit and return the result as JSON.

    Args:
        graph_json: serialised `FitGraphSpec`.
        data_json: serialised `MeasurementInput` (single or array).
        options_json: serialised `FitOptionsSpec`.

    Returns:
        A JSON string matching the `FitResult` Python schema.

    Raises:
        ValueError: If the JSON is malformed or the graph is invalid.
    """
    ...

def fit_arrays(
    graph_json: str,
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    sigma: NDArray[np.float64] | None,
    dataset_sizes: list[int],
    n_dims: int,
    options_json: str,
) -> str:
    """Run a Levenberg-Marquardt fit using raw numpy arrays for measurement data.

    This eliminates JSON serialisation of x/y/sigma, which is the dominant
    bottleneck for large datasets (scales as O(n)).

    Args:
        graph_json: serialised `FitGraphSpec` (JSON string).
        x: flat 1-D numpy array of x-values in point-major layout (stride `n_dims`):
            point `i` of a dataset occupies the slice `x[i*n_dims .. (i+1)*n_dims]`,
            concatenated across datasets (shape `(n_total * n_dims,)`).
        y: flat 1-D numpy array of observed values (shape `(n_total,)`).
        sigma: optional 1-D numpy array of per-point σ (shape `(n_total,)`).
        dataset_sizes: Python list of `int` giving the number of points per
            dataset; must sum to `len(y)`.  Pass `[len(y)]` for a single dataset.
        n_dims: number of x-dimensions per point (1 or 2).  The flat `x`
            buffer is strided by this and reshaped to dims × points.
        options_json: serialised `FitOptionsSpec` (JSON string).

    Returns:
        A JSON string matching the `FitResult` Python schema.

    Raises:
        ValueError: If the JSON is malformed, the graph is invalid, or the array
            shapes are inconsistent (``n_total * n_dims != len(x)``).
    """
    ...

def fit_arrays_numpy(
    graph_json: str,
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    sigma: NDArray[np.float64] | None,
    dataset_sizes: list[int],
    n_dims: int,
    options_json: str,
) -> tuple[str, NDArray[np.float64]]:
    """Like `fit_arrays`, but bypasses JSON serialisation of per-point arrays.

    Returns `(compact_result_json, best_fit_array)` where:
    - `compact_result_json` contains parameters + scalar fit metrics only
      (best_fit / residuals / init_fit / components are stripped out).
    - `best_fit_array` is a 1-D float64 NumPy array of fitted values.

    This eliminates the dominant per-call overhead (~2 ms) when the caller
    only needs the fitted curve as a NumPy array, not as a JSON list.

    Args:
        graph_json: serialised `FitGraphSpec` (JSON string).
        x: flat 1-D numpy array of x-values in point-major layout (stride `n_dims`).
        y: flat 1-D numpy array of observed values.
        sigma: optional 1-D numpy array of per-point uncertainties.
        dataset_sizes: Python list of point counts per dataset; must sum to `len(y)`.
        n_dims: number of x-dimensions per point (1 or 2).
        options_json: serialised `FitOptionsSpec` (JSON string).

    Returns:
        A tuple `(compact_result_json, best_fit_array)` where `compact_result_json`
        is a JSON string and `best_fit_array` is a 1-D float64 NumPy array.

    Raises:
        ValueError: If the JSON is malformed, the graph is invalid, or the array
            shapes are inconsistent (``n_total * n_dims != len(x)``).
    """
    ...

def evaluate(graph_json: str, params_json: str, data_json: str) -> str:
    """Evaluate model at the given parameters.  Returns a flat JSON array [f64, ...].

    Raises:
        ValueError: If JSON is malformed or parameters are inconsistent.

    """
    ...

def evaluate_components(graph_json: str, params_json: str, data_json: str) -> str:
    """Evaluate each node independently and return a JSON object.

    Args:
        graph_json: serialised `FitGraphSpec`.
        params_json: flat dict `{"node.param": value, ...}` as JSON string.
        data_json: serialised `MeasurementInput`.

    Returns:
        A JSON object `{"node_id": [f64, ...], ...}`.

    Raises:
        ValueError: If JSON is malformed or parameters are inconsistent.

    """
    ...

def model_type_wire_strings() -> str:
    """Return the canonical wire-format string of every supported model type.

    The strings are returned in `ModelTypeStr` declaration order, sourced from
    the single Rust source of truth (the `model_manifest!`-generated
    `ModelTypeStr::ALL`).  This is the canonical model enumerator the Rust ↔
    Python `ModelType` parity test pins the hand-written Python enum against.

    Returns:
        A JSON-encoded array of canonical model-type wire strings.
    """
    ...
