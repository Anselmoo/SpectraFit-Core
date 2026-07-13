"""Pin the trust-ledger contract before anything writes to it."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from oracles.trust_ledger import (  # noqa: F401
    CredibilityRung,
    TrustBlock,
    TrustLedger,
    WireResult,
    WireStatus,
)


def test_wire_result_has_required_fields():
    r = WireResult(
        wire_id="W2a",
        name="metric_identity",
        status="pass",
        evidence="recomputed r2 from (x, y, params), allclose to contract value",
    )
    assert r.wire_id == "W2a"
    assert r.status == "pass"


def test_wire_result_status_is_literal():
    with pytest.raises(ValidationError):
        WireResult(wire_id="W1", name="x", status="green", evidence="x")  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]  # deliberately invalid status to test ValidationError


def test_trust_block_aggregates_wires():
    block = TrustBlock(
        rung=CredibilityRung.RUNG_4,
        wires=[
            WireResult(wire_id="W1", name="synth_invariants", status="pass", evidence=""),
            WireResult(wire_id="W2a", name="metric_identity", status="pass", evidence=""),
        ],
        n_claims_audited=2,
        n_claims_total=2,
    )
    assert block.rung == CredibilityRung.RUNG_4
    assert len(block.wires) == 2


def test_trust_block_rejects_extra_fields():
    with pytest.raises(ValidationError):
        TrustBlock(rung=CredibilityRung.RUNG_2, wires=[], n_claims_audited=0, n_claims_total=0, rogue="x")  # type: ignore[call-arg]  # ty: ignore[unknown-argument]  # deliberately unknown field to test extra='forbid'
