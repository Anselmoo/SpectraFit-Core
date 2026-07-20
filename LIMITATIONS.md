# Known Limitations

`spectrafit-core` is **alpha** software. In the spirit of good scientific
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
  external-validation unlock rests on the 8 non-optional converging datasets;
  broader coverage is planned (see roadmap).

## Backends

- **JAX reports no parameter uncertainties.** The JAX backend returns no
  per-parameter σ (a `None` sentinel); uncertainty-coverage metrics are computed
  only where a backend supplies σ.

## Dashboard showcase

- **multidim / time-resolved showcases are deferred.** The contract carries `multidim` (2-D Gaussian map) and `time_resolved` (global joint fit) fields; their showcase panels are deferred — not rendered in this build.

## Planned validation (not yet built)

The credibility rung is a verification-*completeness* score, not a statistical
inference. Two validation axes are **disclosed as unmeasured** and tracked for a
later release (see the 2026-06-17 ADR in [DECISIONS.md](DECISIONS.md)):

- **Reduced / nested-model adequacy.** We never fit a reduced (fewer-term) model
  to full-model data and test whether the simplification is statistically adequate
  (likelihood-ratio / F-test / AIC-BIC). Model-selection robustness is unmeasured.
- **An inferential hypothesis test behind the headline.** The rung is an ASME V&V
  checklist, not a statistical test of the headline trust claim. The only
  inferential tests today — accuracy-parity equivalence (TOST, FDR-controlled) and
  bootstrap winner-stability — are scoped to per-case accuracy/speed.

## Status

- APIs (PyO3 ABI, the `BenchReport` contract, the `spc-bench` CLI) are **not yet
  stable**; breaking changes may occur before the beta release. See
  [DECISIONS.md](DECISIONS.md) for the API-stability review (planned for beta).
