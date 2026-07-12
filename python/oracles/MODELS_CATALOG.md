# 100 Fitting Functions — Catalog & Implementation Status

Authoritative target catalog for the benchmark: lineshapes, UV/VIS, IR, XAS K-/L-edge,
time-resolved XAS, 2-D RIXS, noise models, and optimization benchmark functions
(from [useful-math-functions](https://anselmoo.github.io/useful-math-functions/latest/)).

**Status legend**
- ✅ **implemented** — a Rust kernel in `MODEL_REGISTRY` (or a `LANDSCAPE_REGISTRY` entry)
- ◐ **expressible** — no new kernel; a `CaseSpec`/`CaseFamily` recipe of existing kernels
- 🔲 **kernel** — needs a new 1-D Rust kernel via the multi-crate path (see below)
- 🧩 **engine** — needs an engine feature (2-D fit subject / IRF convolution / χ(k) class / noise knob)
- — **analysis** — a post-fit derived quantity, not a fittable curve (out of scope)

The multi-crate path for a 🔲 kernel (one new shape): `crates/spectrafit-models/src/<name>.rs`
(`Model`: eval + param_names + FD Jacobian) → `ModelTypeStr` in `crates/spectrafit-types`
→ `model_type_to_str` in **both** `spectrafit-graph` and `spectrafit-varpro` → Python
`ModelType` → bench `register_model` + a case recipe. The numpy oracle in
`oracles.models` must be **numerically identical** to the Rust kernel (the
`test_kernel_parity` gate). `log_normal` is the worked example.

> **Note on parallelization:** every 🔲 kernel edits the *same* shared registration files
> (`ModelTypeStr`, the two `model_type_to_str` tables, the Python enum, the bench registry),
> so kernels are **not** independently mergeable — they serialize on those files. A codegen
> step that emits those tables from one manifest would unlock parallel kernel work; until
> then, add kernels in small sequenced waves on the main branch.

---

## Part 1 — Lineshapes & Simple Peaks (1–12)
| # | Name | Status | Registry key / notes |
|---|------|--------|----------------------|
| 1 | Gaussian | ✅ | `gaussian` |
| 2 | Lorentzian | ✅ | `lorentzian` |
| 3 | Voigt (Faddeeva) | ✅ | `true_voigt` |
| 4 | Pseudo-Voigt | ✅ | `pseudo_voigt` / `voigt` |
| 5 | Pearson VII | ✅ | `pearson7` — params (A, x0, σ, m) |
| 6 | Asymmetric (split-σ) Gaussian | ✅ | `split_gaussian` — (A, μ, σ_L, σ_R) |
| 7 | Doniach–Šunjić | ✅ | `doniach_sunjic` |
| 8 | Fano | ✅ | `fano` |
| 9 | Log-Normal | ✅ | `log_normal` (positive-x) |
| 10 | Bi-Gaussian | ✅ | covered by `split_gaussian` (amplitude-continuous 2-width spec) — no separate kernel |
| 11 | Split-Pearson VII | ✅ | `split_pearson7` — (A, x0, σ_L, σ_R, m_L, m_R) |
| 12 | Skewed Gaussian / EMG | ✅ | `skewed_gaussian` + `exp_gaussian` |

## Part 2 — UV/VIS (13–22)
| # | Name | Status |
|---|------|--------|
| 13 Beer–Lambert | ◐ (linear) · 14/15 Gaussian mixtures ◐ · 16 Marcus–Hush ◐ (Gaussian) · 17 Tauc ✅ `tauc` ·
18 Drude 🧩 (complex ε) · 19 Cauchy dispersion ✅ `cauchy_dispersion` · 20 multi-chromophore ◐ ·
21 vibronic/Franck–Condon 🔲 (Poisson-weighted Gaussian sum) · 22 bands + baseline ◐ |

## Part 3 — IR (23–30)
23 harmonic oscillator ✅ `harmonic_ir` · 24/29 multi-Lorentzian + bg ◐ · 25 Morse levels — · 26 Fermi doublet ◐
(two Lorentzians) · 27 Fano-IR ✅ (`fano` + bg) · 28 Kubo width — (scalar T-law) · 30 asymmetric IR
(Gauss×sigmoid) ✅ `asym_ir`.

## Part 4 — XAS K-edge (31–42)
31 arctan ✅ `arctan_step` · 32 erf ✅ `erfc_step` · 33/34 ✅ (`reality` xas + `lineshapes` k_edge) ·
35 double-step ◐ · 40 white-line+step ✅ (`lineshapes`) · 41 Doniach+step ✅.
EXAFS 36/37/38/39/42 (χ(k) shells, Debye–Waller, splines, FT) 🧩 — a separate χ(k) model class.

## Part 5 — XAS L-edge (43–54)
43 double-step ✅ · 45 crystal-field ◐ · 47 spin-orbit ✅ (`lineshapes` l_edge) · 53 Fano exciton ✅.
46/54 lifetime/multiplet broadening 🧩 (convolution). 44/48/49/50/51 branching / XMCD / saturation /
sum-rules — (analyses).

## Part 6 — Time-resolved XAS (55–64)
🧩 needs the time-series engine path (multi-dataset `GlobalFitGraph` + IRF convolution).
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
**Implemented (✅) — all 20:** sphere(85), sum_squares(86), trid(87), zirilli(88), bohachevsky(89),
perm_beta(90), ackley(91), rastrigin(92), schwefel(93), griewank(94), levy(95), drop_wave(96),
egg_holder(97), cross_in_tray(98), shubert(99), cosine_mixture(100), plus rosenbrock,
styblinski_tang, salomon, alpine. (`cross_in_tray`'s `exp(100…)` is clamped to avoid overflow.)

---

## Current implementation snapshot

> Counts are exact: the `test_catalog_drift` guard fails CI if these lines drift from
> `len(MODEL_REGISTRY)` / `len(LANDSCAPE_REGISTRY)`, or if any registry key is unnamed below.

- **32 peak/background kernels** (`MODEL_REGISTRY`): gaussian, lorentzian, pseudo_voigt, voigt,
  fano, constant, linear, quadratic, arctan_step, tanh_step, erfc_step, double_exponential,
  true_voigt, skewed_gaussian, exp_gaussian, doniach_sunjic, log_normal, pearson7, split_gaussian,
  moffat, students_t, split_pearson7, breit_wigner, asym_ir, harmonic_ir, tauc,
  cauchy_dispersion, kww, **saturating_exponential**, **power_saturation**, **power_law_offset**,
  **mgh09_rational** (the four newest — the NIST StRD BoxBOD/Misra1a, Misra1b, Bennett5, and MGH09
  kernels). `voigt` is a frozen alias of `pseudo_voigt`.
- **20 optimization landscapes** (`LANDSCAPE_REGISTRY`, see Part 9): ackley, rastrigin, griewank,
  rosenbrock, schwefel, levy, bohachevsky, drop_wave, shubert, styblinski_tang, salomon, alpine,
  sphere, trid, zirilli, cosine_mixture, egg_holder, sum_squares, cross_in_tray, perm_beta.
- **Catalog:** 139 diversity-driven cases (no count padding) across easy / **complex** (asymmetric
  & true-Voigt & Fano blends) / reality / optfn / scaling / edge / lineshapes.

## Next kernels (highest diversity per unit of multi-crate work)
1. **vibronic/Franck–Condon** (21) — Poisson-weighted Gaussian progression.
2. **lorentzian2d** (66) / **voigt2d** (67) — separable 2-D RIXS products (gaussian2d pattern).
3. A χ(k) EXAFS model class (Part 4) and the IRF-convolution time-series path (Part 6).

Then the 🧩 engine features as separate efforts: a `noise_model` knob (Part 8), a 2-D fit subject
(Part 7), IRF convolution + multi-dataset (Part 6), and a χ(k) EXAFS class (Part 4).
