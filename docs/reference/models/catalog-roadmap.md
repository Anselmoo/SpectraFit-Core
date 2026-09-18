---
icon: lucide/list-checks
description: The 100-function target catalog behind spectrafit-core's benchmark — implementation status and next-kernel priorities, kept in sync with MODEL_REGISTRY/LANDSCAPE_REGISTRY by test_catalog_drift.py.
tags:
  - Benchmarking
  - Models
---

# 100 Fitting Functions — Catalog & Implementation Status

Authoritative target catalog for the benchmark: lineshapes, UV/VIS, IR, XAS K-/L-edge,
time-resolved XAS, 2-D RIXS, noise models, and optimization benchmark functions. The
optimization landscapes (Part 9) are attributed to primary literature and survey
citations there; [useful-math-functions](https://anselmoo.github.io/useful-math-functions/latest/)
is the *implementation* the Rust kernels are ported from, not the literature origin of
the functions themselves.

See the [Model Reference](index.md) for the canonical formulas and parameter
names of every currently-implemented (✅) model below — this page tracks the
broader target catalog and what's still planned.

**Status legend**
- ✅ **implemented** — a Rust kernel in `MODEL_REGISTRY` (or a `LANDSCAPE_REGISTRY` entry)
- ◐ **expressible** — no new kernel; a `CaseSpec`/`CaseFamily` recipe of existing kernels
- 🔲 **kernel** — needs a new 1-D Rust kernel via the multi-crate path (see below)
- 🧩 **engine** — needs an engine feature (2-D fit subject / IRF convolution / $\chi(k)$ class / noise knob)
- — **analysis** — a post-fit derived quantity, not a fittable curve (out of scope)

The multi-crate path for a 🔲 kernel (one new shape): `crates/spectrafit-models/src/<name>.rs`
(`Model`: eval + param_names + FD Jacobian) → `ModelTypeStr` variant + its match arm in
`ModelTypeStr::as_str()` in `crates/spectrafit-types` (the single canonical wire-format string
per model — callers in `spectrafit-graph::compiler` and `spectrafit-varpro` read this method;
there are no longer duplicate per-crate `model_type_to_str` tables to update) → Python
`ModelType` → bench `register_model` + a case recipe. The numpy oracle in
`oracles.models` must be **numerically identical** to the Rust kernel (the
`test_kernel_parity` gate). `log_normal` is the worked example.

> **Note on parallelization:** every 🔲 kernel still edits several shared registration files
> (`ModelTypeStr` + its `as_str()` match arm, the `spectrafit-builder` exhaustiveness gate, the
> Python enum, the bench registry), so kernels are **not** independently mergeable — they
> serialize on those files. A codegen step that emits those tables from one manifest would
> unlock parallel kernel work; until then, add kernels in small sequenced waves on the main
> branch.

---

## Part 1 — Lineshapes & simple peaks (1–12)
| # | Name | Status | Registry key / notes |
|---|------|--------|----------------------|
| 1 | Gaussian | ✅ | `gaussian` |
| 2 | Lorentzian | ✅ | `lorentzian` |
| 3 | Voigt (Faddeeva) | ✅ | `true_voigt` |
| 4 | Pseudo-Voigt | ✅ | `pseudo_voigt` / `voigt` |
| 5 | Pearson VII | ✅ | `pearson7` — params (A, x0, $\sigma$, m) |
| 6 | Asymmetric (split-$\sigma$) Gaussian | ✅ | `split_gaussian` — (A, $\mu$, $\sigma_L$, $\sigma_R$) |
| 7 | Doniach–Šunjić | ✅ | `doniach_sunjic` |
| 8 | Fano | ✅ | `fano` |
| 9 | Log-Normal | ✅ | `log_normal` (positive-x) |
| 10 | Bi-Gaussian | ✅ | covered by `split_gaussian` (amplitude-continuous 2-width spec) — no separate kernel |
| 11 | Split-Pearson VII | ✅ | `split_pearson7` — (A, x0, $\sigma_L$, $\sigma_R$, m_L, m_R) |
| 12 | Skewed Gaussian / EMG | ✅ | `skewed_gaussian` + `exp_gaussian` |

## Part 2 — UV/VIS (13–22)
| # | Name | Status |
|---|------|--------|
| 13 Beer–Lambert | ◐ (linear) · 14/15 Gaussian mixtures ◐ · 16 Marcus–Hush ◐ (Gaussian) · 17 Tauc ✅ `tauc` ·
18 Drude 🧩 (complex $\varepsilon$) · 19 Cauchy dispersion ✅ `cauchy_dispersion` · 20 multi-chromophore ◐ ·
21 vibronic/Franck–Condon 🔲 (Poisson-weighted Gaussian sum) · 22 bands + baseline ◐ |

## Part 3 — IR (23–30)
23 harmonic oscillator ✅ `harmonic_ir` · 24/29 multi-Lorentzian + bg ◐ · 25 Morse levels — · 26 Fermi doublet ◐
(two Lorentzians) · 27 Fano-IR ✅ (`fano` + bg) · 28 Kubo width — (scalar T-law) · 30 asymmetric IR
(Gauss$\times$sigmoid) ✅ `asym_ir`.

## Part 4 — XAS K-edge (31–42)
31 arctan ✅ `arctan_step` · 32 erf ✅ `erfc_step` · 33/34 ✅ (`reality` xas + `lineshapes`
k_edge) · 35 double-step ◐ · 40 white-line+step ✅ (`lineshapes`) · 41 Doniach+step ✅. Extended
X-ray Absorption Fine Structure (EXAFS) 36/37/38/39/42 ($\chi(k)$ shells, Debye–Waller,
splines, FT) 🧩 — a separate $\chi(k)$ model class.

## Part 5 — XAS L-edge (43–54)
43 double-step ✅ · 45 crystal-field ◐ · 47 spin-orbit ✅ (`lineshapes` l_edge) · 53 Fano exciton ✅.
46/54 lifetime/multiplet broadening 🧩 (convolution). 44/48/49/50/51 branching / XMCD / saturation /
sum-rules — (analyses).

## Part 6 — Time-resolved XAS (55–64)
🧩 needs the time-series engine path (multi-dataset `GlobalFitGraph` + instrument response
function (IRF) convolution).
56 bi-exponential ◐ (`double_exponential`). 57 KWW ✅ `kww` (stretched exponential, positive-t).
60 global analysis ✅ — `engine._global_fit()` runs a real multi-dataset `GlobalFitGraph`
joint fit (shared centers/widths across dataset slices, per-slice amplitudes). 64 SVD —.

## Part 7 — 2-D RIXS (65–76)
65 2-D Gaussian ✅ `gaussian2d` — spectrafit-core's native 2-D (n_dims=2) kernel. (SP-2:
`engine._multidim()` now fits a genuine **3-D** problem with the parametric `gaussian_nd`
kernel, `source=spectrafit-core`, not the scipy oracle.) 66 2-D Lorentzian 🔲 `lorentzian2d`
· 67 2-D Voigt 🔲 `voigt2d` (separable products).
68–76 (elastic line, phonon sidebands, Kramers–Heisenberg, …) 🧩 as 2-D suite cases.

## Part 8 — Noise models (77–84)
🧩 a per-case `noise_model` knob on `CaseSpec`/`materialize` (these GENERATE data, they are not
fittable kernels). 77 additive Gaussian ✅ (the engine adds Gaussian noise per case).
78 Poisson / 79 Cauchy / 80 pink / 81 heteroscedastic / 82 mixed / 83 AR(1) 🧩. 84 detector bg ◐.

## Part 9 — Optimization landscapes (85–100)
Fit a 2-Gaussian surrogate to a multimodal 1-D slice (`optfn` category, `LANDSCAPE_REGISTRY`).
The suite as a whole follows the benchmark-function compendium of Jamil &
Yang[^jamil-yang-2013]; the Rust kernels are ported from
[useful-math-functions](https://anselmoo.github.io/useful-math-functions/latest/), which is the
*implementation* source, not the literature origin of the functions.

**Implemented (✅) — all 20:** sphere(85), sum_squares(86), trid(87), zirilli(88),
bohachevsky(89)[^bohachevsky-1986], perm_beta(90), ackley(91)[^ackley-1987], rastrigin(92),
schwefel(93)[^schwefel-1981], griewank(94)[^griewank-1981], levy(95)[^levy-montalvo-1985],
drop_wave(96), egg_holder(97), cross_in_tray(98), shubert(99)[^shubert-1972],
cosine_mixture(100), plus rosenbrock[^rosenbrock-1960], styblinski_tang[^styblinski-tang-1990],
salomon[^salomon-1996], alpine. (`cross_in_tray`'s `exp(100…)` is clamped to avoid overflow.)

Nine of the twenty trace to a verifiable primary paper (footnoted above). For the
remaining eleven — sphere, sum_squares, trid, perm_beta, drop_wave, egg_holder,
cross_in_tray, cosine_mixture, alpine, rastrigin, and zirilli — **no primary source could be
established**: the first nine of those are standard benchmark-suite functions with no
identifiable originating paper, and Rastrigin's and Zirilli's namesakes could not be
independently verified (the monograph Rastrigin's function is usually traced to is unindexed in the sources checked, and
no record was found for Zirilli). All twenty are covered by the Jamil & Yang compendium
above; the eleven get no per-function citation beyond that.

---

## Current implementation snapshot

> Counts are exact: the `test_catalog_drift` guard fails CI if these lines drift from
> `len(MODEL_REGISTRY)` / `len(LANDSCAPE_REGISTRY)`, or if any registry key is unnamed below.

- **35 peak/background kernels** (`MODEL_REGISTRY`): gaussian, lorentzian, pseudo_voigt, voigt,
  fano, constant, linear, quadratic, arctan_step, tanh_step, erfc_step, double_exponential,
  true_voigt, skewed_gaussian, exp_gaussian, doniach_sunjic, log_normal, pearson7, split_gaussian,
  moffat, students_t, split_pearson7, breit_wigner, asym_ir, harmonic_ir, tauc,
  cauchy_dispersion, kww, saturating_exponential, power_saturation, power_law_offset,
  mgh09_rational, **rational_cubic**, **generalised_logistic**, **exp_over_linear**.
  `voigt` is a frozen alias of `pseudo_voigt`.

  The last three are deliberately *families* rather than one-dataset kernels, and each covers
  several NIST StRD problems at once: `rational_cubic` fits Kirby2 (quadratic/quadratic, with the
  cubic coefficients held at zero), Hahn1 and Thurber, and subsumes `mgh09_rational`;
  `generalised_logistic` fits Rat43 and, with its shape exponent fixed at 1, Rat42;
  `exp_over_linear` fits Chwirut1 and Chwirut2. Together with five datasets that needed no new
  kernel at all — Lanczos2 and Lanczos3 reuse Lanczos1's builder, Eckerle4 is a Gaussian whose
  amplitude is projected from its width, Roszman1 is a line plus an arctan step, and DanWood is a
  power law with the offset fixed — NIST StRD coverage is **22 of 27**.
- **20 optimization landscapes** (`LANDSCAPE_REGISTRY`, see Part 9): ackley, rastrigin, griewank,
  rosenbrock, schwefel, levy, bohachevsky, drop_wave, shubert, styblinski_tang, salomon, alpine,
  sphere, trid, zirilli, cosine_mixture, egg_holder, sum_squares, cross_in_tray, perm_beta.
- **Catalog:** 160 diversity-driven cases (no count padding) across ten categories: easy /
  **complex** (asymmetric & true-Voigt & Fano blends) / reality / optfn / scaling / edge /
  lineshapes / fixed / tied / robust (IRLS on outlier-contaminated spectra).

## Next kernels (highest diversity per unit of multi-crate work)
1. **vibronic/Franck–Condon** (21) — Poisson-weighted Gaussian progression.
2. **lorentzian2d** (66) / **voigt2d** (67) — separable 2-D RIXS products (gaussian2d pattern).
3. A $\chi(k)$ EXAFS model class (Part 4) and the IRF-convolution time-series path (Part 6).

Then the 🧩 engine features as separate efforts: a `noise_model` knob (Part 8), a 2-D fit subject
(Part 7), IRF convolution + multi-dataset (Part 6), and a $\chi(k)$ EXAFS class (Part 4).

## Next steps

- **Implement one of the kernels above** — [Adding a model](../../how-to/adding-a-model.md)
  walks the same multi-crate path (Rust kernel → `ModelTypeStr` → Python
  `ModelType` → bench registry) step by step.

[^jamil-yang-2013]: Jamil, M. & Yang, X.-S. (2013). "A literature survey of benchmark functions
    for global optimisation problems." *International Journal of Mathematical Modelling and
    Numerical Optimisation* 4(2), 150. https://doi.org/10.1504/ijmmno.2013.055204
[^rosenbrock-1960]: Rosenbrock, H. H. (1960). "An Automatic Method for Finding the Greatest or
    Least Value of a Function." *The Computer Journal* 3(3), 175-184.
    https://doi.org/10.1093/comjnl/3.3.175
[^ackley-1987]: Ackley, D. H. (1987). *A Connectionist Machine for Genetic Hillclimbing.*
    Springer US. https://doi.org/10.1007/978-1-4613-1997-9
[^griewank-1981]: Griewank, A. O. (1981). "Generalized descent for global optimization."
    *Journal of Optimization Theory and Applications* 34(1), 11-39.
    https://doi.org/10.1007/bf00933356
[^schwefel-1981]: Schwefel, H.-P. (1981). *Numerical Optimization of Computer Models.*
    Chichester: Wiley. (German original 1977.)
[^levy-montalvo-1985]: Levy, A. V. & Montalvo, A. (1985). "The Tunneling Algorithm for the
    Global Minimization of Functions." *SIAM Journal on Scientific and Statistical Computing*
    6(1), 15-29. https://doi.org/10.1137/0906002
[^bohachevsky-1986]: Bohachevsky, I. O., Johnson, M. E. & Stein, M. L. (1986). "Generalized
    Simulated Annealing for Function Optimization." *Technometrics* 28(3), 209-217.
    https://doi.org/10.1080/00401706.1986.10488128
[^shubert-1972]: Shubert, B. O. (1972). "A Sequential Method Seeking the Global Maximum of a
    Function." *SIAM Journal on Numerical Analysis* 9(3), 379-388.
    https://doi.org/10.1137/0709036
[^styblinski-tang-1990]: Styblinski, M. A. & Tang, T.-S. (1990). "Experiments in nonconvex
    optimization: Stochastic approximation with function smoothing and simulated annealing."
    *Neural Networks* 3(4), 467-483. https://doi.org/10.1016/0893-6080(90)90029-k
[^salomon-1996]: Salomon, R. (1996). "Re-evaluating genetic algorithm performance under
    coordinate rotation of benchmark functions." *Biosystems* 39(3), 263-278.
    https://doi.org/10.1016/0303-2647(96)01621-8
