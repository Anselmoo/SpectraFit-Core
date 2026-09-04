r"""Metamorphic relations for the graph compiler (`crates/spectrafit-graph`).

Neither relation below needs a known-correct answer — that is the point of a
metamorphic relation: it holds for *any* valid graph, so the test can compare
two outputs of the system under test to each other instead of to an oracle.

1. **Superposition** — a two-node graph must evaluate to the sum of two
   independent one-node graphs, to machine epsilon
   ($\mathrm{atol} = 10^{-12}$, not exact equality, since floating-point
   summation order legitimately differs between "sum two evaluations" and
   "evaluate one graph with two nodes"). A failure at that tolerance means
   `crates/spectrafit-graph/src/executor.rs` accumulates node contributions
   incorrectly, not merely in a different order.
2. **Serialisation round-trip** — compiling a graph, serialising it to JSON,
   and compiling the result must reproduce the identical curve
   ($\mathrm{atol} = 0$, exact bit-for-bit equality). Every number crossing
   the PyO3 boundary is serialised as JSON, so this also exercises float
   fidelity end to end.

If either relation fails, that failure is the deliverable: report the
magnitude of the violation rather than loosening the tolerance to make the
test pass.
"""

from __future__ import annotations

import numpy as np
from numpy.testing import assert_allclose
from spectrafit_core import (
    FitGraph,
    MeasurementData,
    compose,
    evaluate,
    evaluate_components,
    gaussian,
    lorentzian,
)

_X = np.linspace(-5.0, 5.0, 300)

# Fixed initial values for each one-node building block. Kept in one place so
# every helper below builds the identical node for a given id.
_NODE_FACTORIES = {
    "p0": lambda: gaussian("p0", amplitude=3.0, center=-1.2, sigma=0.7),
    "p1": lambda: lorentzian("p1", amplitude=2.0, center=1.4, sigma=0.5),
}
_NODE_PARAMS = {
    "p0": {"p0.amplitude": 3.0, "p0.center": -1.2, "p0.sigma": 0.7},
    "p1": {"p1.amplitude": 2.0, "p1.center": 1.4, "p1.sigma": 0.5},
}


def _graph_with(ids: list[str]) -> FitGraph:
    """Build a validated ``FitGraph`` containing exactly the named nodes.

    Args:
        ids: Node ids to include, drawn from ``_NODE_FACTORIES``.

    Returns:
        The compiled ``FitGraph`` (compilation happens at construction).
    """
    return compose([_NODE_FACTORIES[node_id]() for node_id in ids]).build()


def _params_for(ids: list[str]) -> dict[str, float]:
    """Merge the fixed dotted ``"node_id.param"`` values for the named nodes."""
    merged: dict[str, float] = {}
    for node_id in ids:
        merged.update(_NODE_PARAMS[node_id])
    return merged


def _measurement(x: np.ndarray) -> MeasurementData:
    """Wrap ``x`` as a ``MeasurementData`` with dummy ``y`` (unused by eval)."""
    return MeasurementData(x=x, y=np.zeros_like(x))


def _evaluate(ids: list[str], x: np.ndarray) -> np.ndarray:
    """Evaluate the summed curve for a graph built from ``ids`` over ``x``."""
    graph = _graph_with(ids)
    return evaluate(graph, _params_for(ids), _measurement(x))


def test_superposition_holds_to_machine_epsilon() -> None:
    """eval(two-node graph) == eval(node p0) + eval(node p1), to 1e-12.

    Two independently constructed and evaluated one-node graphs are summed in
    Python; a single two-node graph containing both nodes is evaluated once.
    If these disagree beyond floating-point reordering noise, the executor's
    per-node accumulation in `crates/spectrafit-graph/src/executor.rs` is
    genuinely wrong.
    """
    both = _evaluate(["p0", "p1"], _X)
    apart = _evaluate(["p0"], _X) + _evaluate(["p1"], _X)
    assert_allclose(both, apart, rtol=0.0, atol=1e-12)


def test_evaluate_components_sum_matches_evaluate() -> None:
    """Sum of `evaluate_components` on a two-node graph equals `evaluate`.

    This exercises the ``evaluate_components`` PyO3 entry point — a different
    code path from the independent-graphs construction above — as an
    additional (not a replacement) check of the same superposition relation.
    """
    graph = _graph_with(["p0", "p1"])
    params = _params_for(["p0", "p1"])
    data = _measurement(_X)

    components = evaluate_components(graph, params, data)
    summed = components["p0"] + components["p1"]
    whole = evaluate(graph, params, data)

    assert_allclose(summed, whole, rtol=0.0, atol=1e-12)


def test_serialisation_round_trip_is_curve_identical() -> None:
    """A graph survives JSON serialisation without changing its output.

    Compiling a two-node graph, dumping it to JSON, and re-validating that
    JSON back into a ``FitGraph`` must reproduce the identical curve — exact
    equality, not merely close, since every number crossing the PyO3
    boundary is serialised and a lossy JSON writer would show up here.
    """
    ids = ["p0", "p1"]
    graph = _graph_with(ids)
    round_tripped = FitGraph.model_validate_json(graph.model_dump_json())

    params = _params_for(ids)
    data = _measurement(_X)
    original_curve = evaluate(graph, params, data)
    round_tripped_curve = evaluate(round_tripped, params, data)

    assert_allclose(original_curve, round_tripped_curve, rtol=0.0, atol=0.0)
