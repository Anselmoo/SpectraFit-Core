"""Claim-ledger semantics: the registry is populated and `audited_count`
counts only claims whose backing wire passed.

The wire-id set is the real one declared by ``oracles.audit.wires`` — each
``WireResult.wire_id`` returned by the wires in ``ALL_WIRES``.
"""

from __future__ import annotations

import inspect

from oracles.audit.claims import CLAIM_REGISTRY, audited_count
from oracles.audit.wires import ALL_WIRES


def _invoke(fn):
    if "audit_records" in inspect.signature(fn).parameters:
        return fn(audit_records=None)
    return fn()


# The real wire-id set, derived from the wires themselves (no hardcoded list).
_REAL_WIRE_IDS = {wr.wire_id for fn in ALL_WIRES for wr in _invoke(fn)}


def test_registry_has_at_least_16_claims():
    assert len(CLAIM_REGISTRY) >= 16


def test_every_claim_wire_id_is_real():
    for claim in CLAIM_REGISTRY.values():
        assert claim.wire_id in _REAL_WIRE_IDS, (
            f"{claim.claim_id} declares unknown wire {claim.wire_id!r}; "
            f"real ids are {sorted(_REAL_WIRE_IDS)}"
        )


def test_every_claim_id_is_dotted_and_unique():
    ids = [c.claim_id for c in CLAIM_REGISTRY.values()]
    assert len(ids) == len(set(ids)), "duplicate claim_id"
    for cid in ids:
        assert "." in cid, f"claim_id {cid!r} is not a dotted namespace"


def test_audited_count_only_counts_passing_wires():
    total = len(CLAIM_REGISTRY)
    n_w2c = sum(1 for c in CLAIM_REGISTRY.values() if c.wire_id == "W2c")
    assert n_w2c >= 1, "expected at least one claim backed by W2c"

    wire_status = {wid: "pass" for wid in _REAL_WIRE_IDS}
    wire_status["W2c"] = "fail"

    assert audited_count(wire_status) == total - n_w2c
    assert audited_count(wire_status) < total


def test_audited_count_all_pass_equals_total():
    wire_status = {wid: "pass" for wid in _REAL_WIRE_IDS}
    assert audited_count(wire_status) == len(CLAIM_REGISTRY)
