"""PyO3 binding-coverage tests for the remaining uncovered branches in
``crates/spectrafit-core/src/lib.rs`` (Task #85 binding-coverage follow-up).

``test_core_error_paths.py`` already exercises most of the explicit
validation branches; this file targets the handful that were still
uncovered when running only ``tests/unit/spectrafit_core``:

* ``model_type_wire_strings`` (L537-540) — the whole function body, never
  called from anywhere in this test tree (only ``tests/parity`` and
  ``tests/meta`` call it, and those are out of scope for this suite).
* ``collect_eval_x`` (L124) — the ``None => Ok(Vec::new())`` arm, reached
  only when ``MeasurementInput::into_vec()`` yields zero datasets.
* ``fit`` (L207) — the success-path JSON serialisation of the ``FitResult``.
  Every existing direct ``_core.fit(...)`` call in this tree hits an error
  branch; the Python-level ``fit()`` wrapper calls ``core.fit_arrays``, not
  ``core.fit``, so the JSON entrypoint's own happy path was never exercised.

This file's scope is deliberately narrow: wire strings, ``collect_eval_x``,
the JSON ``fit()`` success path, and (in the module docstring only, since no
legitimate input reaches it — see below) the panic-guard notes.
``transpose_x_for_solver``'s rejection branches (empty-coordinate-row,
ragged-x, the zero-point no-op) and ``split_array_datasets``'s
``checked_mul`` overflow / sigma-slice-out-of-bounds guards are exercised
through ``fit_arrays``/``fit_arrays_numpy`` in ``test_binding_array_paths.py``
instead ("array/shape/transpose/split paths" scope) — they are not repeated
here to avoid two files asserting the same Rust lines.

The Rust-panic branch inside ``guard`` (L74-82) is intentionally NOT
exercised here: see ``test_panic_boundary.py``'s
``test_fit_arrays_maps_a_rust_panic_to_valueerror`` (skipped, with a
recorded reasoning) for why no legitimate Python-reachable panic input is
currently known. That analysis was re-verified while writing this file (see
open_issues in the accompanying report) and still holds.
"""

from __future__ import annotations

import json

from spectrafit_core import ModelType, _core

# ---------------------------------------------------------------------------
# Local helpers (mirrors test_core_error_paths.py's inline builders).
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
                },
            ],
            "expr_edges": [],
        },
    )


def _params_json(node_id: str, amplitude: float, center: float, sigma: float) -> str:
    return json.dumps(
        {
            f"{node_id}.amplitude": amplitude,
            f"{node_id}.center": center,
            f"{node_id}.sigma": sigma,
        },
    )


def _options_json() -> str:
    return json.dumps(
        {
            "schema_version": "0.1",
            "solver": "lm",
            "max_iterations": 50,
            "tolerance": 1e-8,
        },
    )


def _measurement_json(
    x: list[list[float]],
    y: list[float],
) -> str:
    return json.dumps(
        {
            "schema_version": "0.1",
            "x": x,
            "y": y,
            "sigma": None,
            "label": None,
        },
    )


# ---------------------------------------------------------------------------
# model_type_wire_strings (L537-540)
# ---------------------------------------------------------------------------


def test_model_type_wire_strings_matches_python_enum() -> None:
    """The Rust manifest's wire strings equal the Python ``ModelType`` set.

    ``tests/parity/test_schema_parity.py`` pins this same invariant, but that
    file is outside ``tests/unit/spectrafit_core`` and so does not exercise
    ``model_type_wire_strings`` when this suite runs in isolation.
    """
    wire = json.loads(_core.model_type_wire_strings())

    assert isinstance(wire, list)
    assert all(isinstance(s, str) for s in wire)
    assert len(wire) == len(set(wire)), "wire strings must be unique"

    python_wire = {m.value for m in ModelType}
    assert set(wire) == python_wire, (
        "ModelType drift between Python and Rust (the manifest is the source):\n"
        f"  only in Python: {sorted(python_wire - set(wire))}\n"
        f"  only in Rust:   {sorted(set(wire) - python_wire)}"
    )


# ---------------------------------------------------------------------------
# collect_eval_x — the `None => Ok(Vec::new())` arm (L124)
# ---------------------------------------------------------------------------


def test_evaluate_with_zero_datasets_returns_empty_array() -> None:
    """``MeasurementInput::Multi(vec![])`` (JSON ``[]``) has no `.first()`.

    ``collect_eval_x`` falls through to ``None => Ok(Vec::new())`` rather
    than the single/multi-dataset branches above it, so ``evaluate()``
    should succeed with an empty x grid and return an empty JSON array.
    """
    graph_j = _gaussian_graph_json()
    params_j = _params_json("g", amplitude=1.0, center=0.0, sigma=1.0)

    result = _core.evaluate(graph_j, params_j, "[]")

    assert json.loads(result) == []


# ---------------------------------------------------------------------------
# fit — the success-path JSON serialisation (L207)
# ---------------------------------------------------------------------------


def test_fit_json_boundary_success_path_serialises_result() -> None:
    """A valid direct ``_core.fit()`` call reaches the success branch.

    Every existing ``_core.fit(...)`` call in this test tree raises
    ``ValueError`` (deliberately, to pin an error path); the Python-level
    ``fit()`` wrapper never calls this JSON entrypoint at all (it uses
    ``fit_arrays``/``fit_arrays_numpy``). This is the only direct,
    successful exercise of the JSON `fit()` entrypoint's return-serialisation
    line in this suite.
    """
    graph_j = _gaussian_graph_json()
    options_j = _options_json()
    data_j = _measurement_json(x=[[0.0], [1.0], [2.0]], y=[1.0, 0.5, 0.25])

    result = _core.fit(graph_j, data_j, options_j)

    decoded = json.loads(result)
    assert decoded["schema_version"] == "0.1"
    assert decoded["success"] is True
    assert set(decoded["parameters"]) == {"g.amplitude", "g.center", "g.sigma"}
