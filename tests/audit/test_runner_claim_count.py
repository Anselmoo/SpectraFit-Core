"""The runner counts *verified* claims (backing wire passed), not merely
registered ones. A failing W2c wire leaves its κ(J) claim un-audited, so
n_claims_audited < n_claims_total — the honest, rung-2-capped count.
"""

from __future__ import annotations

import json
from pathlib import Path

from oracles.audit import runner as runner_mod
from oracles.audit.claims import CLAIM_REGISTRY
from oracles.audit.runner import run_audit
from oracles.trust_ledger import WireResult


def _stub_wires(monkeypatch) -> None:
    """Replace ALL_WIRES with no-arg fns: every wire passes except W2c."""
    real_ids = ["W1", "W2a", "W2b", "W2c", "W2d", "W3", "W4", "W5", "W6", "W7", "W8"]

    def _make(wid: str):
        status = "fail" if wid == "W2c" else "pass"

        def _fn() -> list[WireResult]:
            return [WireResult(wire_id=wid, name=wid, status=status, evidence="stub")]

        return _fn

    monkeypatch.setattr(runner_mod, "ALL_WIRES", [_make(w) for w in real_ids])


def test_runner_counts_only_verified_claims(
    tmp_path: Path, monkeypatch, no_runtime_l3
) -> None:
    # Isolates the *claim-counting* concern with a stub payload; the *resolution*
    # concern (runtime L3) is covered separately (no_runtime_l3 fixture docstring).
    _stub_wires(monkeypatch)
    (tmp_path / "results.json").write_text(json.dumps({"x": 1}))

    ledger = run_audit(tmp_path)
    block = ledger.block

    total = len(CLAIM_REGISTRY)
    n_w2c = sum(1 for c in CLAIM_REGISTRY.values() if c.wire_id == "W2c")

    assert block.n_claims_total == total
    assert block.n_claims_audited == total - n_w2c
    assert block.n_claims_audited < block.n_claims_total
