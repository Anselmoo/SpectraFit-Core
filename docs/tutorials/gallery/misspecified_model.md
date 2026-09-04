---
icon: lucide/scan-search
description: A model that is simply wrong, fitted to real measured data — r-squared climbs to 0.99 and AIC falls by 300 while the residual stays structured at every step.
tags:
  - Validation
  - Models
---

# A Wrong Model with a Good $r^2$

!!! info "Real measured data, reproduced by permission"
    This page fits `manuscript/examples/fecl4/FeCl4_d5.txt`, the Fe L-edge of
    $[\text{FeCl}_4]^-$. **These spectra are reproduced in this repository by
    permission of the original authors and are not covered by its MIT licence**,
    which applies to the code. Cite Wasinger EC, de Groot FMF, Hedman B, Hodgson
    KO, Solomon EI. L-edge X-ray absorption spectroscopy of non-heme iron sites:
    experimental determination of differential orbital covalency. *J Am Chem
    Soc.* 2003;125(42):12894-906.
    [doi:10.1021/ja034634s](https://doi.org/10.1021/ja034634s). A third party
    wanting to reuse them should seek permission from those authors — see
    `manuscript/examples/fecl4/ro-crate-metadata.json`.

## Quick example

**Every other page in this gallery fits data the model can actually
describe.** This one deliberately does not, using a real measurement rather
than a synthetic fixture, because the effect it demonstrates is a property
of real spectra.

```python
--8<-- "misspecified_model.py:data"
```

The window spans the L3 white line near 707.9 eV and the weaker feature near
713.4 eV, stopping short of the L2 edge so the comparison stays about one
absorption region.

```python
--8<-- "misspecified_model.py:ladder"
```

A *run* is a maximal stretch of same-signed residuals. Independent noise around
a correct model gives about $2 n_+ n_- / n + 1$ runs; far fewer means the signs
arrive in long stretches — the curve sits systematically above the data in one
place and below it in another.

```python
--8<-- "misspecified_model.py:runs_test"
```

![Three fits of the same Fe L-edge window, top row, with residuals below each. The fitted curve visibly improves left to right while every residual panel keeps an oscillating systematic shape.](_static/misspecified_model.png)

## Why this works

Each other page in this gallery therefore ends with a high $r^2$ that means
what it appears to mean. Three models of the same L3 window, in increasing
order of elaboration, are compared here instead. Watch two scalar
goodness-of-fit scores and one property of the residual disagree completely:

| model | $r^2$ | AIC | runs | expected | $z$ |
|---|---:|---:|---:|---:|---:|
| 1 Gaussian | 0.87195 | 69.9 | 5 | 34.4 | −9.8 |
| 2 Gaussians | 0.97500 | −121.8 | 9 | 56.4 | −9.5 |
| 3 Voigts | 0.99098 | −233.1 | 22 | 59.3 | −7.1 |

$r^2$ climbs to 0.99. AIC falls by 300. **Both say "better" at every rung. The
runs test says "still the wrong model" at every rung, including the last.**

## What just happened

1. **One Gaussian ($r^2 = 0.872$)** — captures the white line and nothing else.
   The 713.4 eV feature is missed entirely and the residual carries it whole.
   Not a subtle failure; included as the baseline.

2. **Two Gaussians ($r^2 = 0.975$)** — now both features have a component, and
   the fit looks convincing at a glance. The residual has shrunk from $\pm 2$ to
   $\pm 1.5$ but kept its shape: the same oscillation across the white line,
   because a Gaussian cannot produce the line's wings.

3. **Three Voigts ($r^2 = 0.991$)** — a defensible model, and by both scalar
   scores an excellent one. The residual amplitude is down to $\pm 0.8$, yet it
   still oscillates through the white line with $z = -7.1$. The remaining
   structure is real: an Fe L3 edge carries multiplet structure that no small
   number of independent symmetric components reproduces.

**The residual amplitude falls at every rung. The residual *shape* does not.**
That distinction is invisible to $r^2$ and to AIC, both of which reduce the
residual to a single number and discard the ordering that carries the evidence.

!!! warning "What the runs test does and does not license"
    The test assumes independent residuals. This spectrum is oversampled — 0.1 eV
    steps across the white line — so genuinely correlated measurement noise
    would also depress the run count. Read a large negative $z$ as strong
    corroboration of what the residual panel already shows, not as a calibrated
    p-value. The claim here is "the residual is not noise", not a significance
    level.

## What to do about it

- **Plot the residual. Always.** Every conclusion on this page comes from the
  bottom row of the figure; the top row alone would have been persuasive and
  wrong.
- **Prefer a diagnostic that uses residual *order*** — a runs test, a
  Durbin-Watson statistic, an autocorrelation — over one that does not.
  $r^2$, $\chi^2_\text{red}$, AIC and BIC are all order-blind.
- **Do not fix structure by adding components.** Rungs 2 and 3 do exactly that
  and the structure survives both. A residual that keeps its shape while
  shrinking is telling you the *form* is wrong, not that the count is too low.
- **Let AIC/BIC rank models you already believe**, rather than certify that any
  of them is right. Rung 3 wins the AIC comparison decisively and is still
  rejected by the residual.

## See also

- **Related examples**: [`failed_fit.md`](failed_fit.md) (the other way to be
  misled — a converged fit reporting `success=True` with a negative $r^2$),
  [`confidence_intervals.md`](confidence_intervals.md) (uncertainties on
  parameters that assume the model is correct to begin with).
- **API docs**: `FitResult.residuals`, `FitResult.r_squared`, `FitResult.aic`,
  `FitResult.bic`.
- **Glossary**: [Glossary](../../glossary.md) — definitions for this page's
  project-specific terms (`residual`, `AIC`, `BIC`).
