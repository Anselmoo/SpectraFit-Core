"""Evaluate helpers exposed at the top-level Python API."""

from __future__ import annotations

import json
from collections.abc import Mapping
from importlib import import_module

import numpy as np

from .data import MeasurementInput, dump_measurement_json
from .graph import FitGraph, _dump_params_json


def evaluate(
    graph: FitGraph, params: Mapping[str, object], data: MeasurementInput
) -> np.ndarray:
    """Evaluate the summed model over ``data`` at fixed parameters (no fit).

    Validates ``graph`` into a :class:`~spectrafit_core.graph.FitGraph`, then
    calls the ``spectrafit_core._core`` PyO3 extension's ``evaluate`` (JSON-in,
    JSON-out): the graph, ``params``, and the measurement data are each
    serialised to JSON strings, the compiled Rust ``CompiledGraph`` sums every
    node's model contribution at the given parameter values (applying any
    ``expr_edges`` / per-parameter ``Parameter.expr`` ties), and the resulting
    per-point vector comes back as a JSON array that is decoded into a NumPy
    array. This is a pure forward evaluation — no solver iterations run.

    Args:
        graph: Model topology as a :class:`~spectrafit_core.graph.FitGraph`
            (or anything :meth:`FitGraph.model_validate` accepts). ``nodes``
            must have unique ids; ``expr_edges`` and per-parameter ``expr``
            constraints, if present, must form a DAG.
        params: Parameter values keyed by ``"node_id.param_name"`` (dotted
            notation), e.g. ``{"peak1.amplitude": 1.0, "peak1.center": 0.0}``.
            Values are JSON-encoded as-is (:class:`~pydantic.BaseModel`,
            :class:`numpy.ndarray`/:class:`numpy.generic`, and nested
            list/dict/mapping values are all converted to plain JSON via
            :func:`~spectrafit_core.graph._dump_params_json`).
        data: One or more datasets as a
            :class:`~spectrafit_core.data.MeasurementData` or a sequence
            thereof (anything accepted by
            :func:`~spectrafit_core.data.dump_measurement_json`). Only the
            ``x`` coordinates are used; ``y``/``sigma`` are ignored for
            evaluation.

    Returns:
        A 1-D :class:`numpy.ndarray` of ``float64`` model values, one per
        data point, in the same order as the flattened input ``x``.

    Raises:
        pydantic.ValidationError: If ``graph`` fails
            :class:`~spectrafit_core.graph.FitGraph` validation (duplicate
            node ids, unknown nodes/params referenced by an expression edge,
            or a cyclic constraint graph).
        ValueError: Propagated across the PyO3 boundary from the Rust engine
            if ``params`` is missing a parameter required by a node, or if a
            node references an undefined model type.

    """
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
    """Evaluate each model node separately, returning per-node component arrays.

    Identical in spirit to :func:`evaluate`, but calls the
    ``spectrafit_core._core`` extension's ``evaluate_components`` instead,
    which evaluates every node's model contribution independently (still
    applying any ``expr_edges`` / ``Parameter.expr`` ties) rather than
    summing them, so the returned components sum to what :func:`evaluate`
    (or :attr:`~spectrafit_core.result.FitResult.best_fit`) would return.
    Useful for plotting individual peaks/baselines under a shared fit.

    Args:
        graph: Model topology as a :class:`~spectrafit_core.graph.FitGraph`
            (or anything :meth:`FitGraph.model_validate` accepts). ``nodes``
            must have unique ids; ``expr_edges`` and per-parameter ``expr``
            constraints, if present, must form a DAG.
        params: Parameter values keyed by ``"node_id.param_name"`` (dotted
            notation). Values are JSON-encoded via
            :func:`~spectrafit_core.graph._dump_params_json`.
        data: One or more datasets as a
            :class:`~spectrafit_core.data.MeasurementData` or a sequence
            thereof. Only the ``x`` coordinates are used.

    Returns:
        A dict mapping each node's ``id`` to a 1-D :class:`numpy.ndarray` of
        ``float64`` model values for that node alone, one value per data
        point, in the same order as the flattened input ``x``.

    Raises:
        pydantic.ValidationError: If ``graph`` fails
            :class:`~spectrafit_core.graph.FitGraph` validation (duplicate
            node ids, unknown nodes/params referenced by an expression edge,
            or a cyclic constraint graph).
        ValueError: Propagated across the PyO3 boundary from the Rust engine
            if ``params`` is missing a parameter required by a node, or if a
            node references an undefined model type.

    """
    validated_graph = FitGraph.model_validate(graph)
    core = import_module("spectrafit_core._core")
    payload = core.evaluate_components(
        validated_graph.model_dump_json(),
        _dump_params_json(params),
        dump_measurement_json(data),
    )
    raw = json.loads(payload)
    return {key: np.asarray(value, dtype=float) for key, value in raw.items()}
