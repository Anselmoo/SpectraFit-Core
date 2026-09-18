# Ground-truth reference — closing the oracle gap

Self-contained essentials. Historical specialist content lives in git
history under `.claude/skills/ground-truth/`.

## What "ground truth" means here

Scientific / numerical software has the oracle problem: how do you test
code whose correct answer you don't know? Strategies, in order of
preference:

1. **Manufactured solutions** — construct a problem with a known closed
   form, solve it, compare. The cleanest oracle when available.
2. **Convergence studies** — verify error → 0 at the predicted rate as
   resolution → ∞.
3. **Metamorphic relations** — if the input is transformed by f, the
   output must transform by g(f). Robust when no closed form exists.
4. **Significant-digit checks** — for tabulated reference data (NIST
   StRD), assert agreement to N digits.
5. **Differential tests** — compare against an independent
   implementation (lmfit vs spectrafit vs jax — already wired in).
6. **Synthetic ground truth** — generate data from a model the solver
   must recover; the model parameters are the truth.
7. **Uncertainty quantification** — report parameter standard errors
   and coverage probabilities, not just point estimates.

## The benchmark fairness contract (CLAUDE.md)

spectrafit is the **subject**; lmfit and jax (+optimistix) are
independent cross-verification **oracles**. The solve is timed in
isolation (the `run` call only) and via the compact `fit_fast` path,
so model construction and per-point array serialization never pollute
the comparison. Keep stopping tolerances matched across backends; do
not tighten one without the others.

## Claim-to-evidence map (for manuscripts)

When the user writes "spectrafit is N× faster than lmfit" in a
manuscript, the V&V skill ties that claim to its evidence:

| Claim type | Evidence required |
|------------|-------------------|
| Speedup | `manifest.geomean_speedup_vs_baseline` over a named scenario set |
| Accuracy | `max_abs_delta_r2` on the LM-family cases vs the named baseline |
| Robustness | win-rate + per-category breakdown + UQ coverage |
| Convergence | a convergence study with rate ≥ theoretical |
| Bit-identicality | a metamorphic test that flips a seed and asserts agreement |

A claim without a backing wire is flagged as **vacuous** — see
`oracles/audit/wires.py` (`n_claims_audited` counts non-vacuous
claims).

## Stuck-mode entry

A V&V finding that reopens — e.g. an oracle that says "no agreement"
when the eye says "looks right" — is often a tolerance mismatch or a
seed dependency. Curiosity sub-cycle: re-read the oracle's tolerance,
trace the seed through to the assertion.
