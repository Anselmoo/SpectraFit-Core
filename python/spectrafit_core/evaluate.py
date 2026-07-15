"""Evaluate helpers exposed at the top-level Python API."""

from __future__ import annotations

import json
from importlib import import_module
from collections.abc import Mapping

import numpy as np

from .data import MeasurementInput, dump_measurement_json
from .graph import FitGraph, _dump_params_json


def evaluate(
    graph: FitGraph, params: Mapping[str, object], data: MeasurementInput
) -> np.ndarray:
    """Evaluate model sum via PyO3 binding and return a numpy vector."""
    validated_graph = FitGraph.model_validate(graph)
    core = import_module("spectrafit_core._core")
    payload = core.evaluate(
        validated_graph.model_dump_json(),
        _dump_params_json(params),
        dump_measurement_json(data),
    )
    return np.asarray(json.loads(payload), dtype=float)


def evaluate_components(
    graph: FitGraph,
    params: Mapping[str, object],
    data: MeasurementInput,
) -> dict[str, np.ndarray]:
    """Evaluate per-node model components via PyO3 binding."""
    validated_graph = FitGraph.model_validate(graph)
    core = import_module("spectrafit_core._core")
    payload = core.evaluate_components(
        validated_graph.model_dump_json(),
        _dump_params_json(params),
        dump_measurement_json(data),
    )
    raw = json.loads(payload)
    return {key: np.asarray(value, dtype=float) for key, value in raw.items()}
