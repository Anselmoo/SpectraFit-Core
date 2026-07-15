//! VarPro solver: runs `SeparableProblemBuilder` + `LevMarSolver` and maps
//! results back to `FitResultSpec`.

use std::collections::HashMap;

use nalgebra::DVector;
use spectrafit_graph::{
    compiler::CompiledGraph,
    executor::{evaluate_compiled, evaluate_components_compiled, jacobian_compiled},
};
use spectrafit_types::{
    CoreError, DatasetSliceSpec, FitGraphSpec, FitOptionsSpec, FitResultSpec, MeasurementSpec,
    ParameterResultSpec, ParameterSpec, TerminationReason,
};
use varpro::{problem::SeparableProblemBuilder, solvers::levmar::LevMarSolver};

use crate::model::GraphSeparableModel;

/// Run the varpro solver on one or more datasets sharing the same separable model.
///
/// For multi-dataset fits all datasets are concatenated vertically before
/// building the basis matrix, so nonlinear shape parameters (α) are shared
/// across all datasets while amplitudes are solved jointly.
///
/// # Errors
/// - [`CoreError::Eval`] if the model construction or solve fails.
pub fn solve_varpro(
    graph: &FitGraphSpec,
    datasets: &[MeasurementSpec],
    all_params: &HashMap<String, ParameterSpec>,
    _options: &FitOptionsSpec,
) -> Result<FitResultSpec, CoreError> {
    if datasets.is_empty() {
        return Err(CoreError::Eval("VarPro: no datasets provided".into()));
    }

    // ── 0. Stack all datasets into a single synthetic MeasurementSpec ─────────
    // Shared nonlinear params (α) apply to the concatenated problem; amplitudes
    // (linear coefficients) are solved jointly across the stacked data.
    let x_concat: Vec<f64> = datasets
        .iter()
        .flat_map(|ds| ds.x.first().cloned().unwrap_or_default())
        .collect();
    let y_concat: Vec<f64> = datasets
        .iter()
        .flat_map(|ds| ds.y.iter().copied())
        .collect();
    let sigma_concat: Option<Vec<f64>> = if datasets.iter().any(|ds| ds.sigma.is_some()) {
        Some(
            datasets
                .iter()
                .flat_map(|ds| {
                    let n = ds.y.len();
                    match &ds.sigma {
                        Some(s) => s.clone(),
                        None => vec![1.0_f64; n],
                    }
                })
                .collect(),
        )
    } else {
        None
    };
    let stacked = MeasurementSpec {
        schema_version: None,
        x: vec![x_concat.clone()],
        y: y_concat.clone(),
        sigma: sigma_concat,
        label: None,
    };

    // ── 1. Build the separable model ─────────────────────────────────────────
    let model = GraphSeparableModel::new(graph, &stacked, all_params)
        .map_err(|e| CoreError::Eval(format!("VarPro model build error: {e:?}")))?;

    let alpha_keys = model.alpha_keys.clone();

    // ── 2. Build y and optional weights ──────────────────────────────────────
    let y = DVector::from_vec(y_concat.clone());
    let weights_opt = stacked.sigma.as_ref().map(|s| {
        DVector::from_vec(
            s.iter()
                .map(|&si| if si > 0.0 { 1.0 / si } else { 1.0 })
                .collect(),
        )
    });

    // ── 3. Build the fitting problem and solve ────────────────────────────────
    let fit_result = if let Some(weights) = weights_opt {
        let problem = SeparableProblemBuilder::new(model)
            .observations(y)
            .weights(weights)
            .build()
            .map_err(|e| CoreError::Eval(format!("VarPro problem build error: {e:?}")))?;
        LevMarSolver::default()
            .solve(problem)
            .map_err(|e| CoreError::Eval(format!("VarPro solve failed: {e:?}")))?
    } else {
        let problem = SeparableProblemBuilder::new(model)
            .observations(y)
            .build()
            .map_err(|e| CoreError::Eval(format!("VarPro problem build error: {e:?}")))?;
        LevMarSolver::default()
            .solve(problem)
            .map_err(|e| CoreError::Eval(format!("VarPro solve failed: {e:?}")))?
    };

    let alpha = fit_result.nonlinear_parameters();
    let coefficients = fit_result
        .linear_coefficients()
        .ok_or_else(|| CoreError::Eval("VarPro: linear coefficients unavailable".into()))?;

    // ── 4. Reconstruct parameters ─────────────────────────────────────────────
    let compiled = CompiledGraph::compile(graph).map_err(|e| CoreError::Eval(format!("{e}")))?;
    let mut parameters: HashMap<String, ParameterResultSpec> = HashMap::new();

    for (i, key) in alpha_keys.iter().enumerate() {
        let init_spec = all_params.get(key).cloned().unwrap_or(ParameterSpec {
            value: 0.0,
            min: f64::NEG_INFINITY,
            max: f64::INFINITY,
            vary: true,
            expr: None,
            scale: None,
        });
        parameters.insert(
            key.clone(),
            ParameterResultSpec {
                name: key.clone(),
                value: alpha[i],
                min: if init_spec.min.is_infinite() {
                    None
                } else {
                    Some(init_spec.min)
                },
                max: if init_spec.max.is_infinite() {
                    None
                } else {
                    Some(init_spec.max)
                },
                vary: true,
                expr: None,
                scale: init_spec.scale,
                stderr: None, // filled below from Jacobian
            },
        );
    }

    for (j, node_entry) in compiled.nodes.iter().enumerate() {
        let amp_key = format!("{}.amplitude", node_entry.id);
        if let Some(init_spec) = all_params.get(&amp_key) {
            let value = if j < coefficients.len() {
                coefficients[j]
            } else {
                1.0
            };
            parameters.insert(
                amp_key.clone(),
                ParameterResultSpec {
                    name: amp_key,
                    value,
                    min: if init_spec.min.is_infinite() {
                        None
                    } else {
                        Some(init_spec.min)
                    },
                    max: if init_spec.max.is_infinite() {
                        None
                    } else {
                        Some(init_spec.max)
                    },
                    vary: init_spec.vary,
                    expr: None,
                    scale: init_spec.scale,
                    stderr: None, // filled below
                },
            );
        }
    }

    for (key, spec) in all_params {
        if !parameters.contains_key(key) {
            parameters.insert(
                key.clone(),
                ParameterResultSpec {
                    name: key.clone(),
                    value: spec.value,
                    min: if spec.min.is_infinite() {
                        None
                    } else {
                        Some(spec.min)
                    },
                    max: if spec.max.is_infinite() {
                        None
                    } else {
                        Some(spec.max)
                    },
                    vary: spec.vary,
                    expr: spec.expr.clone(),
                    scale: spec.scale,
                    stderr: None,
                },
            );
        }
    }

    // ── 5. Compute best-fit, residuals, statistics ────────────────────────────
    let flat_params: HashMap<String, f64> = parameters
        .iter()
        .map(|(k, v)| (k.clone(), v.value))
        .collect();

    let best_fit = evaluate_compiled(&compiled, &flat_params, &x_concat)
        .map_err(|e| CoreError::Eval(format!("{e}")))?;

    let init_flat: HashMap<String, f64> = all_params
        .iter()
        .map(|(k, s)| (k.clone(), s.value))
        .collect();
    let init_fit = evaluate_compiled(&compiled, &init_flat, &x_concat)
        .unwrap_or_else(|_| vec![0.0; y_concat.len()]);

    // Per-component contributions evaluated at the stacked x
    let components =
        evaluate_components_compiled(&compiled, &flat_params, &x_concat).unwrap_or_default();

    let n_total = y_concat.len();
    let n_free = alpha_keys.len() + coefficients.len();
    let dof = (n_total as i64 - n_free as i64).max(1);

    let residuals: Vec<f64> = y_concat
        .iter()
        .zip(best_fit.iter())
        .map(|(yi, fi)| yi - fi)
        .collect();
    let chi2: f64 = residuals.iter().map(|r| r * r).sum();
    let y_mean = y_concat.iter().sum::<f64>() / n_total.max(1) as f64;
    let ss_tot: f64 = y_concat.iter().map(|yi| (yi - y_mean).powi(2)).sum();
    let r_squared = if ss_tot > 0.0 {
        1.0 - chi2 / ss_tot
    } else {
        1.0
    };
    let reduced_chi2 = chi2 / dof as f64;
    let aic = chi2 + 2.0 * n_free as f64;
    let bic = chi2 + n_free as f64 * (n_total as f64).ln();

    // ── 6. Stderr from analytical Jacobian at solution ────────────────────────
    // Compute Σ = (JᵀJ)⁻¹ · (χ²/DOF) for all free parameters.
    // Use the sigma-weighted Jacobian if sigma was provided.
    if let Ok(j_final) = jacobian_compiled(&compiled, &flat_params, &x_concat) {
        let sigma_provided = datasets.iter().any(|ds| ds.sigma.is_some());
        let cov_opt = if sigma_provided {
            let sigma_vec: Vec<f64> = datasets
                .iter()
                .flat_map(|ds| {
                    let n = ds.y.len();
                    match &ds.sigma {
                        Some(s) => s.clone(),
                        None => vec![1.0_f64; n],
                    }
                })
                .collect();
            let mut j_w = j_final.clone();
            for (i, &s) in sigma_vec.iter().enumerate() {
                let w = if s > 0.0 { 1.0 / s } else { 1.0 };
                for col in 0..j_w.ncols() {
                    j_w[(i, col)] *= w;
                }
            }
            (j_w.transpose() * &j_w).try_inverse()
        } else {
            (j_final.transpose() * &j_final)
                .try_inverse()
                .map(|inv| inv * (chi2 / dof as f64))
        };

        if let Some(cov) = cov_opt {
            // free_keys in compiled order = alpha_keys + amplitude keys (in node order)
            let mut col = 0usize;
            for key in &alpha_keys {
                let v = cov[(col, col)];
                if v >= 0.0 {
                    if let Some(p) = parameters.get_mut(key) {
                        p.stderr = Some(v.sqrt());
                    }
                }
                col += 1;
            }
            for node_entry in &compiled.nodes {
                let amp_key = format!("{}.amplitude", node_entry.id);
                if col < cov.nrows() {
                    let v = cov[(col, col)];
                    if v >= 0.0 {
                        if let Some(p) = parameters.get_mut(&amp_key) {
                            p.stderr = Some(v.sqrt());
                        }
                    }
                    col += 1;
                }
            }
        }
    }

    // ── 7. Per-dataset slices (only populated for multi-dataset fits) ─────────
    let dataset_slices = if datasets.len() > 1 {
        let mut offset = 0usize;
        let slices: Vec<DatasetSliceSpec> = datasets
            .iter()
            .map(|ds| {
                let n = ds.y.len();
                let bf_slice = best_fit[offset..offset + n].to_vec();
                let ds_chi2: f64 =
                    ds.y.iter()
                        .zip(bf_slice.iter())
                        .map(|(obs, pred)| (obs - pred).powi(2))
                        .sum();
                let res_slice: Vec<f64> =
                    ds.y.iter()
                        .zip(bf_slice.iter())
                        .map(|(obs, pred)| obs - pred)
                        .collect();
                offset += n;
                DatasetSliceSpec {
                    label: ds.label.clone(),
                    n_points: n,
                    best_fit: bf_slice,
                    residuals: res_slice,
                    chi2: ds_chi2,
                }
            })
            .collect();
        Some(slices)
    } else {
        None
    };

    // Build the covariance_param_order that matches the VarPro Jacobian column
    // order used in §6 above: alpha_keys first, then amplitude keys in node order.
    // This mirrors the `col` iteration in the stderr loop (alpha_keys → amplitude
    // keys) so consumers can address cov[i][j] by name. VarPro currently emits
    // `covariance: None` at the result level (the matrix was used internally for
    // stderrs only), so this order is informational — it will become load-bearing
    // once the covariance matrix is also exposed on the VarPro path.
    let covariance_param_order: Vec<String> = alpha_keys
        .iter()
        .cloned()
        .chain(compiled.nodes.iter().map(|n| format!("{}.amplitude", n.id)))
        .collect();

    Ok(FitResultSpec {
        schema_version: "0.1".into(),
        parameters,
        covariance: None,
        covariance_param_order,
        chi2,
        reduced_chi2,
        r_squared,
        dof,
        aic,
        bic,
        n_iter: 0,
        n_func_evals: None,
        n_jac_evals: None,
        success: true,
        message: TerminationReason::Converged.as_str().to_string(),
        best_fit,
        residuals,
        init_fit,
        components,
        dataset_slices,
        // VarPro does not form the full JᵀJ over all parameters, so the
        // condition number is not computed on this path.
        condition_number: None,
        // VarPro is not a DE/global path.
        n_de_generations: None,
        // VarPro's separable projection has no per-iteration LM trajectory; the
        // benchmark layer reconstructs a labelled proxy from initial/final cost.
        cost_history: Vec::new(),
        gradient_norm_history: Vec::new(),
        params_history: Vec::new(),
    })
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;
    use spectrafit_types::{
        FitGraphSpec, FitOptionsSpec, MeasurementSpec, ModelNodeSpec, ModelTypeStr, ParameterSpec,
    };

    // ── Fixture helpers ───────────────────────────────────────────────────────

    fn free_param(value: f64) -> ParameterSpec {
        ParameterSpec {
            value,
            min: f64::NEG_INFINITY,
            max: f64::INFINITY,
            vary: true,
            expr: None,
            scale: None,
        }
    }

    /// Generate noiseless Gaussian data: y = amp * exp(-(x-center)^2 / (2*sigma^2))
    fn gaussian_data(x: &[f64], amp: f64, center: f64, sigma: f64) -> Vec<f64> {
        x.iter()
            .map(|&xi| amp * (-(xi - center).powi(2) / (2.0 * sigma * sigma)).exp())
            .collect()
    }

    // ── R1c: solve_varpro recovers known amplitude + sigma from 1-Gaussian ───
    //
    // Truth: amplitude = 3.5, center = 0.0 (fixed), sigma = 1.2.
    // Initial guess: amplitude = 1.0, sigma = 0.8 (20% off truth).
    // Tolerance: 1e-3 relative — loose enough for VarPro convergence on a clean
    // noiseless dataset with a 20%-off starting point, tight enough to be useful.
    // center is fixed (vary=false) because VarPro only optimises the nonlinear
    // free parameters (alpha); a known-good center allows amplitude+sigma recovery
    // to be tested in isolation.
    #[test]
    fn solve_varpro_recovers_gaussian_amplitude_and_sigma() {
        // ── 1. Truth ──────────────────────────────────────────────────────────
        let true_amp = 3.5_f64;
        let true_center = 0.0_f64;
        let true_sigma = 1.2_f64;

        // 100 points from -4 to +4
        let n = 100usize;
        let x: Vec<f64> = (0..n)
            .map(|i| -4.0 + 8.0 * i as f64 / (n - 1) as f64)
            .collect();
        let y = gaussian_data(&x, true_amp, true_center, true_sigma);

        // ── 2. Spec: center fixed; amplitude + sigma free ─────────────────────
        let node_id = "g0";
        let mut params_map: HashMap<String, ParameterSpec> = HashMap::new();
        // Amplitude: initial guess 1.0 (will be solved as a linear coefficient)
        params_map.insert(format!("{node_id}.amplitude"), free_param(1.0));
        // Center: fixed at truth so only sigma is the nonlinear unknown
        params_map.insert(
            format!("{node_id}.center"),
            ParameterSpec {
                value: true_center,
                min: f64::NEG_INFINITY,
                max: f64::INFINITY,
                vary: false,
                expr: None,
                scale: None,
            },
        );
        // Sigma: initial guess 20% off truth
        params_map.insert(format!("{node_id}.sigma"), free_param(0.8));

        let mut node_parameters = HashMap::new();
        node_parameters.insert("amplitude".into(), free_param(1.0));
        node_parameters.insert(
            "center".into(),
            ParameterSpec {
                value: true_center,
                min: f64::NEG_INFINITY,
                max: f64::INFINITY,
                vary: false,
                expr: None,
                scale: None,
            },
        );
        node_parameters.insert("sigma".into(), free_param(0.8));

        let graph = FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![ModelNodeSpec {
                id: node_id.into(),
                model_type: ModelTypeStr::Gaussian,
                parameters: node_parameters,
                dataset_index: None,
            }],
            expr_edges: vec![],
        };

        let dataset = MeasurementSpec {
            schema_version: None,
            x: vec![x],
            y,
            sigma: None,
            label: None,
        };

        let options = FitOptionsSpec::default();

        // ── 3. Solve ──────────────────────────────────────────────────────────
        let result = solve_varpro(&graph, &[dataset], &params_map, &options)
            .expect("VarPro must succeed on a clean 1-Gaussian dataset");

        // ── 4. Assert recovered parameters ───────────────────────────────────
        let amp_key = format!("{node_id}.amplitude");
        let sigma_key = format!("{node_id}.sigma");

        let recovered_amp = result
            .parameters
            .get(&amp_key)
            .unwrap_or_else(|| panic!("Missing parameter {amp_key}"))
            .value;
        let recovered_sigma = result
            .parameters
            .get(&sigma_key)
            .unwrap_or_else(|| panic!("Missing parameter {sigma_key}"))
            .value;

        // Relative tolerance of 1e-3 (0.1%) — noiseless data, clean Gaussian,
        // VarPro eliminates the linear dimension so sigma convergence is robust.
        assert_relative_eq!(
            recovered_amp,
            true_amp,
            max_relative = 1e-3,
            epsilon = 1e-10
        );
        assert_relative_eq!(
            recovered_sigma,
            true_sigma,
            max_relative = 1e-3,
            epsilon = 1e-10
        );

        // Also verify R² is near 1.0 (sanity check on best_fit quality)
        assert!(
            result.r_squared > 0.9999,
            "R² should be near 1.0 on a noiseless fit, got {}",
            result.r_squared
        );
    }

    // ── Error path: no datasets ───────────────────────────────────────────────

    #[test]
    fn solve_varpro_errors_on_empty_datasets() {
        let graph = FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![],
            expr_edges: vec![],
        };
        let options = FitOptionsSpec::default();
        let result = solve_varpro(&graph, &[], &HashMap::new(), &options);
        assert!(result.is_err(), "VarPro with no datasets must return Err");
    }

    // ── Weighted path: dataset with sigma exercises lines 48-97 ──────────────

    #[test]
    fn solve_varpro_weighted_dataset_sigma_path() {
        let true_amp = 2.5_f64;
        let true_center = 0.0_f64;
        let true_sigma = 1.0_f64;
        let n = 80usize;
        let x: Vec<f64> = (0..n)
            .map(|i| -4.0 + 8.0 * i as f64 / (n - 1) as f64)
            .collect();
        let y = gaussian_data(&x, true_amp, true_center, true_sigma);
        let sigma_vec = vec![0.05_f64; n];

        let node_id = "g0";
        let mut params_map: HashMap<String, ParameterSpec> = HashMap::new();
        params_map.insert(format!("{node_id}.amplitude"), free_param(1.0));
        params_map.insert(
            format!("{node_id}.center"),
            ParameterSpec {
                value: true_center,
                min: f64::NEG_INFINITY,
                max: f64::INFINITY,
                vary: false,
                expr: None,
                scale: None,
            },
        );
        params_map.insert(format!("{node_id}.sigma"), free_param(0.8));

        let mut node_parameters = HashMap::new();
        node_parameters.insert("amplitude".into(), free_param(1.0));
        node_parameters.insert(
            "center".into(),
            ParameterSpec {
                value: true_center,
                min: f64::NEG_INFINITY,
                max: f64::INFINITY,
                vary: false,
                expr: None,
                scale: None,
            },
        );
        node_parameters.insert("sigma".into(), free_param(0.8));

        let graph = FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![ModelNodeSpec {
                id: node_id.into(),
                model_type: ModelTypeStr::Gaussian,
                parameters: node_parameters,
                dataset_index: None,
            }],
            expr_edges: vec![],
        };

        let dataset = MeasurementSpec {
            schema_version: None,
            x: vec![x],
            y,
            sigma: Some(sigma_vec),
            label: None,
        };

        let options = FitOptionsSpec::default();
        let result = solve_varpro(&graph, &[dataset], &params_map, &options)
            .expect("weighted VarPro must succeed on clean noiseless data");

        assert_relative_eq!(
            result.parameters[&format!("{node_id}.amplitude")].value,
            true_amp,
            max_relative = 5e-2,
            epsilon = 1e-10
        );
        assert_relative_eq!(
            result.parameters[&format!("{node_id}.sigma")].value,
            true_sigma,
            max_relative = 5e-2,
            epsilon = 1e-10
        );
    }

    // ── Multi-dataset path: exercises dataset_slices population (lines 306-336)

    #[test]
    fn solve_varpro_multi_dataset_produces_slices() {
        let true_amp = 2.0_f64;
        let true_center = 0.0_f64;
        let true_sigma = 1.0_f64;
        let n = 40usize;
        let x: Vec<f64> = (0..n)
            .map(|i| -3.0 + 6.0 * i as f64 / (n - 1) as f64)
            .collect();
        let y = gaussian_data(&x, true_amp, true_center, true_sigma);

        let node_id = "g0";
        let mut params_map: HashMap<String, ParameterSpec> = HashMap::new();
        params_map.insert(format!("{node_id}.amplitude"), free_param(1.0));
        params_map.insert(
            format!("{node_id}.center"),
            ParameterSpec {
                value: true_center,
                min: f64::NEG_INFINITY,
                max: f64::INFINITY,
                vary: false,
                expr: None,
                scale: None,
            },
        );
        params_map.insert(format!("{node_id}.sigma"), free_param(0.8));

        let mut node_parameters = HashMap::new();
        node_parameters.insert("amplitude".into(), free_param(1.0));
        node_parameters.insert(
            "center".into(),
            ParameterSpec {
                value: true_center,
                min: f64::NEG_INFINITY,
                max: f64::INFINITY,
                vary: false,
                expr: None,
                scale: None,
            },
        );
        node_parameters.insert("sigma".into(), free_param(0.8));

        let graph = FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![ModelNodeSpec {
                id: node_id.into(),
                model_type: ModelTypeStr::Gaussian,
                parameters: node_parameters,
                dataset_index: None,
            }],
            expr_edges: vec![],
        };

        let make_ds = |label: &str| MeasurementSpec {
            schema_version: None,
            x: vec![x.clone()],
            y: y.clone(),
            sigma: None,
            label: Some(label.into()),
        };

        let options = FitOptionsSpec::default();
        let result = solve_varpro(
            &graph,
            &[make_ds("ds1"), make_ds("ds2")],
            &params_map,
            &options,
        )
        .expect("multi-dataset VarPro must succeed");

        let slices = result
            .dataset_slices
            .expect("dataset_slices must be Some for a 2-dataset fit");
        assert_eq!(slices.len(), 2, "expected 2 slices, one per dataset");
        assert_eq!(slices[0].n_points, n);
        assert_eq!(slices[1].n_points, n);
    }
}
