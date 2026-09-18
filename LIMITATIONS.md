# Known Limitations

`spectrafit-core` is **beta** software (`0.1.0`, promoted from alpha 2026-06-23). In the spirit of good scientific
practice, the benchmark discloses its own credibility ceiling rather than hiding
it. The dashboard's render-truth credibility rung and claim ledger surface these
in-app; this file is the prose summary.

## Benchmark / verification

- **Jacobian conditioning (W2c) passes for the subject; lmfit/JAX are a disclosed
  oracle gap.** $\kappa(J)$ is verified for spectrafit (the subject under test): the W2c
  wire reads `pass` when the audit sidecar shows a finite condition number for every
  subject entry. lmfit and JAX do not expose a Jacobian condition number, so for
  those oracles $\kappa(J)$ is reported `n/a` — a disclosed per-backend limitation that is
  non-capping (it neither fails the wire nor caps the credibility rung). With no
  audit sidecar the wire is `skipped`, not `gap`. (A genuine `gap` arises only if the
  *subject* stops exposing $\kappa$.)
- **NIST StRD validation is a subset, and the shipped ledger is narrower than
  the current code.** Two numbers have to be kept apart here.

    *At the current commit*, `oracles.audit.nist._RECIPES` implements **22 of the
    27** NIST StRD nonlinear-regression datasets, each with a fixture in
    `python/oracles/nist_strd/` — Gauss1/2/3, Lanczos1/2/3, BoxBOD, Misra1a,
    Misra1b, MGH17, Bennett5, MGH09, Eckerle4, Roszman1, DanWood, Kirby2, Hahn1,
    Thurber, Rat42, Rat43, Chwirut1 and Chwirut2. Five StRD problems (ENSO,
    MGH10, Misra1c, Misra1d, Nelson) remain unexercised.

    *The shipped benchmark run's trust ledger* is older and narrower: its W8
    (`nist_certified_validation`) entry records `n_datasets: 10` with a minimum
    agreement of 6.4984 significant figures against a 4.0 threshold. The
    22-dataset figures above are recomputed at the current commit and are not yet
    baked into a shipped ledger. Neither number should be quoted as the other.

    The rung-5 external-validation unlock rests on **every** dataset in
    `_RECIPES` converging: `run_nist_validation` is a strict `all()` with no
    exclusion in the production path, so a regression in any one of them —
    including the two NIST-"Higher"-difficulty entries, Bennett5 and MGH09 —
    caps the rung exactly like any other dataset failure. (`tests/audit/`
    tracks a narrower optional-dataset subset for its own assertion; that
    exclusion is local to the test and never reaches the W8 wire.) Broader
    coverage is planned — see the roadmap.

    *Provenance:* the 22/27 count and the five named exclusions are Table 5
    and its lead-in in `manuscript/draft/sections/evidence.md` ("Agreement
    with certified reference values"), derived by
    `manuscript/examples/figures/nist_table2.py`.

- **The accuracy and speed denominators disagree, in this project's favour on
  both.** The headline $\max \lvert \Delta r^2 \rvert$ accuracy figure is
  measured over the 131 cases that remain once the `optfn` category is excluded
  (`python/oracles/reports.py:267`, `case.category != "optfn"`), while the
  geometric-mean speedup is measured over all 151. Those same `optfn` cases are
  the fastest category at 28.3x, so excluding them from the speed figure as well
  drops the speedup against lmfit from 16.4x to 15.1x. The category carved out
  of the accuracy claim is the one inflating the speed claim; the two headline
  numbers rest on different case sets, and neither should be read as qualifying
  the other. *Provenance:* the 16.4x figure is the deepest rung
  (`rung_050`, `reps_effective=50`) of `manuscript/examples/ladder/`; both
  denominators and the 15.1x recomputation are in
  `manuscript/draft/sections/evidence.md` under "What this evidence does not
  establish".
- **lmfit is the slowest comparator, so a speedup quoted against lmfit is the
  most favourable headline available.** The three `scipy-ls-*` configurations
  are faster than the lmfit baseline throughout, and on the `optfn` category
  they are faster than spectrafit-core too: 78.5x, 96.6x and 115.2x against
  that baseline, against spectrafit-core's own 28.3x on the same cases. The
  "no accuracy regressions" counter is also not an accuracy measurement — it
  flags non-convergence only. *Provenance:* the per-backend geomeans are in
  `manuscript/examples/ladder/` (`rung_050`); the framing is
  `manuscript/draft/sections/evidence.md`, "lmfit is the slowest comparator".
- **The timers are asymmetric, and both directions were measured.** On a
  10-case stratified sample, lmfit's covariance step is a median 12.6% of its
  own timed solve, so the speedup over lmfit is inflated by roughly that much.
  In the opposite direction, SciPy's standard-error step falls outside its
  timer and would add a median 4.4% if counted, so the speedup over SciPy is
  conservative by roughly that much. *Provenance:* both figures are measured
  and recorded in `manuscript/examples/figures/se_timer_bias.json`, produced
  by `manuscript/examples/figures/measure_se_timer_bias.py`.
- **Stopping tolerances are not normalised across backends.** Defaults very
  nearly coincide at 1e-8, except lmfit's MINPACK 1.49e-8, a looser tolerance
  that stops sooner. This compares configurations as they ship, not algorithms
  under a common stopping rule, so no reported ratio is tolerance-matched.
  *Provenance:* the per-backend `stopping` block (including lmfit's 1.49e-8)
  is recorded in `manuscript/examples/ladder/ladder.json` under
  `config.solvers`.
- **JAX timings reflect a partly cold compile cache.** JAX ran on CPU with no
  GPU result claimed, and its compiled-executable cache is deliberately
  bounded, which removes a cross-case compile-reuse advantage no other backend
  had. That is a fairness choice rather than a handicap, but it is a choice,
  and JAX timings should be read with it in mind. *Provenance:*
  `config.solvers.jax.runtime` in `manuscript/examples/ladder/ladder.json`
  records `device: "cpu:0"` and `compile_budget: 64`.
- **The NIST agreement figures are at the shipped tolerance, not the best one.**
  The certified-value audit runs every solver at 1e-12, the tolerance the
  shipped audit itself uses. A rerun at 1e-15 also ships, and it raises
  spectrafit-core's own significant-figure agreement without lowering any of
  them — so the shipped choice is not the most favourable one available to this
  project. See [NIST validation](explanation/nist-validation.md) for the method
  and for both tolerance runs. *Provenance:* the two runs are
  `manuscript/examples/figures/nist_table2.json` (1e-12, shipped) and
  `manuscript/examples/figures/nist_table2_tol1e15.json` (1e-15, the
  favourable rerun).

## Solver results

- **`success=True` does not mean the fit is good: a negative $r^2$ can still
  report success.** The degeneracy guard in
  `crates/spectrafit-solver/src/postfit.rs` demotes `success` only when
  $r^2 < 0$ **and** a free `.amplitude`/`.height` parameter has collapsed below
  1% of the data scale (`v.abs() / y_max_abs < 1e-2`). Both conditions must
  hold. A fit that converged to something worse than a flat line, but whose
  amplitude stays above that 1% line, keeps `success=True` and the ordinary
  `converged_ftol` message. The guard is narrow deliberately — a blanket
  "$r^2 < 0$ means failure" rule would misreport legitimate fits of data whose
  baseline the model was never asked to describe — but the consequence is that
  `success` is necessary and not sufficient. Read `r_squared` and the recovered
  parameters alongside it. A worked case that converges at $r^2 = -0.53$ and
  still reports `success=True` is in
  [When a Fit Fails](tutorials/gallery/failed_fit.md).

## Backends

- **JAX reports no parameter uncertainties.** The JAX backend returns no
  per-parameter $\sigma$ (a `None` sentinel); uncertainty-coverage metrics are computed
  only where a backend supplies $\sigma$.

## Planned validation (not yet built)

The credibility rung is a verification-*completeness* score, not a statistical
inference. One validation axis remains **disclosed as a design limitation**
(see the 2026-06-17 ADR in `DECISIONS.md`); nested-model adequacy
(reduced-vs-full model comparison via LRT/F-test/AIC-BIC) and the `multidim`/
`global_fit` dashboard showcases were both built and wired since this section
was last written — see `oracles/nested.py` (wire W9) and CLAUDE.md's "Native
showcases" note respectively:

- **The rung itself is not a single inferential hypothesis test.** The rung is
  an ASME V&V completeness checklist, not a statistical test of the headline
  trust claim. Today's inferential tests — accuracy-parity equivalence (TOST,
  FDR-controlled; per-case), bootstrap winner-stability (per-case), $\sigma$-calibration
  coverage (W10, a CI-inclusion TOST), and speed-significance (W11, a bootstrap
  CI on geomean speedup) — each scope a specific claim; none of them make the
  rung itself a single unified hypothesis test of "is this report trustworthy."

## Status

- APIs (PyO3 ABI, the `BenchReport` contract) are **not yet stable**; breaking
  changes may still occur post-beta, before a 1.0 release. See
  `DECISIONS.md` for the API-stability review. The `spc-bench`
  console script no longer exists — it was removed entirely (Option A packaging,
  2026-06-23; a wheel-shipped console script whose deps live in the
  `[benchmark]` extra ImportErrors on a clean install). Run the bench via
  `uv run poe benchmark` or `python -m oracles.cli` instead.

## Docs site

- **Body-link text fails WCAG AA contrast (light scheme).** `--md-typeset-a-color`
  (`docs/stylesheets/tokens/palette.css`), which drives all light-scheme body
  link text, resolves to `#007aff` — measured at ~4.02:1 contrast against a
  white background, short of the 4.5:1 AA threshold for normal-weight text.
  This is a disclosed, deliberately out-of-scope gap: `#007aff` is the
  systemBlue brand hex shared with the benchmark dashboard, so fixing it is a
  brand-color decision, not a one-off code fix.
