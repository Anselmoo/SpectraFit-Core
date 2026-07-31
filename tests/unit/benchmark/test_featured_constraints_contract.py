"""TDD tests for Track 3: fixedParams / exprEdges on Featured contract.

RED-FIRST: these tests are written before implementation. They document the
exact contract changes:

  1. Featured → fixed_params (wire: fixedParams) — per-node fixed param names.
  2. Featured → expr_edges (wire: exprEdges) — tied-param expression edges.

Both are additive-minor: optional with default ({}  / []) so old payloads
validate without error.
"""

from __future__ import annotations

from oracles.bench_contract import Featured


def test_featured_carries_constraints_camelcase() -> None:
    """Featured accepts fixedParams and exprEdges via camelCase wire names."""
    f = Featured.model_validate(
        {
            "id": "FX-001",
            "name": "x",
            "category": "fixed",
            "x": [0.0],
            "ref": [0.0],
            "guess": [0.0],
            "truth": [],
            "noise": 0.02,
            "baseline": 1.0,
            "profiles": {},
            "peaks": [],
            "paramNames": [],
            "corr": [],
            "Ngrid": [10],
            "schedule": [1],
            "runsSched": [1],
            "crossN": 0.0,
            "fixedParams": {"p0": ["center"]},
            "exprEdges": [
                {
                    "targetNode": "p1",
                    "targetParam": "sigma",
                    "expression": "p0.sigma",
                }
            ],
        }
    )
    assert f.fixed_params == {"p0": ["center"]}
    assert f.expr_edges[0].target_param == "sigma"
    # Serializes to camelCase on the wire (targetNode/targetParam/expression).
    assert f.model_dump(by_alias=True)["exprEdges"][0]["targetParam"] == "sigma"


def test_featured_constraints_default_empty() -> None:
    """Featured defaults fixed_params to {} and expr_edges to [] (additive-minor)."""
    f = Featured.model_validate(
        {
            "id": "EZ-001",
            "name": "x",
            "category": "easy",
            "x": [0.0],
            "ref": [0.0],
            "guess": [0.0],
            "truth": [],
            "noise": 0.0,
            "baseline": 1.0,
            "profiles": {},
            "peaks": [],
            "paramNames": [],
            "corr": [],
            "Ngrid": [10],
            "schedule": [1],
            "runsSched": [1],
            "crossN": 0.0,
        }
    )
    assert f.fixed_params == {}
    assert f.expr_edges == []


def test_featured_constraints_serialise_camelcase() -> None:
    """Serialised output uses camelCase wire names fixedParams / exprEdges."""
    f = Featured.model_validate(
        {
            "id": "FX-002",
            "name": "y",
            "category": "fixed",
            "x": [1.0],
            "ref": [1.0],
            "guess": [1.0],
            "truth": [],
            "noise": 0.01,
            "baseline": 0.0,
            "profiles": {},
            "peaks": [],
            "paramNames": [],
            "corr": [],
            "Ngrid": [5],
            "schedule": [2],
            "runsSched": [2],
            "crossN": 0.0,
            "fixedParams": {"p0": ["amplitude"]},
            "exprEdges": [],
        }
    )
    payload = f.model_dump(by_alias=True)
    assert "fixedParams" in payload
    assert "exprEdges" in payload
    assert payload["fixedParams"] == {"p0": ["amplitude"]}
    assert payload["exprEdges"] == []
