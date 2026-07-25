# Known Limitations

`spectrafit-core` is **beta** software (`0.1.0b1`, promoted from alpha 2026-06-23). In the spirit of good scientific
practice, the benchmark discloses its own credibility ceiling rather than hiding
it. The dashboard's render-truth credibility rung and claim ledger surface these
in-app; this file is the prose summary.

## Benchmark / verification

- **Jacobian conditioning (W2c) passes for the subject; lmfit/JAX are a disclosed
  oracle gap.** κ(J) is verified for spectrafit (the subject under test): the W2c
  wire reads `pass` when the audit sidecar shows a finite condition number for every
  subject entry. lmfit and JAX do not expose a Jacobian condition number, so for
  those oracles κ(J) is reported `n/a` — a disclosed per-backend limitation that is
  non-capping (it neither fails the wire nor caps the credibility rung). With no
  audit sidecar the wire is `skipped`, not `gap`. (A genuine `gap` arises only if the
  *subject* stops exposing κ.)
- **NIST StRD validation is a narrow subset.** External certified-value
  reproduction covers 10 of the 27 NIST StRD nonlinear-regression datasets — and
  those 10 span **6 model families** (Gauss1/2/3 share one DoubleExp+2-Gaussian
  model; +Lanczos1/MGH17 exponential-sum; +BoxBOD/Misra1a saturating-exponential;
  +Misra1b power-law saturation; +Bennett5 power-law-with-offset; +MGH09
  Kowalik–Osborne rational function). It is a *narrow* subset, not a representative
  one: MGH10 and many other StRD problems remain unexercised. Bennett5 and MGH09
  are included as kernel-correctness checks (the ``POWER_LAW_OFFSET`` and
  ``MGH09_RATIONAL`` kernels and parity oracles are verified), but LM-solver
  convergence to the certified values from the NIST published starts is not
  guaranteed — they are marked ``xfail`` in the scenario tests. The rung-5
  external-validation unlock rests on **all 10** NIST StRD datasets converging
  (including Bennett5 and MGH09) — the production W8 wire is a strict `all()`
  over every dataset, so a regression in either of those two would cap the rung
  at RUNG_2 like any other dataset failure; broader coverage is planned (see
  roadmap).

## Backends

- **JAX reports no parameter uncertainties.** The JAX backend returns no
  per-parameter σ (a `None` sentinel); uncertainty-coverage metrics are computed
  only where a backend supplies σ.

## Planned validation (not yet built)

The credibility rung is a verification-*completeness* score, not a statistical
inference. One validation axis remains **disclosed as a design limitation**
(see the 2026-06-17 ADR in [DECISIONS.md](DECISIONS.md)); nested-model adequacy
(reduced-vs-full model comparison via LRT/F-test/AIC-BIC) and the `multidim`/
`global_fit` dashboard showcases were both built and wired since this section
was last written — see `oracles/nested.py` (wire W9) and CLAUDE.md's "Native
showcases" note respectively:

- **The rung itself is not a single inferential hypothesis test.** The rung is
  an ASME V&V completeness checklist, not a statistical test of the headline
  trust claim. Today's inferential tests — accuracy-parity equivalence (TOST,
  FDR-controlled; per-case), bootstrap winner-stability (per-case), σ-calibration
  coverage (W10, a CI-inclusion TOST), and speed-significance (W11, a bootstrap
  CI on geomean speedup) — each scope a specific claim; none of them make the
  rung itself a single unified hypothesis test of "is this report trustworthy."

## Status

- APIs (PyO3 ABI, the `BenchReport` contract) are **not yet stable**; breaking
  changes may still occur post-beta, before a 1.0 release. See
  [DECISIONS.md](DECISIONS.md) for the API-stability review. The `spc-bench`
  console script no longer exists — it was removed entirely (Option A packaging,
  2026-06-23; a wheel-shipped console script whose deps live in the
  `[benchmark]` extra ImportErrors on a clean install). Run the bench via
  `uv run poe benchmark` or `python -m oracles.cli` instead.
