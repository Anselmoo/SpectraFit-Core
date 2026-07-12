"""Trust-ledger contract — single source of truth for what was audited.

The TrustBlock is embedded in BenchReport (optional, additive). It maps each
audited claim to a wire-id, the evidence sentence, and a pass/warn/fail status,
plus an aggregate credibility rung. The block is written to disk as
``trust.json`` next to ``manifest.json`` AND inlined into ``results.json`` so a
single payload carries its own provenance.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Wire outcomes. `gap` is distinct from `fail`: it means the property could not be
# verified because the backend does NOT expose the input (a disclosed CAPABILITY
# gap, e.g. κ(J) is not surfaced by spectrafit/lmfit/jax), not because a computed
# value was wrong. Like `skipped`, a `gap` does not cap the credibility rung; only
# a genuine `fail` does (see runner._compute_rung).
WireStatus = Literal["pass", "warn", "fail", "skipped", "gap"]


class CredibilityRung(IntEnum):
    """V&V maturity ladder (inspired by ASME V&V credibility levels).

    The live wire set earns RUNG_2..RUNG_4. RUNG_1 / RUNG_5 are reserved
    end-stops (see the per-member comments), part of the public contract and
    pinned by an enum-value test — reserved, not dead.
    """

    RUNG_1 = 1  # reserved: hand examples / smoke only (below this suite's floor)
    RUNG_2 = 2  # regression tests with tolerances
    RUNG_3 = 3  # metamorphic / property-based + numerical reliability
    RUNG_4 = 4  # synthetic recovery with coverage
    RUNG_5 = (
        5  # reserved: independent differential validation + UQ (external replication)
    )


class WireResult(BaseModel):
    """One verification wire's outcome."""

    model_config = ConfigDict(extra="forbid")

    wire_id: str = Field(..., description="W1..W6 from the value-stream diagram.")
    name: str
    status: WireStatus
    evidence: str = Field(..., description="One-line evidence statement.")
    details: dict[str, float | int | str | bool | None] = Field(default_factory=dict)


class NistParam(BaseModel):
    """One parameter's certified-vs-fitted agreement for a NIST StRD dataset."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="NIST parameter name, e.g. 'b1'.")
    certified: float = Field(..., description="NIST certified value (10+ sig figs).")
    fitted: float = Field(..., description="Spectrafit recovered value.")
    sig_figs_agreed: float = Field(
        ...,
        description="-log10(|fitted-certified|/|certified|); ∞-capped for exact agreement.",
    )


class NistDataset(BaseModel):
    """Per-dataset NIST StRD certified-value validation result."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="StRD problem name, e.g. 'Gauss1'.")
    model: str = Field(..., description="Human-readable model description.")
    n_params: int
    params: list[NistParam]
    min_sig_figs: float = Field(
        ..., description="Worst (minimum) per-parameter sig-fig agreement."
    )
    passed: bool = Field(
        ..., description="True iff min_sig_figs ≥ the validation threshold."
    )


class NistValidation(BaseModel):
    """Aggregate NIST StRD certified-value validation (the W8 evidence block).

    Independent external replication against NIST's extended-precision certified
    values — the evidence RUNG_5 was reserved for. Additive on TrustBlock.
    """

    model_config = ConfigDict(extra="forbid")

    threshold_sig_figs: float = Field(
        ..., description="Required minimum significant-figure agreement."
    )
    datasets: list[NistDataset]
    min_sig_figs: float = Field(
        ..., description="Worst min_sig_figs across all datasets."
    )
    passed: bool = Field(
        ..., description="True iff every dataset agrees to ≥ threshold sig figs."
    )
    total_available: int | None = Field(
        default=None,
        description=(
            "Size of the external NIST StRD nonlinear-regression universe (the "
            "denominator for 'N of M' coverage). Emitted by the validation builder so "
            "the UI never hardcodes the total. Additive — None for payloads written "
            "before this field existed."
        ),
    )


class TrustBlock(BaseModel):
    """Aggregate trust evidence attached to a BenchReport."""

    model_config = ConfigDict(extra="forbid")

    rung: CredibilityRung
    wires: list[WireResult]
    n_claims_audited: int
    n_claims_total: int
    nist_validation: NistValidation | None = Field(
        default=None,
        description=(
            "NIST StRD certified-value validation (W8). Additive — Pydantic fills "
            "None for payloads that predate the A7 external-validation wire."
        ),
    )

    @model_validator(mode="after")
    def _rung5_requires_nist_and_inference(self) -> "TrustBlock":
        if self.rung != CredibilityRung.RUNG_5:
            return self
        # NIST StRD (W8) evidence must be present and passed (existing requirement).
        if not (self.nist_validation is not None and self.nist_validation.passed):
            raise ValueError(
                "rung==RUNG_5 requires nist_validation present with passed=True "
                "(claim↔evidence integrity: no claim without visible evidence)"
            )
        # Inferential wires W10 (σ-calibration) and W11 (speed inference) must
        # both be present with status "pass" (no pass-by-absence at the ceiling).
        w10_pass = any(
            w.wire_id == "W10" and w.status == "pass" for w in self.wires
        )
        if not w10_pass:
            raise ValueError(
                "rung==RUNG_5 requires a WireResult with wire_id='W10' and "
                "status='pass' (σ-calibration inference wire — claim↔evidence integrity)"
            )
        w11_pass = any(
            w.wire_id == "W11" and w.status == "pass" for w in self.wires
        )
        if not w11_pass:
            raise ValueError(
                "rung==RUNG_5 requires a WireResult with wire_id='W11' and "
                "status='pass' (speed inference wire — claim↔evidence integrity)"
            )
        return self


class TrustLedger(BaseModel):
    """Persisted ledger written to ``trust.json``."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    run_id: str
    block: TrustBlock
