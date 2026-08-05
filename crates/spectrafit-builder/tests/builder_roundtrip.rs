//! Roundtrip test: every builder method emits JSON structurally identical to a
//! hand-written `FitGraphSpec` literal.
//!
//! We compare via `serde_json::Value` (not raw strings) because
//! `ModelNodeSpec.parameters` is a `HashMap<String, ParameterSpec>` whose
//! serialised key order is process-randomised; `Value` equality compares object
//! contents, which is the property we actually care about. The byte-identical
//! intent of the contract is preserved at the value level: every key, every
//! number, every nesting matches exactly.

use std::collections::HashMap;

use approx::assert_relative_eq;
use serde_json::Value;
use spectrafit_builder::{FitGraphBuilder, SCHEMA_VERSION};
use spectrafit_types::types::{ExprEdge, FitGraphSpec, ModelNodeSpec, ModelTypeStr, ParameterSpec};

/// Convenience: unbounded, varying parameter — the default the builder writes.
fn p(value: f64) -> ParameterSpec {
    ParameterSpec {
        value,
        min: f64::NEG_INFINITY,
        max: f64::INFINITY,
        vary: true,
        expr: None,
        scale: None,
    }
}

/// Build a hand-written `FitGraphSpec` containing a single node.
fn hand_spec(id: &str, model_type: ModelTypeStr, params: &[(&str, f64)]) -> FitGraphSpec {
    let mut map = HashMap::new();
    for (name, value) in params {
        map.insert((*name).to_string(), p(*value));
    }
    FitGraphSpec {
        schema_version: SCHEMA_VERSION.to_string(),
        nodes: vec![ModelNodeSpec {
            id: id.to_string(),
            model_type,
            parameters: map,
            dataset_index: None,
        }],
        expr_edges: Vec::new(),
    }
}

/// Assert the two specs serialise to JSON-equivalent values.
#[track_caller]
fn assert_specs_equivalent(built: &FitGraphSpec, handwritten: &FitGraphSpec) {
    let v_built: Value = serde_json::to_value(built).expect("built spec serialises");
    let v_hand: Value = serde_json::to_value(handwritten).expect("hand spec serialises");
    assert_eq!(
        v_built, v_hand,
        "builder JSON does not match hand-written literal:\nbuilt = {v_built:#}\nhand  = {v_hand:#}",
    );
}

// ---------------------------------------------------------------------------
// One test per kernel — every variant must roundtrip.
// ---------------------------------------------------------------------------

#[test]
fn roundtrip_gaussian() {
    let built = FitGraphBuilder::new()
        .add_gaussian("g0", 1.5, 0.25, 0.8)
        .build();
    let hand = hand_spec(
        "g0",
        ModelTypeStr::Gaussian,
        &[("amplitude", 1.5), ("center", 0.25), ("sigma", 0.8)],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_gaussian2d() {
    let built = FitGraphBuilder::new()
        .add_gaussian2d("g2d", 2.0, 0.1, -0.4, 0.7, 0.9)
        .build();
    let hand = hand_spec(
        "g2d",
        ModelTypeStr::Gaussian2D,
        &[
            ("amplitude", 2.0),
            ("center_x", 0.1),
            ("center_y", -0.4),
            ("sigma_x", 0.7),
            ("sigma_y", 0.9),
        ],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_gaussian_nd() {
    // The fluent helper adds the 1-D instance (amplitude, center_0, sigma_0);
    // the compiler infers higher D from the indexed center_<i> params.
    let built = FitGraphBuilder::new()
        .add_gaussian_nd("gnd", 2.0, 0.1, 0.7)
        .build();
    let hand = hand_spec(
        "gnd",
        ModelTypeStr::GaussianNd,
        &[("amplitude", 2.0), ("center_0", 0.1), ("sigma_0", 0.7)],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_lorentzian() {
    let built = FitGraphBuilder::new()
        .add_lorentzian("l0", 3.0, 1.0, 0.5)
        .build();
    let hand = hand_spec(
        "l0",
        ModelTypeStr::Lorentzian,
        &[("amplitude", 3.0), ("center", 1.0), ("sigma", 0.5)],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_voigt() {
    // The `voigt` wire key is the pseudo-Voigt linear mixture; fourth param
    // is `fraction`, not `gamma` — pinned here so a future rename catches.
    let built = FitGraphBuilder::new()
        .add_voigt("v0", 2.5, 0.0, 0.6, 0.3)
        .build();
    let hand = hand_spec(
        "v0",
        ModelTypeStr::Voigt,
        &[
            ("amplitude", 2.5),
            ("center", 0.0),
            ("sigma", 0.6),
            ("fraction", 0.3),
        ],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_constant() {
    let built = FitGraphBuilder::new().add_constant("c0", 0.42).build();
    let hand = hand_spec("c0", ModelTypeStr::Constant, &[("c", 0.42)]);
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_linear() {
    let built = FitGraphBuilder::new().add_linear("lin", 1.1, -0.3).build();
    let hand = hand_spec(
        "lin",
        ModelTypeStr::Linear,
        &[("slope", 1.1), ("intercept", -0.3)],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_quadratic() {
    let built = FitGraphBuilder::new()
        .add_quadratic("q0", 0.5, 0.0, 0.1)
        .build();
    let hand = hand_spec(
        "q0",
        ModelTypeStr::Quadratic,
        &[("amplitude", 0.5), ("center", 0.0), ("offset", 0.1)],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_arctan_step() {
    let built = FitGraphBuilder::new()
        .add_arctan_step("s", 1.0, 0.0, 0.5)
        .build();
    let hand = hand_spec(
        "s",
        ModelTypeStr::ArctanStep,
        &[("amplitude", 1.0), ("center", 0.0), ("sigma", 0.5)],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_tanh_step() {
    let built = FitGraphBuilder::new()
        .add_tanh_step("s", 1.0, 0.0, 0.5)
        .build();
    let hand = hand_spec(
        "s",
        ModelTypeStr::TanhStep,
        &[("amplitude", 1.0), ("center", 0.0), ("sigma", 0.5)],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_erfc_step() {
    let built = FitGraphBuilder::new()
        .add_erfc_step("s", 1.0, 0.0, 0.5)
        .build();
    let hand = hand_spec(
        "s",
        ModelTypeStr::ErfcStep,
        &[("amplitude", 1.0), ("center", 0.0), ("sigma", 0.5)],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_pseudo_voigt() {
    let built = FitGraphBuilder::new()
        .add_pseudo_voigt("pv", 2.0, 0.1, 0.5, 0.25)
        .build();
    let hand = hand_spec(
        "pv",
        ModelTypeStr::PseudoVoigt,
        &[
            ("amplitude", 2.0),
            ("center", 0.1),
            ("sigma", 0.5),
            ("fraction", 0.25),
        ],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_fano() {
    let built = FitGraphBuilder::new()
        .add_fano("f0", 1.0, 0.5, 0.1, 2.0)
        .build();
    let hand = hand_spec(
        "f0",
        ModelTypeStr::Fano,
        &[
            ("amplitude", 1.0),
            ("center", 0.5),
            ("gamma", 0.1),
            ("q", 2.0),
        ],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_double_exponential() {
    let built = FitGraphBuilder::new()
        .add_double_exponential("de", 1.0, 0.5, 0.3, 0.05)
        .build();
    let hand = hand_spec(
        "de",
        ModelTypeStr::DoubleExponential,
        &[("A1", 1.0), ("lam1", 0.5), ("A2", 0.3), ("lam2", 0.05)],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_saturating_exponential() {
    let built = FitGraphBuilder::new()
        .add_saturating_exponential("se", 1.0, 0.5)
        .build();
    let hand = hand_spec(
        "se",
        ModelTypeStr::SaturatingExponential,
        &[("amplitude", 1.0), ("rate", 0.5)],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_true_voigt() {
    let built = FitGraphBuilder::new()
        .add_true_voigt("tv", 1.0, 0.0, 0.5, 0.3)
        .build();
    let hand = hand_spec(
        "tv",
        ModelTypeStr::TrueVoigt,
        &[
            ("amplitude", 1.0),
            ("center", 0.0),
            ("sigma", 0.5),
            ("gamma", 0.3),
        ],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_skewed_gaussian() {
    let built = FitGraphBuilder::new()
        .add_skewed_gaussian("sg", 1.0, 0.0, 0.5, 1.5)
        .build();
    let hand = hand_spec(
        "sg",
        ModelTypeStr::SkewedGaussian,
        &[
            ("amplitude", 1.0),
            ("center", 0.0),
            ("sigma", 0.5),
            ("gamma", 1.5),
        ],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_exp_gaussian() {
    let built = FitGraphBuilder::new()
        .add_exp_gaussian("emg", 1.0, 0.0, 0.5, 0.2)
        .build();
    let hand = hand_spec(
        "emg",
        ModelTypeStr::ExpGaussian,
        &[
            ("amplitude", 1.0),
            ("center", 0.0),
            ("sigma", 0.5),
            ("gamma", 0.2),
        ],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_doniach_sunjic() {
    let built = FitGraphBuilder::new()
        .add_doniach_sunjic("ds", 1.0, 0.0, 0.5, 0.1)
        .build();
    let hand = hand_spec(
        "ds",
        ModelTypeStr::DoniachSunjic,
        &[
            ("amplitude", 1.0),
            ("center", 0.0),
            ("sigma", 0.5),
            ("gamma", 0.1),
        ],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_log_normal() {
    let built = FitGraphBuilder::new()
        .add_log_normal("ln0", 1.0, 1.0, 0.3)
        .build();
    let hand = hand_spec(
        "ln0",
        ModelTypeStr::LogNormal,
        &[("amplitude", 1.0), ("center", 1.0), ("sigma", 0.3)],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_pearson7() {
    let built = FitGraphBuilder::new()
        .add_pearson7("p7", 1.0, 0.0, 0.5, 2.0)
        .build();
    let hand = hand_spec(
        "p7",
        ModelTypeStr::Pearson7,
        &[
            ("amplitude", 1.0),
            ("center", 0.0),
            ("sigma", 0.5),
            ("m", 2.0),
        ],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_split_gaussian() {
    let built = FitGraphBuilder::new()
        .add_split_gaussian("sg", 1.0, 0.0, 0.3, 0.5)
        .build();
    let hand = hand_spec(
        "sg",
        ModelTypeStr::SplitGaussian,
        &[
            ("amplitude", 1.0),
            ("center", 0.0),
            ("sigma_l", 0.3),
            ("sigma_r", 0.5),
        ],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_moffat() {
    let built = FitGraphBuilder::new()
        .add_moffat("m0", 1.0, 0.0, 0.5, 2.5)
        .build();
    let hand = hand_spec(
        "m0",
        ModelTypeStr::Moffat,
        &[
            ("amplitude", 1.0),
            ("center", 0.0),
            ("sigma", 0.5),
            ("beta", 2.5),
        ],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_students_t() {
    let built = FitGraphBuilder::new()
        .add_students_t("st", 1.0, 0.0, 0.5, 4.0)
        .build();
    let hand = hand_spec(
        "st",
        ModelTypeStr::StudentsT,
        &[
            ("amplitude", 1.0),
            ("center", 0.0),
            ("sigma", 0.5),
            ("nu", 4.0),
        ],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_split_pearson7() {
    let built = FitGraphBuilder::new()
        .add_split_pearson7("sp7", 1.0, 0.0, 0.3, 0.5, 2.0, 3.0)
        .build();
    let hand = hand_spec(
        "sp7",
        ModelTypeStr::SplitPearson7,
        &[
            ("amplitude", 1.0),
            ("center", 0.0),
            ("sigma_l", 0.3),
            ("sigma_r", 0.5),
            ("m_l", 2.0),
            ("m_r", 3.0),
        ],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_breit_wigner() {
    let built = FitGraphBuilder::new()
        .add_breit_wigner("bw", 1.0, 0.0, 0.5, 2.0)
        .build();
    let hand = hand_spec(
        "bw",
        ModelTypeStr::BreitWigner,
        &[
            ("amplitude", 1.0),
            ("center", 0.0),
            ("sigma", 0.5),
            ("q", 2.0),
        ],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_asym_ir() {
    let built = FitGraphBuilder::new()
        .add_asym_ir("ai", 1.0, 0.0, 0.5, 1.2)
        .build();
    let hand = hand_spec(
        "ai",
        ModelTypeStr::AsymIr,
        &[
            ("amplitude", 1.0),
            ("center", 0.0),
            ("sigma", 0.5),
            ("k", 1.2),
        ],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_harmonic_ir() {
    let built = FitGraphBuilder::new()
        .add_harmonic_ir("hir", 1.0, 0.0, 0.5)
        .build();
    let hand = hand_spec(
        "hir",
        ModelTypeStr::HarmonicIr,
        &[("amplitude", 1.0), ("center", 0.0), ("sigma", 0.5)],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_tauc() {
    let built = FitGraphBuilder::new().add_tauc("tc", 1.0, 1.5, 0.5).build();
    let hand = hand_spec(
        "tc",
        ModelTypeStr::Tauc,
        &[("amplitude", 1.0), ("e_gap", 1.5), ("exponent", 0.5)],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_cauchy_dispersion() {
    let built = FitGraphBuilder::new()
        .add_cauchy_dispersion("cd", 1.4, 0.01, 1e-4)
        .build();
    let hand = hand_spec(
        "cd",
        ModelTypeStr::CauchyDispersion,
        &[("a", 1.4), ("b", 0.01), ("c", 1e-4)],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_kww() {
    let built = FitGraphBuilder::new().add_kww("kww", 1.0, 0.5, 0.7).build();
    let hand = hand_spec(
        "kww",
        ModelTypeStr::Kww,
        &[("amplitude", 1.0), ("tau", 0.5), ("beta", 0.7)],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_power_saturation() {
    let built = FitGraphBuilder::new()
        .add_power_saturation("ps", 338.0, 3.9e-4)
        .build();
    let hand = hand_spec(
        "ps",
        ModelTypeStr::PowerSaturation,
        &[("amplitude", 338.0), ("rate", 3.9e-4)],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_power_law_offset() {
    let built = FitGraphBuilder::new()
        .add_power_law_offset("b5", -2523.5, 46.74, 0.9322)
        .build();
    let hand = hand_spec(
        "b5",
        ModelTypeStr::PowerLawOffset,
        &[("amplitude", -2523.5), ("offset", 46.74), ("shape", 0.9322)],
    );
    assert_specs_equivalent(&built, &hand);
}

#[test]
fn roundtrip_mgh09_rational() {
    // MGH09 certified parameters (Kowalik–Osborne rational function)
    let built = FitGraphBuilder::new()
        .add_mgh09_rational(
            "mgh09",
            1.9280693458e-01,
            1.9128232873e-01,
            1.2305650693e-01,
            1.3606233068e-01,
        )
        .build();
    let hand = hand_spec(
        "mgh09",
        ModelTypeStr::Mgh09Rational,
        &[
            ("amplitude", 1.9280693458e-01),
            ("num_lin", 1.9128232873e-01),
            ("den_lin", 1.2305650693e-01),
            ("den_const", 1.3606233068e-01),
        ],
    );
    assert_specs_equivalent(&built, &hand);
}

// ---------------------------------------------------------------------------
// Cross-cutting tests: chaining, tie edges, available_models parity.
// ---------------------------------------------------------------------------

#[test]
fn chained_multi_node_roundtrip() {
    // A more realistic two-peak + linear baseline graph with a parameter tie.
    let built = FitGraphBuilder::new()
        .add_gaussian("g0", 1.0, 0.0, 0.5)
        .add_lorentzian("l0", 0.8, 1.0, 0.4)
        .add_linear("bg", 0.0, 0.1)
        .tie("l0", "center", "g0.center + 1.0")
        .build();

    let hand = FitGraphSpec {
        schema_version: SCHEMA_VERSION.to_string(),
        nodes: vec![
            ModelNodeSpec {
                id: "g0".to_string(),
                model_type: ModelTypeStr::Gaussian,
                parameters: {
                    let mut m = HashMap::new();
                    m.insert("amplitude".into(), p(1.0));
                    m.insert("center".into(), p(0.0));
                    m.insert("sigma".into(), p(0.5));
                    m
                },
                dataset_index: None,
            },
            ModelNodeSpec {
                id: "l0".to_string(),
                model_type: ModelTypeStr::Lorentzian,
                parameters: {
                    let mut m = HashMap::new();
                    m.insert("amplitude".into(), p(0.8));
                    m.insert("center".into(), p(1.0));
                    m.insert("sigma".into(), p(0.4));
                    m
                },
                dataset_index: None,
            },
            ModelNodeSpec {
                id: "bg".to_string(),
                model_type: ModelTypeStr::Linear,
                parameters: one_param_linear(0.0, 0.1),
                dataset_index: None,
            },
        ],
        expr_edges: vec![ExprEdge {
            target_node: "l0".to_string(),
            target_param: "center".to_string(),
            expression: "g0.center + 1.0".to_string(),
        }],
    };

    assert_specs_equivalent(&built, &hand);

    // Sanity-check the tie made it through.
    assert_eq!(built.expr_edges.len(), 1);
    assert_eq!(built.expr_edges[0].target_node, "l0");
    assert_eq!(built.expr_edges[0].expression, "g0.center + 1.0");
}

fn one_param_linear(slope: f64, intercept: f64) -> HashMap<String, ParameterSpec> {
    let mut m = HashMap::new();
    m.insert("slope".into(), p(slope));
    m.insert("intercept".into(), p(intercept));
    m
}

/// `available_models()` must contain the wire-format string for every
/// `ModelTypeStr` variant — same exhaustive list as the
/// `model_type_as_str_matches_serde_wire_for_every_variant` parity test in
/// `spectrafit-types`. Adding a variant without listing it here is a deliberate
/// failure.
#[test]
fn available_models_matches_modeltypestr_parity_list() {
    let expected: Vec<&'static str> = [
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
    ]
    .iter()
    .map(|m| m.as_str())
    .collect();

    let actual = FitGraphBuilder::available_models();
    assert_eq!(
        actual, expected,
        "FitGraphBuilder::available_models() drifted from the ModelTypeStr parity list",
    );
}

/// Belt-and-braces: numeric values stay exactly equal through the builder
/// (no FP rounding). Uses `approx::assert_relative_eq!` per house style.
#[test]
fn builder_preserves_float_values_exactly() {
    let v = 1.234_567_890_123_456_7_f64;
    let spec = FitGraphBuilder::new().add_constant("c", v).build();
    let actual = spec.nodes[0]
        .parameters
        .get("c")
        .expect("c parameter present")
        .value;
    assert_relative_eq!(actual, v, max_relative = 0.0);
}
