---
icon: lucide/sigma
description: Canonical formulas, parameter names, and wire strings for all 37 models in spectrafit-core, mirroring the model_manifest! macro.
tags:
  - Models
  - Rust
---

# Model Reference

Canonical formulas and parameter names for all models in spectrafit-core.

!!! note "Authoritative source"
    The `model_manifest!` macro in
    `crates/spectrafit-types/src/types.rs` — 37 wire variants, exported at runtime
    as `spectrafit_core._core.model_type_wire_strings()` and pinned by
    `tests/parity/test_schema_parity.py`. This document mirrors that manifest
    (all 37 variants below); if the two ever disagree, the manifest wins. The
    numpy formulas in `python/oracles/models.py` are the parity oracles —
    numerically identical to the Rust kernels for the 35 of these 37 variants
    registered in `oracles.models.MODEL_REGISTRY` (enforced by
    `tests/parity/test_kernel_parity.py`), not for "all" of them — see
    [Why spectrafit-core](../../why-spectrafit-core.md) for the two
    denominators in play.

**Conventions:** amplitude = peak value at center (not area); $\sigma$ = standard
deviation (not FWHM; $\mathrm{FWHM} = 2\sqrt{2\ln 2}\,\sigma \approx 2.355\,\sigma$);
the pseudo-Voigt mixing weight is always named **`fraction`** — never `eta`, never
`frac`. Exceptions where a parameter deliberately means something else (HWHM
widths, asymptotic amplitudes) are called out per section.

## Symmetric peak lineshapes

| Wire string | Formula | Parameters | Python `ModelType` |
|---|---|---|---|
| `gaussian` | <!-- formula:gaussian -->$A \cdot \exp\!\left(-\dfrac{(x-c)^2}{2\sigma^2}\right)$<!-- /formula --> | amplitude, center, sigma | `GAUSSIAN` |
| `lorentzian` | <!-- formula:lorentzian -->$\dfrac{A}{1 + \left(\dfrac{x-c}{\sigma}\right)^{\!2}}$<!-- /formula --> — $\sigma$ is the **HWHM** | amplitude, center, sigma | `LORENTZIAN` |
| `pseudo_voigt`[^wertheim-1974][^ida-2000] | <!-- formula:pseudo_voigt -->$A\!\left[\mathrm{fraction}\cdot\frac{1}{1+\!\left(\frac{x-c}{\sigma}\right)^{\!2}}+(1-\mathrm{fraction})\cdot e^{-\frac{(x-c)^2}{2\sigma^2}}\right]$<!-- /formula --> | amplitude, center, sigma, **fraction** | `PSEUDO_VOIGT` |
| `voigt`[^wertheim-1974][^ida-2000] | <!-- formula:voigt -->$A\!\left[\mathrm{fraction}\cdot\frac{1}{1+\!\left(\frac{x-c}{\sigma}\right)^{\!2}}+(1-\mathrm{fraction})\cdot e^{-\frac{(x-c)^2}{2\sigma^2}}\right]$<!-- /formula --> — alias, same formula as Pseudo-Voigt (frozen copy on the Python side; dedicated Rust kernel cross-checked in the parity test). **Not the literature's Voigt profile** (the true Gaussian⊗Lorentzian convolution, below as `true_voigt`) — this kernel exists for a fixed, pinned wire string and does not switch meaning if `true_voigt`'s formula ever changes | amplitude, center, sigma, **fraction** | `VOIGT` |
| `true_voigt` | <!-- formula:true_voigt -->$A \cdot \mathrm{Re}\!\left[W\!\left(\dfrac{x-c+i\gamma}{\sigma\sqrt{2}}\right)\right]\,/\,\mathrm{Re}\!\left[W\!\left(\dfrac{i\gamma}{\sigma\sqrt{2}}\right)\right]$<!-- /formula -->, $z=((x-c)+i\gamma)/(\sigma\sqrt{2})$, $z_0=i\gamma/(\sigma\sqrt{2})$ — true Gaussian $\otimes$ Lorentzian via the Faddeeva function (Rust: Hui–Armstrong–Wray[^hui-1978] numerical evaluation, ~1e-6; numpy: `scipy.special.wofz` $\to$ wheel-vs-numpy parity ~1e-4) | amplitude, center, sigma, gamma | `TRUE_VOIGT` |
| `pearson7`[^pearson-1916][^hall-1977] | <!-- formula:pearson7 -->$A \cdot \left(1 + \left(\dfrac{x-c}{\sigma}\right)^{\!2}\left(2^{1/m}-1\right)\right)^{\!-m}$<!-- /formula --> — $\sigma$ is the **HWHM**; $m\to 1$ Lorentzian, $m\to\infty$ Gaussian | amplitude, center, sigma, m | `PEARSON7` |
| `moffat` | <!-- formula:moffat -->$A \cdot \left(1 + \left(\dfrac{x-c}{\sigma}\right)^{\!2}\right)^{\!-\beta}$<!-- /formula --> — $\sigma$ is a Lorentzian-family scale (the HWHM at $\beta=1$), not a standard deviation | amplitude, center, sigma, beta | `MOFFAT` |
| `students_t`[^student-1908] | <!-- formula:students_t -->$A \cdot \left(1 + \dfrac{(x-c)^2}{\nu\,\sigma^2}\right)^{\!-(\nu+1)/2}$<!-- /formula --> — $\sigma$ is a Lorentzian-family scale (the HWHM at $\nu=1$), not a standard deviation | amplitude, center, sigma, nu | `STUDENTS_T` |
| `log_normal` | <!-- formula:log_normal -->$A \cdot \exp\!\left(-\dfrac{\left(\ln(x/c)\right)^2}{2\sigma^2}\right),\quad x>0$<!-- /formula -->, else 0 — $\sigma$ is the log-space width | amplitude, center, sigma | `LOG_NORMAL` |

**Why a Voigt shape at all.** A measured line is broadened by more than one
mechanism at once — Gaussian instrumental resolution or Doppler broadening,
convolved with a Lorentzian natural-lifetime or collisional/pressure
broadening — and the two do not simply add. `true_voigt` computes that
convolution directly; `pseudo_voigt`/`voigt` approximate it with a linear
mix, which is cheaper and usually adequate away from the line's far wings,
where the true convolution's Lorentzian tails and the mix's weighted-sum
tails diverge most.

**`pearson7`, `moffat` and `students_t` are one shape with an adjustable wing
weight.** Each reduces to a Lorentzian exactly at one value of its shape
parameter — `pearson7` at $m=1$, `moffat` at $\beta=1$, `students_t` at
$\nu=1$ — and pulls its tails in as that parameter grows, `pearson7` and
`students_t` both approaching a Gaussian in the limit. Pick between them by
which one your community already names, not by capability. They are in the
catalogue because it mirrors lmfit's, so a wire string a reader already knows
resolves to the same curve here. That is catalogue parity and nothing more:
the benchmark's lmfit backend wraps spectrafit-core's own kernel and uses
lmfit purely as the optimiser (`python/oracles/backends/_lmfit.py`), so no
number published here compares these shapes against lmfit's independent
implementations of them.

## Asymmetric / resonance lineshapes

| Wire string | Formula | Parameters | Python `ModelType` |
|---|---|---|---|
| `fano`[^fano-1961] | <!-- formula:fano -->$A \cdot \dfrac{(q + \varepsilon)^2}{1 + \varepsilon^2},\quad \varepsilon=\dfrac{x-c}{\gamma}$<!-- /formula --> | amplitude, center, gamma, q | `FANO` |
| `breit_wigner`[^breit-wigner-1936] | Breit–Wigner–Fano <!-- formula:breit_wigner -->$A \cdot \dfrac{(q\sigma/2 + x - c)^2}{(x-c)^2 + (\sigma/2)^2}$<!-- /formula --> | amplitude, center, sigma, q | `BREIT_WIGNER` |
| `skewed_gaussian`[^azzalini-1985] | <!-- formula:skewed_gaussian -->$A \cdot \exp\!\left(-\dfrac{(x-c)^2}{2\sigma^2}\right)\cdot \left(1 + \mathrm{erf}\!\left(\dfrac{\gamma(x-c)}{\sigma\sqrt{2}}\right)\right)$<!-- /formula --> — $\gamma$ is the skew | amplitude, center, sigma, gamma | `SKEWED_GAUSSIAN` |
| `exp_gaussian`[^grushka-1972] | Exponentially-modified Gaussian (EMG) <!-- formula:exp_gaussian -->$A \cdot \dfrac{\gamma}{2}\exp\!\left(\dfrac{\gamma}{2}(2c-2x+\gamma\sigma^2)\right)\cdot\mathrm{erfc}\!\left(\dfrac{c-x+\gamma\sigma^2}{\sigma\sqrt{2}}\right)$<!-- /formula --> — evaluated via an overflow-free `erfcx`[^cody-1969] split; non-finite $\to$ 0 (Rust parity ~1e-9). **`A` is the total integrated area under the curve, not a peak height** — the standard EMG normalisation identity makes $\int f\,dx = A$ exactly for $\gamma>0$ | amplitude, center, sigma, gamma | `EXP_GAUSSIAN` |
| `doniach_sunjic`[^doniach-sunjic-1970] | <!-- formula:doniach_sunjic -->$A \cdot \dfrac{\cos\!\left(\tfrac{\pi\gamma}{2}+(1-\gamma)\arctan\!\left(\tfrac{x-c}{\sigma}\right)\right)}{\left(1+\left(\tfrac{x-c}{\sigma}\right)^{\!2}\right)^{(1-\gamma)/2}}$<!-- /formula -->, $u=(x-c)/\sigma$ — XPS core-level asymmetry $\gamma$ | amplitude, center, sigma, gamma | `DONIACH` |
| `split_gaussian` | <!-- formula:split_gaussian -->$A \cdot \exp\!\left(-\dfrac{(x-c)^2}{2\sigma_{\mathrm{L/R}}^2}\right),\quad \sigma_\mathrm{L}\text{ for }x<c,\;\sigma_\mathrm{R}\text{ for }x\ge c$<!-- /formula --> — bi-Gaussian: width `sigma_l` for $x < c$, `sigma_r` for $x \geq c$ | amplitude, center, sigma_l, sigma_r | `SPLIT_GAUSSIAN` |
| `split_pearson7`[^pearson-1916][^hall-1977] | <!-- formula:split_pearson7 -->$A \cdot \left(1+\left(\dfrac{x-c}{\sigma_{\mathrm{L/R}}}\right)^{\!2}\left(2^{1/m_{\mathrm{L/R}}}-1\right)\right)^{\!-m_{\mathrm{L/R}}},\quad \text{L/R by side}$<!-- /formula --> — Pearson VII with per-side width **and** exponent (`sigma_l`/`m_l` left, `sigma_r`/`m_r` right) | amplitude, center, sigma_l, sigma_r, m_l, m_r | `SPLIT_PEARSON7` |
| `asym_ir` | <!-- formula:asym_ir -->$\dfrac{A \cdot \exp\!\left(-\dfrac{(x-c)^2}{2\sigma^2}\right)}{1+\exp\!\left(-k(x-c)\right)}$<!-- /formula --> — Gaussian × logistic sigmoid; sigmoid exponent clamped at 50 (Rust parity) | amplitude, center, sigma, k | `ASYM_IR` |
| `harmonic_ir` | <!-- formula:harmonic_ir -->$\dfrac{A}{(c^2-x^2)^2+(\sigma x)^2}$<!-- /formula --> — driven damped harmonic-oscillator IR absorption; $\sigma$ is a damping coefficient with frequency units, not a standard deviation; not symmetric about $c$ ($f(c+d) \neq f(c-d)$) | amplitude, center, sigma | `HARMONIC_IR` |

**Amplitude exceptions in this section, not covered by the blanket
"amplitude = peak value at center" convention above:** `fano` and
`breit_wigner` both evaluate to $A q^2$ at $x=c$ (not $A$), and the true
maximum of `fano` sits off-center at $x-c=\gamma/q$, not at $c$ itself;
`doniach_sunjic` evaluates to $A\cos(\pi\gamma/2)$ at $x=c$ (not $A$, for any
nonzero asymmetry $\gamma$); `asym_ir` evaluates to $A/2$ at $x=c$ (the
logistic factor is exactly $\tfrac12$ there, independent of $k$); `harmonic_ir`
evaluates to $A/(\sigma c)^2$ at $x=c$ (not $A$). In all five,
`amplitude` is a scale prefactor rather than the literal value the curve takes
at its center — seed an initial guess from an observed peak height with that
in mind.

## Multi-dimensional peaks

| Wire string | Formula | Parameters | Python `ModelType` |
|---|---|---|---|
| `gaussian2d` | $A \cdot e^{-(x-c_x)^2/(2\sigma_x^2) - (y-c_y)^2/(2\sigma_y^2)}$ — axis-aligned, `n_dims = 2` | amplitude, center_x, center_y, sigma_x, sigma_y | `GAUSSIAN2D` |
| `gaussian_nd` | $A \cdot e^{-\sum_i (x_i-c_i)^2/(2\sigma_i^2)}$ — axis-aligned, parametric dimensionality (SP-2): D is **inferred** from the node's indexed `center_0, center_1, …, center_{D-1}` parameters (via `infer_parametric_n_dims`), not from an explicit field — there is no `n_dims` field on `ModelNodeSpec`;[^n-dims-field] params are indexed | amplitude, center_0…center_{D−1}, sigma_0…sigma_{D−1} | `GAUSSIAN_ND` |

Both are engine subjects (the benchmark's 2-D map and N-D showcases) but are
exempt from the 1-D `oracles.models` `MODEL_REGISTRY` (see
`_MULTIDIM_EXEMPTIONS` in `tests/parity/test_model_type_registry_bijection.py`).

**Limitation, not just a formula detail: no covariance/rotation term.**
Both kernels are axis-aligned by construction — there is no cross term
between dimensions, so a peak whose principal axes are rotated relative to
the coordinate frame (a common real case: a tilted detector, or correlated
broadening across two spectral axes) cannot be fit exactly. Pre-rotate the
data to the peak's own axes, or expect the fitted `sigma_x`/`sigma_y` to be a
biased, frame-dependent approximation to the true covariance ellipse.

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
| `constant` | <!-- formula:constant -->$c$<!-- /formula --> | c | `CONSTANT` |
| `linear` | <!-- formula:linear -->$\mathrm{slope} \cdot x + \mathrm{intercept}$<!-- /formula --> | slope, intercept | `LINEAR` |
| `quadratic` | <!-- formula:quadratic -->$A \cdot (x - c)^2 + \mathrm{offset}$<!-- /formula --> | amplitude, center, offset | `QUADRATIC` |

A quadratic node forms a convex bowl ideal for clean convex optimization objectives. Summing
several Quadratic nodes together builds a sum-of-squares landscape; pairing a quadratic with
a Linear node tilts the bowl.

## Step / edge models

`Arctan step` is $A\left(\dfrac{1}{2} + \dfrac{1}{\pi}\arctan\left(\dfrac{x-c}{\sigma}\right)\right)$ — used as the absorption-edge background for
X-ray Absorption Spectroscopy (XAS) K-edge cases. `StepSpec` (`oracles/cases.py`) declares the params directly as
`amplitude`/`center`/`sigma` — there is no `step_height`/`step_center`/`step_width` alias layer,
and no `spectrum_schema` module exists in the current tree.

| Wire string | Formula | Parameters | Python `ModelType` |
|---|---|---|---|
| `arctan_step` | <!-- formula:arctan_step -->$A \cdot \left(\tfrac{1}{2} + \dfrac{1}{\pi}\arctan\!\left(\dfrac{x-c}{\sigma}\right)\right)$<!-- /formula --> (rising) | amplitude, center, sigma | `ARCTAN_STEP` |
| `tanh_step` | <!-- formula:tanh_step -->$A \cdot \left(\tfrac{1}{2} + \dfrac{1}{2}\tanh\!\left(\dfrac{x-c}{\sigma}\right)\right)$<!-- /formula --> (rising) | amplitude, center, sigma | `TANH_STEP` |
| `erfc_step` | <!-- formula:erfc_step -->$A \cdot \dfrac{1}{2}\,\mathrm{erfc}\!\left(\dfrac{x-c}{\sigma\sqrt{2}}\right)$<!-- /formula --> (**falling**) | amplitude, center, sigma | `ERFC_STEP` |

## Decay / kinetics models

| Wire string | Formula | Parameters | Python `ModelType` |
|---|---|---|---|
| `double_exponential` | <!-- formula:double_exponential -->$A_1\,e^{-\lambda_1 x} + A_2\,e^{-\lambda_2 x}$<!-- /formula --> — $\lambda_*$ are **rate constants** (1/$\tau$), not times | A1, lam1, A2, lam2 | `DOUBLE_EXPONENTIAL` |
| `kww`[^kohlrausch-1854][^williams-watts-1970] | Kohlrausch–Williams–Watts stretched exponential <!-- formula:kww -->$A \cdot \exp\!\left(-\left(\dfrac{x}{\tau}\right)^{\!\beta}\right),\quad x\ge 0$<!-- /formula -->, else 0 | amplitude, tau, beta | `KWW` |

## Saturation / rational models (NIST StRD kernels)

Real native kernels with exact Jacobians. For the saturating exponential and power-law
saturation kernels, `amplitude` is the **asymptotic saturation level** (the plateau approached
as $x \to \infty$), not a peak-at-center value.

| Wire string | Formula | Parameters | Python `ModelType` | NIST |
|---|---|---|---|---|
| `saturating_exponential` | <!-- formula:saturating_exponential -->$A \cdot \left(1 - e^{-k\,x}\right)$<!-- /formula --> | amplitude, rate | `SATURATING_EXPONENTIAL` | BoxBOD[^box-hunter-1978] |
| `power_saturation` | <!-- formula:power_saturation -->$A \cdot \left(1 - \left(1 + \dfrac{k\,x}{2}\right)^{\!-2}\right)$<!-- /formula --> | amplitude, rate | `POWER_SATURATION` | Misra1b[^misra-1978] |
| `power_law_offset` | <!-- formula:power_law_offset -->$A \cdot (b + x)^{-1/s}$<!-- /formula --> — caller must keep `offset + x > 0` | amplitude, offset, shape | `POWER_LAW_OFFSET` | Bennett5[^bennett-1994] |
| `mgh09_rational` | Kowalik–Osborne <!-- formula:mgh09_rational -->$A \cdot \dfrac{x^2 + b_2\,x}{x^2 + b_3\,x + b_4}$<!-- /formula --> with $b_2=\text{num\_lin}$, $b_3=\text{den\_lin}$, $b_4=\text{den\_const}$ ($A=b_1$) | amplitude, num_lin, den_lin, den_const | `MGH09_RATIONAL` | MGH09[^kowalik-osborne-1978] |
| `rational_cubic` | <!-- formula:rational_cubic -->$\dfrac{a_0 + a_1 x + a_2 x^2 + a_3 x^3}{1 + b_1 x + b_2 x^2 + b_3 x^3}$<!-- /formula --> — cubic/cubic rational; subsumes `mgh09_rational`, and holding the cubic coefficients at zero gives the quadratic/quadratic form | a0, a1, a2, a3, b1, b2, b3 | `RATIONAL_CUBIC` | Kirby2, Hahn1, Thurber |
| `generalised_logistic`[^richards-1959] | <!-- formula:generalised_logistic -->$\dfrac{A}{\left(1 + e^{\,b - k x}\right)^{1/s}}$<!-- /formula --> with $b=\text{shift}$, $k=\text{rate}$, $s=\text{shape}$ (Richards curve; $s$ fixed at 1 gives the plain logistic) | amplitude, shift, rate, shape | `GENERALISED_LOGISTIC` | Rat43, Rat42[^ratkowsky-1983] |
| `exp_over_linear` | <!-- formula:exp_over_linear -->$\dfrac{e^{-k x}}{c + m\,x}$<!-- /formula --> with $k=\text{rate}$, $c=\text{lin\_const}$, $m=\text{lin\_slope}$ | rate, lin_const, lin_slope | `EXP_OVER_LINEAR` | Chwirut1, Chwirut2[^chwirut-1979] |

## Optical / dispersion models

| Wire string | Formula | Parameters | Python `ModelType` |
|---|---|---|---|
| `tauc`[^tauc-1966] | Tauc band-gap edge <!-- formula:tauc -->$A \cdot (x - E_\mathrm{gap})^{\mathrm{exponent}},\quad x>E_\mathrm{gap}$<!-- /formula -->, else 0 (Heaviside cut keeps the fractional power real) | amplitude, e_gap, exponent | `TAUC` |
| `cauchy_dispersion` | Cauchy refractive-index dispersion $n(x) =$ <!-- formula:cauchy_dispersion -->$a + \dfrac{b}{x^2} + \dfrac{c}{x^4}$<!-- /formula --> for $x > 0$, else 0 | a, b, c | `CAUCHY_DISPERSION` |

## Test / optimization surrogates (benchmark only)

The four multimodal functions below are **not** native kernels: in the benchmark they are
approximated by a fixed **2-Gaussian basis solved by the global (DE) optimizer**, so their
reported $r^2$ reflects the basis ceiling, not solver convergence (see `_optfn` in
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

[^fano-1961]: Fano, U. (1961). "Effects of Configuration Interaction on Intensities and
    Phase Shifts." *Physical Review* 124(6), 1866–1878.
    https://doi.org/10.1103/physrev.124.1866
[^breit-wigner-1936]: Breit, G. & Wigner, E. (1936). "Capture of Slow Neutrons." *Physical
    Review* 49(7), 519–531. https://doi.org/10.1103/physrev.49.519
[^doniach-sunjic-1970]: Doniach, S. & Šunjić, M. (1970). "Many-electron singularity in
    X-ray photoemission and X-ray line spectra from metals." *Journal of Physics C: Solid
    State Physics* 3(2), 285–291. https://doi.org/10.1088/0022-3719/3/2/010
[^grushka-1972]: Grushka, E. (1972). "Characterization of exponentially modified Gaussian
    peaks in chromatography." *Analytical Chemistry* 44(11), 1733–1738.
    https://doi.org/10.1021/ac60319a011
[^cody-1969]: Cody, W. J. (1969). "Rational Chebyshev approximations for the error
    function." *Mathematics of Computation* 23(107), 631–637.
    https://doi.org/10.1090/s0025-5718-1969-0247736-4 — cited for the `erfcx`-based
    evaluation `exp_gaussian` and the Faddeeva-function evaluation `true_voigt` use, not
    as a lineshape origin.
[^azzalini-1985]: Azzalini, A. (1985). "A class of distributions which includes the
    normal ones." *Scandinavian Journal of Statistics* 12, 171–178.
[^kohlrausch-1854]: Kohlrausch, R. (1854). "Theorie des elektrischen Rückstandes in der
    Leidener Flasche." *Annalen der Physik* 167(1), 56–82.
    https://doi.org/10.1002/andp.18541670103
[^williams-watts-1970]: Williams, G. & Watts, D. C. (1970). "Non-symmetrical dielectric
    relaxation behaviour arising from a simple empirical decay function." *Transactions
    of the Faraday Society* 66, 80. https://doi.org/10.1039/tf9706600080
[^pearson-1916]: Pearson, K. (1916). "Mathematical contributions to the theory of
    evolution. XIX. Second supplement to a memoir on skew variation." *Philosophical
    Transactions of the Royal Society A* 216, 429–457.
    https://doi.org/10.1098/rsta.1916.0009
[^hall-1977]: Hall, M. M., Veeraraghavan, V. G., Rubin, H. & Winchell, P. G. (1977). "The
    approximation of symmetric X-ray peaks by Pearson type VII distributions." *Journal
    of Applied Crystallography* 10(1), 66–68. https://doi.org/10.1107/s0021889877012849
[^student-1908]: Student (1908). "The Probable Error of a Mean." *Biometrika* 6(1), 1.
    https://doi.org/10.1093/biomet/6.1.1
[^richards-1959]: Richards, F. J. (1959). "A Flexible Growth Function for Empirical Use."
    *Journal of Experimental Botany* 10(2), 290–301. https://doi.org/10.1093/jxb/10.2.290
[^tauc-1966]: Tauc, J., Grigorovici, R. & Vancu, A. (1966). "Optical Properties and
    Electronic Structure of Amorphous Germanium." *physica status solidi (b)* 15(2),
    627–637. https://doi.org/10.1002/pssb.19660150224
[^wertheim-1974]: Wertheim, G. K., Butler, M. A., West, K. W. & Buchanan, D. N. E. (1974).
    "Determination of the Gaussian and Lorentzian content of experimental line shapes."
    *Review of Scientific Instruments* 45(11), 1369–1371. https://doi.org/10.1063/1.1686503
[^ida-2000]: Ida, T., Ando, M. & Toraya, H. (2000). "Extended pseudo-Voigt function for
    approximating the Voigt profile." *Journal of Applied Crystallography* 33(6),
    1311–1316. https://doi.org/10.1107/s0021889800010219
[^hui-1978]: Hui, A. K., Armstrong, B. H. & Wray, A. A. (1978). "Rapid computation of the
    Voigt and complex error functions." *JQSRT* 19(5), 509–516.
    https://doi.org/10.1016/0022-4073(78)90019-5 — cited here for the numerical method
    `true_voigt` implements (the Faddeeva-function evaluation), not as the Voigt
    profile's own origin.
[^box-hunter-1978]: Box, G. P., Hunter, W. G. & Hunter, J. S. (1978). *Statistics for
    Experimenters.* New York, NY: Wiley, pp. 483–487.
[^misra-1978]: Misra, D., NIST (1978). *Dental Research Monomolecular Adsorption Study.*
[^bennett-1994]: Bennett, L., Swartzendruber, L. & Brown, H., NIST (1994).
    *Superconductivity Magnetization Modeling.*
[^ratkowsky-1983]: Ratkowsky, D. A. (1983). *Nonlinear Regression Modeling.* New York,
    NY: Marcel Dekker.
[^chwirut-1979]: Chwirut, D., NIST (1979). *Ultrasonic Reference Block Study.*
[^kowalik-osborne-1978]: Kowalik, J. S. & Osborne, M. R. (1978). *Methods for
    Unconstrained Optimization Problems.* New York, NY: Elsevier North-Holland.
