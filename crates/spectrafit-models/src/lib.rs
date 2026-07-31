//! spectrafit-models — analytical model kernels with exact Jacobians.
#![warn(missing_docs)]

pub(crate) mod erf_ext;
pub(crate) mod math_backend;

/// Asymmetric IR band (Gaussian × logistic sigmoid).
pub mod asym_ir;
/// Breit-Wigner-Fano resonance.
pub mod breit_wigner;
/// Cauchy refractive-index dispersion (`a + b/x² + c/x⁴`).
pub mod cauchy_dispersion;
/// Doniach–Šunjić asymmetric core-level lineshape (XPS).
pub mod doniach;
/// Exponentially-modified Gaussian (asymmetric tailing peak).
pub mod emg;
/// Exponential decay and double-exponential models.
pub mod exponential;
/// Fano resonance lineshape model.
pub mod fano;
/// Gaussian peak model with exact Jacobian.
pub mod gaussian;
/// Axis-aligned 2-D Gaussian peak model (n_dims == 2).
pub mod gaussian2d;
/// Axis-aligned N-D Gaussian peak model (parametric dimensionality, SP-2).
pub mod gaussian_nd;
/// Driven damped harmonic-oscillator IR absorption.
pub mod harmonic_ir;
/// Kohlrausch–Williams–Watts stretched exponential (`A·exp(−(x/τ)^β)`).
pub mod kww;
/// Log-normal peak (`A·exp(−(ln(x/c))²/(2σ²))` for x > 0).
pub mod log_normal;
/// Lorentzian (Cauchy) peak model with exact Jacobian.
pub mod lorentzian;
/// Kowalik–Osborne rational function (NIST StRD MGH09):
/// `amplitude · (x² + num_lin·x) / (x² + den_lin·x + den_const)`.
pub mod mgh09_rational;
/// Moffat peak (`A / (((x−c)/σ)²+1)^β`).
pub mod moffat;
/// Pearson VII peak (`A / [1 + ((x−c)/σ)²·(2^{1/m}−1)]^m`).
pub mod pearson7;
/// Constant and linear polynomial baseline models.
pub mod polynomial;
/// Power-law with offset: `amplitude · (offset + x)^(−1/shape)` (Bennett5 model).
pub mod power_law_offset;
/// Power-law saturation: `amplitude · (1 − (1 + rate·x/2)^(−2))` (Misra1b model).
pub mod power_saturation;
/// Pseudo-Voigt (Gaussian/Lorentzian mixture) model.
pub mod pseudo_voigt;
/// Saturating exponential: `amplitude · (1 − exp(−rate · x))` (BoxBOD model).
pub mod saturating_exponential;
/// Skewed Gaussian (error-function-modulated asymmetry).
pub mod skewed_gaussian;
/// Split (asymmetric) Gaussian — different width each side (a.k.a. bi-Gaussian).
pub mod split_gaussian;
/// Split Pearson VII (split width + exponent each side).
pub mod split_pearson7;
/// Step-function models: arctan, tanh, and erfc variants.
pub mod step;
/// Student's-t peak (`A / (1+((x−c)/σ)²/ν)^((ν+1)/2)`).
pub mod students_t;
/// Tauc optical band-gap edge (`A·((x−e_gap)·H(x−e_gap))^p`).
pub mod tauc;
/// Pseudo-Voigt linear-mixture model (the `voigt`/`pseudo_voigt` key).
pub mod voigt;
/// True Voigt profile via the Faddeeva function (Gaussian ⊗ Lorentzian).
pub mod voigt_true;

/// Core model trait implemented by every built-in kernel.
///
/// Convention: `x` is a coordinate slice.
/// - 1-D models expect `x.len() == 1` (i.e. `x[0]` is the scalar coordinate).
/// - n-D models declare `n_dims() > 1`.
pub trait Model: Send + Sync {
    /// Evaluate the model at coordinate `x` with the given `params`.
    ///
    /// # Preconditions
    ///
    /// Implementations index `params` and `x` by raw position and assume the
    /// caller has already validated arity (this keeps the per-point evaluation
    /// branch-free on the hot path). The caller MUST guarantee:
    /// - `params.len() == self.param_names().len()`
    /// - `x.len() >= self.n_dims()`
    ///
    /// # Panics
    ///
    /// Panics (index-out-of-bounds) if `params.len() < self.param_names().len()`
    /// or `x.len() < self.n_dims()`. Because the pyo3 binding crate calls these
    /// kernels on the hot path, a panic here would unwind across the FFI
    /// boundary — validate param/coordinate arity at graph-compile time so the
    /// kernel is only ever invoked well-formed.
    fn eval(&self, x: &[f64], params: &[f64]) -> f64;

    /// Jacobian — one derivative per parameter, in the same order as
    /// `param_names()`.
    ///
    /// The default implementation uses forward-difference finite differences
    /// with step `h = 1e-7 * |p[i]|.max(1e-7)` (relative + absolute floor).
    /// Override with an analytical formula when possible for best performance.
    ///
    /// # Preconditions / Panics
    ///
    /// Same arity contract as [`eval`](Model::eval): the caller MUST ensure
    /// `params.len() == self.param_names().len()` and `x.len() >= self.n_dims()`.
    /// A short slice panics with an index-out-of-bounds rather than returning an
    /// error; the same FFI-unwind hazard applies, so validate arity upstream.
    fn jacobian(&self, x: &[f64], params: &[f64]) -> Vec<f64> {
        let f0 = self.eval(x, params);
        let mut p = params.to_vec();
        (0..params.len())
            .map(|i| {
                let h = 1e-7_f64 * params[i].abs().max(1e-7);
                p[i] = params[i] + h;
                let df = (self.eval(x, &p) - f0) / h;
                p[i] = params[i];
                df
            })
            .collect()
    }

    /// Fill a pre-allocated slice with Jacobian values (one entry per parameter).
    ///
    /// This is the hot-path companion to [`jacobian`].  The caller provides a
    /// scratch buffer (`out`) of length ≥ `param_names().len()`; the method
    /// writes derivatives into `out[0..n_params]` without any heap allocation.
    ///
    /// The default falls back to [`jacobian`] and copies the result.  Models
    /// with analytical Jacobians **should override** this to compute values
    /// directly into `out`, sharing intermediate calculations across parameters.
    #[inline]
    fn jacobian_into(&self, x: &[f64], params: &[f64], out: &mut [f64]) {
        let jac = self.jacobian(x, params);
        out[..jac.len()].copy_from_slice(&jac);
    }

    /// Batch evaluation of a 1-D model: fill `out[i] = eval([xs[i]], params)`.
    ///
    /// **Only called when `n_dims() == 1`.**
    ///
    /// Default: per-point loop calling `eval()`.  Override to hoist
    /// loop-invariant constants (e.g. precompute `1/(2σ²)` once) and let LLVM
    /// eliminate redundant arithmetic across the slice.
    #[inline]
    fn eval_slice_into(&self, xs: &[f64], params: &[f64], out: &mut [f64]) {
        debug_assert_eq!(xs.len(), out.len());
        for (xi, slot) in xs.iter().zip(out.iter_mut()) {
            *slot = self.eval(std::slice::from_ref(xi), params);
        }
    }

    /// Batch Jacobian for a 1-D model: fill `out` in row-major layout
    /// `[i * params.len() + j] = d(model)/d(params[j])` at `xs[i]`.
    ///
    /// **Only called when `n_dims() == 1`.**
    ///
    /// Default: per-point loop calling `jacobian_into()`.  Override to hoist
    /// invariants (avoids recomputing `σ²` and the `exp()` argument for every
    /// point call).
    #[inline]
    fn jac_slice_into(&self, xs: &[f64], params: &[f64], out: &mut [f64]) {
        debug_assert_eq!(xs.len() * params.len(), out.len());
        let np = params.len();
        for (i, xi) in xs.iter().enumerate() {
            self.jacobian_into(
                std::slice::from_ref(xi),
                params,
                &mut out[i * np..(i + 1) * np],
            );
        }
    }

    /// Ordered parameter names, matching the layout expected by `eval` and `jacobian`.
    ///
    /// Returns an owned `Vec` of `Cow<'static, str>` so that runtime-generated
    /// models (e.g. `GaussianND{d}` with dynamic `center_0..center_{d-1}`) can
    /// produce their parameter names without requiring compile-time-static slices.
    /// For all built-in kernels with static names, every element is
    /// `Cow::Borrowed(&'static str)` — zero extra heap allocation.
    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>>;

    /// Number of coordinate dimensions consumed from `x`.  Defaults to 1.
    fn n_dims(&self) -> usize {
        1
    }
}

/// Canonical list of every model-type string [`model_from_str`] can construct.
///
/// **Derived from the single source of truth** — the
/// `model_manifest!`-generated `spectrafit_types::ModelTypeStr::ALL`, mapped
/// through `as_str()`. There is no second hand-maintained list to drift: adding
/// a model is one manifest row in `spectrafit-types`, and it auto-enrolls here.
///
/// The invariant `all_model_types_round_trip_through_model_from_str` (in the
/// self-consistency test) pins that every entry here is accepted by
/// [`model_from_str`] and that every `model_from_str` arm appears here — which,
/// now that this list IS the manifest, proves every `ModelTypeStr` variant's
/// wire string is constructible. Adding a model is therefore one manifest row
/// plus one [`model_from_str`] arm — never a third edit to a parallel list here.
/// Order follows `ModelTypeStr::ALL` declaration order (consumers iterate it as
/// a set, not by position).
pub fn all_model_types() -> &'static [&'static str] {
    use std::sync::LazyLock;
    static ALL: LazyLock<Vec<&'static str>> = LazyLock::new(|| {
        spectrafit_types::ModelTypeStr::ALL
            .iter()
            .map(|m| m.as_str())
            .collect()
    });
    ALL.as_slice()
}

/// Dimension-aware model construction (SP-2).
///
/// Identical to [`model_from_str`] for every fixed-dimensionality kernel, but
/// for the parametric `"gaussian_nd"` it builds a [`gaussian_nd::GaussianND`] of
/// the dimensionality `n_dims` (the node's explicit field, passed by the
/// compiler). Returns `None` for an unknown type, OR for `"gaussian_nd"` with
/// `n_dims == None` (the caller must surface a clear "dimension required" error).
pub fn model_from_str_with_dims(model_type: &str, n_dims: Option<usize>) -> Option<Box<dyn Model>> {
    match model_type {
        "gaussian_nd" => {
            n_dims.map(|d| Box::new(crate::gaussian_nd::GaussianND::new(d)) as Box<dyn Model>)
        }
        other => model_from_str(other),
    }
}

/// Dispatch a model type string to a boxed `Model` implementation.
///
/// Returns `None` for unknown type strings.
pub fn model_from_str(model_type: &str) -> Option<Box<dyn Model>> {
    match model_type {
        "gaussian" => Some(Box::new(crate::gaussian::Gaussian)),
        "gaussian2d" => Some(Box::new(crate::gaussian2d::Gaussian2D)),
        // Default 1-D instance for the string-registry roundtrip; the compiler
        // builds the real D-dimensional instance via `model_from_str_with_dims`
        // from the node's explicit `n_dims` (SP-2).
        "gaussian_nd" => Some(Box::new(crate::gaussian_nd::GaussianND::new(1))),
        "lorentzian" => Some(Box::new(crate::lorentzian::Lorentzian)),
        "voigt" => Some(Box::new(crate::voigt::Voigt)),
        "constant" => Some(Box::new(crate::polynomial::Constant)),
        "linear" => Some(Box::new(crate::polynomial::Linear)),
        "quadratic" => Some(Box::new(crate::polynomial::Quadratic)),
        "arctan_step" => Some(Box::new(crate::step::ArctanStep)),
        "tanh_step" => Some(Box::new(crate::step::TanhStep)),
        "erfc_step" => Some(Box::new(crate::step::ErfcStep)),
        "pseudo_voigt" => Some(Box::new(crate::pseudo_voigt::PseudoVoigt)),
        "fano" => Some(Box::new(crate::fano::Fano)),
        "double_exponential" => Some(Box::new(crate::exponential::DoubleExponential)),
        "true_voigt" => Some(Box::new(crate::voigt_true::TrueVoigt)),
        "skewed_gaussian" => Some(Box::new(crate::skewed_gaussian::SkewedGaussian)),
        "exp_gaussian" => Some(Box::new(crate::emg::ExpGaussian)),
        "doniach_sunjic" => Some(Box::new(crate::doniach::DoniachSunjic)),
        "log_normal" => Some(Box::new(crate::log_normal::LogNormal)),
        "pearson7" => Some(Box::new(crate::pearson7::Pearson7)),
        "split_gaussian" => Some(Box::new(crate::split_gaussian::SplitGaussian)),
        "moffat" => Some(Box::new(crate::moffat::Moffat)),
        "students_t" => Some(Box::new(crate::students_t::StudentsT)),
        "split_pearson7" => Some(Box::new(crate::split_pearson7::SplitPearson7)),
        "breit_wigner" => Some(Box::new(crate::breit_wigner::BreitWigner)),
        "asym_ir" => Some(Box::new(crate::asym_ir::AsymIr)),
        "harmonic_ir" => Some(Box::new(crate::harmonic_ir::HarmonicIr)),
        "tauc" => Some(Box::new(crate::tauc::Tauc)),
        "cauchy_dispersion" => Some(Box::new(crate::cauchy_dispersion::CauchyDispersion)),
        "kww" => Some(Box::new(crate::kww::Kww)),
        "saturating_exponential" => Some(Box::new(
            crate::saturating_exponential::SaturatingExponential,
        )),
        "power_saturation" => Some(Box::new(crate::power_saturation::PowerSaturation)),
        "power_law_offset" => Some(Box::new(crate::power_law_offset::PowerLawOffset)),
        "mgh09_rational" => Some(Box::new(crate::mgh09_rational::Mgh09Rational)),
        _ => None,
    }
}
