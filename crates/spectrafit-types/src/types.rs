use serde::{Deserialize, Deserializer, Serialize, Serializer};
use std::collections::HashMap;

// ---------------------------------------------------------------------------
// Helper: deserialise null → NEG_INFINITY (for min bound)
// ---------------------------------------------------------------------------
fn deser_min<'de, D>(d: D) -> Result<f64, D::Error>
where
    D: Deserializer<'de>,
{
    let opt: Option<f64> = Option::deserialize(d)?;
    Ok(opt.unwrap_or(f64::NEG_INFINITY))
}

// ---------------------------------------------------------------------------
// Helper: deserialise null → INFINITY (for max bound)
// ---------------------------------------------------------------------------
fn deser_max<'de, D>(d: D) -> Result<f64, D::Error>
where
    D: Deserializer<'de>,
{
    let opt: Option<f64> = Option::deserialize(d)?;
    Ok(opt.unwrap_or(f64::INFINITY))
}

// ---------------------------------------------------------------------------
// Helper: serialise ±inf → null
// ---------------------------------------------------------------------------
fn ser_bound<S>(value: &f64, s: S) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    if value.is_infinite() {
        s.serialize_none()
    } else {
        s.serialize_some(value)
    }
}

// ---------------------------------------------------------------------------
// ParameterSpec — mirrors Python Parameter schema
// ---------------------------------------------------------------------------

/// A single model parameter with its initial value, bounds, and vary flag.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParameterSpec {
    /// Initial (or fixed) parameter value.
    pub value: f64,
    #[serde(deserialize_with = "deser_min", serialize_with = "ser_bound")]
    /// Lower bound; `null` in JSON deserialises to `NEG_INFINITY`.
    pub min: f64,
    #[serde(deserialize_with = "deser_max", serialize_with = "ser_bound")]
    /// Upper bound; `null` in JSON deserialises to `INFINITY`.
    pub max: f64,
    /// Whether this parameter is optimised (`true`) or held fixed (`false`).
    pub vary: bool,
    #[serde(default)]
    /// Optional symbolic expression (not yet evaluated by the engine).
    pub expr: Option<String>,
    #[serde(default)]
    /// Optional scale hint for display (does not affect fitting).
    pub scale: Option<f64>,
}

// ---------------------------------------------------------------------------
// ModelTypeStr — string enum matching Python ModelType values
// ---------------------------------------------------------------------------

/// Stable string enum for model kernel selection.
///
/// The `snake_case` serde representation is the wire format used in JSON
/// `FitGraphSpec` payloads and Python bindings.
/// Declarative single-source manifest for every model kernel's **type
/// identity**: the enum variant + its canonical `snake_case` wire string. From
/// this ONE table the macro generates the [`ModelTypeStr`] enum (with the serde
/// rename pinned per variant), [`ModelTypeStr::as_str`], the derived
/// [`ModelTypeStr::VARIANT_COUNT`], and the [`ModelTypeStr::ALL`] enumeration.
///
/// Adding / renaming / removing a model's identity is therefore a single edit
/// here, not the previously hand-duplicated set of an enum variant + an `as_str`
/// arm + a hand-typed `VARIANT_COUNT` + several all-variants lists in downstream
/// crates. Those lists could (and did) silently drift — the `spectrafit-varpro`
/// `all_variants` guard once went 4 variants stale — precisely because each was
/// a separate hand-list. Now they iterate [`ModelTypeStr::ALL`] instead.
///
/// **Scope (deliberate):** the manifest carries ONLY type identity — NOT solver
/// eligibility. VarPro separability classification stays in `spectrafit-varpro`
/// (which derives its variant list from [`ModelTypeStr::ALL`] but keeps its own
/// SEPARABLE/INVARIANT/non-varpro buckets). Keeping solver-layer knowledge out
/// of the type crate avoids turning `spectrafit-types` into a god-module.
macro_rules! model_manifest {
    (
        $(
            $(#[$attr:meta])*
            $variant:ident => $wire:literal
        ),+ $(,)?
    ) => {
        /// Stable string enum for model kernel selection.
        ///
        /// The `snake_case` serde representation is the wire format used in JSON
        /// `FitGraphSpec` payloads and Python bindings. Each variant's wire
        /// string is pinned explicitly (generated from the manifest), so the
        /// serde rename and [`ModelTypeStr::as_str`] are byte-identical by
        /// construction and cannot drift.
        #[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
        pub enum ModelTypeStr {
            $(
                $(#[$attr])*
                #[serde(rename = $wire)]
                $variant,
            )+
        }

        impl ModelTypeStr {
            /// Every variant, in declaration order — the single enumeration
            /// source. Downstream all-variants lists (the parity guard, the
            /// varpro classifier list) iterate THIS rather than re-listing the
            /// variants, so they cannot silently drift from the enum.
            pub const ALL: &'static [ModelTypeStr] = &[ $( ModelTypeStr::$variant ),+ ];

            /// Total number of variants — derived from [`ALL`](Self::ALL),
            /// never hand-typed.
            pub const VARIANT_COUNT: usize = ModelTypeStr::ALL.len();

            /// Canonical wire-format string for this model type.
            ///
            /// One canonical table for the whole workspace — previously
            /// duplicated (byte-identical) in `spectrafit-graph::compiler` and
            /// `spectrafit-varpro::lib`. Generated from the manifest, so it is
            /// byte-identical to the serde `rename` on each variant (pinned by
            /// `model_type_as_str_matches_serde_wire_for_every_variant`).
            #[must_use]
            pub fn as_str(&self) -> &'static str {
                match self {
                    $( ModelTypeStr::$variant => $wire, )+
                }
            }
        }
    };
}

model_manifest! {
    /// Gaussian peak: `A · exp(−(x−c)² / (2σ²))`.
    Gaussian => "gaussian",
    /// Axis-aligned 2-D Gaussian peak (n_dims == 2):
    /// `A · exp(−(x−cₓ)²/(2σₓ²) − (y−c_y)²/(2σ_y²))`.
    Gaussian2D => "gaussian2d",
    /// Axis-aligned N-D Gaussian peak (parametric dimensionality, SP-2). The
    /// node's explicit `n_dims` field sets D; params are indexed
    /// `center_0..center_{D-1}` / `sigma_0..sigma_{D-1}`.
    GaussianNd => "gaussian_nd",
    /// Lorentzian (Cauchy) peak: `A · γ² / ((x−c)² + γ²)`.
    Lorentzian => "lorentzian",
    /// Voigt profile: convolution of Gaussian and Lorentzian.
    Voigt => "voigt",
    /// Constant offset: `c`.
    Constant => "constant",
    /// Linear baseline: `m·x + b`.
    Linear => "linear",
    /// Quadratic bowl: `A·(x−c)² + b`.
    Quadratic => "quadratic",
    /// Arctangent step function.
    ArctanStep => "arctan_step",
    /// Hyperbolic tangent step function.
    TanhStep => "tanh_step",
    /// Complementary error function step.
    ErfcStep => "erfc_step",
    /// Pseudo-Voigt: linear combination `η·L + (1−η)·G`.
    PseudoVoigt => "pseudo_voigt",
    /// Fano resonance lineshape.
    Fano => "fano",
    /// Double-exponential decay: `A1·exp(-λ1·x) + A2·exp(-λ2·x)`.
    DoubleExponential => "double_exponential",
    /// True Voigt profile (Gaussian ⊗ Lorentzian) via the Faddeeva function.
    TrueVoigt => "true_voigt",
    /// Skewed Gaussian: error-function-modulated asymmetric peak.
    SkewedGaussian => "skewed_gaussian",
    /// Exponentially-modified Gaussian (asymmetric tailing peak).
    ExpGaussian => "exp_gaussian",
    /// Doniach–Šunjić asymmetric core-level lineshape (XPS).
    DoniachSunjic => "doniach_sunjic",
    /// Log-normal peak: `A · exp(−(ln(x/c))² / (2σ²))` for `x > 0`, else `0`.
    LogNormal => "log_normal",
    /// Pearson VII peak: `A / [1 + ((x−c)/σ)²·(2^{1/m}−1)]^m`.
    Pearson7 => "pearson7",
    /// Split (asymmetric) Gaussian: different width on each side of the center.
    SplitGaussian => "split_gaussian",
    /// Moffat peak.
    Moffat => "moffat",
    /// Student's-t peak.
    StudentsT => "students_t",
    /// Split Pearson VII (split width + exponent each side).
    SplitPearson7 => "split_pearson7",
    /// Breit-Wigner-Fano resonance.
    BreitWigner => "breit_wigner",
    /// Asymmetric IR band (Gaussian × logistic sigmoid).
    AsymIr => "asym_ir",
    /// Driven damped harmonic-oscillator IR absorption.
    HarmonicIr => "harmonic_ir",
    /// Tauc optical band-gap edge: `A·((x−e_gap)·H(x−e_gap))^p`.
    Tauc => "tauc",
    /// Cauchy refractive-index dispersion: `a + b/x² + c/x⁴`.
    CauchyDispersion => "cauchy_dispersion",
    /// Kohlrausch–Williams–Watts stretched exponential: `A·exp(−(x/τ)^β)`.
    Kww => "kww",
    /// Saturating exponential (BoxBOD): `amplitude · (1 − exp(−rate · x))`.
    SaturatingExponential => "saturating_exponential",
    /// Power-law saturation (Misra1b): `amplitude · (1 − (1 + rate·x/2)^(−2))`.
    PowerSaturation => "power_saturation",
    /// Power-law with offset (Bennett5): `amplitude · (offset + x)^(−1/shape)`.
    PowerLawOffset => "power_law_offset",
    /// Kowalik–Osborne rational function (MGH09):
    /// `amplitude · (x² + num_lin·x) / (x² + den_lin·x + den_const)`.
    Mgh09Rational => "mgh09_rational",
}

// ---------------------------------------------------------------------------
// ModelNodeSpec
// ---------------------------------------------------------------------------

/// A single model node in the fit graph.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelNodeSpec {
    /// Unique node identifier (e.g. `"g1"`, `"peak"`).
    pub id: String,
    /// Kernel type selecting which model function to evaluate.
    pub model_type: ModelTypeStr,
    /// Parameter map: key = parameter name (e.g. `"amplitude"`).
    pub parameters: HashMap<String, ParameterSpec>,
    /// Dataset (slice) scope for global analysis. `None` (the default, and the
    /// only value that matters for single-dataset fits) means the node is
    /// **global** — it contributes to every dataset/slice. `Some(i)` makes the
    /// node **local** to slice `i`: in a multi-dataset fit it contributes only to
    /// dataset `i`'s (contiguous) points, and its Jacobian columns are zero for
    /// every other slice. This is the primitive behind simultaneous global
    /// analysis (shared global shapes + per-slice local amplitudes).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub dataset_index: Option<usize>,
}

// ---------------------------------------------------------------------------
// ExprEdge
// ---------------------------------------------------------------------------

/// A directed expression edge that constrains one parameter to a formula.
///
/// `expr_edges` ARE supported: `fit()` compiles them into a cycle-checked tied-
/// parameter plan that is applied each solver iteration (the target parameter is
/// driven by the expression instead of varied freely).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExprEdge {
    /// Id of the node whose parameter is constrained.
    pub target_node: String,
    /// Name of the constrained parameter within `target_node`.
    pub target_param: String,
    /// Symbolic expression referencing other node parameters.
    pub expression: String,
}

// ---------------------------------------------------------------------------
// FitGraphSpec
// ---------------------------------------------------------------------------

/// A directed acyclic graph specifying the model topology for a fit.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FitGraphSpec {
    /// Schema version string (e.g. `"0.1"`).
    pub schema_version: String,
    /// Ordered list of model nodes.
    pub nodes: Vec<ModelNodeSpec>,
    #[serde(default)]
    /// Directed expression edges. Compiled into a cycle-checked tied-parameter
    /// plan and evaluated each solver iteration.
    pub expr_edges: Vec<ExprEdge>,
}

// ---------------------------------------------------------------------------
// MeasurementSpec
// ---------------------------------------------------------------------------

/// A single measurement dataset for fitting.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MeasurementSpec {
    #[serde(default)]
    /// Schema version (optional, may be `None`).
    pub schema_version: Option<String>,
    /// Coordinate array: outer index = dimension, inner index = point.
    /// For 1-D fits, `x[0]` is the x-axis vector.
    pub x: Vec<Vec<f64>>,
    /// Observed y-values, one per point.
    pub y: Vec<f64>,
    #[serde(default)]
    /// Per-point standard deviations for weighted fitting.  `None` → uniform
    /// weight of 1.
    pub sigma: Option<Vec<f64>>,
    #[serde(default)]
    /// Optional label for display in multi-dataset fit reports.
    pub label: Option<String>,
}

// ---------------------------------------------------------------------------
// MeasurementInput — accepts single object or JSON array
// ---------------------------------------------------------------------------

/// Serde-untagged wrapper that accepts either a single `MeasurementSpec` or
/// a JSON array of them.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum MeasurementInput {
    /// A single measurement.
    Single(MeasurementSpec),
    /// Multiple measurements (multi-dataset fit).
    Multi(Vec<MeasurementSpec>),
}

impl MeasurementInput {
    /// Consume self and return a `Vec<MeasurementSpec>`, wrapping a single
    /// measurement in a one-element vec if necessary.
    #[must_use]
    pub fn into_vec(self) -> Vec<MeasurementSpec> {
        match self {
            MeasurementInput::Single(s) => vec![s],
            MeasurementInput::Multi(v) => v,
        }
    }
}

// ---------------------------------------------------------------------------
// FitOptionsSpec
// ---------------------------------------------------------------------------

/// Solver configuration for a fit call.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FitOptionsSpec {
    #[serde(default)]
    /// Schema version (optional).
    pub schema_version: Option<String>,
    /// Solver name: `"lm"` (faer trust-region default), `"lm-legacy"` (nalgebra
    /// oracle), `"trf"` (Coleman–Li bound scaling), `"geodesic"` (LM + geodesic
    /// acceleration), `"varpro"`, `"auto"`, `"irls"`, `"irls:bisquare"`,
    /// `"irls:cauchy"`, or `"global"`.
    pub solver: String,
    /// Maximum number of function evaluations (LM patience).
    pub max_iterations: u64,
    /// Convergence tolerance passed to the underlying solver.
    pub tolerance: f64,
    /// Initial trust-region radius `Δ` for the Dogleg / Newton-CG solvers.
    /// `None` (or omitted) keeps the library default (0.0 → problem-derived).
    /// Cycle 8.2 binding; serde-default so 1.1 payloads keep validating.
    #[serde(default)]
    pub delta0: Option<f64>,
    /// Hard upper bound on the trust-region radius `Δ` for Dogleg / Newton-CG.
    /// `None` keeps the library default (1e3). Cycle 8.2.
    #[serde(default)]
    pub max_delta: Option<f64>,
    /// Step-acceptance threshold for Dogleg / Newton-CG (accept when `ρ > eta`).
    /// `None` keeps the library default (1e-4). Cycle 8.2.
    #[serde(default)]
    pub eta: Option<f64>,
}

impl Default for FitOptionsSpec {
    /// Matches the Python `FitOptions()` defaults — `solver="lm"`,
    /// `max_iterations=200`, `tolerance=1e-8`, and `None` for every optional knob.
    /// Future struct literals should use `..Default::default()` so a new field
    /// doesn't ripple through every test fixture and call site.
    fn default() -> Self {
        Self {
            schema_version: None,
            solver: "lm".to_string(),
            max_iterations: 200,
            tolerance: 1e-8,
            delta0: None,
            max_delta: None,
            eta: None,
        }
    }
}

// ---------------------------------------------------------------------------
// Output types
// ---------------------------------------------------------------------------

/// Stable, serialisable reason why the LM solver stopped.
///
/// Replaces `format!("{:?}", report.termination)` so downstream code can
/// match on exact string keys without parsing opaque debug output.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum TerminationReason {
    /// Residuals reached machine precision — cost is effectively zero.
    ResidualsZero,
    /// Gradient became orthogonal to residuals — a local minimum was reached.
    Orthogonal,
    /// Converged within the specified function or parameter tolerance.
    Converged,
    /// Maximum number of iterations reached without meeting convergence criteria.
    MaxIterations,
    /// No improvement possible — Jacobian is singular or near-singular.
    NoImprovementPossible,
    /// Problem has no free parameters.
    NoParameters,
    /// Problem produced no residuals.
    NoResiduals,
    /// Jacobian or residual dimension mismatch.
    WrongDimensions,
    /// Numerical instability (NaN/Inf in residuals or Jacobian).
    NumericalError,
    /// Solver was cancelled from within the problem implementation.
    UserCancelled,
}

impl TerminationReason {
    /// Stable snake_case key for use as the `FitResultSpec.message` field.
    #[must_use]
    pub fn as_str(&self) -> &'static str {
        match self {
            TerminationReason::ResidualsZero => "residuals_zero",
            TerminationReason::Orthogonal => "orthogonal",
            TerminationReason::Converged => "converged",
            TerminationReason::MaxIterations => "max_iterations",
            TerminationReason::NoImprovementPossible => "no_improvement_possible",
            TerminationReason::NoParameters => "no_parameters",
            TerminationReason::NoResiduals => "no_residuals",
            TerminationReason::WrongDimensions => "wrong_dimensions",
            TerminationReason::NumericalError => "numerical_error",
            TerminationReason::UserCancelled => "user_cancelled",
        }
    }

    /// Whether this reason indicates a successful solve.
    #[must_use]
    pub fn was_successful(&self) -> bool {
        matches!(
            self,
            TerminationReason::ResidualsZero
                | TerminationReason::Orthogonal
                | TerminationReason::Converged
        )
    }
}

/// Serialise ±inf → null for result output (used in ParameterResultSpec)
fn ser_opt_bound<S>(value: &Option<f64>, s: S) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    match value {
        Some(v) if v.is_infinite() => s.serialize_none(),
        other => other.serialize(s),
    }
}

/// Per-parameter result including fitted value, standard error, and bounds.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParameterResultSpec {
    /// Fully-qualified parameter key `"node_id.param_name"`.
    pub name: String,
    /// Fitted (or fixed) parameter value.
    pub value: f64,
    #[serde(serialize_with = "ser_opt_bound", default)]
    /// Lower bound used during fitting (`None` → unbounded).
    pub min: Option<f64>,
    #[serde(serialize_with = "ser_opt_bound", default)]
    /// Upper bound used during fitting (`None` → unbounded).
    pub max: Option<f64>,
    /// Whether this parameter was free (`true`) or fixed (`false`).
    pub vary: bool,
    #[serde(default)]
    /// Expression string if this parameter was expression-constrained.
    pub expr: Option<String>,
    #[serde(default)]
    /// Scale hint for display.
    pub scale: Option<f64>,
    #[serde(default)]
    /// 1-σ standard error from the covariance matrix (`None` if unavailable).
    pub stderr: Option<f64>,
}

/// Per-dataset statistics for a multi-dataset fit.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DatasetSliceSpec {
    /// Optional dataset label from `MeasurementSpec`.
    pub label: Option<String>,
    /// Number of data points in this dataset.
    pub n_points: usize,
    /// Best-fit model values at each point.
    pub best_fit: Vec<f64>,
    /// Residuals `y − ŷ` at each point.
    pub residuals: Vec<f64>,
    /// Unweighted χ² for this dataset slice.
    pub chi2: f64,
}

/// Full result from a fit call.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FitResultSpec {
    /// Schema version string (e.g. `"0.1"`).
    pub schema_version: String,
    /// Per-parameter results keyed by `"node_id.param_name"`.
    pub parameters: HashMap<String, ParameterResultSpec>,
    /// Full covariance matrix for the free parameters (row-major, optional).
    pub covariance: Option<Vec<Vec<f64>>>,
    /// Total unweighted χ² = Σ(ŷ − y)².
    pub chi2: f64,
    /// Reduced χ² = χ² / DOF.
    pub reduced_chi2: f64,
    /// Coefficient of determination R² ∈ [−∞, 1].
    pub r_squared: f64,
    /// Degrees of freedom = n_points − n_free.
    pub dof: i64,
    /// Akaike Information Criterion: χ² + 2 · n_free.
    pub aic: f64,
    /// Bayesian Information Criterion: χ² + n_free · ln(n_points).
    pub bic: f64,
    /// Number of function evaluations performed by the solver.
    pub n_iter: u64,
    /// Number of residual function calls (None if not tracked by this solver).
    #[serde(default)]
    pub n_func_evals: Option<u64>,
    /// Number of Jacobian calls (None if not tracked by this solver).
    #[serde(default)]
    pub n_jac_evals: Option<u64>,
    /// Whether the solver reported a successful termination.
    pub success: bool,
    /// Stable termination reason key (e.g. `"converged"`, `"max_iterations"`).
    pub message: String,
    /// Best-fit model values at each data point.
    pub best_fit: Vec<f64>,
    /// Residuals `y − ŷ` at each data point.
    pub residuals: Vec<f64>,
    /// Model values evaluated at the initial parameter guess.
    pub init_fit: Vec<f64>,
    /// Per-node component curves keyed by node id.
    pub components: HashMap<String, Vec<f64>>,
    #[serde(default)]
    /// Per-dataset statistics for multi-dataset fits (`None` for single-dataset).
    pub dataset_slices: Option<Vec<DatasetSliceSpec>>,
    /// Condition number of `JᵀJ` at the solution: ratio of largest to smallest
    /// singular value. Large values (≫ 1) flag an ill-conditioned problem where
    /// parameters are poorly determined. `None` when not computed by the solver
    /// (e.g. singular Hessian, or solvers that do not form `JᵀJ`).
    ///
    /// `#[serde(default)]` keeps old JSON (without this field) deserialising to
    /// `None` for back-compat.
    #[serde(default)]
    pub condition_number: Option<f64>,
    /// Number of differential-evolution generations completed before the LM
    /// refinement on the `solver="global"` path. `None` for direct LM and
    /// other solvers. Surfaces the DE search effort that `n_iter` — which
    /// counts only the post-DE refinement iterations — would otherwise hide
    /// (a global fit can legitimately report `n_iter=0` after DE did the work).
    ///
    /// `#[serde(default)]` keeps old JSON deserialising to `None` for back-compat.
    #[serde(default)]
    pub n_de_generations: Option<u64>,
    /// Per-iteration cost `½‖r‖²` trajectory recorded by the faer LM / trust-region
    /// drivers (index 0 = initial point, last = terminal cost). Empty for solvers
    /// that do not track it (e.g. VarPro, the lm-legacy oracle) — the benchmark
    /// layer reconstructs a labelled proxy in that case.
    ///
    /// Observability only: it does not affect the fit. `#[serde(default)]` keeps
    /// old JSON (without this field) deserialising to an empty vec for back-compat.
    #[serde(default)]
    pub cost_history: Vec<f64>,
    /// Per-iteration gradient infinity-norm `‖Jᵀr‖_∞` recorded alongside each
    /// [`cost_history`](Self::cost_history) entry. Empty when not tracked.
    #[serde(default)]
    pub gradient_norm_history: Vec<f64>,
    /// Per-iteration free-parameter vector `θ` recorded alongside each
    /// [`cost_history`](Self::cost_history) entry (same length and ordering;
    /// the order matches [`covariance_param_order`](Self::covariance_param_order)
    /// when present, else the solver's free-parameter order). This is the raw
    /// material for the convergence-to-truth metric `dₖ = ‖(θₖ − θ_true)/s‖₂` on
    /// synthetic cases. Empty for solvers that do not track it (only the faer LM
    /// driver records it today). Observability only — it does not affect the fit.
    /// `#[serde(default)]` keeps old JSON deserialising to an empty vec.
    #[serde(default)]
    pub params_history: Vec<Vec<f64>>,
    /// Ordered list of free-parameter names that index the rows and columns of
    /// [`covariance`](Self::covariance). `covariance[i][j]` is the covariance
    /// between `covariance_param_order[i]` and `covariance_param_order[j]`.
    ///
    /// This field makes the covariance matrix unambiguously addressable: a
    /// consumer that wants `cov("g.amplitude", "g.sigma")` looks up
    /// `idx_a = covariance_param_order.index("g.amplitude")` and
    /// `idx_s = covariance_param_order.index("g.sigma")`, then reads
    /// `covariance[idx_a][idx_s]`, independent of `HashMap` iteration order.
    ///
    /// `#[serde(default)]` keeps old JSON (without this field) deserialising to
    /// an empty `Vec` for back-compat.
    #[serde(default)]
    pub covariance_param_order: Vec<String>,
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parameter_spec_null_min_max() {
        let json = r#"{"value":1.0,"min":null,"max":null,"vary":true}"#;
        let p: ParameterSpec = serde_json::from_str(json).unwrap();
        assert!(
            p.min.is_infinite() && p.min < 0.0,
            "min should be NEG_INFINITY"
        );
        assert!(p.max.is_infinite() && p.max > 0.0, "max should be INFINITY");
    }

    #[test]
    fn parameter_spec_finite_bounds() {
        let json = r#"{"value":1.0,"min":0.0,"max":10.0,"vary":true}"#;
        let p: ParameterSpec = serde_json::from_str(json).unwrap();
        assert_eq!(p.min, 0.0);
        assert_eq!(p.max, 10.0);
    }

    #[test]
    fn parameter_spec_roundtrip_inf_as_null() {
        let p = ParameterSpec {
            value: 1.0,
            min: f64::NEG_INFINITY,
            max: f64::INFINITY,
            vary: true,
            expr: None,
            scale: None,
        };
        let json = serde_json::to_string(&p).unwrap();
        assert!(
            json.contains("\"min\":null"),
            "min should serialise as null"
        );
        assert!(
            json.contains("\"max\":null"),
            "max should serialise as null"
        );
    }

    #[test]
    fn model_type_str_roundtrip() {
        let json = r#""gaussian""#;
        let mt: ModelTypeStr = serde_json::from_str(json).unwrap();
        assert_eq!(mt, ModelTypeStr::Gaussian);
        let out = serde_json::to_string(&mt).unwrap();
        assert_eq!(out, r#""gaussian""#);
    }

    /// `ModelTypeStr::as_str()` returns the canonical wire-format string and
    /// must agree with serde's serialization for every variant. The two duplicate
    /// `model_type_to_str` match tables in `spectrafit-graph::compiler` and
    /// `spectrafit-varpro::lib` collapse into a single call to this method, so
    /// adding a new variant must update one match arm here (not three across
    /// crates) — and this test catches drift between `as_str` and the serde
    /// rename automatically. Anti-regression for the Vista-platform audit's
    /// "ModelTypeStr drift risk" seam.
    #[test]
    fn model_type_as_str_matches_serde_wire_for_every_variant() {
        // Iterate the single enumeration source generated by `model_manifest!`
        // (`ModelTypeStr::ALL`). There is no hand-maintained variant list here
        // to drift — a new manifest row joins `ALL` automatically, and
        // `VARIANT_COUNT == ALL.len()` by construction.
        for variant in ModelTypeStr::ALL {
            let wire = serde_json::to_string(variant).unwrap();
            let trimmed = wire.trim_matches('"');
            assert_eq!(
                variant.as_str(),
                trimmed,
                "as_str() must equal the serde wire format for {variant:?}",
            );
        }
    }

    #[test]
    fn measurement_input_single() {
        let json = r#"{"x":[[0.0,1.0]],"y":[2.0,3.0]}"#;
        let input: MeasurementInput = serde_json::from_str(json).unwrap();
        let v = input.into_vec();
        assert_eq!(v.len(), 1);
        assert_eq!(v[0].y.len(), 2);
    }

    #[test]
    fn measurement_input_multi() {
        let json = r#"[{"x":[[0.0]],"y":[1.0]},{"x":[[2.0]],"y":[3.0]}]"#;
        let input: MeasurementInput = serde_json::from_str(json).unwrap();
        let v = input.into_vec();
        assert_eq!(v.len(), 2);
    }

    /// Build a minimal, valid `FitResultSpec` for serde tests.
    fn minimal_fit_result(condition_number: Option<f64>) -> FitResultSpec {
        FitResultSpec {
            schema_version: "0.1".into(),
            parameters: HashMap::new(),
            covariance: None,
            chi2: 0.0,
            reduced_chi2: 0.0,
            r_squared: 1.0,
            dof: 1,
            aic: 0.0,
            bic: 0.0,
            n_iter: 0,
            n_func_evals: None,
            n_jac_evals: None,
            success: true,
            message: "converged".into(),
            best_fit: vec![],
            residuals: vec![],
            init_fit: vec![],
            components: HashMap::new(),
            dataset_slices: None,
            condition_number,
            n_de_generations: None,
            cost_history: Vec::new(),
            gradient_norm_history: Vec::new(),
            params_history: Vec::new(),
            covariance_param_order: Vec::new(),
        }
    }

    /// `condition_number` round-trips through JSON when present.
    #[test]
    fn fit_result_condition_number_roundtrip_some() {
        let r = minimal_fit_result(Some(42.5));
        let json = serde_json::to_string(&r).unwrap();
        assert!(
            json.contains("\"condition_number\":42.5"),
            "condition_number should serialise: {json}"
        );
        let back: FitResultSpec = serde_json::from_str(&json).unwrap();
        assert_eq!(back.condition_number, Some(42.5));
    }

    /// Back-compat: JSON without a `condition_number` key deserialises to `None`.
    #[test]
    fn fit_result_condition_number_roundtrip_back_compat() {
        // Serialise a result whose condition_number is None, then strip nothing:
        // a None still emits `"condition_number":null`, so also test legacy JSON
        // that omits the key entirely.
        let r = minimal_fit_result(None);
        let json = serde_json::to_string(&r).unwrap();
        let back: FitResultSpec = serde_json::from_str(&json).unwrap();
        assert_eq!(back.condition_number, None);

        // Legacy JSON produced before the field existed: key absent entirely.
        let legacy = r#"{
            "schema_version":"0.1","parameters":{},"covariance":null,
            "chi2":0.0,"reduced_chi2":0.0,"r_squared":1.0,"dof":1,
            "aic":0.0,"bic":0.0,"n_iter":0,"success":true,"message":"converged",
            "best_fit":[],"residuals":[],"init_fit":[],"components":{}
        }"#;
        let back_legacy: FitResultSpec = serde_json::from_str(legacy).unwrap();
        assert_eq!(
            back_legacy.condition_number, None,
            "legacy JSON without the field must default to None"
        );
        assert!(
            back_legacy.covariance_param_order.is_empty(),
            "legacy JSON without covariance_param_order must default to empty vec"
        );
    }

    /// `covariance_param_order` is populated in current JSON and round-trips.
    #[test]
    fn fit_result_covariance_param_order_roundtrip() {
        let mut r = minimal_fit_result(None);
        r.covariance_param_order = vec!["g.amplitude".into(), "g.sigma".into()];
        let json = serde_json::to_string(&r).unwrap();
        assert!(
            json.contains("\"covariance_param_order\":[\"g.amplitude\",\"g.sigma\"]"),
            "covariance_param_order should serialise as ordered array: {json}"
        );
        let back: FitResultSpec = serde_json::from_str(&json).unwrap();
        assert_eq!(back.covariance_param_order, vec!["g.amplitude", "g.sigma"]);
    }
}
