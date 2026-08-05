---
icon: lucide/sigma
description: Canonical formulas, parameter names, and wire strings for all 34 models in spectrafit-core, mirroring the model_manifest! macro.
---

# Model Reference

Canonical formulas and parameter names for all models in spectrafit-core.

!!! note "Authoritative source"
    The `model_manifest!` macro in
    `crates/spectrafit-types/src/types.rs` — 34 wire variants, exported at runtime
    as `spectrafit_core._core.model_type_wire_strings()` and pinned by
    `tests/parity/test_schema_parity.py`. This document mirrors that manifest
    (all 34 variants below); if the two ever disagree, the manifest wins. The
    numpy formulas in `python/oracles/models.py` are the parity oracles —
    numerically identical to the Rust kernels (enforced by
    `tests/unit/oracles/test_wheel_eval.py`).

**Conventions:** amplitude = peak value at center (not area); $\sigma$ = standard
deviation (not FWHM; $\mathrm{FWHM} = 2\sqrt{2\ln 2}\,\sigma \approx 2.355\,\sigma$);
the pseudo-Voigt mixing weight is always named **`fraction`** — never `eta`, never
`frac`. Exceptions where a parameter deliberately means something else (HWHM
widths, asymptotic amplitudes) are called out per section.

## Symmetric peak lineshapes

| Wire string | Formula | Parameters | Python `ModelType` |
|---|---|---|---|
| `gaussian` | $A \cdot e^{-(x-c)^2/(2\sigma^2)}$ | amplitude, center, sigma | `GAUSSIAN` |
| `lorentzian` | $A / (1 + ((x-c)/\sigma)^2)$ — $\sigma$ is the **HWHM** | amplitude, center, sigma | `LORENTZIAN` |
| `pseudo_voigt` | $\text{fraction} \cdot L(x) + (1-\text{fraction}) \cdot G(x)$ | amplitude, center, sigma, **fraction** | `PSEUDO_VOIGT` |
| `voigt` | alias — same formula as Pseudo-Voigt (frozen copy on the Python side; dedicated Rust kernel cross-checked in the parity test) | amplitude, center, sigma, **fraction** | `VOIGT` |
| `true_voigt` | $A \cdot \mathrm{Re}[w(z)]/\mathrm{Re}[w(z_0)]$, $z=((x-c)+i\gamma)/(\sigma\sqrt{2})$, $z_0=i\gamma/(\sigma\sqrt{2})$ — true Gaussian⊗Lorentzian via the Faddeeva function (Rust: Hui–Armstrong–Wray, ~1e-6; numpy: `scipy.special.wofz` → wheel-vs-numpy parity ~1e-4) | amplitude, center, sigma, gamma | `TRUE_VOIGT` |
| `pearson7` | $A / \left[1 + \left(\dfrac{x-c}{\sigma}\right)^2 (2^{1/m}-1)\right]^m$ — $\sigma$ is the **HWHM**; $m\to 1$ Lorentzian, $m\to\infty$ Gaussian | amplitude, center, sigma, m | `PEARSON7` |
| `moffat` | $A / \left(\left(\dfrac{x-c}{\sigma}\right)^2 + 1\right)^\beta$ | amplitude, center, sigma, beta | `MOFFAT` |
| `students_t` | $A / \left(1 + \dfrac{((x-c)/\sigma)^2}{\nu}\right)^{(\nu+1)/2}$ | amplitude, center, sigma, nu | `STUDENTS_T` |
| `log_normal` | $A \cdot e^{-(\ln(x/c))^2/(2\sigma^2)}$ for $x > 0$, else 0 — $\sigma$ is the log-space width | amplitude, center, sigma | `LOG_NORMAL` |
| `harmonic_ir` | $A / ((c^2-x^2)^2 + (\sigma x)^2)$ — driven damped harmonic-oscillator IR absorption | amplitude, center, sigma | `HARMONIC_IR` |

## Asymmetric / resonance lineshapes

| Wire string | Formula | Parameters | Python `ModelType` |
|---|---|---|---|
| `fano` | $A(q+\epsilon)^2/(1+\epsilon^2)$, $\epsilon=(x-c)/\gamma$ | amplitude, center, gamma, q | `FANO` |
| `breit_wigner` | Breit–Wigner–Fano $A(qg+(x-c))^2/(g^2+(x-c)^2)$, $g=\sigma/2$ | amplitude, center, sigma, q | `BREIT_WIGNER` |
| `skewed_gaussian` | $A e^{-\frac{1}{2}((x-c)/\sigma)^2}\left(1 + \mathrm{erf}\left(\dfrac{\gamma(x-c)}{\sigma\sqrt{2}}\right)\right)$ — $\gamma$ is the skew | amplitude, center, sigma, gamma | `SKEWED_GAUSSIAN` |
| `exp_gaussian` | Exponentially-modified Gaussian (EMG) $A\dfrac{\gamma}{2} e^{\gamma(c-x)+\frac{1}{2}(\gamma\sigma)^2}\,\mathrm{erfc}(z)$, $z=\dfrac{c+\gamma\sigma^2-x}{\sigma\sqrt{2}}$ — evaluated via an overflow-free `erfcx` split; non-finite → 0 (Rust parity ~1e-9). **`A` is the total integrated area under the curve, not a peak height** — the standard EMG normalisation identity makes $\int f\,dx = A$ exactly for $\gamma>0$ | amplitude, center, sigma, gamma | `EXP_GAUSSIAN` |
| `doniach_sunjic` | $A\dfrac{\cos\left[\pi\gamma/2 + (1-\gamma)\arctan(u)\right]}{(1+u^2)^{(1-\gamma)/2}}$, $u=(x-c)/\sigma$ — XPS core-level asymmetry $\gamma$ | amplitude, center, sigma, gamma | `DONIACH` |
| `split_gaussian` | Gaussian with width `sigma_l` for $x < c$, `sigma_r` for $x \geq c$ (bi-Gaussian) | amplitude, center, sigma_l, sigma_r | `SPLIT_GAUSSIAN` |
| `split_pearson7` | Pearson VII with per-side width **and** exponent (`sigma_l`/`m_l` left, `sigma_r`/`m_r` right) | amplitude, center, sigma_l, sigma_r, m_l, m_r | `SPLIT_PEARSON7` |
| `asym_ir` | $A \cdot e^{-(x-c)^2/(2\sigma^2)} / (1 + e^{-k(x-c)})$ — Gaussian × logistic sigmoid; sigmoid exponent clamped at 50 (Rust parity) | amplitude, center, sigma, k | `ASYM_IR` |

## Multi-dimensional peaks

| Wire string | Formula | Parameters | Python `ModelType` |
|---|---|---|---|
| `gaussian2d` | $A \cdot e^{-(x-c_x)^2/(2\sigma_x^2) - (y-c_y)^2/(2\sigma_y^2)}$ — axis-aligned, `n_dims = 2` | amplitude, center_x, center_y, sigma_x, sigma_y | `GAUSSIAN2D` |
| `gaussian_nd` | $A \cdot e^{-\sum_i (x_i-c_i)^2/(2\sigma_i^2)}$ — axis-aligned, parametric dimensionality (SP-2): D is **inferred** from the node's indexed `center_0, center_1, …, center_{D-1}` parameters (via `infer_parametric_n_dims`), not from an explicit field — there is no `n_dims` field on `ModelNodeSpec`;[^n-dims-field] params are indexed | amplitude, center_0…center_{D−1}, sigma_0…sigma_{D−1} | `GAUSSIAN_ND` |

Both are engine subjects (the benchmark's 2-D map and N-D showcases) but are
exempt from the 1-D `oracles.models` `MODEL_REGISTRY` (see
`_MULTIDIM_EXEMPTIONS` in `tests/parity/test_model_type_registry_bijection.py`).

[^n-dims-field]: An explicit `n_dims` field on `ModelNodeSpec` was the initially-approved
    design, but it was reversed during implementation: adding the field to that
    widely-constructed struct would have broken 40+ struct literals workspace-wide
    for no offsetting benefit, so the compiler instead counts the node's
    `center_<i>` parameters to determine D and builds `GaussianND::new(d)` via
    `model_from_str_with_dims`; a `gaussian_nd` node with no `center_*` params
    raises a clear `MissingParameter("center_0")`. See DECISIONS.md, 2026-06-21
    entry.

## Polynomial / background models

| Wire string | Formula | Parameters | Python `ModelType` |
|---|---|---|---|
| `constant` | $c$ | c | `CONSTANT` |
| `linear` | $\text{slope} \cdot x + \text{intercept}$ | slope, intercept | `LINEAR` |
| `quadratic` | $A(x-c)^2 + \text{offset}$ | amplitude, center, offset | `QUADRATIC` |

A quadratic node forms a convex bowl ideal for clean convex optimization objectives. Summing
several Quadratic nodes together builds a sum-of-squares landscape; pairing a quadratic with
a Linear node tilts the bowl.

## Step / edge models

`Arctan step` is $A\left(\dfrac{1}{2} + \dfrac{1}{\pi}\arctan\left(\dfrac{x-c}{\sigma}\right)\right)$ — used as the absorption-edge background for
XAS K-edge cases. `StepSpec` (`oracles/cases.py`) declares the params directly as
`amplitude`/`center`/`sigma` — there is no `step_height`/`step_center`/`step_width` alias layer,
and no `spectrum_schema` module exists in the current tree.

| Wire string | Formula | Parameters | Python `ModelType` |
|---|---|---|---|
| `arctan_step` | $A\left(\dfrac{1}{2} + \dfrac{1}{\pi}\arctan\left(\dfrac{x-c}{\sigma}\right)\right)$ (rising) | amplitude, center, sigma | `ARCTAN_STEP` |
| `tanh_step` | $\dfrac{A}{2}\left(1 + \tanh\left(\dfrac{x-c}{\sigma}\right)\right)$ (rising) | amplitude, center, sigma | `TANH_STEP` |
| `erfc_step` | $\dfrac{A}{2}\,\mathrm{erfc}\left(\dfrac{x-c}{\sigma\sqrt{2}}\right)$ (**falling**) | amplitude, center, sigma | `ERFC_STEP` |

## Decay / kinetics models

| Wire string | Formula | Parameters | Python `ModelType` |
|---|---|---|---|
| `double_exponential` | $A_1 e^{-\lambda_1 x} + A_2 e^{-\lambda_2 x}$ — $\lambda_*$ are **rate constants** (1/τ), not times | A1, lam1, A2, lam2 | `DOUBLE_EXPONENTIAL` |
| `kww` | Kohlrausch–Williams–Watts stretched exponential $A e^{-(x/\tau)^\beta}$ for $x \geq 0$, else 0 | amplitude, tau, beta | `KWW` |

## Saturation / rational models (NIST StRD kernels)

Real native kernels with exact Jacobians. For the saturating exponential and power-law
saturation kernels, `amplitude` is the **asymptotic saturation level** (the plateau approached
as $x \to \infty$), not a peak-at-center value.

| Wire string | Formula | Parameters | Python `ModelType` | NIST |
|---|---|---|---|---|
| `saturating_exponential` | $A(1 - e^{-\text{rate}\cdot x})$ | amplitude, rate | `SATURATING_EXPONENTIAL` | BoxBOD |
| `power_saturation` | $A\left(1 - \left(1 + \dfrac{\text{rate}\cdot x}{2}\right)^{-2}\right)$ | amplitude, rate | `POWER_SATURATION` | Misra1b |
| `power_law_offset` | $A(\text{offset} + x)^{-1/\text{shape}}$ — caller must keep `offset + x > 0` | amplitude, offset, shape | `POWER_LAW_OFFSET` | Bennett5 |
| `mgh09_rational` | Kowalik–Osborne $A\dfrac{x^2 + b_2 x}{x^2 + b_3 x + b_4}$ with $b_2=\text{num\_lin}$, $b_3=\text{den\_lin}$, $b_4=\text{den\_const}$ ($A=b_1$) | amplitude, num_lin, den_lin, den_const | `MGH09_RATIONAL` | MGH09 |

## Optical / dispersion models

| Wire string | Formula | Parameters | Python `ModelType` |
|---|---|---|---|
| `tauc` | Tauc band-gap edge $A(x - e_{\text{gap}})^p$ for $x > e_{\text{gap}}$, else 0 (Heaviside cut keeps the fractional power real) | amplitude, e_gap, exponent | `TAUC` |
| `cauchy_dispersion` | Cauchy refractive-index dispersion $n(x) = a + b/x^2 + c/x^4$ for $x > 0$, else 0 | a, b, c | `CAUCHY_DISPERSION` |

## Test / optimization surrogates (benchmark only)

The four multimodal functions below are **not** native kernels: in the benchmark they are
approximated by a fixed **2-Gaussian basis solved by the global (DE) optimizer**, so their
reported r² reflects the basis ceiling, not solver convergence (see `_optfn` in
`oracles/cases.py`, which builds the 2-`GaussianSpec` surrogate for whichever landscape is
selected).

| Model | Python fn | `CaseSpec.landscape` | Rust `ModelType` | Fit basis |
|---|---|---|---|---|
| Ackley | `_ackley()` (`opt_func/ackley.py`, `@register_landscape("ackley")`) | `"ackley"` | — | 2-Gaussian + DE |
| Rastrigin | `_rastrigin()` (`opt_func/rastrigin.py`) | `"rastrigin"` | — | 2-Gaussian + DE |
| Rosenbrock | `_rosenbrock()` (`opt_func/rosenbrock.py`) | `"rosenbrock"` | — | 2-Gaussian + DE |
| Griewank | `_griewank()` (`opt_func/griewank.py`) | `"griewank"` | — | 2-Gaussian + DE |

Each landscape function is registered into `opt_func.LANDSCAPE_REGISTRY` via
`@register_landscape(name)`; there is no separate `model_hint` field — the case's
`landscape` string (on `CaseSpec`) is both the lookup key and the recorded condition name.

## Parameter constraint surfaces

A parameter can be constrained (tied to another parameter's value or a formula) via **two equivalent surfaces**:

| Surface | Declaration | Note |
|---|---|---|
| `ExprEdge` | Add `ExprEdge(target_node=…, target_param=…, expression=…)` to `FitGraph.expr_edges` | Graph-level; best for multi-edge topologies built programmatically. |
| `Parameter.expr` | Set `expr="source_node.param"` on the target `Parameter` | Per-parameter; best for inline node construction. |

Both surfaces resolve through the **same** dependency-ordered, cycle-checked tied-plan evaluator. The constraint is applied on every solver iteration, so the converged result is numerically identical regardless of which surface is used. References must use fully-qualified `node_id.param` form (e.g. `"g1.sigma"`). Arithmetic is supported (`"g1.sigma * 2.0"`).

**`DuplicateExprTarget` error.** If the same `node.param` is targeted by both a `Parameter.expr` and a matching `ExprEdge`, the compiler raises a `DuplicateExprTarget` error at fit-compile time. Fix by removing one surface — pick either `ExprEdge` *or* `Parameter.expr` for each tie, never both.

**`vary` is irrelevant when `expr` is set.** The engine excludes any parameter whose `Parameter.expr` is non-`None` from the free set regardless of the `vary` flag. By convention set `vary=False` to make the intent obvious, but the engine would honour the tie either way.

!!! warning "Global-solver stochasticity"

    Ties from either surface compile to the same tied-plan. The LM-family solvers (`lm`/`trf`/`geodesic`/`dogleg`/`newton-cg`/`irls`) apply it on every iteration. The `global` (differential-evolution) solver runs in two phases: the DE search holds tied parameters at their seed values, and the **post-search LM refinement** applies the tied-plan — so the **final** `global` result is tie-correct (CX-VPE-02). Both surfaces reach the identical result on every solver. Note the `global` solver is a stochastic global optimiser and is not guaranteed to find the global optimum on hard multi-modal landscapes.

!!! warning "VarPro tied-parameter limitation"

    The variable-projection (`solver="varpro"`) path does not support expression ties from **either** surface. A tied graph — whether the tie comes from an `expr_edge` or a per-parameter `Parameter.expr` — is never auto-selected for VarPro and is rejected by explicit `solver="varpro"` with `VarproExprEdgesUnsupported`. Both surfaces are guarded identically (CX-VPE-01, resolved); use `solver="lm"`, `"trf"`, or `"geodesic"` for tied fits.

## Pseudo-Voigt parameter name history

The mixing fraction has had three names across the codebase. The canonical name is now `fraction` everywhere:

| Location | Old name | Canonical name |
|---|---|---|
| Python `models.py` | `eta` | `fraction` |
| Catalog `true_params` | `"eta"` | `"fraction"` |
| Rust `pseudo_voigt.rs` | — | `"fraction"` ✓ |
| Rust `voigt.rs` | `"frac"` | `"fraction"` ✓ |
