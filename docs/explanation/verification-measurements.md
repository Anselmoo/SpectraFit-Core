---
icon: lucide/split
description: Two measurements behind the credibility ladder — how many significant digits post-fit statistics actually carry, and which of numerical, model-form, or input-uncertainty error dominates a reported stderr.
tags:
  - Validation
  - Benchmarking
  - Uncertainty
---

# Significant digits & the uncertainty budget

The credibility ladder ([The self-auditing benchmark](self-auditing-benchmark.md#credibility-rung-derivation))
reports rung 5. Two of its requirements are measurements, not assertions:
rung 3 needs the *number of significant digits* a reported quantity actually
carries, and rung 5 needs a *quantified uncertainty budget* splitting error
into its constituent sources. Both were closed on 2026-08-21 by two
Monte-Carlo studies run against the public `spectrafit_core` API. This page
reports what they found; the full method, raw tables, and reproduction
recipe live in the source records cited under [Raw records](#raw-records).

## Significant digits (rung 3)

No stochastic-arithmetic tool (Shaman, CADNA, Verificarlo) is installed in
this repository, so until this measurement the number of digits actually
significant in `chi2`, `r_squared`, a fitted parameter's value, and so on
was assumed rather than measured — "however many float64 prints." The
measurement instead perturbs every input datum by one unit in the last
place (ulp), in a random direction, refits from the same initial guess,
repeats $N=50$ times, and for each reported quantity $q$ computes

$$
s = -\log_{10}\!\left(\frac{\sigma_{\text{out}}}{|\mu_{\text{out}}|}\right)
$$

— the number of decimal digits of $q$ that survive an input perturbation at
the last representable bit, where $\mu_{\text{out}}$ and $\sigma_{\text{out}}$
are the sample mean and standard deviation across the 50 perturbed refits.
This is a Monte-Carlo-arithmetic *estimate*, not CADNA's or Shaman's
certified worst-case bound, and the 50-sample variance estimate itself
carries roughly $\pm 10\%$ relative uncertainty.

Run on a realistic two-Gaussian-plus-linear-background case (150 points,
$\sigma_\text{noise}=0.05$), every measured quantity carried between **14.61
and 16+ decimal digits** — essentially the full float64 noise floor:

| quantity | significant digits |
|---|---:|
| `chi2` | 14.61 (worst measured) |
| `reduced_chi2` | 14.61 (worst measured) |
| `condition_number` | 15.10 |
| stderr terms (all 8 parameters) | 14.89–14.92 |
| value terms (all 8 parameters) | 15.67–16.02 |
| `aic` / `bic` | 15.37–15.38 |
| `r_squared`, `p1.center.value` | >15.9 (exactly reproducible, `sigma=0`) |

**No quantity is printed to more digits than it measurably carries.** A
cross-check of every display call site across `python/oracles/*.py`,
`web/src/**`, and `docs/tutorials/gallery/*.py` found the tightest case —
`r_squared` at `.10f`, ~10–11 significant digits — still comfortably under
its measured budget of >15.9 digits. Every other call site prints 2–6
digits against a budget of 14.6–16+. The over-precision audit this rung
requires therefore finds nothing to fix; it closes the gap in the
"everything carries enough digits" direction, which is itself the valid
result the check exists to produce.

## The uncertainty budget (rung 5)

Rung 5 needs independent differential validation — which the project has,
via six solver backends and the National Institute of Standards and
Technology's Statistical Reference Datasets (NIST StRD) — plus a quantified
answer to "which error term dominates a reported `value` $\pm$ `stderr`, and
is it worth reducing?" Three terms were measured and ranked on a
representative single Gaussian fit ($A=5.0$, $c=2.0$, $\sigma=0.5$), each
held in isolation from a clean baseline (noiseless data, correct kernel,
double-precision arithmetic):

| term | magnitude (amplitude, representative case) | in units of term 3's $\sigma$ |
|---|---:|---:|
| 1. Numerical error | $\sim 2.7\times10^{-13}$ relative | $\sim 6.6\times10^{-11}\,\sigma$ |
| 2. Model-form error (wrong kernel) | $-2.85\%$ relative ($-4.75\sigma$) | $4.75\,\sigma$ |
| 3. Input uncertainty (measurement noise) | $\pm 0.4\%$ relative | $1\,\sigma$ (reference) |

**Model-form error dominates, at roughly 4.75$\times$ the input-uncertainty
term, when the fitted kernel is wrong.** Term 2 was measured by generating
synthetic data from a true Voigt profile (`ModelType.TRUE_VOIGT`, the
Faddeeva Gaussian $\otimes$ Lorentzian convolution — not the pinned
pseudo-Voigt alias `ModelType.VOIGT`) and fitting it with a plain
`ModelType.GAUSSIAN`. The fitted amplitude came out **4.75 reported standard
errors** away from truth: a fit that converges, reports `success=True`, and
hands back a 1$\sigma$ error bar that is wrong by nearly five of its own
error bars — purely from choosing the wrong lineshape. `center` came back
essentially unbiased (Voigt and Gaussian share a peak location by
construction), which is itself informative: model-form error is
parameter-specific, not a uniform inflation factor.

**Numerical error is utterly negligible** — about ten orders of magnitude
below the input-uncertainty floor, corroborated two ways: the rung-3
significant-digit measurement above (a relative floor of roughly
$10^{-14.6}$ to $10^{-16}$), and an independent refit of the representative
case with `y` perturbed at $10^{-12}$ relative magnitude, which produced an
output change of the same order with no amplification. Neither reading
leaves numerical precision as something worth spending effort on at this
problem scale and conditioning.

**Input uncertainty** — ordinary measurement-noise propagation — was
confirmed well-calibrated: 100 noisy refits landed the empirical parameter
spread inside the coverage harness's own [50%, 82%] envelope for a
68%-expected rate at $N=100$, i.e. the reported stderr is an honest estimate
of *this* term specifically.

### Method: OAT, not Sobol — stated plainly

The three terms were ranked with a **one-at-a-time (OAT)** sensitivity
sweep, not a first-order Sobol decomposition. A joint Sobol study would need
a single generative model driven simultaneously by all three factors —
floating-point rounding, a discrete kernel choice, and continuous
measurement noise don't share a natural combined sample space without
inventing one — and was judged disproportionate to the question this budget
exists to answer. The cost of that choice is stated, not hidden: **OAT
misses interaction effects entirely.** In particular it cannot tell us
whether a wrong-kernel fit makes the input-uncertainty term *more* sensitive
to noise than a correctly-specified fit would be, since a biased fit sits
away from the true residual minimum, which can distort the local curvature
the covariance estimate depends on. The ranking above is scoped to one
representative case and one wrong-kernel pairing (Gaussian-on-Voigt); a
different or subtler misspecification would likely change the multiplier,
not the order of magnitude.

### A defect found along the way

While building this budget, `crates/spectrafit-varpro`'s reported stderr
vector was found to be **permuted**: for a clean single Gaussian, `lm` and
`trf` both report `[0.011324, 0.004433, 0.004433]` for
`(amplitude, center, sigma)`, while `varpro` reports
`[0.004433, 0.011324, 0.004433]` — positions 0 and 1 swapped, though the
fitted *values* agree to six decimal places across all three solvers. Every
measurement in this budget therefore excludes `varpro` and uses `lm`.
Separately, `spectrafit-varpro` computes its covariance via the Kaufman
(1975) approximation[^kaufman-1975] rather than full Golub–Pereyra variable
projection[^golub-pereyra-1973], so even a correctly-indexed VarPro
covariance would be approximate by construction. Neither issue was fixed as part of this measurement — see the
[Changelog](../release-notes/changelog.md) for the fix once it lands.

## What neither measurement claims

- Neither is a certified worst-case bound (CADNA/Shaman-grade); both are
  Monte-Carlo estimates with the sample sizes and uncertainties stated
  above.
- The budget's ranking is scoped to one representative 1-D, single-Gaussian,
  well-conditioned case and one wrong-kernel pairing. A poorly conditioned
  or many-parameter fit could shift the numerical term out of "negligible,"
  and a different misspecification could shift the model-form multiplier —
  neither was tested here.
- No joint Sobol indices — see the OAT discussion above.

## The takeaway

For this project, at this problem scale, **numerical precision is not where
the error lives.** The dominant term by orders of magnitude is *which
lineshape you chose* — a wrong kernel biases a parameter by multiples of its
own reported error bar, while floating-point rounding stays roughly ten
orders of magnitude below the measurement-noise floor. That is a
concrete, measured answer to "where should I spend effort improving my
fit," and it could not be stated honestly before these two records existed.

## Raw records

The full method, complete result tables, and reproduction commands live in
two git-tracked records under `analysis/vv/` (excluded from the public
mirror by design, alongside the rest of `analysis/` — see
`scripts/publish_exclusions.py`):

- `analysis/vv/significant-digits.md` — the rung-3 measurement, including the
  full per-quantity digit table and the display-site cross-check.
- `analysis/vv/uncertainty-budget.md` — the rung-5 budget, including the
  representative-case setup, all three terms' full data, and the defect
  report above in full.

Reproduce the significant-digits measurement with:

```bash
uv run python scripts/measure_significant_digits.py --trials 50 --seed 20260821
```

The uncertainty budget was run interactively against the public API rather
than as a committed script; `analysis/vv/uncertainty-budget.md` carries the
exact recipe.

## See also

- **Related explanation**: [The self-auditing benchmark](self-auditing-benchmark.md) —
  how these two measurements feed the credibility-rung derivation.
  [NIST StRD Validation](nist-validation.md) — the certified-value agreement
  check these measurements complement.
- **Glossary**: [Glossary](../glossary.md) — definitions for this page's
  project-specific terms (`StRD`, `NIST`, `VarPro`, `residual`).

[^golub-pereyra-1973]: Golub, G. H. & Pereyra, V. (1973). "The Differentiation of
    Pseudo-Inverses and Nonlinear Least Squares Problems Whose Variables
    Separate." *SIAM Journal on Numerical Analysis* 10(2), 413–432.
    [10.1137/0710036](https://doi.org/10.1137/0710036).
[^kaufman-1975]: Kaufman, L. (1975). "A variable projection method for solving separable
    nonlinear least squares problems." *BIT* 15(1), 49–57.
    [10.1007/bf01932995](https://doi.org/10.1007/bf01932995).
