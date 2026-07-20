"""Construction-time validation of per-parameter ``Parameter.expr`` constraints.

Tests mirror the Rust ``compile_rejects_param_expr_cycle_a_b_a`` test so that
Python construction raises the SAME error class at the SAME stage (graph build)
that the Rust compiler does.  Both constraint surfaces — ``expr_edges`` and
per-parameter ``Parameter.expr`` — must be validated identically at
``FitGraph(...)`` construction time, not only at Rust ``fit()``-time.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from spectrafit_core import FitGraph, ModelNodeSpec, ModelType, Parameter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gaussian_node(
    node_id: str,
    amplitude: float = 1.0,
    center: float = 0.0,
    sigma: float = 1.0,
    amplitude_expr: str | None = None,
) -> ModelNodeSpec:
    """Build a Gaussian ``ModelNodeSpec``, optionally with an ``expr`` on amplitude."""
    return ModelNodeSpec(
        id=node_id,
        model_type=ModelType.GAUSSIAN,
        parameters={
            "amplitude": Parameter(
                value=amplitude,
                expr=amplitude_expr,
                vary=amplitude_expr is None,
            ),
            "center": Parameter(value=center),
            "sigma": Parameter(value=sigma, min=1e-3),
        },
    )


# ---------------------------------------------------------------------------
# I1 — construction-time validation for Parameter.expr
# ---------------------------------------------------------------------------


def test_param_expr_cycle_rejected_at_construction() -> None:
    """A cycle via ``Parameter.expr`` (g1.amplitude↔g2.amplitude) must raise at construction.

    Mirrors Rust test ``compile_rejects_param_expr_cycle_a_b_a``.  Both nodes
    carry a ``Parameter.expr`` that references the other node's amplitude,
    forming a cycle.  ``FitGraph(...)`` must raise ``pydantic.ValidationError``
    — not defer the error to ``fit()``-time.
    """
    with pytest.raises(ValidationError, match="acyclic"):
        FitGraph(
            nodes=[
                _gaussian_node("g1", amplitude_expr="g2.amplitude"),
                _gaussian_node("g2", amplitude_expr="g1.amplitude"),
            ]
        )


def test_param_expr_unknown_node_rejected_at_construction() -> None:
    """A ``Parameter.expr`` referencing an unknown node must raise at construction.

    ``g1.amplitude`` carries ``expr="missing_node.amplitude"`` where
    ``"missing_node"`` is not a node in the graph.  ``FitGraph(...)`` must raise
    ``pydantic.ValidationError`` — not defer to ``fit()``-time.
    """
    with pytest.raises(ValidationError, match="unknown source node"):
        FitGraph(
            nodes=[
                _gaussian_node("g1", amplitude_expr="missing_node.amplitude"),
            ]
        )
