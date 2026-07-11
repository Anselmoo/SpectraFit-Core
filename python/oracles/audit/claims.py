"""Claim registry. Claims register themselves; the runner discovers them.

Vista-trap preemption: the audit harness never references claims by name. Adding
the 101st claim is a single class definition; the runner picks it up from
``CLAIM_REGISTRY``. Mirrors ``MODEL_REGISTRY`` in ``oracles.models``.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, ClassVar

CLAIM_REGISTRY: dict[str, type["Claim"]] = {}

# Source-field sentinels that are NOT JSON paths into the payload (external
# oracle / file / API references). The runtime + test L3 resolvers skip these.
NON_PATH_SOURCE_FIELDS: frozenset[str] = frozenset(
    {"results.json", "/api/*", "scipy.least_squares"}
)


def resolve_source_field(payload: Any, path: str) -> bool:
    """Return True iff ``path`` resolves to ≥1 non-null value in ``payload``.

    Minimal JSON-path resolver shared by the data-level L3 test and the runtime
    L3 guard in :func:`oracles.audit.runner.run_audit`. Syntax::

        a.b        dict key traversal
        a[].b      list — at least one element must carry a non-null value
        a[Key]     list element whose ``name`` == Key, OR dict key ``Key``
        *          wildcard dict key (any value in a mapping)
    """
    parts = re.split(r"\.", path)
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
        seg, rest = segs[0], segs[1:]
        if seg == "[]":
            if not isinstance(node, list) or not node:
                return False
            return any(_resolve(item, rest) for item in node)
        m_bracket = re.match(r"^\[(.+)\]$", seg)
        if m_bracket:
            key = m_bracket.group(1)
            if isinstance(node, list):
                return any(
                    isinstance(item, dict) and item.get("name") == key and _resolve(item, rest)
                    for item in node
                )
            if isinstance(node, dict):
                return key in node and _resolve(node[key], rest)
            return False
        if seg == "*":
            if not isinstance(node, dict) or not node:
                return False
            return any(_resolve(v, rest) for v in node.values())
        if isinstance(node, dict):
            return seg in node and _resolve(node[seg], rest)
        return False

    return _resolve(payload, expanded)


class Claim:
    """Abstract claim. Subclasses set the four class attributes."""

    claim_id: ClassVar[str]  # e.g. "metric.r2"
    wire_id: ClassVar[str]   # W1..W6
    source_field: ClassVar[str]  # JSON path into results.json, e.g. "suite[].backends.spectrafit.r2"
    description: ClassVar[str]


def register_claim(cls: type[Claim]) -> type[Claim]:
    """Decorator: add a Claim subclass to the registry."""
    cid = cls.claim_id
    if "." not in cid:
        raise ValueError(f"claim_id must be a dotted namespace (e.g. 'metric.r2'); got {cid!r}")
    if cid in CLAIM_REGISTRY:
        raise ValueError(f"claim {cid!r} already registered")
    CLAIM_REGISTRY[cid] = cls
    return cls


def audited_count(wire_status: Mapping[str, str]) -> int:
    """Count claims whose backing verification wire passed.

    A claim is *audited* only when its declared ``wire_id`` maps to ``"pass"`` in
    ``wire_status``. A failing/skipped wire (e.g. W2c κ(J)) leaves its claims
    un-audited, so ``audited_count`` truthfully falls below the registered total
    instead of vacuously equalling it.
    """
    return sum(1 for c in CLAIM_REGISTRY.values() if wire_status.get(c.wire_id) == "pass")


# --- The claim ledger ------------------------------------------------------
# Each Claim links a load-bearing dashboard assertion to the wire that verifies
# it. The runner counts a claim as audited iff its backing wire passed.


@register_claim
class _SynthInvariants(Claim):
    claim_id = "synth.invariants"
    wire_id = "W1"
    source_field = "analyzed[].truth"
    description = "synthetic ground truth satisfies hypothesis invariants"


@register_claim
class _MetricR2(Claim):
    claim_id = "metric.r2"
    wire_id = "W2a"
    source_field = "analyzed[].profiles.*.summary.r2"
    description = "R² metric formula recomputed from stored best-fit and consistent with stored value"


@register_claim
class _MetricRmse(Claim):
    claim_id = "metric.rmse"
    wire_id = "W2a"
    source_field = "analyzed[].profiles.*.summary.rmse"
    description = "RMSE metric formula recomputed from stored best-fit and consistent with stored value"


@register_claim
class _MetricChi2(Claim):
    claim_id = "metric.chi2"
    wire_id = "W2a"
    source_field = "analyzed[].profiles.*.summary.chi2"
    description = (
        "χ² metric verified via reduced-χ² recompute (χ² = reduced-χ² × dof; "
        "same formula, checked against storedChi2Red in W2a)"
    )


@register_claim
class _MetricRedChi2(Claim):
    claim_id = "metric.red_chi2"
    wire_id = "W2a"
    source_field = "analyzed[].profiles.*.summary.redChi2"
    description = (
        "reduced χ² recomputed from stored y/fit/sigma/dof arrays and consistent "
        "with stored value (W2a)"
    )


@register_claim
class _UncertaintyCoverage(Claim):
    claim_id = "uncertainty.coverage"
    wire_id = "W2b"
    source_field = "analyzed[].profiles.*.uncertainty.coverage"
    description = "1σ coverage over MC ensemble within tolerance"


@register_claim
class _ConditioningKappa(Claim):
    claim_id = "conditioning.kappa"
    wire_id = "W2c"
    source_field = "analyzed[].profiles.*.jacobianConditionNumber"
    description = "Jacobian condition number finite & recomputed"


@register_claim
class _SolverOutputOracle(Claim):
    claim_id = "solver.output_oracle"
    wire_id = "W2d"
    # External-oracle sentinel (not a payload path) — like contract.roundtrip /
    # contract.api_schema, the L3 resolver skips these non-path source_fields.
    source_field = "scipy.least_squares"
    description = "fitted params + covariance σ match scipy.optimize.least_squares"


@register_claim
class _ContractRoundtrip(Claim):
    claim_id = "contract.roundtrip"
    wire_id = "W3"
    source_field = "results.json"
    description = "results.json round-trips bytewise through the contract"


@register_claim
class _ContractApiSchema(Claim):
    claim_id = "contract.api_schema"
    wire_id = "W4"
    source_field = "/api/*"
    description = "every API response validates against BenchReport"


@register_claim
class _GateGeomeanSpeedup(Claim):
    claim_id = "gate.geomean_speedup"
    wire_id = "W6"
    source_field = "manifest.geomeanSpeedupVsBaseline"
    description = "headline geomean speedup equals the gate value"


@register_claim
class _GateMaxDeltaR2(Claim):
    claim_id = "gate.max_delta_r2"
    wire_id = "W6"
    source_field = "manifest.maxAbsDeltaR2"
    description = "headline max |Δr²| equals the gate value"


@register_claim
class _GateWinRate(Claim):
    claim_id = "gate.win_rate"
    wire_id = "W6"
    source_field = "manifest.spectrafitWinRate"
    description = "subject win rate equals the gate value"


@register_claim
class _GateState(Claim):
    claim_id = "gate.state"
    wire_id = "W6"
    source_field = "manifest.gateState"
    description = "gate PASS/FAIL is a closed literal carried in the manifest"


@register_claim
class _InferenceSpeedupCi(Claim):
    claim_id = "inference.speedup_ci"
    wire_id = "W7"
    source_field = "inference.cases[].speedupCi"
    description = "speedup CIs reproduce from the seed"


@register_claim
class _InferenceDeltaR2Ci(Claim):
    claim_id = "inference.delta_r2_ci"
    wire_id = "W7"
    source_field = "inference.cases[].deltaR2Ci"
    description = "Δr² CIs reproduce from the seed"


@register_claim
class _InferenceEquivalence(Claim):
    claim_id = "inference.equivalence"
    wire_id = "W7"
    source_field = "inference.equivalence"
    description = "TOST equivalence verdicts reproduce from the seed"


# --- NIST StRD external-replication claims (W8) ------------------------------
# Each dataset's recovery of NIST's certified values is a distinct claim, backed
# by W8. They are audited only when W8 passes (all four datasets reproduce the
# certified values to ≥ the sig-fig threshold), which is also what unlocks RUNG_5.


@register_claim
class _NistGauss1(Claim):
    claim_id = "nist.gauss1"
    wire_id = "W8"
    source_field = "trustBlock.nist_validation.datasets[Gauss1]"
    description = "Gauss1 recovers NIST certified values to ≥ threshold sig figs"


@register_claim
class _NistGauss2(Claim):
    claim_id = "nist.gauss2"
    wire_id = "W8"
    source_field = "trustBlock.nist_validation.datasets[Gauss2]"
    description = "Gauss2 recovers NIST certified values to ≥ threshold sig figs"


@register_claim
class _NistGauss3(Claim):
    claim_id = "nist.gauss3"
    wire_id = "W8"
    source_field = "trustBlock.nist_validation.datasets[Gauss3]"
    description = "Gauss3 recovers NIST certified values to ≥ threshold sig figs"


@register_claim
class _NistLanczos1(Claim):
    claim_id = "nist.lanczos1"
    wire_id = "W8"
    source_field = "trustBlock.nist_validation.datasets[Lanczos1]"
    description = "Lanczos1 recovers NIST certified values to ≥ threshold sig figs"
