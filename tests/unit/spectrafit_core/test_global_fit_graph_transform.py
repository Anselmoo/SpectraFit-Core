"""Unit tests for GlobalFitGraph.to_fit_graph() transformation.

Tests the node-replication and expr_edge-generation logic in isolation,
without invoking the Rust engine or full fit pipeline.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from spectrafit_core.graph import ExprEdge, FitGraph, GlobalFitGraph
from spectrafit_core.models import ModelNodeSpec, ModelType
from spectrafit_core.parameters import Parameter


def _gaussian(node_id: str, **params: float) -> ModelNodeSpec:
    """Helper: a gaussian ModelNodeSpec with given parameter values."""
    return ModelNodeSpec(
        id=node_id,
        model_type=ModelType.GAUSSIAN,
        parameters={k: Parameter(value=v) for k, v in params.items()},
    )


# ---------------------------------------------------------------------------
# Node count invariants
# ---------------------------------------------------------------------------


def test_global_only_produces_exact_node_count() -> None:
    """N global nodes × 0 local × S slices → N nodes in the flat graph."""
    g = GlobalFitGraph(
        global_nodes=[_gaussian("g0"), _gaussian("g1")],
        local_nodes=[],
        n_slices=3,
    )
    flat = g.to_fit_graph()
    assert len(flat.nodes) == 2
    assert flat.expr_edges == []


def test_local_replication_count() -> None:
    """0 global + L local × S slices → L×S nodes."""
    g = GlobalFitGraph(
        global_nodes=[],
        local_nodes=[_gaussian("bg")],
        n_slices=4,
    )
    flat = g.to_fit_graph()
    assert len(flat.nodes) == 4


def test_mixed_node_count() -> None:
    """G global + L local × S slices → G + L×S nodes."""
    g = GlobalFitGraph(
        global_nodes=[_gaussian("g0"), _gaussian("g1")],
        local_nodes=[_gaussian("l0"), _gaussian("l1")],
        n_slices=3,
    )
    flat = g.to_fit_graph()
    assert len(flat.nodes) == 2 + 2 * 3  # == 8


# ---------------------------------------------------------------------------
# Node-ID and dataset_index correctness
# ---------------------------------------------------------------------------


def test_replicated_node_ids_have_slice_suffix() -> None:
    """Local node 'bg' with n_slices=3 produces ids ['bg_s0', 'bg_s1', 'bg_s2']."""
    g = GlobalFitGraph(
        global_nodes=[],
        local_nodes=[_gaussian("bg")],
        n_slices=3,
    )
    flat = g.to_fit_graph()
    assert [n.id for n in flat.nodes] == ["bg_s0", "bg_s1", "bg_s2"]


def test_replicated_nodes_have_correct_dataset_index() -> None:
    """Each replica has dataset_index equal to its slice index i."""
    g = GlobalFitGraph(
        global_nodes=[],
        local_nodes=[_gaussian("l")],
        n_slices=3,
    )
    flat = g.to_fit_graph()
    for i, node in enumerate(flat.nodes):
        assert node.dataset_index == i


def test_all_node_ids_are_unique() -> None:
    """Replicated + global node IDs must be unique (FitGraph validates this)."""
    g = GlobalFitGraph(
        global_nodes=[_gaussian("g")],
        local_nodes=[_gaussian("l")],
        n_slices=3,
    )
    flat = g.to_fit_graph()
    ids = [n.id for n in flat.nodes]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# shared_local_params → expr_edges
# ---------------------------------------------------------------------------


def test_shared_param_generates_correct_edge_count() -> None:
    """1 local × 1 shared param × (n_slices-1) → (n_slices-1) expr_edges."""
    n = 4
    g = GlobalFitGraph(
        global_nodes=[],
        local_nodes=[_gaussian("l", amplitude=1.0)],
        n_slices=n,
        shared_local_params=["amplitude"],
    )
    flat = g.to_fit_graph()
    assert len(flat.expr_edges) == n - 1  # 3 edges: s1→s0, s2→s0, s3→s0


def test_shared_param_edge_targets_slice_zero() -> None:
    """Each shared-param expr_edge ties slice i to slice 0's value."""
    g = GlobalFitGraph(
        global_nodes=[],
        local_nodes=[_gaussian("p", amplitude=1.0)],
        n_slices=3,
        shared_local_params=["amplitude"],
    )
    flat = g.to_fit_graph()
    expected = [
        ExprEdge(
            target_node="p_s1", target_param="amplitude", expression="p_s0.amplitude"
        ),
        ExprEdge(
            target_node="p_s2", target_param="amplitude", expression="p_s0.amplitude"
        ),
    ]
    assert flat.expr_edges == expected


def test_missing_shared_param_generates_no_edges() -> None:
    """shared_local_params naming a non-existent param produces zero edges."""
    g = GlobalFitGraph(
        global_nodes=[],
        local_nodes=[_gaussian("l")],  # no 'sigma' parameter
        n_slices=3,
        shared_local_params=["sigma"],  # not in local node
    )
    flat = g.to_fit_graph()
    assert flat.expr_edges == []


# ---------------------------------------------------------------------------
# Hypothesis: random slices → always a valid DAG
# ---------------------------------------------------------------------------


@given(n_slices=st.integers(min_value=1, max_value=6))
@settings(max_examples=50)
def test_to_fit_graph_always_produces_valid_dag(n_slices: int) -> None:
    """for any n_slices in [1, 6], shared-param tying never introduces a cycle."""
    g = GlobalFitGraph(
        global_nodes=[_gaussian("g")],
        local_nodes=[_gaussian("l", amplitude=1.0)],
        n_slices=n_slices,
        shared_local_params=["amplitude"],
    )
    flat = g.to_fit_graph()
    assert isinstance(flat, FitGraph)
    # FitGraph validates acyclicity at construction; reaching here means no cycle
    assert len(flat.nodes) == 1 + n_slices  # 1 global + n_slices local replicas
