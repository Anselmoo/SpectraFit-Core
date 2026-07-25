"""Value-provenance spine — Invariant V, the single declarative source of truth.

Every numerical value the dashboard renders gets exactly one ``ValueProvenance``
record here: where it is produced, the contract field that carries it, the
independent oracle that checks it, the panel that renders it, and — crucially —
whether it is ``real`` or a ``proxy`` (and if a proxy, the tracked task to make
it real). The claim ledger, the proxy register, and contract-coverage all
*derive* from this registry, so a value's provenance can never drift across two
code paths.

Invariant V — End-to-end Value Provenance:

* **V1** produced for real at the source (not a proxy) — ``status``.
* **V2** a first-class contract field that resolves non-null — ``contract_field``.
* **V3** checked against an independent oracle within a declared tolerance —
  ``oracle``.
* **V4** no silent skip — ``skip_policy`` says what a missing check means.
* **V5** no silent proxy — ``status == "proxy"`` *requires* a ``proxy_task``
  (enforced structurally at construction; the best enforcement tier).

Vista-trap preemption (evolutionary-platform-thinking): adding the next metric
is a single record, not new gate code. The registry mirrors ``CLAIM_REGISTRY``
in :mod:`oracles.audit.claims` and ``MODEL_REGISTRY`` in :mod:`oracles.models`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

ProvenanceStatus = Literal["real", "proxy", "deferred"]
"""``real`` — computed for real + oracle-checked. ``proxy`` — a stand-in for an
unimplemented quantity (must be declared). ``deferred`` — a contract field that
exists but no panel renders yet."""

SkipPolicy = Literal["caps_rung", "gap"]
"""What a *missing* oracle check means (V4). ``caps_rung`` — a skip is a real
coverage hole that must cap the credibility rung (never a silent pass).
``gap`` — a disclosed capability absence (e.g. κ(J) not exposed) that does not
cap the rung but is reported honestly."""


class OracleRef(BaseModel):
    """The independent oracle that verifies a value, and its declared tolerance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    wire_id: str
    """The verification wire that performs the check (W1..W8, W2d)."""
    reference: str
    """Human-readable name of the independent reference the value is checked against."""
    tolerance: float | None = None
    """Declared numeric tolerance for the check; ``None`` for non-numeric / band /
    finite-only / bitwise-exact checks (described in ``reference``)."""


class ValueProvenance(BaseModel):
    """One rendered numerical value, traced source → contract → oracle → render."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    """Dotted namespace, e.g. ``"convergence.theta_distance"``. Equals the
    ``claim_id`` for values that are also audited claims."""
    source: str
    """The symbol / pipeline that produces the value (Rust fn, Python fn)."""
    contract_field: str
    """JSON-path leaf into the serialised BenchReport payload."""
    oracle: OracleRef | None = None
    """The independent oracle + tolerance (V3). ``None`` means no oracle yet —
    valid only for ``proxy`` / ``deferred`` values awaiting implementation."""
    panel_id: str | None = None
    """The web panel that renders this value, or ``None`` if deferred / not rendered."""
    status: ProvenanceStatus = "real"
    proxy_task: str | None = None
    """Tracked task to implement the real metric; required iff ``status == "proxy"``."""
    skip_policy: SkipPolicy = "caps_rung"

    @model_validator(mode="after")
    def _structural_invariants(self) -> "ValueProvenance":
        if "." not in self.id:
            raise ValueError(
                f"provenance id must be a dotted namespace (e.g. 'metric.r2'); got {self.id!r}"
            )
        if self.status == "proxy" and not self.proxy_task:
            raise ValueError(
                f"provenance {self.id!r}: status='proxy' requires a proxy_task "
                "(V5: no silent proxy)"
            )
        if self.status == "real" and self.oracle is None:
            raise ValueError(
                f"provenance {self.id!r}: status='real' requires an oracle "
                "(V3: a real value must be oracle-checked)"
            )
        return self


# --- recompute / band / exact oracle references -----------------------------
_RECOMPUTE = "recompute from raw x/y/fit arrays (W2a)"
_GATE_EXACT = "manifest headline equals the gate value (bitwise)"
_INFER_BITWISE = "seeded bootstrap reproduces bit-for-bit (W7)"
_NIST_CERT = "NIST StRD certified values, ≥ threshold sig figs (W8)"


def _record(
    id: str,
    source: str,
    contract_field: str,
    *,
    wire_id: str,
    reference: str,
    tolerance: float | None = None,
    panel_id: str | None = None,
    skip_policy: SkipPolicy = "caps_rung",
) -> ValueProvenance:
    return ValueProvenance(
        id=id,
        source=source,
        contract_field=contract_field,
        oracle=OracleRef(wire_id=wire_id, reference=reference, tolerance=tolerance),
        panel_id=panel_id,
        status="real",
        skip_policy=skip_policy,
    )


# --- The provenance ledger --------------------------------------------------
# Audited-claim values (parity with CLAIM_REGISTRY: id == claim_id,
# contract_field == claim.source_field, oracle.wire_id == claim.wire_id).
_RECORDS: list[ValueProvenance] = [
    _record(
        "synth.invariants",
        "oracles.synth ground-truth generator",
        "analyzed[].truth",
        wire_id="W1",
        reference="hypothesis invariants on synthetic ground truth",
    ),
    _record(
        "metric.r2",
        "spectrafit_core fit → FitResult.r_squared",
        "analyzed[].profiles.*.summary.r2",
        wire_id="W2a",
        reference=_RECOMPUTE,
        tolerance=1e-6,
    ),
    _record(
        "metric.rmse",
        "spectrafit_core fit → residuals → rmse_of",
        "analyzed[].profiles.*.summary.rmse",
        wire_id="W2a",
        reference=_RECOMPUTE,
        tolerance=1e-6,
    ),
    _record(
        "metric.chi2",
        "spectrafit_core fit → FitResult.chi2",
        "analyzed[].profiles.*.summary.chi2",
        wire_id="W2a",
        reference="recompute reduced-χ² from raw x/y/fit/sigma/dof arrays (χ²=red_chi2×dof; W2a)",
        tolerance=1e-6,
    ),
    _record(
        "metric.red_chi2",
        "spectrafit_core fit → FitResult.reduced_chi2",
        "analyzed[].profiles.*.summary.redChi2",
        wire_id="W2a",
        reference=_RECOMPUTE,
        tolerance=1e-6,
    ),
    _record(
        "uncertainty.coverage",
        "oracles.metrics.pulls_from_mc over the MC ensemble",
        "analyzed[].profiles.*.uncertainty.coverage",
        wire_id="W2b",
        reference="1σ pull coverage within band [0.5, 0.85]",
    ),
    _record(
        "conditioning.kappa",
        "spectrafit_core fit → FitResult.condition_number (κ(JᵀJ))",
        "analyzed[].profiles.*.jacobianConditionNumber",
        wire_id="W2c",
        reference="κ(J) finite (capability gap if unexposed)",
        skip_policy="gap",
    ),
    _record(
        "solver.output_oracle",
        "spectrafit_core.fit vs scipy.optimize.least_squares (method='lm')",
        "scipy.least_squares",
        wire_id="W2d",
        reference="independent LM oracle: params (rel<1e-4) + covariance σ (rel<0.10)",
    ),
    _record(
        "contract.roundtrip",
        "oracles.bench_contract.BenchReport round-trip",
        "results.json",
        wire_id="W3",
        reference="results.json round-trips bytewise through the contract",
    ),
    _record(
        "contract.api_schema",
        "oracles.api FastAPI responses",
        "/api/*",
        wire_id="W4",
        reference="every API response validates against BenchReport",
    ),
    _record(
        "gate.geomean_speedup",
        "oracles.reports._compute_headline_numbers",
        "manifest.geomeanSpeedupVsBaseline",
        wire_id="W6",
        reference=_GATE_EXACT,
        tolerance=0.0,
        panel_id="standing-headline",
    ),
    _record(
        "gate.max_delta_r2",
        "oracles.reports._compute_headline_numbers",
        "manifest.maxAbsDeltaR2",
        wire_id="W6",
        reference=_GATE_EXACT,
        tolerance=0.0,
        panel_id="standing-headline",
    ),
    _record(
        "gate.win_rate",
        "oracles.reports._compute_headline_numbers",
        "manifest.spectrafitWinRate",
        wire_id="W6",
        reference=_GATE_EXACT,
        tolerance=0.0,
        panel_id="standing-headline",
    ),
    _record(
        "gate.state",
        "oracles.reports._compute_default_gate_state",
        "manifest.gateState",
        wire_id="W6",
        reference="gate PASS/WARN/FAIL is a closed literal carried in the manifest",
        panel_id="standing-headline",
    ),
    _record(
        "inference.speedup_ci",
        "oracles.inference.speedup_ci (seed=20260612)",
        "inference.cases[].speedupCi",
        wire_id="W7",
        reference=_INFER_BITWISE,
        tolerance=0.0,
    ),
    _record(
        "inference.delta_r2_ci",
        "oracles.inference.delta_r2_ci (seed=20260612)",
        "inference.cases[].deltaR2Ci",
        wire_id="W7",
        reference=_INFER_BITWISE,
        tolerance=0.0,
    ),
    _record(
        "inference.equivalence",
        "oracles.inference.tost_paired (seed=20260612)",
        "inference.equivalence",
        wire_id="W7",
        reference=_INFER_BITWISE,
    ),
    _record(
        "nist.gauss1",
        "oracles.audit.nist.run_nist_validation",
        "trustBlock.nist_validation.datasets[Gauss1]",
        wire_id="W8",
        reference=_NIST_CERT,
        panel_id="nist-validation",
    ),
    _record(
        "nist.gauss2",
        "oracles.audit.nist.run_nist_validation",
        "trustBlock.nist_validation.datasets[Gauss2]",
        wire_id="W8",
        reference=_NIST_CERT,
        panel_id="nist-validation",
    ),
    _record(
        "nist.gauss3",
        "oracles.audit.nist.run_nist_validation",
        "trustBlock.nist_validation.datasets[Gauss3]",
        wire_id="W8",
        reference=_NIST_CERT,
        panel_id="nist-validation",
    ),
    _record(
        "nist.lanczos1",
        "oracles.audit.nist.run_nist_validation",
        "trustBlock.nist_validation.datasets[Lanczos1]",
        wire_id="W8",
        reference=_NIST_CERT,
        panel_id="nist-validation",
    ),
    # --- Convergence-to-truth: now REAL (was a χ²-floor proxy) ---------------
    # Per-iteration θ is recorded by the faer LM driver (FitResult.params_history),
    # the engine computes dₖ = ‖(θₖ − θ_true)/s‖₂ into the contract field, and the
    # web renders it directly. Oracle = the ground-truth V&V test.
    _record(
        "convergence.theta_distance",
        "oracles.engine._theta_distance_to_truth (from FitResult.params_history)",
        "analyzed[].profiles.*.thetaDistance",
        wire_id="vv-convergence",
        reference=(
            "ground-truth V&V: dₖ decreases to ≤ recovery tol on synthetic cases "
            "(tests/integration/benchmark/test_convergence_to_truth.py)"
        ),
        tolerance=0.1,
        panel_id="convergence-truth",
    ),
]


def _build_registry(records: list[ValueProvenance]) -> dict[str, ValueProvenance]:
    registry: dict[str, ValueProvenance] = {}
    for rec in records:
        if rec.id in registry:
            raise ValueError(f"duplicate provenance id {rec.id!r}")
        registry[rec.id] = rec
    return registry


VALUE_PROVENANCE: dict[str, ValueProvenance] = _build_registry(_RECORDS)
