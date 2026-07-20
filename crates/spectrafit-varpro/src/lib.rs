//! Variable Projection (VarPro) solver path for separable nonlinear models.
#![warn(missing_docs)]
//!
//! A graph is **separable** when every model node has exactly one linear
//! parameter (`amplitude`) and the remaining parameters are nonlinear shape
//! parameters.  Examples: Gaussian, Lorentzian, Voigt, step functions, Fano.
//!
//! For such graphs varpro eliminates the linear amplitude dimensions from the
//! optimisation, reducing it to a pure nonlinear problem over the shape params.
//! This gives faster convergence and better numerical conditioning vs vanilla LM.
//!
//! # Bounds
//! varpro has no native bounds support.  When any nonlinear parameter has finite
//! bounds **and** `options.solver == "varpro"`, we fall back to LM and log a
//! warning.  With `options.solver == "auto"` we transparently fall back.

pub mod model;
pub mod solver;

pub use solver::solve_varpro;

use spectrafit_types::FitGraphSpec;

/// Set of model types whose `amplitude` is the single linear coefficient.
///
/// Polynomial models (`constant`, `linear`) are excluded because they have no
/// nonlinear parameters at all, so they contribute *invariant* basis functions
/// (no gain from VarPro).  Mixed graphs (e.g. Gaussian + constant) are
/// supported via invariant basis functions; see [`model::GraphSeparableModel`].
const SEPARABLE_MODEL_TYPES: &[&str] = &[
    "gaussian",
    "lorentzian",
    "voigt",
    "arctan_step",
    "tanh_step",
    "erfc_step",
    "pseudo_voigt",
    "fano",
];

/// Invariant (purely linear) model types — contribute a basis function that
/// does not depend on any nonlinear parameter.
const INVARIANT_MODEL_TYPES: &[&str] = &["constant", "linear"];

/// Returns `true` when every node in the graph is either separable (has an
/// `amplitude` linear param + nonlinear shape params) or invariant (all params
/// linear).  Returns `false` for unknown or non-conforming node types.
///
/// The wire-format string for each `ModelTypeStr` is read from the canonical
/// `ModelTypeStr::as_str()` in `spectrafit-types`; VarPro separability is then
/// a membership check against [`SEPARABLE_MODEL_TYPES`] /
/// [`INVARIANT_MODEL_TYPES`]. Non-separable variants (true Voigt, skewed
/// Gaussian, EMG, log-normal, Pearson VII, Tauc, Cauchy, KWW, …) fall through
/// here untouched — they are simply absent from `SEPARABLE_MODEL_TYPES`, so
/// callers see them as non-VarPro candidates and route to the general solver.
pub fn is_separable(graph: &FitGraphSpec) -> bool {
    for node in &graph.nodes {
        let type_str = node.model_type.as_str();
        if !SEPARABLE_MODEL_TYPES.contains(&type_str) && !INVARIANT_MODEL_TYPES.contains(&type_str)
        {
            return false;
        }
    }
    true
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use spectrafit_types::{FitGraphSpec, ModelNodeSpec, ModelTypeStr, ParameterSpec};
    use std::collections::HashMap;

    // ── Helpers ──────────────────────────────────────────────────────────────

    fn make_param(value: f64, vary: bool) -> ParameterSpec {
        ParameterSpec {
            value,
            min: f64::NEG_INFINITY,
            max: f64::INFINITY,
            vary,
            expr: None,
            scale: None,
        }
    }

    /// Build a minimal single-node FitGraphSpec.
    fn single_node_graph(model_type: ModelTypeStr) -> FitGraphSpec {
        let mut parameters = HashMap::new();
        match &model_type {
            ModelTypeStr::Gaussian => {
                parameters.insert("amplitude".into(), make_param(1.0, true));
                parameters.insert("center".into(), make_param(0.0, true));
                parameters.insert("sigma".into(), make_param(1.0, true));
            }
            ModelTypeStr::Constant => {
                parameters.insert("amplitude".into(), make_param(0.0, true));
            }
            ModelTypeStr::TrueVoigt => {
                parameters.insert("amplitude".into(), make_param(1.0, true));
                parameters.insert("center".into(), make_param(0.0, true));
                parameters.insert("sigma".into(), make_param(1.0, true));
                parameters.insert("gamma".into(), make_param(1.0, true));
            }
            _ => {
                parameters.insert("amplitude".into(), make_param(1.0, true));
            }
        }
        FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![ModelNodeSpec {
                id: "n0".into(),
                model_type,
                parameters,
                dataset_index: None,
            }],
            expr_edges: vec![],
        }
    }

    // ── R1a: is_separable returns true for a pure-Gaussian graph ─────────────

    #[test]
    fn is_separable_true_for_gaussian() {
        let graph = single_node_graph(ModelTypeStr::Gaussian);
        assert!(
            is_separable(&graph),
            "A pure-Gaussian graph must be separable"
        );
    }

    // ── R1a variant: all SEPARABLE_MODEL_TYPES return true ───────────────────

    #[test]
    fn is_separable_true_for_all_declared_separable_types() {
        for &type_str in SEPARABLE_MODEL_TYPES {
            // Reconstruct a graph from the wire string via the ModelTypeStr list.
            // We use serde_json to deserialise so we don't need to enumerate manually.
            let json = format!("\"{}\"", type_str);
            let model_type: ModelTypeStr = serde_json::from_str(&json).unwrap_or_else(|_| {
                panic!("Could not deserialise ModelTypeStr from SEPARABLE_MODEL_TYPES entry: {type_str}")
            });
            let graph = single_node_graph(model_type);
            assert!(
                is_separable(&graph),
                "is_separable should return true for SEPARABLE_MODEL_TYPES entry: {type_str}"
            );
        }
    }

    // ── R1b: is_separable returns false for a non-separable model ────────────

    #[test]
    fn is_separable_false_for_true_voigt() {
        let graph = single_node_graph(ModelTypeStr::TrueVoigt);
        assert!(
            !is_separable(&graph),
            "true_voigt is not in SEPARABLE_MODEL_TYPES and must return false"
        );
    }

    // ── R1b variant: INVARIANT_MODEL_TYPES are separable ─────────────────────

    #[test]
    fn is_separable_true_for_invariant_types() {
        for &type_str in INVARIANT_MODEL_TYPES {
            let json = format!("\"{}\"", type_str);
            let model_type: ModelTypeStr = serde_json::from_str(&json).unwrap_or_else(|_| {
                panic!("Could not deserialise ModelTypeStr from INVARIANT_MODEL_TYPES entry: {type_str}")
            });
            let graph = single_node_graph(model_type);
            assert!(
                is_separable(&graph),
                "is_separable should return true for INVARIANT_MODEL_TYPES entry: {type_str}"
            );
        }
    }

    // ── R1b variant: mixed separable+non-separable graph is non-separable ────

    #[test]
    fn is_separable_false_for_mixed_graph() {
        let mut graph = single_node_graph(ModelTypeStr::Gaussian);
        // Append a true_voigt node to make it non-separable
        let mut params = HashMap::new();
        params.insert("amplitude".into(), make_param(1.0, true));
        params.insert("center".into(), make_param(0.0, true));
        params.insert("sigma".into(), make_param(1.0, true));
        params.insert("gamma".into(), make_param(1.0, true));
        graph.nodes.push(ModelNodeSpec {
            id: "tv0".into(),
            model_type: ModelTypeStr::TrueVoigt,
            parameters: params,
            dataset_index: None,
        });
        assert!(
            !is_separable(&graph),
            "A graph containing true_voigt must not be separable"
        );
    }

    // ── R2: every ModelTypeStr variant is classified in one of three buckets ─
    //
    // This test enumerates ALL ModelTypeStr variants exhaustively and asserts
    // each is either in SEPARABLE_MODEL_TYPES, in INVARIANT_MODEL_TYPES, or
    // explicitly in the NON_VARPRO allow-list below.  Any newly-added variant
    // that is not placed in one of the three buckets fails the test, preventing
    // silent VarPro-miss (the model would forever be routed to the general solver
    // without the developer noticing).
    //
    // Mirror of `model_type_as_str_matches_serde_wire_for_every_variant` in
    // spectrafit-types (which tests the serde↔as_str parity); this test adds
    // the VarPro-eligibility layer.
    #[test]
    fn model_type_str_varpro_parity_guard() {
        // Variants that are intentionally absent from SEPARABLE/INVARIANT lists.
        // Each exclusion must be explained.
        //
        // Non-VarPro: these models cannot be expressed as amplitude × shape(α)
        // because their formulas are non-separable (multiple amplitude-like roles,
        // asymmetric integrals, etc.), or they live in multi-dimensional space.
        let non_varpro: &[&str] = &[
            // --- N-D kernels: no 1-D VarPro basis-column concept applies ----------
            "gaussian2d",
            "gaussian_nd", // parametric N-D Gaussian; multi-dimensional, like gaussian2d
            // --- Quadratic has no amplitude as a pure linear scaler ---------------
            "quadratic",
            // --- Non-separable asymmetric/complex lineshapes ----------------------
            "double_exponential", // two amplitudes, not one linear coefficient
            "true_voigt",         // Faddeeva convolution — not A × f(σ,γ,x)
            "skewed_gaussian",    // error-function modulated; asymmetric shape
            "exp_gaussian",       // exponentially-modified Gaussian; EMG tail integral
            "doniach_sunjic",     // XPS asymmetric; power-law tail, not separable
            "log_normal",         // domain-restricted (x>0); shape not amplitude-linear
            "pearson7",           // exponent `m` couples with amplitude
            "split_gaussian",     // two sigmas; shape not uniform across center
            "moffat",             // beta exponent couples with amplitude
            "students_t",         // nu exponent couples with amplitude
            "split_pearson7",     // split variant; two exponents, two sigmas
            "breit_wigner",       // complex resonance; not separable
            "asym_ir",            // logistic sigmoid modulation; not amplitude-linear
            "harmonic_ir",        // driven oscillator; amplitude couples with damping
            "tauc",               // power-law edge; exponent makes it non-separable
            "cauchy_dispersion",  // multi-coefficient refractive-index; not one amplitude
            "kww",                // stretched-exponential; beta exponent non-separable
            // --- Separable-ELIGIBLE but not (yet) VarPro-enrolled -----------------
            // These four have `amplitude` as a single linear scaler × shape(α), so
            // they COULD join SEPARABLE_MODEL_TYPES. They are intentionally left on
            // the general-LM path for now: enrolling them flips solver routing and
            // shifts benchmark numbers, so it is a deliberate, benchmarked change —
            // not a guard-coverage fix. Listed here (honestly: deferred, not
            // "non-separable") so the parity guard covers all VARIANT_COUNT variants.
            "saturating_exponential", // BoxBOD: amplitude·(1−exp(−rate·x)) — eligible, deferred
            "power_saturation",       // Misra1b: amplitude·(1−(1+rate·x/2)^−2) — eligible, deferred
            "power_law_offset", // Bennett5: amplitude·(offset+x)^(−1/shape) — eligible, deferred
            "mgh09_rational",   // MGH09: amplitude·rational(x;α) — eligible, deferred
        ];

        // Iterate the manifest source of truth directly — `ModelTypeStr::ALL`
        // (generated by `model_manifest!` in spectrafit-types). There is no
        // hand-maintained variant list here to drift: a new manifest row is
        // automatically classified-or-fails below, which is the exact silent
        // drift this guard exists to prevent (it itself once suffered it —
        // 4 NIST kernels went unchecked behind a stale hand-list).
        for variant in ModelTypeStr::ALL {
            let wire = variant.as_str();
            let in_separable = SEPARABLE_MODEL_TYPES.contains(&wire);
            let in_invariant = INVARIANT_MODEL_TYPES.contains(&wire);
            let in_non_varpro = non_varpro.contains(&wire);

            assert!(
                in_separable || in_invariant || in_non_varpro,
                "ModelTypeStr variant {:?} (wire=\"{}\") is not classified in \
                SEPARABLE_MODEL_TYPES, INVARIANT_MODEL_TYPES, or the NON_VARPRO \
                allow-list. Add it to one of the three buckets and explain why.",
                variant,
                wire
            );

            // Mutual exclusion: a variant must not appear in two buckets.
            let bucket_count = [in_separable, in_invariant, in_non_varpro]
                .iter()
                .filter(|&&b| b)
                .count();
            assert_eq!(
                bucket_count, 1,
                "ModelTypeStr variant {:?} (wire=\"{}\") appears in more than one \
                classification bucket (separable={}, invariant={}, non_varpro={}). \
                Each variant must belong to exactly one bucket.",
                variant, wire, in_separable, in_invariant, in_non_varpro
            );
        }
    }
}
