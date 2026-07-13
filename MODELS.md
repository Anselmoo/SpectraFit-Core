# Model Reference

Canonical formulas and parameter names for all models in spectrafit-core.

> **Authoritative source:** the `model_manifest!` macro in
> `crates/spectrafit-types/src/types.rs` — 34 wire variants, exported at runtime
> as `spectrafit_core._core.model_type_wire_strings()` and pinned by
> `tests/parity/test_schema_parity.py`. This document mirrors that manifest
> (all 34 variants below); if the two ever disagree, the manifest wins. The
> numpy formulas in `python/oracles/models.py` are the parity oracles —
> numerically identical to the Rust kernels (enforced by
> `tests/unit/oracles/test_wheel_eval.py`).

**Conventions:** amplitude = peak value at center (not area); σ = standard
deviation (not FWHM; FWHM = 2√(2 ln 2)·σ ≈ 2.355·σ); the pseudo-Voigt mixing
weight is always named **`fraction`** — never `eta`, never `frac`. Exceptions
where a parameter deliberately means something else (HWHM widths, asymptotic
amplitudes) are called out per section.

## Symmetric peak lineshapes

| Wire string | Formula | Parameters | Python `ModelType` |
|---|---|---|---|
| `gaussian` | `A · exp(−(x−c)²/(2σ²))` | amplitude, center, sigma | `GAUSSIAN` |
| `lorentzian` | `A / (1 + ((x−c)/σ)²)` — σ is the **HWHM** | amplitude, center, sigma | `LORENTZIAN` |
| `pseudo_voigt` | `fraction·L(x) + (1−fraction)·G(x)` | amplitude, center, sigma, **fraction** | `PSEUDO_VOIGT` |
| `voigt` | alias — same formula as Pseudo-Voigt (frozen copy on the Python side; dedicated Rust kernel cross-checked in the parity test) | amplitude, center, sigma, **fraction** | `VOIGT` |
| `true_voigt` | `A · Re[w(z)]/Re[w(z₀)]`, `z=((x−c)+iγ)/(σ√2)`, `z₀=iγ/(σ√2)` — true Gaussian⊗Lorentzian via the Faddeeva function (Rust: Hui–Armstrong–Wray, ~1e-6; numpy: `scipy.special.wofz` → wheel-vs-numpy parity ~1e-4) | amplitude, center, sigma, gamma | `TRUE_VOIGT` |
| `pearson7` | `A / [1 + ((x−c)/σ)²·(2^{1/m}−1)]^m` — σ is the **HWHM**; m→1 Lorentzian, m→∞ Gaussian | amplitude, center, sigma, m | `PEARSON7` |
| `moffat` | `A / (((x−c)/σ)² + 1)^β` | amplitude, center, sigma, beta | `MOFFAT` |
| `students_t` | `A / (1 + ((x−c)/σ)²/ν)^((ν+1)/2)` | amplitude, center, sigma, nu | `STUDENTS_T` |
| `log_normal` | `A · exp(−(ln(x/c))²/(2σ²))` for `x > 0`, else 0 — σ is the log-space width | amplitude, center, sigma | `LOG_NORMAL` |
| `harmonic_ir` | `A / ((c²−x²)² + (σ·x)²)` — driven damped harmonic-oscillator IR absorption | amplitude, center, sigma | `HARMONIC_IR` |

## Asymmetric / resonance lineshapes

| Wire string | Formula | Parameters | Python `ModelType` |
|---|---|---|---|
| `fano` | `A·(q+ε)²/(1+ε²)`, `ε=(x−c)/γ` | amplitude, center, gamma, q | `FANO` |
| `breit_wigner` | Breit–Wigner–Fano `A·(q·g+(x−c))²/(g²+(x−c)²)`, `g=σ/2` | amplitude, center, sigma, q | `BREIT_WIGNER` |
| `skewed_gaussian` | `A·exp(−½((x−c)/σ)²)·(1 + erf(γ(x−c)/(σ√2)))` — γ is the skew | amplitude, center, sigma, gamma | `SKEWED_GAUSSIAN` |
| `exp_gaussian` | Exponentially-modified Gaussian (EMG) `A·(γ/2)·exp(γ(c−x)+½(γσ)²)·erfc(z)`, `z=(c+γσ²−x)/(σ√2)` — evaluated via an overflow-free `erfcx` split; non-finite → 0 (Rust parity ~1e-9) | amplitude, center, sigma, gamma | `EXP_GAUSSIAN` |
| `doniach_sunjic` | `A·cos[πγ/2 + (1−γ)·atan(u)] / (1+u²)^((1−γ)/2)`, `u=(x−c)/σ` — XPS core-level asymmetry γ | amplitude, center, sigma, gamma | `DONIACH` |
| `split_gaussian` | Gaussian with width `sigma_l` for `x < c`, `sigma_r` for `x ≥ c` (bi-Gaussian) | amplitude, center, sigma_l, sigma_r | `SPLIT_GAUSSIAN` |
| `split_pearson7` | Pearson VII with per-side width **and** exponent (`sigma_l`/`m_l` left, `sigma_r`/`m_r` right) | amplitude, center, sigma_l, sigma_r, m_l, m_r | `SPLIT_PEARSON7` |
| `asym_ir` | `A·exp(−(x−c)²/(2σ²)) / (1 + exp(−k·(x−c)))` — Gaussian × logistic sigmoid; sigmoid exponent clamped at 50 (Rust parity) | amplitude, center, sigma, k | `ASYM_IR` |

## Multi-dimensional peaks

| Wire string | Formula | Parameters | Python `ModelType` |
|---|---|---|---|
| `gaussian2d` | `A · exp(−(x−cₓ)²/(2σₓ²) − (y−c_y)²/(2σ_y²))` — axis-aligned, `n_dims = 2` | amplitude, center_x, center_y, sigma_x, sigma_y | `GAUSSIAN2D` |
| `gaussian_nd` | `A · exp(−Σᵢ (xᵢ−cᵢ)²/(2σᵢ²))` — axis-aligned, parametric dimensionality (SP-2): D comes from the node's explicit `n_dims`; params are indexed | amplitude, center_0…center_{D−1}, sigma_0…sigma_{D−1} | `GAUSSIAN_ND` |

Both are engine subjects (the benchmark's 2-D map and N-D showcases) but are
exempt from the 1-D `oracles.models` `MODEL_REGISTRY` (see
`_MULTIDIM_EXEMPTIONS` in `tests/parity/test_model_type_registry_bijection.py`).

## Polynomial / background models

| Wire string | Formula | Parameters | Python `ModelType` |
|---|---|---|---|
| `constant` | `c` | c | `CONSTANT` |
| `linear` | `slope·x + intercept` | slope, intercept | `LINEAR` |
| `quadratic` | `A·(x−c)² + offset` | amplitude, center, offset | `QUADRATIC` |

The quadratic bowl backs the `convex_baseline` family (clean convex objectives); summing
several Quadratic nodes builds a sum-of-squares landscape, and pairing one with a Linear node
gives a tilted bowl (`diagonal_quadratic`).

## Step / edge models

`Arctan step` is `A·(½ + (1/π)·arctan((x−c)/σ))` — used as the absorption-edge background for
XAS K-edge cases. The catalog spells the params `step_height`/`step_center`/`step_width`;
these map to amplitude/center/sigma and are exposed as recoverable `bg.*` true params (see
`spectrum_schema._background_true_params`).

| Wire string | Formula | Parameters | Python `ModelType` |
|---|---|---|---|
| `arctan_step` | `A·(½ + (1/π)·arctan((x−c)/σ))` (rising) | amplitude, center, sigma | `ARCTAN_STEP` |
| `tanh_step` | `(A/2)·(1 + tanh((x−c)/σ))` (rising) | amplitude, center, sigma | `TANH_STEP` |
| `erfc_step` | `(A/2)·erfc((x−c)/(σ√2))` (**falling**) | amplitude, center, sigma | `ERFC_STEP` |

## Decay / kinetics models

| Wire string | Formula | Parameters | Python `ModelType` |
|---|---|---|---|
| `double_exponential` | `A1·exp(−lam1·x) + A2·exp(−lam2·x)` — `lam*` are **rate constants** (1/τ), not times | A1, lam1, A2, lam2 | `DOUBLE_EXPONENTIAL` |
| `kww` | Kohlrausch–Williams–Watts stretched exponential `A·exp(−(x/τ)^β)` for `x ≥ 0`, else 0 | amplitude, tau, beta | `KWW` |

## Saturation / rational models (NIST StRD kernels)

Real native kernels with exact Jacobians. For the saturating exponential and power-law
saturation kernels, `amplitude` is the **asymptotic saturation level** (the plateau approached
as `x → ∞`), not a peak-at-center value.

| Wire string | Formula | Parameters | Python `ModelType` | NIST |
|---|---|---|---|---|
| `saturating_exponential` | `A·(1 − exp(−rate·x))` | amplitude, rate | `SATURATING_EXPONENTIAL` | BoxBOD |
| `power_saturation` | `A·(1 − (1 + rate·x/2)^(−2))` | amplitude, rate | `POWER_SATURATION` | Misra1b |
| `power_law_offset` | `A·(offset + x)^(−1/shape)` — caller must keep `offset + x > 0` | amplitude, offset, shape | `POWER_LAW_OFFSET` | Bennett5 |
| `mgh09_rational` | Kowalik–Osborne `A·(x² + b₂x)/(x² + b₃x + b₄)` with `b₂=num_lin, b₃=den_lin, b₄=den_const` (`A=b₁`) | amplitude, num_lin, den_lin, den_const | `MGH09_RATIONAL` | MGH09 |

## Optical / dispersion models

| Wire string | Formula | Parameters | Python `ModelType` |
|---|---|---|---|
| `tauc` | Tauc band-gap edge `A·(x − e_gap)^p` for `x > e_gap`, else 0 (Heaviside cut keeps the fractional power real) | amplitude, e_gap, exponent | `TAUC` |
| `cauchy_dispersion` | Cauchy refractive-index dispersion `n(x) = a + b/x² + c/x⁴` for `x > 0`, else 0 | a, b, c | `CAUCHY_DISPERSION` |

## Test / optimization surrogates (benchmark only)

The four multimodal functions below are **not** native kernels: in the benchmark they are
approximated by a fixed **3-Gaussian basis solved by the global (DE) optimizer**, so their
reported r² reflects the basis ceiling, not solver convergence (see `_PATHOLOGICAL_MODELS` in
`backends/_spectrafit.py`).

| Model | Python fn | Benchmark `model_hint` | Rust `ModelType` | Fit basis |
|---|---|---|---|---|
| Ackley slice | `ackley_slice()` | `"ackley"` | — | 3-Gaussian + DE |
| Rastrigin slice | `rastrigin_slice()` | `"rastrigin"` | — | 3-Gaussian + DE |
| Rosenbrock projection | — | `"rosenbrock"` | — | 3-Gaussian + DE |
| Griewank projection | — | `"griewank"` | — | 3-Gaussian + DE |

## Parameter constraint surfaces

A parameter can be constrained (tied to another parameter's value or a formula) via **two equivalent surfaces**:

| Surface | Declaration | Note |
|---|---|---|
| `ExprEdge` | Add `ExprEdge(target_node=…, target_param=…, expression=…)` to `FitGraph.expr_edges` | Graph-level; best for multi-edge topologies built programmatically. |
| `Parameter.expr` | Set `expr="source_node.param"` on the target `Parameter` | Per-parameter; best for inline node construction. |

Both surfaces resolve through the **same** dependency-ordered, cycle-checked tied-plan evaluator. The constraint is applied on every solver iteration, so the converged result is numerically identical regardless of which surface is used. References must use fully-qualified `node_id.param` form (e.g. `"g1.sigma"`). Arithmetic is supported (`"g1.sigma * 2.0"`).

**`DuplicateExprTarget` error.** If the same `node.param` is targeted by both a `Parameter.expr` and a matching `ExprEdge`, the compiler raises a `DuplicateExprTarget` error at fit-compile time. Fix by removing one surface — pick either `ExprEdge` *or* `Parameter.expr` for each tie, never both.

**`vary` is irrelevant when `expr` is set.** The engine excludes any parameter whose `Parameter.expr` is non-`None` from the free set regardless of the `vary` flag. By convention set `vary=False` to make the intent obvious, but the engine would honour the tie either way.

**Solver coverage of ties.** Ties from either surface compile to the same tied-plan. The LM-family solvers (`lm`/`trf`/`geodesic`/`dogleg`/`newton-cg`/`irls`) apply it on every iteration. The `global` (differential-evolution) solver runs in two phases: the DE search holds tied parameters at their seed values, and the **post-search LM refinement** applies the tied-plan — so the **final** `global` result is tie-correct (CX-VPE-02). Both surfaces reach the identical result on every solver. Note the `global` solver is a stochastic global optimiser and is not guaranteed to find the global optimum on hard multi-modal landscapes.

**VarPro limitation.** The variable-projection (`solver="varpro"`) path does not support expression ties from **either** surface. A tied graph — whether the tie comes from an `expr_edge` or a per-parameter `Parameter.expr` — is never auto-selected for VarPro and is rejected by explicit `solver="varpro"` with `VarproExprEdgesUnsupported`. Both surfaces are guarded identically (CX-VPE-01, resolved); use `solver="lm"`, `"trf"`, or `"geodesic"` for tied fits.

## Pseudo-Voigt parameter name history

The mixing fraction has had three names across the codebase. The canonical name is now `fraction` everywhere:

| Location | Old name | Canonical name |
|---|---|---|
| Python `models.py` | `eta` | `fraction` |
| Catalog `true_params` | `"eta"` | `"fraction"` |
| Rust `pseudo_voigt.rs` | — | `"fraction"` ✓ |
| Rust `voigt.rs` | `"frac"` | `"fraction"` ✓ |
