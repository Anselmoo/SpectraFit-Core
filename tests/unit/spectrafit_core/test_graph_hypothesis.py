"""Phase 8 — test_graph_hypothesis.py

Hypothesis-based property tests for FitGraph._validate_graph cycle detection,
plus deterministic edge-case tests covering self-loops, multi-node cycles,
duplicate node ids, unknown nodes in expressions, and DAG validation.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st
from pydantic import ValidationError

from spectrafit_core import FitGraph, ModelNodeSpec, ModelType, Parameter
from spectrafit_core.graph import ExprEdge


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _node(nid: str) -> ModelNodeSpec:
    """Create a minimal valid Gaussian node for testing."""
    return ModelNodeSpec(
        id=nid,
        model_type=ModelType.GAUSSIAN,
        parameters={
            "amplitude": Parameter(value=1.0),
            "center": Parameter(value=0.0),
            "sigma": Parameter(value=1.0, min=1e-3),
        },
    )


# ---------------------------------------------------------------------------
# Deterministic tests
# ---------------------------------------------------------------------------


def test_duplicate_node_ids_rejected() -> None:
    """Duplicate node IDs are rejected at construction time."""
    with pytest.raises(ValidationError):
        FitGraph(nodes=[_node("g"), _node("g")])


def test_self_loop_rejected() -> None:
    """Self-loop (node references itself) is rejected."""
    with pytest.raises(ValidationError):
        FitGraph(
            nodes=[_node("g")],
            expr_edges=[
                ExprEdge(
                    target_node="g",
                    target_param="amplitude",
                    expression="g.sigma",
                )
            ],
        )


def test_two_node_cycle_rejected() -> None:
    """Two-node cycle (A → B → A) is rejected."""
    with pytest.raises(ValidationError):
        FitGraph(
            nodes=[_node("a"), _node("b")],
            expr_edges=[
                ExprEdge(
                    target_node="b",
                    target_param="amplitude",
                    expression="a.sigma",
                ),
                ExprEdge(
                    target_node="a",
                    target_param="amplitude",
                    expression="b.sigma",
                ),
            ],
        )


def test_three_node_cycle_rejected() -> None:
    """Three-node cycle (A → B → C → A) is rejected."""
    with pytest.raises(ValidationError):
        FitGraph(
            nodes=[_node("a"), _node("b"), _node("c")],
            expr_edges=[
                ExprEdge(
                    target_node="b",
                    target_param="amplitude",
                    expression="a.sigma",
                ),
                ExprEdge(
                    target_node="c",
                    target_param="amplitude",
                    expression="b.sigma",
                ),
                ExprEdge(
                    target_node="a",
                    target_param="amplitude",
                    expression="c.sigma",
                ),
            ],
        )


def test_unknown_target_node_rejected() -> None:
    """Unknown target node in ExprEdge is rejected."""
    with pytest.raises(ValidationError):
        FitGraph(
            nodes=[_node("g")],
            expr_edges=[
                ExprEdge(
                    target_node="nonexistent",
                    target_param="amplitude",
                    expression="g.sigma",
                )
            ],
        )


def test_unknown_source_node_in_expression_rejected() -> None:
    """Unknown source node referenced in expression is rejected."""
    with pytest.raises(ValidationError):
        FitGraph(
            nodes=[_node("g")],
            expr_edges=[
                ExprEdge(
                    target_node="g",
                    target_param="amplitude",
                    expression="ghost.sigma",
                )
            ],
        )


def test_linear_chain_three_nodes_accepted() -> None:
    """Linear chain (A → B → C) is a valid DAG and accepted."""
    FitGraph(
        nodes=[_node("a"), _node("b"), _node("c")],
        expr_edges=[
            ExprEdge(target_node="b", target_param="sigma", expression="a.sigma"),
            ExprEdge(target_node="c", target_param="sigma", expression="b.sigma"),
        ],
    )


def test_diamond_dag_accepted() -> None:
    """Diamond DAG (A → B,C and B,C → D) is valid and accepted."""
    FitGraph(
        nodes=[_node("a"), _node("b"), _node("c"), _node("d")],
        expr_edges=[
            ExprEdge(target_node="b", target_param="sigma", expression="a.sigma"),
            ExprEdge(target_node="c", target_param="sigma", expression="a.sigma"),
            ExprEdge(target_node="d", target_param="sigma", expression="b.sigma"),
        ],
    )


# ---------------------------------------------------------------------------
# Hypothesis tests
# ---------------------------------------------------------------------------


@given(n=st.integers(min_value=1, max_value=10))
@settings(max_examples=50)
def test_topological_chain_never_cycles(n: int) -> None:
    """A topological chain of N nodes (0→1→...→N-1) is always a valid DAG."""
    nodes = [_node(f"n{i}") for i in range(n)]
    edges = [
        ExprEdge(target_node=f"n{i+1}", target_param="sigma", expression=f"n{i}.sigma")
        for i in range(n - 1)
    ]
    FitGraph(nodes=nodes, expr_edges=edges)  # must not raise


@given(n=st.integers(min_value=2, max_value=10))
@settings(max_examples=50)
def test_back_edge_always_creates_cycle(n: int) -> None:
    """Back-edge in a topological chain always creates a cycle and is rejected."""
    nodes = [_node(f"n{i}") for i in range(n)]
    edges = [
        ExprEdge(target_node=f"n{i+1}", target_param="sigma", expression=f"n{i}.sigma")
        for i in range(n - 1)
    ]
    # Add back-edge: n{n-1} → n0 (creates a cycle)
    edges.append(
        ExprEdge(
            target_node="n0",
            target_param="amplitude",
            expression=f"n{n-1}.sigma",
        )
    )
    with pytest.raises(ValidationError):
        FitGraph(nodes=nodes, expr_edges=edges)
