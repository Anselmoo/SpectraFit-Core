"""Audit runner — walks the wire list, computes the credibility rung.

Persists trust.json next to manifest.json, and inlines the TrustBlock into
results.json.
"""

from __future__ import annotations

import inspect
import json
import math
from collections.abc import Mapping
from pathlib import Path

from oracles.audit.claims import (
    CLAIM_REGISTRY,
    NON_PATH_SOURCE_FIELDS,
    audited_count,
    resolve_source_field,
)
from oracles.audit.structure_wires import run_structure_wires
from oracles.audit.wires import ALL_WIRES
from oracles.trust_ledger import CredibilityRung, TrustBlock, TrustLedger, WireResult


def _sanitize(obj: object) -> object:
    """Recursively replace non-finite floats (NaN / ±Inf) with ``None``.

    Mirrors ``oracles.reports._sanitize``, but replaces with ``None`` (JSON
    null) rather than 0.0 so that diagnostic detail fields (e.g.
    ``WireResult.details["max_abs_delta"]``) remain visually distinct from a
    legitimate zero when read back.  The receiver must handle null for any
    float field it reads from ``details``.

    G5 — annotation: when a float value inside a dict is non-finite and nulled,
    a sibling key ``<key>_suppressed`` is also written with a human-readable
    string describing the suppressed value (e.g. ``"non-finite (inf) suppressed"``).
    This makes the suppression VISIBLE to consumers instead of silently emitting
    a bare ``null``.  The annotation is additive — finite values are untouched,
    no new typed contract fields are added, and the free-form ``details`` dict's
    schema is unchanged.
    """
    # ``case bool()`` MUST precede ``case float()``: bool is a float subclass,
    # so a true/false value matches both class patterns — ordering pins the
    # bool-precedes-float invariant explicitly.
    match obj:
        case bool():
            return obj
        case float():
            return None if not math.isfinite(obj) else obj
        case dict():
            out: dict[str, object] = {}
            for k, v in obj.items():
                key: str = str(k)
                out[key] = _sanitize(v)
                # G5: annotate suppressed non-finite float values with a sibling
                # key. Only annotate when the original value was a non-finite
                # float (not bool — bools are subclasses of float in Python).
                if (
                    isinstance(v, float)
                    and not isinstance(v, bool)
                    and not math.isfinite(v)
                ):
                    label = "nan" if math.isnan(v) else "inf"
                    out[f"{key}_suppressed"] = f"non-finite ({label}) suppressed"
            return out
        case list() as xs:
            return [_sanitize(v) for v in xs]
        case _:
            return obj


def _compute_rung(wires: list[WireResult]) -> CredibilityRung:
    """Map wire statuses to a credibility rung.

    Only a genuine ``fail`` caps the rung at RUNG_2. A ``gap`` (a disclosed
    capability absence, e.g. κ(J) not exposed) and a ``skipped`` (test never ran)
    are NON-CAPPING: they neither earn a rung nor cap it, so the earned rung is
    whatever the passing wires support.

    The core wires (everything except W8, W10, W11) earn RUNG_2..RUNG_4. RUNG_5
    — reserved for "independent differential validation + external replication +
    inferential checks" — is unlocked only when **W8 (NIST StRD certified-value
    validation) ∧ W10 (σ-calibration) ∧ W11 (speed inference) all pass** AND the
    core wires already clear RUNG_4. Any of the three top-rung gates absent or
    skipped → the rung honestly caps at RUNG_4; a lower-rung ``fail`` still caps
    at RUNG_2 regardless of W8/W10/W11.

    Two tiers of "unverified value wire" capping (EF-PY-13):

    - **Soft-cap wires** (W2a/W2b/W2c): ``skipped`` means the audit sidecar was
      absent so the recompute could not run — a graceful degradation. ``skipped``
      on any of these caps the rung at RUNG_3 (V4 guard).

    - **Hard-cap value-oracle wires** (W2d): ``skipped`` means the pytest
      ``lastfailed`` cache was absent (UNKNOWN state on a fresh checkout). An
      absent cache is indistinguishable from "never verified"; the solver-output
      oracle claim must not be silently passed. ``skipped`` on W2d caps the rung
      at RUNG_2, exactly like a genuine ``fail``.
    """
    # Structure wires (S-prefixed) are non-capping for now: they verify the repo's
    # self-description, not a run's numbers, and some confirmed structural items are
    # pending triage. They ride in TrustBlock.wires for visibility but are excluded
    # from rung capping so structural drift can't conflate with "the science is
    # unverified" (RUNG_2's meaning). Promote them once the structural backlog clears.
    numerical = [w for w in wires if not w.wire_id.startswith("S")]
    statuses = {w.status for w in numerical}
    if "fail" in statuses:
        return CredibilityRung.RUNG_2  # any genuine failure → cap at regression-tests

    # EF-PY-13 — hard-cap: pytest-cache-backed value-oracle wires whose UNKNOWN
    # state (absent cache) maps to "skipped". An absent cache on W2d is
    # indistinguishable from "this check never ran"; the claim must not pass silently.
    # Treat "skipped" on these wires exactly like "fail" — cap at RUNG_2.
    hard_cap_value_oracle_wires = {"W2d"}
    if any(
        w.wire_id in hard_cap_value_oracle_wires and w.status == "skipped"
        for w in wires
    ):
        return CredibilityRung.RUNG_2

    # V4 — no silent skip: a *skipped* audited value wire (a wire that verifies a
    # numerical value/claim) means that value was never checked, so it must not
    # pass silently into the upper rungs. A disclosed "gap" (subject does not
    # expose the metric) is honest and stays non-capping; a skip on the
    # visible/render lane (W5) is conservative-by-design, not a value hole. W8
    # (external replication) is excluded: its skip is already handled by the
    # w8_passed gate below — absent W8 honestly caps at the core ladder (RUNG_4),
    # it does not undermine the core value verification.
    soft_cap_value_wires = {"W2a", "W2b", "W2c"}
    value_wire_skipped = any(
        w.wire_id in soft_cap_value_wires and w.status == "skipped" for w in wires
    )

    # W8/W10/W11 are top-rung gates; they earn RUNG_5 but must not inflate the
    # core-wire pass count that earns RUNG_2..RUNG_4.  All three are excluded
    # from the core ladder so their votes only count at the RUNG_5 gate below.
    w8_passed = any(w.wire_id == "W8" and w.status == "pass" for w in wires)
    _TOP_RUNG_GATES = {"W8", "W10", "W11"}
    core = [w for w in wires if w.wire_id not in _TOP_RUNG_GATES]
    pass_count = sum(1 for w in core if w.status == "pass")
    # gap + skipped are both non-capping, non-earning: count them together so a
    # disclosed gap is treated exactly like a skip for the "<3 unproven" guard.
    unproven_count = sum(1 for w in core if w.status in {"skipped", "gap"})

    if pass_count >= 6:
        base = CredibilityRung.RUNG_4
    elif pass_count >= 3 and unproven_count < 3:
        base = CredibilityRung.RUNG_3
    else:
        base = CredibilityRung.RUNG_2

    # V4: an unverified (skipped) soft-cap value wire caps the ladder below the
    # coverage rung — RUNG_4/5 require every value wire actually checked, never
    # skipped-but-silently-passed.
    if value_wire_skipped and base > CredibilityRung.RUNG_3:
        base = CredibilityRung.RUNG_3

    # Inferential wires: σ-calibration (W10) and speed inference (W11) must both
    # pass to earn RUNG_5.  Absent or skipped → no pass-by-absence at the ceiling.
    w10_passed = any(w.wire_id == "W10" and w.status == "pass" for w in wires)
    w11_passed = any(w.wire_id == "W11" and w.status == "pass" for w in wires)

    # External replication + inferential wires earn RUNG_5 only once the core
    # ladder is fully climbed.  All three gates (W8 ∧ W10 ∧ W11) are required.
    if w8_passed and w10_passed and w11_passed and base == CredibilityRung.RUNG_4:
        return CredibilityRung.RUNG_5
    return base


def _assert_audited_claims_resolve(
    results: dict, wire_status: Mapping[str, str]
) -> None:
    """Refuse to emit a report whose audited claims lack resolvable evidence.

    Runtime L3 (Invariant V, V2): a report whose *audited* claims point at
    evidence that is null/absent in the serialised payload must not be written.
    Promotes the previously test-only claim⇒evidence integrity check
    (``tests/audit/test_claim_evidence_integrity.py``) to a write-time guard: a
    claim is audited only when its backing wire passed, so any audited claim
    whose ``source_field`` (a real JSON path, not an external sentinel) does not
    resolve is a severed claim⇒evidence link and must halt the write.
    """
    failures = [
        f"{cid} (source_field={claim.source_field!r}, wire={claim.wire_id})"
        for cid, claim in CLAIM_REGISTRY.items()
        if wire_status.get(claim.wire_id) == "pass"
        and claim.source_field not in NON_PATH_SOURCE_FIELDS
        and not resolve_source_field(results, claim.source_field)
    ]
    if failures:
        raise ValueError(
            "runtime L3 (claim⇒evidence integrity): audited claim(s) have no "
            f"resolvable evidence in the payload: {failures}"
        )


def run_audit(run_dir: Path) -> TrustLedger:
    """Execute the audit harness against an existing run directory.

    Walks every registered wire, aggregates WireResult records into a
    TrustBlock, persists trust.json next to manifest.json, and inlines the
    block into results.json so a single payload carries its own provenance.

    Returns the persisted TrustLedger.
    """
    # Load the audit.json sidecar if present (written by cli.run).
    audit_path = run_dir / "audit.json"
    recs = json.loads(audit_path.read_text()) if audit_path.exists() else None

    # Compute the NIST StRD validation ONCE before the wires loop so that both
    # the W8 WireResult and TrustBlock.nist_validation derive from the SAME
    # object — divergence is structurally impossible. The W8 wire reads from this
    # pre-computed block (via nist_validation=… kwarg) instead of re-running.
    # On import/build failure we leave it None (W8 reports "skipped" in that case).
    nist_validation = None
    try:
        from oracles.audit.nist import run_nist_validation

        nist_validation = run_nist_validation()
    except Exception:  # pragma: no cover - defensive: missing build/fixtures
        nist_validation = None

    # Extract the nested-model adequacy V&V result from results.json (the first
    # analyzed case that carries a nestedAdequacy block). This is pre-computed once
    # so W9 and any future consumer share the same object — the same pattern as the
    # nist_validation block above.
    nested_adequacy = None
    results_path = run_dir / "results.json"
    if results_path.exists():
        try:
            from oracles.bench_contract import NestedAdequacy as _NestedAdequacy

            _results_raw = json.loads(results_path.read_text())
            _analyzed = _results_raw.get("analyzed") or []
            for _entry in _analyzed:
                _na_raw = _entry.get("nestedAdequacy")
                if _na_raw is not None:
                    nested_adequacy = _NestedAdequacy.model_validate(_na_raw)
                    break
        except Exception:  # pragma: no cover - defensive: parse error / missing build
            nested_adequacy = None

    # Extract the inference block (W10/W11 — σ-calibration + speed inference).
    # The JSON key is camelCase ``inference`` → ``calibration`` / ``speedInference``.
    # Pre-computed once so W10 and W11 share the same objects — same pattern as W8/W9.
    calibration = None
    speed_inference = None
    if results_path.exists():
        try:
            from oracles.bench_contract import (
                CalibrationResult as _CalibrationResult,
                SpeedInferenceResult as _SpeedInferenceResult,
            )

            _results_raw = json.loads(results_path.read_text())
            _inf = _results_raw.get("inference") or {}
            if _inf.get("calibration"):
                calibration = _CalibrationResult.model_validate(_inf["calibration"])
            if _inf.get("speedInference"):
                speed_inference = _SpeedInferenceResult.model_validate(
                    _inf["speedInference"]
                )
        except Exception:  # pragma: no cover - defensive: parse error / missing build
            calibration = None
            speed_inference = None

    # Injectable wire-fn parameters, in dispatch-priority order. The extracted
    # discriminator below is the tuple of these names present in a wire fn's
    # signature (in THIS order), so structural `match` patterns with a `*_`
    # tail reproduce the original first-match-wins chain exactly.
    _injectable = (
        "audit_records",
        "nist_validation",
        "nested_adequacy",
        "calibration",
        "speed_inference",
        "current_run_id",
    )

    wires: list[WireResult] = []
    for wire_fn in ALL_WIRES:
        sig = inspect.signature(wire_fn).parameters
        match tuple(name for name in _injectable if name in sig):
            case ("audit_records", "nist_validation", *_):
                wire_result = wire_fn(
                    audit_records=recs,  # ty: ignore[unknown-argument]
                    nist_validation=nist_validation,  # ty: ignore[unknown-argument]
                )
                wires.extend(wire_result)
            case ("audit_records", *_):
                wires.extend(wire_fn(audit_records=recs))  # ty: ignore[unknown-argument]  # guarded by runtime signature check
            case ("nist_validation", *_):
                wires.extend(wire_fn(nist_validation=nist_validation))  # ty: ignore[unknown-argument]  # guarded by runtime signature check
            case ("nested_adequacy", *_):
                wires.extend(wire_fn(nested_adequacy=nested_adequacy))  # ty: ignore[unknown-argument]  # guarded by runtime signature check
            case ("calibration", *_):
                wires.extend(wire_fn(calibration=calibration))  # ty: ignore[unknown-argument]  # guarded by runtime signature check
            case ("speed_inference", *_):
                wires.extend(wire_fn(speed_inference=speed_inference))  # ty: ignore[unknown-argument]  # guarded by runtime signature check
            case ("current_run_id", *_):
                # Scope per-run wires (W3 roundtrip) to THIS run so a stale failure
                # for an older run on disk can't pin the current run's trust red.
                run_token = f"{run_dir.parent.name}/{run_dir.name}"
                wires.extend(wire_fn(current_run_id=run_token))  # ty: ignore[unknown-argument]  # guarded by runtime signature check
            case _:
                wires.extend(wire_fn())

    # Structure wires (S1..S5) verify the repo's *self-description* — that the
    # claims the tree makes about itself (hook source-of-truth paths, INDEX.yaml
    # anchors, doc owners, the FFI stub, model-list parity) have not drifted from
    # the structure. They emit the same WireResult records as the numerical wires,
    # so they ride in the same TrustBlock and surface on the same audit. They are
    # NON-CAPPING for now (see _compute_rung): structural drift is tracked and
    # visible but does not yet pin the numerical credibility rung, because some
    # confirmed structural items (e.g. F11 phantom pre-merge anchors) are pending
    # triage decisions. Promote to capping once that backlog is cleared.
    wires.extend(run_structure_wires())

    # A claim is audited iff its backing wire passed. Reuse the WireResults the
    # runner already collected for the rung — no extra recompute. A failing,
    # skipped, or gap wire leaves its claims un-audited, so the count honestly
    # falls below the registered total instead of being vacuous.

    wire_status = {wr.wire_id: wr.status for wr in wires}
    block = TrustBlock(
        rung=_compute_rung(wires),
        wires=wires,
        n_claims_audited=audited_count(wire_status),
        n_claims_total=len(CLAIM_REGISTRY),
        nist_validation=nist_validation,
    )
    ledger = TrustLedger(run_id=run_dir.name, block=block)

    # Persist trust.json sidecar.
    (run_dir / "trust.json").write_text(ledger.model_dump_json(indent=2))

    # Inline into results.json under the contract's camelCase alias `trustBlock`
    # (BenchReport uses a to_camel _Base with extra="forbid"; a snake_case
    # `trust_block` sibling would be rejected as an extra key and 500 the API).
    results_path = run_dir / "results.json"
    if results_path.exists():
        results = json.loads(results_path.read_text())
        results.pop("trust_block", None)  # drop any stale snake_case sibling
        # Sanitize the trust block before inlining: WireResult.details may
        # carry non-finite floats (e.g. max_abs_delta=Inf when worst=inf) and
        # NistParam.sig_figs_agreed is ∞-capped for exact agreement.  Raw
        # model_dump() hands these through as Python float("inf"), which
        # json.dumps() renders as the non-RFC-8259 token ``Infinity`` — valid
        # in Python but rejected by JSON.parse() in every browser/bundler.
        results["trustBlock"] = _sanitize(block.model_dump(mode="json"))
        # Runtime L3: prove every audited claim's evidence resolves before the
        # write — a severed claim⇒evidence link halts emission (the andon cord).
        _assert_audited_claims_resolve(results, wire_status)
        results_path.write_text(json.dumps(results, indent=2, allow_nan=False))

    # Track rung + wire pass/total on the run's index entry so `spc-bench trend`
    # can chart verification health over time (the maintainer self-healing log).
    # Best-effort: a tracking-write failure must never red the audit.
    index_path = run_dir.parent.parent / "index.json"
    if index_path.exists():
        try:
            runs = json.loads(index_path.read_text(encoding="utf-8"))
            rung_val = getattr(block.rung, "value", block.rung)
            wires_pass = sum(1 for wr in wires if wr.status == "pass")
            for entry in runs:
                if entry.get("run_id") == run_dir.name:
                    entry["rung"] = rung_val
                    entry["wires_pass"] = wires_pass
                    entry["wires_total"] = len(wires)
                    break
            index_path.write_text(json.dumps(runs, indent=2) + "\n", encoding="utf-8")
        except (json.JSONDecodeError, OSError):
            pass

    return ledger
