"""Invariant V — End-to-end Value Provenance (the spine).

Phase 0 of the value-provenance hardening program. The ``VALUE_PROVENANCE``
registry (``oracles.audit.provenance``) is the single declarative source from
which the claim ledger, the proxy register, and contract-coverage all derive.

These tests pin the spine's two foundational invariants:

* **Parity (V2):** every audited ``Claim`` in ``CLAIM_REGISTRY`` has a matching
  ``ValueProvenance`` record whose ``contract_field`` and oracle wire agree —
  so a claim and its provenance can never drift on two code paths (kills I2 by
  construction).
* **No silent proxy (V5):** every record with ``status == "proxy"`` carries a
  ``proxy_task`` (enforced structurally at construction) AND the known
  convergence proxy is machine-declared, not disclosed only in prose.
"""

from __future__ import annotations


def test_value_provenance_importable():
    """The spine module exists and exposes the registry + models."""
    from oracles.audit.provenance import VALUE_PROVENANCE, ValueProvenance, OracleRef  # noqa: F401

    assert isinstance(VALUE_PROVENANCE, dict)
    assert VALUE_PROVENANCE, "VALUE_PROVENANCE must not be empty"


def test_every_claim_has_a_provenance_record():
    """Parity (V2): claims ⊆ provenance, with matching contract_field + wire.

    A claim whose backing value is not in the provenance spine is a dual-source
    drift risk (I2). The reverse is allowed — the spine may carry values that are
    not yet audited claims (e.g. a registered proxy awaiting its oracle).
    """
    from oracles.audit.claims import CLAIM_REGISTRY
    from oracles.audit.provenance import VALUE_PROVENANCE

    missing: list[str] = []
    mismatched: list[str] = []
    for cid, claim in sorted(CLAIM_REGISTRY.items()):
        rec = VALUE_PROVENANCE.get(cid)
        if rec is None:
            missing.append(f"  {cid!r}: no ValueProvenance record")
            continue
        if rec.contract_field != claim.source_field:
            mismatched.append(
                f"  {cid!r}: contract_field={rec.contract_field!r} != "
                f"claim.source_field={claim.source_field!r}"
            )
        if rec.oracle is None or rec.oracle.wire_id != claim.wire_id:
            got = None if rec.oracle is None else rec.oracle.wire_id
            mismatched.append(
                f"  {cid!r}: oracle.wire_id={got!r} != claim.wire_id={claim.wire_id!r}"
            )

    assert not missing and not mismatched, (
        "claim ↔ provenance parity failed:\n" + "\n".join(missing + mismatched)
    )


def test_proxy_records_are_machine_declared():
    """No silent proxy (V5): every proxy record carries a tracked proxy_task."""
    from oracles.audit.provenance import VALUE_PROVENANCE

    offenders = [
        rec.id
        for rec in VALUE_PROVENANCE.values()
        if rec.status == "proxy" and not rec.proxy_task
    ]
    assert not offenders, f"proxy records without a proxy_task: {offenders}"


def test_convergence_metric_is_now_real():
    """The convergence-to-truth metric is REAL (Phase 4 closed the proxy).

    Per-iteration θ is recorded at the source, the engine computes dₖ into a
    contract field, and the web renders it. The spine record must be real (V1)
    and oracle-checked (V3) — no longer a proxy.
    """
    from oracles.audit.provenance import VALUE_PROVENANCE

    rec = VALUE_PROVENANCE.get("convergence.theta_distance")
    assert rec is not None, "convergence.theta_distance must be in the spine"
    assert rec.status == "real", (
        "Phase 4: the χ²-floor proxy was replaced by the real metric"
    )
    assert rec.oracle is not None, "a real value must be oracle-checked (V3)"
    assert rec.contract_field == "analyzed[].profiles.*.thetaDistance"


def test_proxy_status_requires_task_structurally():
    """Construction-time guard: a proxy without a task cannot be built (best tier)."""
    import pytest
    from oracles.audit.provenance import ValueProvenance

    with pytest.raises(ValueError):
        ValueProvenance(
            id="bad.proxy",
            source="nowhere",
            contract_field="manifest.nothing",
            status="proxy",
            proxy_task=None,
        )
