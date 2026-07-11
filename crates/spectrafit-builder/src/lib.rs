//! spectrafit-builder — typed Rust DSL for [`FitGraphSpec`].
//!
//! Opens the kernel to direct Rust users so they do not have to hand-write JSON
//! payloads. The builder produces the exact same `FitGraphSpec` shape the JSON
//! contract describes — see the `builder_roundtrip` integration test.
//!
//! # Example
//!
//! ```
//! use spectrafit_builder::FitGraphBuilder;
//!
//! let g = FitGraphBuilder::new()
//!     .add_gaussian("g0", 1.0, 0.0, 1.0)
//!     .add_linear("baseline", 0.0, 0.5)
//!     .build();
//!
//! assert_eq!(g.nodes.len(), 2);
//! assert_eq!(g.schema_version, "0.1");
//! ```
#![warn(missing_docs)]
#![forbid(unsafe_code)]
#![allow(clippy::too_many_arguments)]

use std::collections::HashMap;

use spectrafit_models::{model_from_str, Model};
use spectrafit_types::types::{ExprEdge, FitGraphSpec, ModelNodeSpec, ModelTypeStr, ParameterSpec};

/// Canonical schema version embedded in every builder-produced `FitGraphSpec`.
///
/// Mirrors the string Python writes when emitting a fresh spec; lives in one
/// place so any future bump is a single edit.
pub const SCHEMA_VERSION: &str = "0.1";

/// Fluent builder for a [`FitGraphSpec`].
///
/// Internal state is just `(Vec<ModelNodeSpec>, Vec<ExprEdge>)`. Each
/// `add_<model>` arm wires the right `ModelTypeStr` variant — derived from
/// [`ModelTypeStr::as_str`] (no hand-written wire keys) — and constructs a
/// `ParameterSpec` per ordered kernel parameter. Default ranges are unbounded
/// (`±∞`) and `vary = true`, matching the JSON the Python side writes when a
/// user does not pin bounds explicitly.
#[derive(Debug, Clone, Default)]
pub struct FitGraphBuilder {
    nodes: Vec<ModelNodeSpec>,
    expr_edges: Vec<ExprEdge>,
}

impl FitGraphBuilder {
    /// Create an empty builder.
    pub fn new() -> Self {
        Self {
            nodes: Vec::new(),
            expr_edges: Vec::new(),
        }
    }

    /// List every model wire-key the builder can produce.
    ///
    /// Mirror of the [`ModelTypeStr`] registry — the parity test in this crate
    /// pins it against `model_from_str` so a missing variant is caught at
    /// `cargo test` time.
    pub fn available_models() -> Vec<&'static str> {
        ALL_MODELS.iter().map(|m| m.as_str()).collect()
    }

    /// Add a parameter expression edge (a tied parameter).
    ///
    /// Equivalent to a `ExprEdge` JSON entry: the named `target_param` on
    /// `target_node` is driven by `expression` instead of varied freely.
    pub fn tie(
        mut self,
        target_node: impl Into<String>,
        target_param: impl Into<String>,
        expression: impl Into<String>,
    ) -> Self {
        self.expr_edges.push(ExprEdge {
            target_node: target_node.into(),
            target_param: target_param.into(),
            expression: expression.into(),
        });
        self
    }

    /// Finish building and return the underlying [`FitGraphSpec`].
    pub fn build(self) -> FitGraphSpec {
        FitGraphSpec {
            schema_version: SCHEMA_VERSION.to_string(),
            nodes: self.nodes,
            expr_edges: self.expr_edges,
        }
    }

    // -----------------------------------------------------------------------
    // Per-model fluent methods. Each one positionally accepts the kernel's
    // declared `param_names()` in order — keeping the surface aligned with the
    // Rust kernel rather than the Python alias layer.
    // -----------------------------------------------------------------------

    /// Add a Gaussian peak: `A · exp(−(x−c)² / (2σ²))`.
    ///
    /// Parameters (in order): `amplitude`, `center`, `sigma`.
    pub fn add_gaussian(self, id: &str, amplitude: f64, center: f64, sigma: f64) -> Self {
        self.add_node(id, ModelTypeStr::Gaussian, &[amplitude, center, sigma])
    }

    /// Add an axis-aligned 2-D Gaussian peak (`n_dims == 2`).
    ///
    /// Parameters (in order): `amplitude`, `center_x`, `center_y`,
    /// `sigma_x`, `sigma_y`.
    pub fn add_gaussian2d(
        self,
        id: &str,
        amplitude: f64,
        center_x: f64,
        center_y: f64,
        sigma_x: f64,
        sigma_y: f64,
    ) -> Self {
        self.add_node(
            id,
            ModelTypeStr::Gaussian2D,
            &[amplitude, center_x, center_y, sigma_x, sigma_y],
        )
    }

    /// Add a parametric N-D Gaussian peak (`gaussian_nd`, SP-2).
    ///
    /// This fluent helper adds the **1-D** instance (`amplitude`, `center_0`,
    /// `sigma_0`) — the dimensionality the compiler infers from the indexed
    /// `center_<i>` parameters. For higher D, construct the node directly with
    /// `center_0..center_{D-1}` / `sigma_0..sigma_{D-1}` parameters; the builder
    /// helper covers the roundtrip/registry contract for the variant.
    pub fn add_gaussian_nd(self, id: &str, amplitude: f64, center_0: f64, sigma_0: f64) -> Self {
        self.add_node(id, ModelTypeStr::GaussianNd, &[amplitude, center_0, sigma_0])
    }

    /// Add a Lorentzian (Cauchy) peak.
    ///
    /// Parameters (in order): `amplitude`, `center`, `sigma`.
    pub fn add_lorentzian(self, id: &str, amplitude: f64, center: f64, sigma: f64) -> Self {
        self.add_node(id, ModelTypeStr::Lorentzian, &[amplitude, center, sigma])
    }

    /// Add the Voigt kernel.
    ///
    /// Note: the `voigt` wire key is the pseudo-Voigt linear mixture
    /// (`A·(fraction·L + (1−fraction)·G)`) — its fourth parameter is the
    /// mixing weight `fraction` (canonical name per `MODELS.md`), not `gamma`.
    /// Use [`Self::add_true_voigt`] for the Faddeeva-function convolution.
    ///
    /// Parameters (in order): `amplitude`, `center`, `sigma`, `fraction`.
    pub fn add_voigt(
        self,
        id: &str,
        amplitude: f64,
        center: f64,
        sigma: f64,
        fraction: f64,
    ) -> Self {
        self.add_node(
            id,
            ModelTypeStr::Voigt,
            &[amplitude, center, sigma, fraction],
        )
    }

    /// Add a constant offset: `f(x) = c`.
    pub fn add_constant(self, id: &str, c: f64) -> Self {
        self.add_node(id, ModelTypeStr::Constant, &[c])
    }

    /// Add a linear baseline: `slope·x + intercept`.
    pub fn add_linear(self, id: &str, slope: f64, intercept: f64) -> Self {
        self.add_node(id, ModelTypeStr::Linear, &[slope, intercept])
    }

    /// Add a quadratic bowl: `amplitude · (x − center)² + offset`.
    pub fn add_quadratic(
        self,
        id: &str,
        amplitude: f64,
        center: f64,
        offset: f64,
    ) -> Self {
        self.add_node(
            id,
            ModelTypeStr::Quadratic,
            &[amplitude, center, offset],
        )
    }

    /// Add an arctangent step.
    ///
    /// Parameters (in order): `amplitude`, `center`, `sigma`.
    pub fn add_arctan_step(self, id: &str, amplitude: f64, center: f64, sigma: f64) -> Self {
        self.add_node(id, ModelTypeStr::ArctanStep, &[amplitude, center, sigma])
    }

    /// Add a hyperbolic tangent step.
    ///
    /// Parameters (in order): `amplitude`, `center`, `sigma`.
    pub fn add_tanh_step(self, id: &str, amplitude: f64, center: f64, sigma: f64) -> Self {
        self.add_node(id, ModelTypeStr::TanhStep, &[amplitude, center, sigma])
    }

    /// Add a complementary-error-function step.
    ///
    /// Parameters (in order): `amplitude`, `center`, `sigma`.
    pub fn add_erfc_step(self, id: &str, amplitude: f64, center: f64, sigma: f64) -> Self {
        self.add_node(id, ModelTypeStr::ErfcStep, &[amplitude, center, sigma])
    }

    /// Add a pseudo-Voigt linear-mixture peak.
    ///
    /// Parameters (in order): `amplitude`, `center`, `sigma`, `fraction`.
    pub fn add_pseudo_voigt(
        self,
        id: &str,
        amplitude: f64,
        center: f64,
        sigma: f64,
        fraction: f64,
    ) -> Self {
        self.add_node(
            id,
            ModelTypeStr::PseudoVoigt,
            &[amplitude, center, sigma, fraction],
        )
    }

    /// Add a Fano resonance lineshape.
    ///
    /// Parameters (in order): `amplitude`, `center`, `gamma`, `q`.
    pub fn add_fano(
        self,
        id: &str,
        amplitude: f64,
        center: f64,
        gamma: f64,
        q: f64,
    ) -> Self {
        self.add_node(id, ModelTypeStr::Fano, &[amplitude, center, gamma, q])
    }

    /// Add a double-exponential decay: `A₁·exp(−λ₁·x) + A₂·exp(−λ₂·x)`.
    pub fn add_double_exponential(
        self,
        id: &str,
        a1: f64,
        lam1: f64,
        a2: f64,
        lam2: f64,
    ) -> Self {
        self.add_node(
            id,
            ModelTypeStr::DoubleExponential,
            &[a1, lam1, a2, lam2],
        )
    }

    /// Add a saturating exponential rise: `A·(1 − exp(−k·x))`.
    ///
    /// Parameters (in order): `amplitude`, `rate`.
    pub fn add_saturating_exponential(self, id: &str, amplitude: f64, rate: f64) -> Self {
        self.add_node(id, ModelTypeStr::SaturatingExponential, &[amplitude, rate])
    }

    /// Add a power-law saturation: `A·(1 − (1 + rate·x/2)^(−2))` (Misra1b model).
    ///
    /// Parameters (in order): `amplitude`, `rate`.
    pub fn add_power_saturation(self, id: &str, amplitude: f64, rate: f64) -> Self {
        self.add_node(id, ModelTypeStr::PowerSaturation, &[amplitude, rate])
    }

    /// Add a power-law with offset: `amplitude · (offset + x)^(−1/shape)` (Bennett5 model).
    ///
    /// Parameters (in order): `amplitude`, `offset`, `shape`.
    ///
    /// **Domain guard:** requires `offset + x > 0` for all data points; the
    /// kernel returns `NaN` otherwise and the LM solver backs off.
    pub fn add_power_law_offset(
        self,
        id: &str,
        amplitude: f64,
        offset: f64,
        shape: f64,
    ) -> Self {
        self.add_node(
            id,
            ModelTypeStr::PowerLawOffset,
            &[amplitude, offset, shape],
        )
    }

    /// Add the Kowalik–Osborne rational function (NIST StRD MGH09).
    ///
    /// `amplitude · (x² + num_lin·x) / (x² + den_lin·x + den_const)`
    ///
    /// Parameters (in order): `amplitude`, `num_lin`, `den_lin`, `den_const`.
    ///
    /// **Domain guard:** requires `x² + den_lin·x + den_const ≠ 0`; the kernel
    /// returns `NaN` otherwise. At the MGH09 certified parameters the denominator
    /// discriminant is negative, keeping D > 0 for all x.
    pub fn add_mgh09_rational(
        self,
        id: &str,
        amplitude: f64,
        num_lin: f64,
        den_lin: f64,
        den_const: f64,
    ) -> Self {
        self.add_node(
            id,
            ModelTypeStr::Mgh09Rational,
            &[amplitude, num_lin, den_lin, den_const],
        )
    }

    /// Add the true Voigt profile (Gaussian ⊗ Lorentzian) via the Faddeeva
    /// function.
    ///
    /// Parameters (in order): `amplitude`, `center`, `sigma`, `gamma`.
    pub fn add_true_voigt(
        self,
        id: &str,
        amplitude: f64,
        center: f64,
        sigma: f64,
        gamma: f64,
    ) -> Self {
        self.add_node(
            id,
            ModelTypeStr::TrueVoigt,
            &[amplitude, center, sigma, gamma],
        )
    }

    /// Add a skewed Gaussian (error-function-modulated asymmetric peak).
    ///
    /// Parameters (in order): `amplitude`, `center`, `sigma`, `gamma`.
    pub fn add_skewed_gaussian(
        self,
        id: &str,
        amplitude: f64,
        center: f64,
        sigma: f64,
        gamma: f64,
    ) -> Self {
        self.add_node(
            id,
            ModelTypeStr::SkewedGaussian,
            &[amplitude, center, sigma, gamma],
        )
    }

    /// Add an exponentially-modified Gaussian (asymmetric tailing peak).
    ///
    /// Parameters (in order): `amplitude`, `center`, `sigma`, `gamma`.
    pub fn add_exp_gaussian(
        self,
        id: &str,
        amplitude: f64,
        center: f64,
        sigma: f64,
        gamma: f64,
    ) -> Self {
        self.add_node(
            id,
            ModelTypeStr::ExpGaussian,
            &[amplitude, center, sigma, gamma],
        )
    }

    /// Add a Doniach–Šunjić asymmetric XPS core-level lineshape.
    ///
    /// Parameters (in order): `amplitude`, `center`, `sigma`, `gamma`.
    pub fn add_doniach_sunjic(
        self,
        id: &str,
        amplitude: f64,
        center: f64,
        sigma: f64,
        gamma: f64,
    ) -> Self {
        self.add_node(
            id,
            ModelTypeStr::DoniachSunjic,
            &[amplitude, center, sigma, gamma],
        )
    }

    /// Add a log-normal peak (`A·exp(−(ln(x/c))²/(2σ²))` for `x > 0`).
    ///
    /// Parameters (in order): `amplitude`, `center`, `sigma`.
    pub fn add_log_normal(self, id: &str, amplitude: f64, center: f64, sigma: f64) -> Self {
        self.add_node(id, ModelTypeStr::LogNormal, &[amplitude, center, sigma])
    }

    /// Add a Pearson VII peak.
    ///
    /// Parameters (in order): `amplitude`, `center`, `sigma`, `m`.
    pub fn add_pearson7(
        self,
        id: &str,
        amplitude: f64,
        center: f64,
        sigma: f64,
        m: f64,
    ) -> Self {
        self.add_node(
            id,
            ModelTypeStr::Pearson7,
            &[amplitude, center, sigma, m],
        )
    }

    /// Add a split (bi-)Gaussian with different widths each side of `center`.
    ///
    /// Parameters (in order): `amplitude`, `center`, `sigma_l`, `sigma_r`.
    pub fn add_split_gaussian(
        self,
        id: &str,
        amplitude: f64,
        center: f64,
        sigma_l: f64,
        sigma_r: f64,
    ) -> Self {
        self.add_node(
            id,
            ModelTypeStr::SplitGaussian,
            &[amplitude, center, sigma_l, sigma_r],
        )
    }

    /// Add a Moffat peak.
    ///
    /// Parameters (in order): `amplitude`, `center`, `sigma`, `beta`.
    pub fn add_moffat(
        self,
        id: &str,
        amplitude: f64,
        center: f64,
        sigma: f64,
        beta: f64,
    ) -> Self {
        self.add_node(
            id,
            ModelTypeStr::Moffat,
            &[amplitude, center, sigma, beta],
        )
    }

    /// Add a Student's-t peak.
    ///
    /// Parameters (in order): `amplitude`, `center`, `sigma`, `nu`.
    pub fn add_students_t(
        self,
        id: &str,
        amplitude: f64,
        center: f64,
        sigma: f64,
        nu: f64,
    ) -> Self {
        self.add_node(
            id,
            ModelTypeStr::StudentsT,
            &[amplitude, center, sigma, nu],
        )
    }

    /// Add a split Pearson VII (split width + exponent each side of `center`).
    ///
    /// Parameters (in order): `amplitude`, `center`, `sigma_l`, `sigma_r`,
    /// `m_l`, `m_r`.
    pub fn add_split_pearson7(
        self,
        id: &str,
        amplitude: f64,
        center: f64,
        sigma_l: f64,
        sigma_r: f64,
        m_l: f64,
        m_r: f64,
    ) -> Self {
        self.add_node(
            id,
            ModelTypeStr::SplitPearson7,
            &[amplitude, center, sigma_l, sigma_r, m_l, m_r],
        )
    }

    /// Add a Breit-Wigner-Fano resonance.
    ///
    /// Parameters (in order): `amplitude`, `center`, `sigma`, `q`.
    pub fn add_breit_wigner(
        self,
        id: &str,
        amplitude: f64,
        center: f64,
        sigma: f64,
        q: f64,
    ) -> Self {
        self.add_node(
            id,
            ModelTypeStr::BreitWigner,
            &[amplitude, center, sigma, q],
        )
    }

    /// Add an asymmetric IR band (Gaussian × logistic sigmoid).
    ///
    /// Parameters (in order): `amplitude`, `center`, `sigma`, `k`.
    pub fn add_asym_ir(
        self,
        id: &str,
        amplitude: f64,
        center: f64,
        sigma: f64,
        k: f64,
    ) -> Self {
        self.add_node(
            id,
            ModelTypeStr::AsymIr,
            &[amplitude, center, sigma, k],
        )
    }

    /// Add a driven damped harmonic-oscillator IR absorption.
    ///
    /// Parameters (in order): `amplitude`, `center`, `sigma`.
    pub fn add_harmonic_ir(self, id: &str, amplitude: f64, center: f64, sigma: f64) -> Self {
        self.add_node(id, ModelTypeStr::HarmonicIr, &[amplitude, center, sigma])
    }

    /// Add a Tauc optical band-gap edge: `A·((x−e_gap)·H(x−e_gap))^p`.
    ///
    /// Parameters (in order): `amplitude`, `e_gap`, `exponent`.
    pub fn add_tauc(
        self,
        id: &str,
        amplitude: f64,
        e_gap: f64,
        exponent: f64,
    ) -> Self {
        self.add_node(id, ModelTypeStr::Tauc, &[amplitude, e_gap, exponent])
    }

    /// Add a Cauchy refractive-index dispersion: `a + b/x² + c/x⁴`.
    pub fn add_cauchy_dispersion(self, id: &str, a: f64, b: f64, c: f64) -> Self {
        self.add_node(id, ModelTypeStr::CauchyDispersion, &[a, b, c])
    }

    /// Add a Kohlrausch–Williams–Watts stretched exponential: `A·exp(−(x/τ)^β)`.
    ///
    /// Parameters (in order): `amplitude`, `tau`, `beta`.
    pub fn add_kww(self, id: &str, amplitude: f64, tau: f64, beta: f64) -> Self {
        self.add_node(id, ModelTypeStr::Kww, &[amplitude, tau, beta])
    }

    // -----------------------------------------------------------------------
    // Internal: build a `ModelNodeSpec` by looking up the kernel's declared
    // parameter names and zipping them with positional values.
    // -----------------------------------------------------------------------
    fn add_node(mut self, id: &str, model_type: ModelTypeStr, values: &[f64]) -> Self {
        let wire = model_type.as_str();
        let kernel: Box<dyn Model> = model_from_str(wire).unwrap_or_else(|| {
            // Unreachable by construction — every variant is wired into
            // `model_from_str`, and the `available_models_matches_model_from_str`
            // test pins this — but explicit panic beats silent UB if a future
            // contributor adds a variant without registering the kernel.
            panic!(
                "spectrafit-builder: model_from_str({wire:?}) returned None — \
                 add the kernel registration in spectrafit-models::model_from_str"
            )
        });
        let names = kernel.param_names();
        debug_assert_eq!(
            names.len(),
            values.len(),
            "builder arity mismatch for {wire}: kernel expects {} params, got {}",
            names.len(),
            values.len()
        );
        let mut parameters: HashMap<String, ParameterSpec> = HashMap::with_capacity(names.len());
        for (name, value) in names.iter().zip(values.iter()) {
            parameters.insert((*name).to_string(), default_parameter(*value));
        }
        self.nodes.push(ModelNodeSpec {
            id: id.to_string(),
            model_type,
            parameters,
            dataset_index: None,
        });
        self
    }
}

/// Default `ParameterSpec` for a builder-added parameter: unbounded, free.
fn default_parameter(value: f64) -> ParameterSpec {
    ParameterSpec {
        value,
        min: f64::NEG_INFINITY,
        max: f64::INFINITY,
        vary: true,
        expr: None,
        scale: None,
    }
}

/// Every model variant the builder can emit, in declaration order.
///
/// Single source of truth for `available_models()` and for the roundtrip /
/// parity tests. New `ModelTypeStr` variant → one entry here.
const ALL_MODELS: &[ModelTypeStr] = &[
    ModelTypeStr::Gaussian,
    ModelTypeStr::Gaussian2D,
    ModelTypeStr::GaussianNd,
    ModelTypeStr::Lorentzian,
    ModelTypeStr::Voigt,
    ModelTypeStr::Constant,
    ModelTypeStr::Linear,
    ModelTypeStr::Quadratic,
    ModelTypeStr::ArctanStep,
    ModelTypeStr::TanhStep,
    ModelTypeStr::ErfcStep,
    ModelTypeStr::PseudoVoigt,
    ModelTypeStr::Fano,
    ModelTypeStr::DoubleExponential,
    ModelTypeStr::SaturatingExponential,
    ModelTypeStr::TrueVoigt,
    ModelTypeStr::SkewedGaussian,
    ModelTypeStr::ExpGaussian,
    ModelTypeStr::DoniachSunjic,
    ModelTypeStr::LogNormal,
    ModelTypeStr::Pearson7,
    ModelTypeStr::SplitGaussian,
    ModelTypeStr::Moffat,
    ModelTypeStr::StudentsT,
    ModelTypeStr::SplitPearson7,
    ModelTypeStr::BreitWigner,
    ModelTypeStr::AsymIr,
    ModelTypeStr::HarmonicIr,
    ModelTypeStr::Tauc,
    ModelTypeStr::CauchyDispersion,
    ModelTypeStr::Kww,
    ModelTypeStr::PowerSaturation,
    ModelTypeStr::PowerLawOffset,
    ModelTypeStr::Mgh09Rational,
];

#[cfg(test)]
mod tests {
    use super::*;

    /// `available_models()` must enumerate every variant `model_from_str` knows
    /// — otherwise a builder caller would see a model the kernel cannot
    /// instantiate, or vice versa.
    #[test]
    fn available_models_matches_model_from_str() {
        for key in FitGraphBuilder::available_models() {
            assert!(
                model_from_str(key).is_some(),
                "available_models() reported {key:?} but model_from_str does not know it",
            );
        }
    }

    /// Empty builder produces a valid, empty `FitGraphSpec`.
    #[test]
    fn empty_builder_produces_valid_spec() {
        let g = FitGraphBuilder::new().build();
        assert_eq!(g.schema_version, SCHEMA_VERSION);
        assert!(g.nodes.is_empty());
        assert!(g.expr_edges.is_empty());
    }

    /// Compiler-enforced exhaustiveness: every `ModelTypeStr` variant must
    /// appear in `ALL_MODELS`. The `match` here has no wildcard arm, so adding
    /// a new variant to `spectrafit-types::ModelTypeStr` without listing it in
    /// `ALL_MODELS` (and adding the matching `add_<name>()` method) breaks the
    /// build — which is the point. Vista-safety: the builder cannot silently
    /// fall behind a new kernel.
    #[test]
    fn every_model_type_str_variant_is_covered_by_all_models() {
        fn covered(variant: &ModelTypeStr) -> bool {
            ALL_MODELS.iter().any(|m| m.as_str() == variant.as_str())
        }
        // No wildcard — adding a new variant forces this test to grow.
        let representatives = [
            ModelTypeStr::Gaussian,
            ModelTypeStr::Gaussian2D,
            ModelTypeStr::GaussianNd,
            ModelTypeStr::Lorentzian,
            ModelTypeStr::Voigt,
            ModelTypeStr::Constant,
            ModelTypeStr::Linear,
            ModelTypeStr::Quadratic,
            ModelTypeStr::ArctanStep,
            ModelTypeStr::TanhStep,
            ModelTypeStr::ErfcStep,
            ModelTypeStr::PseudoVoigt,
            ModelTypeStr::Fano,
            ModelTypeStr::DoubleExponential,
            ModelTypeStr::SaturatingExponential,
            ModelTypeStr::TrueVoigt,
            ModelTypeStr::SkewedGaussian,
            ModelTypeStr::ExpGaussian,
            ModelTypeStr::DoniachSunjic,
            ModelTypeStr::LogNormal,
            ModelTypeStr::Pearson7,
            ModelTypeStr::SplitGaussian,
            ModelTypeStr::Moffat,
            ModelTypeStr::StudentsT,
            ModelTypeStr::SplitPearson7,
            ModelTypeStr::BreitWigner,
            ModelTypeStr::AsymIr,
            ModelTypeStr::HarmonicIr,
            ModelTypeStr::Tauc,
            ModelTypeStr::CauchyDispersion,
            ModelTypeStr::Kww,
            ModelTypeStr::PowerSaturation,
            ModelTypeStr::PowerLawOffset,
            ModelTypeStr::Mgh09Rational,
        ];
        // The `match` below is the compile-time gate: a new `ModelTypeStr`
        // variant is a non-exhaustive-patterns error here, forcing the
        // contributor to wire the builder arm before the crate even compiles.
        for v in &representatives {
            // No wildcard arm → rustc's exhaustiveness check (E0004) fires on
            // any new `ModelTypeStr` variant. That compile error is the gate.
            let _exhaustive: () = match v {
                ModelTypeStr::Gaussian
                | ModelTypeStr::Gaussian2D
                | ModelTypeStr::GaussianNd
                | ModelTypeStr::Lorentzian
                | ModelTypeStr::Voigt
                | ModelTypeStr::Constant
                | ModelTypeStr::Linear
                | ModelTypeStr::Quadratic
                | ModelTypeStr::ArctanStep
                | ModelTypeStr::TanhStep
                | ModelTypeStr::ErfcStep
                | ModelTypeStr::PseudoVoigt
                | ModelTypeStr::Fano
                | ModelTypeStr::DoubleExponential
                | ModelTypeStr::SaturatingExponential
                | ModelTypeStr::TrueVoigt
                | ModelTypeStr::SkewedGaussian
                | ModelTypeStr::ExpGaussian
                | ModelTypeStr::DoniachSunjic
                | ModelTypeStr::LogNormal
                | ModelTypeStr::Pearson7
                | ModelTypeStr::SplitGaussian
                | ModelTypeStr::Moffat
                | ModelTypeStr::StudentsT
                | ModelTypeStr::SplitPearson7
                | ModelTypeStr::BreitWigner
                | ModelTypeStr::AsymIr
                | ModelTypeStr::HarmonicIr
                | ModelTypeStr::Tauc
                | ModelTypeStr::CauchyDispersion
                | ModelTypeStr::Kww
                | ModelTypeStr::PowerSaturation
                | ModelTypeStr::PowerLawOffset
                | ModelTypeStr::Mgh09Rational => (),
            };
            assert!(
                covered(v),
                "ModelTypeStr::{v:?} is not present in ALL_MODELS — add it \
                 alongside the corresponding `add_<name>()` fluent method",
            );
        }
        assert_eq!(
            ALL_MODELS.len(),
            representatives.len(),
            "ALL_MODELS length drifted from the exhaustive variant list",
        );
    }

    /// `tie()` accumulates edges in call order.
    #[test]
    fn tie_accumulates_edges_in_order() {
        let g = FitGraphBuilder::new()
            .tie("g0", "center", "g1.center + 0.5")
            .tie("g1", "sigma", "g0.sigma")
            .build();
        assert_eq!(g.expr_edges.len(), 2);
        assert_eq!(g.expr_edges[0].target_node, "g0");
        assert_eq!(g.expr_edges[0].target_param, "center");
        assert_eq!(g.expr_edges[0].expression, "g1.center + 0.5");
        assert_eq!(g.expr_edges[1].target_node, "g1");
    }
}
