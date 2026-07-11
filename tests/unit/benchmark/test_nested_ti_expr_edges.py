"""Unit tests: nested-adequacy reducer scopes expr_edges to the reduced order (G11).

Bug: _order_bench_case carries the base spec's expr_edges unchanged.  For a
tied-param case (two peaks, expr_edge target_node="p1"), reducing to order 1
produces a spec whose expr_edges still reference "p1".  The spectrafit backend
raises ``ValueError("unknown target node: p1")`` when building the FitGraph →
the nested fit falls back to null RSS instead of fitting.

Fix: _order_bench_case must drop any expr_edge whose target_node or expression
source nodes are not present in the reduced component set.

TDD cycle: RED (this file) → implement fix in engine.py → GREEN.
"""

from __future__ import annotations

import numpy as np

from oracles.engine import _order_bench_case
from oracles.cases import BenchCase, CaseSpec, GaussianSpec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _two_peak_tied_spec() -> CaseSpec:
    """Minimal CaseSpec: two Gaussians with p1.sigma tied to p0.sigma."""
    p0 = GaussianSpec(amplitude=2.0, center=-1.0, sigma=0.5)
    p1 = GaussianSpec(amplitude=1.5, center=1.0, sigma=0.5)
    return CaseSpec(
        id="test-ti-expr-scope",
        name="test tied expr scope",
        category="tied",
        difficulty=0.2,
        components=[p0, p1],
        x_min=-5.0,
        x_max=5.0,
        n_points=60,
        noise=0.02,
        expr_edges=[
            {
                "target_node": "p1",
                "target_param": "sigma",
                "expression": "p0.sigma",
            }
        ],
    )


def _two_peak_bench_case() -> BenchCase:
    """Materialise the minimal tied spec into a BenchCase."""
    spec = _two_peak_tied_spec()
    p0 = GaussianSpec(amplitude=2.0, center=-1.0, sigma=0.5)
    p1 = GaussianSpec(amplitude=1.5, center=1.0, sigma=0.5)
    x = np.linspace(spec.x_min, spec.x_max, spec.n_points)
    # y = sum of both Gaussians (no noise for simplicity)
    from oracles.cases import curve
    y = curve(x, [p0, p1])
    return BenchCase(
        spec=spec,
        x=x,
        y=y,
        comp_true=[p0, p1],
        comp_guess=[p0, p1],
    )


# ---------------------------------------------------------------------------
# RED tests — these fail BEFORE the fix
# ---------------------------------------------------------------------------


def test_order_bench_case_drops_dangling_expr_edge_at_reduced_order() -> None:
    """Reduced order-1 spec must NOT contain an expr_edge targeting p1.

    Before the fix: _order_bench_case copies expr_edges unchanged, so the
    order-1 spec still has {"target_node": "p1", ...} even though p1 is gone.
    The FitGraph validator raises ValueError("unknown target node: p1").

    After the fix: the dangling edge is dropped → order-1 spec has no
    expr_edges.
    """
    base = _two_peak_bench_case()
    p0 = base.comp_true[0]

    # Reduce to order 1: only p0 remains, p1 is dropped.
    reduced_case = _order_bench_case(base, [p0], [])

    dangling = [
        e for e in reduced_case.spec.expr_edges
        if e["target_node"] == "p1"
    ]
    assert dangling == [], (
        f"Reduced-order spec still carries dangling expr_edge(s) targeting p1: "
        f"{dangling}.\n"
        "Fix: _order_bench_case must filter expr_edges to nodes present at the "
        "reduced order."
    )


def test_order_bench_case_keeps_valid_expr_edges_at_true_order() -> None:
    """True-order (2-peak) spec must KEEP all expr_edges — none are dangling."""
    base = _two_peak_bench_case()
    p0, p1 = base.comp_true

    # True order: both p0 and p1 are present.
    true_order_case = _order_bench_case(base, [p0, p1], [])

    assert len(true_order_case.spec.expr_edges) == 1, (
        f"True-order spec should retain the 1 valid expr_edge; "
        f"got {len(true_order_case.spec.expr_edges)}."
    )
    assert true_order_case.spec.expr_edges[0]["target_node"] == "p1", (
        "The retained edge must target p1 (which exists at order 2)."
    )


def test_reduced_order_case_can_build_fitgraph_without_error() -> None:
    """Building a FitGraph from the reduced-order case must not raise ValueError.

    Before the fix: ValueError("unknown target node: p1") is raised inside the
    spectrafit backend's build() call (FitGraph Pydantic validator).

    After the fix: no exception; the graph is constructed cleanly with 0
    expr_edges.
    """
    from oracles.backends._spectrafit import SpectraFitBackend

    base = _two_peak_bench_case()
    p0 = base.comp_true[0]
    reduced_case = _order_bench_case(base, [p0], [])

    backend = SpectraFitBackend()
    # build() must not raise — the dangling edge has been dropped.
    graph, data, options = backend.build(reduced_case)
    # The FitGraph should have 1 node and 0 expr_edges.
    assert len(graph.nodes) == 1, f"Expected 1 node, got {len(graph.nodes)}"
    assert graph.expr_edges == [], (
        f"Expected 0 expr_edges on the reduced-order graph, got {graph.expr_edges}"
    )
