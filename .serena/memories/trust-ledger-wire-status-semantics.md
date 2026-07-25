# Trust Ledger + WireStatus Semantics (post 2026-06-13)

## WireStatus values
`WireStatus = Literal["pass", "warn", "fail", "skipped", "gap"]`

- `pass` — wire ran and found no problem
- `warn` — wire ran and found a non-blocking issue
- `fail` — wire ran and found a real problem (caps the credibility rung)
- `skipped` — wire not applicable for this case/backend
- `gap` — wire's capability is not yet implemented in the subject (e.g. W2c κ(J) not exposed by lmfit/jax); does NOT cap the rung

## Rung computation rule
`runner.py:_compute_rung`: only `fail` caps the rung downward. A `gap` is disclosed but does not penalize.
This distinction allowed rung 2→4 while W2c remained a disclosed gap.

## Credibility rungs
```python
class CredibilityRung(IntEnum):
    RUNG_1 = 1  # hand examples (reserved/not in use)
    RUNG_2 = 2  # regression tests with tolerances
    RUNG_3 = 3  # metamorphic / property-based + numerical reliability
    RUNG_4 = 4  # synthetic recovery with coverage  ← current earned level
    RUNG_5 = 5  # independent differential validation + UQ (reserved)
```

## Wires (W1–W7)
- W1 — synth.py invariants (hypothesis-based; E[noise]=0, var=σ²)
- W2a — metric identity: r²/RMSE/χ²/reduced-χ² recomputed from raw arrays matches stored
- W2b — 1σ stderr coverage: fraction of MC trials within ±stderr of truth ≈ 68%
- W2c — Jacobian condition number: κ(J) finite and recorded per (case, backend); currently `gap` for lmfit/jax
- W3 — JSON round-trip: results.json re-emitted through BenchReport equals original
- W4 — API schema: every /api/* response validates against BenchReport
- W5 — Render fidelity: Playwright asserts JSON values match DOM-rendered labels
- W6 — Gate state parity: every Python gate state has a TS handler; headline metrics match manifest
- W7 — Inference validity: speedup_ci/delta_r2_ci reproduce bitwise under fixed seed

## Claim ledger
`python/oracles/audit/claims.py` holds 16 registered `Claim` subclasses.
`audited_count(wire_status: dict[str, str]) -> int` returns claims whose backing wire's status is "pass".
Consequence: `n_claims_audited < n_claims_total` when a wire is `fail` or `gap` — this is honest, not a bug.

## Files
- `python/oracles/trust_ledger.py` — WireStatus, CredibilityRung, WireResult, TrustBlock, TrustLedger
- `python/oracles/audit/claims.py` — CLAIM_REGISTRY, @register_claim, 16 claims, audited_count
- `python/oracles/audit/wires.py` — wire_w1..wire_w7 functions
- `python/oracles/audit/runner.py` — run_audit(run_dir); called from benchmark/cli.py after build_report
- `trust.json` written next to manifest.json in each run dir

## Web rendering
- Audit/Verification destination (renamed from "Audit") shows wire matrix W1–W7 with gap rendered distinctly (not red)
- "M of N claims audited" line rendered when n_claims_total > 0 (was suppressed when 0/0)
- Rung badge on Standing deep-links to Verification

## Related
- `docs/_absorb/C1-decisions.md` — 2026-06-13 WireStatus gap + claim ledger entries
