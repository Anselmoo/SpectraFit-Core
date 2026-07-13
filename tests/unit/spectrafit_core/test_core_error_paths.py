"""PyO3 boundary error-path tests for ``spectrafit_core._core``.

These tests exercise the explicit error branches in
``crates/spectrafit-core/src/lib.rs`` that the happy-path tests in
``test_evaluate.py`` / ``test_fit.py`` do not reach:

* ``json_err`` for ``graph_json`` / ``data_json`` / ``params_json`` /
  ``options_json`` deserialisation failures.
* ``collect_eval_x`` multi-dataset rejection (``evaluate()`` /
  ``evaluate_components()``).
* ``collect_eval_x`` n-D coordinate rejection.
* ``split_array_datasets`` validation: ``dataset_sizes`` sum mismatch and
  ``n_total * n_dims`` mismatch (sigma length is enforced implicitly through
  the same dataset-size contract — see ``lib.rs`` ``split_array_datasets``).

Each test is intentionally scoped to a single error branch so coverage maps
1-to-1 with the binding shim's uncovered lines (Task #85 follow-up).
"""

from __future__ import annotations

import json

import numpy as np
import pytest

import spectrafit_core._core as _core


# ---------------------------------------------------------------------------
# Local helpers (duplicated from ``test_evaluate.py`` — three tiny builders
# kept inline to keep the diff small).
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


def _options_json() -> str:
    return json.dumps(
        {
            "schema_version": "0.1",
            "solver": "lm",
            "max_iterations": 50,
            "tolerance": 1e-8,
        }
    )


# ---------------------------------------------------------------------------
# json_err — invalid JSON payloads on each of the four boundary arguments.
# ---------------------------------------------------------------------------


def test_evaluate_rejects_invalid_graph_json() -> None:
    """Malformed ``graph_json`` must surface as ``ValueError('JSON parse error: …')``."""
    params_j = _params_json("g", amplitude=1.0, center=0.0, sigma=1.0)
    data_j = _data_json([0.0])
    with pytest.raises(ValueError, match="JSON parse error"):
        _core.evaluate("{not valid json", params_j, data_j)


def test_evaluate_rejects_invalid_params_json() -> None:
    """Malformed ``params_json`` must surface as ``ValueError('JSON parse error: …')``."""
    graph_j = _gaussian_graph_json("g")
    data_j = _data_json([0.0])
    with pytest.raises(ValueError, match="JSON parse error"):
        _core.evaluate(graph_j, "{bad params", data_j)


def test_evaluate_rejects_invalid_data_json() -> None:
    """Malformed ``data_json`` must surface as ``ValueError('JSON parse error: …')``."""
    graph_j = _gaussian_graph_json("g")
    params_j = _params_json("g", amplitude=1.0, center=0.0, sigma=1.0)
    with pytest.raises(ValueError, match="JSON parse error"):
        _core.evaluate(graph_j, params_j, "{bad data json")


def test_fit_rejects_invalid_options_json() -> None:
    """``_core.fit`` ``options_json`` parse failure must yield ``ValueError``.

    The graph + data are valid; the only deserialisation that should fail
    is options, which exercises the third ``json_err`` site in ``fit()``.
    """
    graph_j = _gaussian_graph_json("g")
    data_j = _data_json([0.0, 1.0, 2.0])
    with pytest.raises(ValueError, match="JSON parse error"):
        _core.fit(graph_j, data_j, "{bad options json")


# ---------------------------------------------------------------------------
# collect_eval_x — multi-dataset rejection on evaluate / evaluate_components.
# ---------------------------------------------------------------------------


def _multi_dataset_json(*x_vals_list: list[float]) -> str:
    """Build a ``MeasurementInput::Multi`` payload (untagged JSON array)."""
    return json.dumps(
        [
            {
                "schema_version": "0.1",
                "x": [[v] for v in x_vals],
                "y": [0.0] * len(x_vals),
                "sigma": None,
                "label": None,
            }
            for x_vals in x_vals_list
        ]
    )


def test_evaluate_rejects_multi_dataset_input() -> None:
    """``evaluate()`` must refuse > 1 dataset with a 'single dataset only' error."""
    graph_j = _gaussian_graph_json("g")
    params_j = _params_json("g", amplitude=1.0, center=0.0, sigma=1.0)
    data_j = _multi_dataset_json([0.0, 1.0], [2.0, 3.0])
    with pytest.raises(
        ValueError, match=r"evaluate\(\) supports a single dataset only"
    ):
        _core.evaluate(graph_j, params_j, data_j)


# ---------------------------------------------------------------------------
# collect_eval_x — n-D coordinate rejection on evaluate / evaluate_components.
# ---------------------------------------------------------------------------


def _nd_data_json() -> str:
    """Build a single-dataset payload whose first ``x`` row carries 2 dimensions."""
    return json.dumps(
        {
            "schema_version": "0.1",
            "x": [[0.0, 1.0]],  # 2-D point — triggers `row.len() > 1`.
            "y": [0.0],
            "sigma": None,
            "label": None,
        }
    )


def test_evaluate_rejects_nd_coordinates() -> None:
    """``evaluate()`` must refuse n-D x rows with a '1-D only' error."""
    graph_j = _gaussian_graph_json("g")
    params_j = _params_json("g", amplitude=1.0, center=0.0, sigma=1.0)
    with pytest.raises(ValueError, match=r"evaluate\(\) is 1-D only"):
        _core.evaluate(graph_j, params_j, _nd_data_json())


def test_evaluate_components_rejects_nd_coordinates() -> None:
    """``evaluate_components()`` shares ``collect_eval_x`` and must reject n-D too."""
    graph_j = _gaussian_graph_json("g")
    params_j = _params_json("g", amplitude=1.0, center=0.0, sigma=1.0)
    with pytest.raises(ValueError, match=r"evaluate\(\) is 1-D only"):
        _core.evaluate_components(graph_j, params_j, _nd_data_json())


# ---------------------------------------------------------------------------
# fit_arrays — split_array_datasets validation paths.
# ---------------------------------------------------------------------------


def test_fit_arrays_rejects_dataset_sizes_sum_mismatch() -> None:
    """``dataset_sizes`` summing to a value != ``len(y)`` must raise.

    Error message: ``"dataset_sizes sum (N) != len(y) (M)"`` from
    ``split_array_datasets`` in ``lib.rs``.
    """
    graph_j = _gaussian_graph_json("g")
    options_j = _options_json()
    # len(y) = 7 but dataset_sizes sums to 10.
    x = np.linspace(0.0, 1.0, 7, dtype=np.float64)
    y = np.zeros(7, dtype=np.float64)
    with pytest.raises(ValueError, match=r"dataset_sizes sum"):
        _core.fit_arrays(
            graph_j,
            x,
            y,
            None,
            [5, 5],
            1,
            options_j,
        )


def test_fit_arrays_rejects_x_length_mismatch_for_n_dims() -> None:
    """``n_total * n_dims`` != ``len(x)`` must raise.

    With ``n_dims=2``, a 7-point dataset requires 14 x values; supplying 7
    triggers the second validation arm in ``split_array_datasets``.
    """
    graph_j = _gaussian_graph_json("g")
    options_j = _options_json()
    x = np.linspace(0.0, 1.0, 7, dtype=np.float64)  # 7 values for 7 points × 2 dims.
    y = np.zeros(7, dtype=np.float64)
    with pytest.raises(ValueError, match=r"n_total \* n_dims"):
        _core.fit_arrays(
            graph_j,
            x,
            y,
            None,
            [7],
            2,
            options_j,
        )


def test_fit_arrays_rejects_zero_n_dims() -> None:
    """``n_dims == 0`` must raise the explicit ``"n_dims must be >= 1"`` error."""
    graph_j = _gaussian_graph_json("g")
    options_j = _options_json()
    x = np.zeros(0, dtype=np.float64)
    y = np.zeros(0, dtype=np.float64)
    with pytest.raises(ValueError, match=r"n_dims must be >= 1"):
        _core.fit_arrays(
            graph_j,
            x,
            y,
            None,
            [0],
            0,
            options_j,
        )


# ---------------------------------------------------------------------------
# A2 follow-up — typed GraphError / SolverError variants reach the PyO3
# boundary as PyValueError (CoreError → PyValueError mapping in
# ``crates/spectrafit-core/src/lib.rs``).
#
# Each of these paths used to construct ``CoreError::Eval(format!(...))``
# directly; after the boundary-error audit they construct a typed
# ``GraphError`` / ``SolverError`` variant that flows through the
# ``From<GraphError|SolverError> for CoreError`` impl before reaching the
# Python boundary. The user-visible behaviour (a ValueError with a
# descriptive message) is unchanged; these tests pin that behaviour so a
# regression to a panic / abort is caught here.
# ---------------------------------------------------------------------------


def _two_node_same_id_graph_json() -> str:
    """Build a graph with two nodes sharing an id — triggers ``GraphError::DuplicateNodeId``."""
    node = {
        "id": "dup",
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
    }
    return json.dumps(
        {
            "schema_version": "0.1",
            "nodes": [node, node],
            "expr_edges": [],
        }
    )


def test_evaluate_rejects_duplicate_node_id() -> None:
    """Duplicate node ids raise ``ValueError`` via ``GraphError::DuplicateNodeId``."""
    graph_j = _two_node_same_id_graph_json()
    params_j = _params_json("dup", amplitude=1.0, center=0.0, sigma=1.0)
    data_j = _data_json([0.0])
    with pytest.raises(ValueError, match=r"duplicate node id"):
        _core.evaluate(graph_j, params_j, data_j)


def test_fit_rejects_duplicate_node_id() -> None:
    """``fit()`` shares the compile path; the same typed error must surface."""
    graph_j = _two_node_same_id_graph_json()
    options_j = _options_json()
    data_j = _data_json([0.0, 1.0, 2.0])
    with pytest.raises(ValueError, match=r"duplicate node id"):
        _core.fit(graph_j, data_j, options_j)


def _varpro_with_expr_edge_graph_json() -> str:
    """Build a Gaussian graph with an ``expr_edge`` — VarPro must reject this."""
    return json.dumps(
        {
            "schema_version": "0.1",
            "nodes": [
                {
                    "id": "g1",
                    "model_type": "gaussian",
                    "parameters": {
                        "amplitude": {
                            "value": 1.0,
                            "min": None,
                            "max": None,
                            # vary=False because amplitude is the tie target;
                            # leaving it free would compile-error first.
                            "vary": False,
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
            "expr_edges": [
                {
                    "target_node": "g1",
                    "target_param": "amplitude",
                    "expression": "2.0",
                }
            ],
        }
    )


def test_fit_varpro_rejects_expr_edges() -> None:
    """``solver='varpro'`` with ``expr_edges`` raises a typed
    ``SolverError::VarproExprEdgesUnsupported`` that maps to ``ValueError``."""
    graph_j = _varpro_with_expr_edge_graph_json()
    options_j = json.dumps(
        {
            "schema_version": "0.1",
            "solver": "varpro",
            "max_iterations": 50,
            "tolerance": 1e-8,
        }
    )
    data_j = _data_json([0.0, 1.0, 2.0])
    # T5 broadened the message to cover both tie surfaces (expr_edges + Parameter.expr).
    with pytest.raises(ValueError, match=r"varpro.*does not support tied parameters"):
        _core.fit(graph_j, data_j, options_j)


def test_evaluate_rejects_unknown_model_type() -> None:
    """An unknown ``model_type`` string deserialises only when the JSON layer
    accepts it; we instead exercise the model-registry lookup that the typed
    ``GraphError::UnknownModelType`` variant guards by sending a JSON value
    matching the wire format. ``ModelTypeStr`` is `serde(rename_all = ...)`,
    so an unknown token is rejected at deserialisation as a ``JSON parse
    error`` — which still proves the boundary maps a graph-malformedness to
    ``ValueError`` (the typed variant is exercised by the in-tree Rust test
    `compile_unknown_model_type_emits_graph_error_variant`)."""
    graph_j = json.dumps(
        {
            "schema_version": "0.1",
            "nodes": [
                {
                    "id": "g",
                    "model_type": "not_a_real_model",
                    "parameters": {},
                }
            ],
            "expr_edges": [],
        }
    )
    params_j = "{}"
    data_j = _data_json([0.0])
    with pytest.raises(ValueError):
        _core.evaluate(graph_j, params_j, data_j)
