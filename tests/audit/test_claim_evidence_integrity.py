"""Claim↔evidence integrity invariants for TrustBlock.

L1 — W8 single-source: wire_w8 derives status from the passed-in block, not a 2nd call.
L2 — TrustBlock validator: rung==RUNG_5 ⟺ nist_validation present and passed.
L3 — Generalised claim-evidence integrity (anti-fingerpointing engine):
     every audited claim's source_field must resolve to a non-null value in the
     actual serialised BenchReport payload (as written to results.json by run_audit).
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from oracles.trust_ledger import TrustBlock, CredibilityRung


# ---------------------------------------------------------------------------
# L3 helpers — minimal JSON-path resolver
# ---------------------------------------------------------------------------

def _resolve_path(payload: Any, path: str) -> bool:
    """Return True iff ``path`` resolves to at least one non-null value in ``payload``.

    Supported syntax::

        a.b           dict key traversal
        a[].b         list — at least one element must carry a non-null value
        a[Key]        match a list element whose ``name`` == Key, OR a dict key ``Key``
        *             wildcard dict key (any key in a mapping)

    Returns False if any step fails (key missing, wrong type, null), True otherwise.
    """
    parts = re.split(r"\.", path)
    # Expand bracket segments: "a[Foo]" → "a", "[Foo]"
    expanded: list[str] = []
    for part in parts:
        m = re.match(r"^([^\[]+)(\[.*)?$", part)
        if m:
            if m.group(1):
                expanded.append(m.group(1))
            if m.group(2):
                expanded.append(m.group(2))
        else:
            expanded.append(part)

    def _resolve(node: Any, segs: list[str]) -> bool:
        if not segs:
            return node is not None
        seg = segs[0]
        rest = segs[1:]

        if seg == "[]":
            # list traversal — at least one element must resolve
            if not isinstance(node, list) or not node:
                return False
            return any(_resolve(item, rest) for item in node)

        m_bracket = re.match(r"^\[(.+)\]$", seg)
        if m_bracket:
            key = m_bracket.group(1)
            if isinstance(node, list):
                # match by ``name`` attribute
                for item in node:
                    if isinstance(item, dict) and item.get("name") == key:
                        return _resolve(item, rest)
                return False
            if isinstance(node, dict):
                if key not in node:
                    return False
                return _resolve(node[key], rest)
            return False

        if seg == "*":
            # wildcard — any dict key
            if not isinstance(node, dict) or not node:
                return False
            return any(_resolve(v, rest) for v in node.values())

        if isinstance(node, dict):
            if seg not in node:
                return False
            return _resolve(node[seg], rest)

        return False

    return _resolve(payload, expanded)


# ---------------------------------------------------------------------------
# L3 fixture — minimal results.json payload (post-audit inlining)
# ---------------------------------------------------------------------------

# This dict mirrors what run_audit writes into results.json:
#   - BenchReport top-level uses camelCase (by_alias=True via write_run)
#   - trustBlock internals are snake_case (block.model_dump(mode="json") — no alias)
#
# Only the fields referenced by audited claims need to be present; everything
# else can be omitted.

_NIST_DATASET_Gauss1 = {
    "name": "Gauss1",
    "model": "Three-term Gaussian",
    "n_params": 8,
    "params": [{"name": "b1", "certified": 98.0, "fitted": 98.0, "sig_figs_agreed": 6.0}],
    "min_sig_figs": 6.0,
    "passed": True,
}
_NIST_DATASET_Gauss2 = {**_NIST_DATASET_Gauss1, "name": "Gauss2"}
_NIST_DATASET_Gauss3 = {**_NIST_DATASET_Gauss1, "name": "Gauss3"}
_NIST_DATASET_Lanczos1 = {**_NIST_DATASET_Gauss1, "name": "Lanczos1", "model": "Lanczos sum"}

_RUNG5_PAYLOAD: dict[str, Any] = {
    # --- manifest (camelCase, as written by write_run → by_alias=True) ---
    "manifest": {
        "geomeanSpeedupVsBaseline": 9.45,
        "maxAbsDeltaR2": 1e-6,
        "spectrafitWinRate": 0.9,
        "gateState": "pass",
    },
    # --- trustBlock (snake_case — TrustBlock.model_dump(mode="json") has no alias) ---
    "trustBlock": {
        "rung": 5,
        "wires": [{"wire_id": "W8", "name": "NIST", "status": "pass", "evidence": "ok", "details": {}}],
        "n_claims_audited": 20,
        "n_claims_total": 20,
        "nist_validation": {
            "threshold_sig_figs": 4.0,
            "datasets": [
                _NIST_DATASET_Gauss1,
                _NIST_DATASET_Gauss2,
                _NIST_DATASET_Gauss3,
                _NIST_DATASET_Lanczos1,
            ],
            "min_sig_figs": 6.0,
            "passed": True,
        },
    },
    # --- analyzed[] (camelCase, by_alias=True) ---
    "analyzed": [
        {
            "truth": [1.0, 2.0, 3.0],
            "profiles": {
                "spectrafit": {
                    "summary": {
                        "r2": 0.999,
                        "chi2": 1.2,
                        "redChi2": 0.6,
                        "rmse": 0.01,
                    },
                    "uncertainty": {"coverage": 0.68},
                    "jacobianConditionNumber": 12.0,
                }
            },
        }
    ],
    # --- inference (camelCase) ---
    "inference": {
        "cases": [{"caseId": "EZ-001", "speedupCi": [5.0, 10.0], "deltaR2Ci": [0.0, 0.001]}],
        "equivalence": [{"category": "easy", "equivalent": True, "margin": 0.1, "diff": 0.01}],
    },
}

# Wire statuses for the rung-5 fixture: every wire passes
_ALL_PASS_WIRE_STATUS: dict[str, str] = {
    "W1": "pass", "W2a": "pass", "W2b": "pass", "W2c": "pass",
    "W3": "pass", "W4": "pass", "W6": "pass", "W7": "pass", "W8": "pass",
}


def test_l3_all_audited_claim_source_fields_resolve():
    """L3 (I1 generalised): every audited claim's source_field resolves non-null
    in the actual serialised payload.

    The test is RED (fails) if any claim's source_field string does not match
    the real key names in results.json.  The KNOWN failing case before the fix:
    NIST claims declare ``trustBlock.nistValidation.*`` (camelCase) but the
    inlined TrustBlock uses snake_case ``nist_validation``.
    """
    from oracles.audit.claims import CLAIM_REGISTRY

    payload = _RUNG5_PAYLOAD

    failing: list[str] = []
    for cid, cls in sorted(CLAIM_REGISTRY.items()):
        # Skip wires that are non-path sentinels (API schema, roundtrip file
        # path, external-oracle reference) — these are not payload JSON paths.
        if cls.source_field in {"results.json", "/api/*", "scipy.least_squares"}:
            continue
        # Only check claims whose wire is "pass" in our all-pass fixture
        if _ALL_PASS_WIRE_STATUS.get(cls.wire_id) != "pass":
            continue
        if not _resolve_path(payload, cls.source_field):
            failing.append(
                f"  {cid!r}: source_field={cls.source_field!r} did not resolve"
            )

    assert not failing, (
        f"L3 claim-evidence integrity: {len(failing)} source_field path(s) "
        f"failed to resolve against the serialised payload:\n"
        + "\n".join(failing)
    )


def test_rung5_requires_passing_nist_evidence():
    with pytest.raises(ValueError):
        TrustBlock(
            rung=CredibilityRung.RUNG_5,
            wires=[],
            n_claims_audited=0,
            n_claims_total=0,
            nist_validation=None,
        )


def test_w8_pass_iff_nist_block_passed_via_single_source():
    """L1 single-source: wire_w8 derives status from the passed-in block, not a 2nd call.

    When nist_validation=None is passed explicitly, the wire falls back to its own
    run_nist_validation() call (direct-call / test back-compat) OR reports skipped
    if the harness can't run.  Either way it returns exactly one W8 WireResult.

    When a PASSING NistValidation block is passed in, the wire must report "pass"
    without running the harness again — status derived purely from the block.
    """
    from oracles.audit.wires import wire_w8_nist_certified_validation
    from oracles.trust_ledger import NistValidation, NistDataset, NistParam

    # --- None path: fallback to its own call (or skipped if unavailable).
    results_none = wire_w8_nist_certified_validation(nist_validation=None)
    assert len(results_none) == 1
    assert results_none[0].wire_id == "W8"
    # Accepts pass, fail, or skipped — all are valid depending on environment.
    assert results_none[0].status in {"pass", "fail", "skipped"}

    # --- Passing block passed in: must produce "pass" without a second harness call.
    passing_param = NistParam(
        name="b1", certified=1.0, fitted=1.0, sig_figs_agreed=15.0
    )
    passing_dataset = NistDataset(
        name="TestDS",
        model="test",
        n_params=1,
        params=[passing_param],
        min_sig_figs=15.0,
        passed=True,
    )
    passing_block = NistValidation(
        threshold_sig_figs=4.0,
        datasets=[passing_dataset],
        min_sig_figs=15.0,
        passed=True,
    )
    results_pass = wire_w8_nist_certified_validation(nist_validation=passing_block)
    assert len(results_pass) == 1
    assert results_pass[0].wire_id == "W8"
    assert results_pass[0].status == "pass"

    # --- Failing block passed in: must produce "fail" (not re-run to get a different result).
    failing_dataset = NistDataset(
        name="TestDS",
        model="test",
        n_params=1,
        params=[NistParam(name="b1", certified=1.0, fitted=2.0, sig_figs_agreed=0.3)],
        min_sig_figs=0.3,
        passed=False,
    )
    failing_block = NistValidation(
        threshold_sig_figs=4.0,
        datasets=[failing_dataset],
        min_sig_figs=0.3,
        passed=False,
    )
    results_fail = wire_w8_nist_certified_validation(nist_validation=failing_block)
    assert len(results_fail) == 1
    assert results_fail[0].wire_id == "W8"
    assert results_fail[0].status == "fail"
