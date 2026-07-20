//! spectrafit-graph — DAG compilation and evaluation engine (Phase 4)
#![warn(missing_docs)]
//!
//! Exposes three top-level functions consumed by the solver and pyo3 bindings:
//!   - [`evaluate`]            — sum of all node contributions at given x-points
//!   - [`evaluate_components`] — per-node contributions
//!   - [`jacobian`]            — full analytical Jacobian matrix \[n_points × n_free_params\]

pub mod compiler;
pub mod error;
pub mod executor;
pub mod expr;

pub use error::GraphError;

use std::collections::HashMap;

use nalgebra::DMatrix;
use spectrafit_types::{CoreError, FitGraphSpec};

pub use executor::{
    evaluate_compiled, evaluate_compiled_indexed, evaluate_components_compiled, jacobian_compiled,
    jacobian_compiled_indexed,
};
pub use expr::{parse as parse_expr, BinOp, Expr, TiedParam, TiedPlan};

/// Evaluate the model sum across all nodes at the given x-points.
///
/// `params_flat` keys follow the `"node_id.param_name"` convention.
pub fn evaluate(
    graph: &FitGraphSpec,
    params_flat: &HashMap<String, f64>,
    x: &[f64],
) -> Result<Vec<f64>, CoreError> {
    let cg = compiler::CompiledGraph::compile(graph)?;
    executor::evaluate_compiled(&cg, params_flat, x)
}

/// Evaluate each node independently.
///
/// Returns a map `{ "node_id" => Vec<f64> }`.
pub fn evaluate_components(
    graph: &FitGraphSpec,
    params_flat: &HashMap<String, f64>,
    x: &[f64],
) -> Result<HashMap<String, Vec<f64>>, CoreError> {
    let cg = compiler::CompiledGraph::compile(graph)?;
    executor::evaluate_components_compiled(&cg, params_flat, x)
}

/// Compute the full analytical Jacobian matrix for use by the solver.
///
/// Returns a matrix of shape `[n_points × n_free_params]`.
///
/// Free parameters are ordered by (node_id alphabetically, then param order
/// as declared by the model's `param_names()`).
pub fn jacobian(
    graph: &FitGraphSpec,
    params_flat: &HashMap<String, f64>,
    x: &[f64],
) -> Result<DMatrix<f64>, CoreError> {
    let cg = compiler::CompiledGraph::compile(graph)?;
    executor::jacobian_compiled(&cg, params_flat, x)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;
    use spectrafit_types::{FitGraphSpec, ModelNodeSpec, ModelTypeStr, ParameterSpec};

    /// Build a minimal `ParameterSpec` with `vary = true`.
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

    /// Convenience: build `params_flat` from a list of `("node.param", value)` pairs.
    fn flat(pairs: &[(&str, f64)]) -> HashMap<String, f64> {
        pairs.iter().map(|(k, v)| (k.to_string(), *v)).collect()
    }

    /// Build a single-Gaussian `FitGraphSpec`.
    fn single_gaussian_graph() -> (FitGraphSpec, HashMap<String, f64>) {
        let mut params = HashMap::new();
        params.insert("amplitude".to_string(), make_param(3.0, true));
        params.insert("center".to_string(), make_param(0.0, true));
        params.insert("sigma".to_string(), make_param(1.0, true));

        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![ModelNodeSpec {
                id: "g1".to_string(),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: None,
                parameters: params,
            }],
            expr_edges: vec![],
        };
        let pf = flat(&[("g1.amplitude", 3.0), ("g1.center", 0.0), ("g1.sigma", 1.0)]);
        (graph, pf)
    }

    // -----------------------------------------------------------------------
    // Test 1: single Gaussian — evaluate at center returns amplitude
    // -----------------------------------------------------------------------
    #[test]
    fn test_single_gaussian_at_center() {
        let (graph, pf) = single_gaussian_graph();
        let result = evaluate(&graph, &pf, &[0.0]).unwrap();
        assert_eq!(result.len(), 1);
        // At x=center the Gaussian equals amplitude (exp(0)=1).
        assert_relative_eq!(result[0], 3.0, epsilon = 1e-12);
    }

    // -----------------------------------------------------------------------
    // Test 2: two-node sum — Gaussian + Constant
    // -----------------------------------------------------------------------
    #[test]
    fn test_two_node_sum_gaussian_constant() {
        let mut g_params = HashMap::new();
        g_params.insert("amplitude".to_string(), make_param(2.0, true));
        g_params.insert("center".to_string(), make_param(0.0, true));
        g_params.insert("sigma".to_string(), make_param(1.0, true));

        let mut c_params = HashMap::new();
        c_params.insert("c".to_string(), make_param(5.0, true));

        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![
                ModelNodeSpec {
                    id: "g1".to_string(),
                    model_type: ModelTypeStr::Gaussian,
                    dataset_index: None,
                    parameters: g_params,
                },
                ModelNodeSpec {
                    id: "bg".to_string(),
                    model_type: ModelTypeStr::Constant,
                    dataset_index: None,
                    parameters: c_params,
                },
            ],
            expr_edges: vec![],
        };
        let pf = flat(&[
            ("g1.amplitude", 2.0),
            ("g1.center", 0.0),
            ("g1.sigma", 1.0),
            ("bg.c", 5.0),
        ]);

        // At x=0: Gaussian(0) = 2.0; Constant = 5.0  → sum = 7.0
        let result = evaluate(&graph, &pf, &[0.0]).unwrap();
        assert_relative_eq!(result[0], 7.0, epsilon = 1e-12);

        // At x=1 (one sigma from center): Gaussian(1) = 2*exp(-0.5); sum += 5.0
        let result2 = evaluate(&graph, &pf, &[1.0]).unwrap();
        let expected = 2.0 * (-0.5f64).exp() + 5.0;
        assert_relative_eq!(result2[0], expected, epsilon = 1e-12);
    }

    // -----------------------------------------------------------------------
    // Test 3: evaluate_components returns correct node keys
    // -----------------------------------------------------------------------
    #[test]
    fn test_evaluate_components_keys() {
        let mut g_params = HashMap::new();
        g_params.insert("amplitude".to_string(), make_param(1.0, true));
        g_params.insert("center".to_string(), make_param(0.0, true));
        g_params.insert("sigma".to_string(), make_param(1.0, true));

        let mut c_params = HashMap::new();
        c_params.insert("c".to_string(), make_param(2.0, false));

        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![
                ModelNodeSpec {
                    id: "peak".to_string(),
                    model_type: ModelTypeStr::Gaussian,
                    dataset_index: None,
                    parameters: g_params,
                },
                ModelNodeSpec {
                    id: "baseline".to_string(),
                    model_type: ModelTypeStr::Constant,
                    dataset_index: None,
                    parameters: c_params,
                },
            ],
            expr_edges: vec![],
        };
        let pf = flat(&[
            ("peak.amplitude", 1.0),
            ("peak.center", 0.0),
            ("peak.sigma", 1.0),
            ("baseline.c", 2.0),
        ]);

        let comps = evaluate_components(&graph, &pf, &[0.0, 1.0]).unwrap();
        assert!(comps.contains_key("peak"), "must have 'peak' component");
        assert!(
            comps.contains_key("baseline"),
            "must have 'baseline' component"
        );
        assert_eq!(comps.len(), 2);

        // peak at x=0 → 1.0; baseline → 2.0
        assert_relative_eq!(comps["peak"][0], 1.0, epsilon = 1e-12);
        assert_relative_eq!(comps["baseline"][0], 2.0, epsilon = 1e-12);
    }

    // -----------------------------------------------------------------------
    // Test 4: jacobian shape is [n_points × n_free_params]
    // -----------------------------------------------------------------------
    #[test]
    fn test_jacobian_shape() {
        let (graph, pf) = single_gaussian_graph();
        // 5 x-points, 3 free params (amplitude, center, sigma)
        let x: Vec<f64> = vec![0.0, 0.5, 1.0, 1.5, 2.0];
        let jac = jacobian(&graph, &pf, &x).unwrap();
        assert_eq!(jac.nrows(), 5, "rows = n_points");
        assert_eq!(jac.ncols(), 3, "cols = n_free_params");
    }

    // -----------------------------------------------------------------------
    // Test 5: jacobian values match finite-difference for Gaussian
    // -----------------------------------------------------------------------
    #[test]
    fn test_jacobian_vs_finite_diff_gaussian() {
        let (graph, pf) = single_gaussian_graph();
        let x = vec![0.5f64];
        let h = 1e-6;

        let jac = jacobian(&graph, &pf, &x).unwrap();

        // free_keys are sorted by node_id ("g1") then model param order:
        //   col 0 = g1.amplitude, col 1 = g1.center, col 2 = g1.sigma
        let param_keys = ["g1.amplitude", "g1.center", "g1.sigma"];
        for (col, key) in param_keys.iter().enumerate() {
            let mut pf_plus = pf.clone();
            *pf_plus.get_mut(*key).unwrap() += h;
            let f_plus = evaluate(&graph, &pf_plus, &x).unwrap()[0];
            let f_base = evaluate(&graph, &pf, &x).unwrap()[0];
            let fd = (f_plus - f_base) / h;
            assert!(
                (jac[(0, col)] - fd).abs() < 1e-5,
                "Jacobian col {} ({}) mismatch: got {}, expected {}",
                col,
                key,
                jac[(0, col)],
                fd
            );
        }
    }

    // -----------------------------------------------------------------------
    // Test 6: compile() rejects a graph that would have cyclic param targets
    // -----------------------------------------------------------------------
    #[test]
    fn test_compile_rejects_duplicate_expr_target() {
        use spectrafit_types::ExprEdge;

        let mut g_params = HashMap::new();
        g_params.insert("amplitude".to_string(), make_param(1.0, false));
        g_params.insert("center".to_string(), make_param(0.0, false));
        g_params.insert("sigma".to_string(), make_param(1.0, false));

        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![ModelNodeSpec {
                id: "g1".to_string(),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: None,
                parameters: g_params,
            }],
            // Two edges pointing to the same target param → cycle/conflict
            expr_edges: vec![
                ExprEdge {
                    target_node: "g1".to_string(),
                    target_param: "amplitude".to_string(),
                    expression: "2.0".to_string(),
                },
                ExprEdge {
                    target_node: "g1".to_string(),
                    target_param: "amplitude".to_string(),
                    expression: "3.0".to_string(),
                },
            ],
        };

        let result = compiler::CompiledGraph::compile(&graph);
        assert!(
            result.is_err(),
            "compile should reject duplicate expr targets"
        );
    }
}
