//! Integration tests for the VarPro solver path.

#[cfg(test)]
mod tests {
    use spectrafit_types::{FitGraphSpec, FitOptionsSpec, MeasurementSpec, ModelNodeSpec};
    use std::collections::HashMap;

    // ── helpers ──────────────────────────────────────────────────────────────

    fn gaussian_graph(amplitude: f64, center: f64, sigma: f64) -> FitGraphSpec {
        use spectrafit_types::{ModelTypeStr, ParameterSpec};
        let node = ModelNodeSpec {
            id: "g0".into(),
            model_type: ModelTypeStr::Gaussian,
            dataset_index: None,
            parameters: {
                let mut m = HashMap::new();
                m.insert(
                    "amplitude".into(),
                    ParameterSpec {
                        value: amplitude,
                        min: 0.0,
                        max: f64::INFINITY,
                        vary: true,
                        expr: None,
                        scale: None,
                    },
                );
                m.insert(
                    "center".into(),
                    ParameterSpec {
                        value: center,
                        min: f64::NEG_INFINITY,
                        max: f64::INFINITY,
                        vary: true,
                        expr: None,
                        scale: None,
                    },
                );
                m.insert(
                    "sigma".into(),
                    ParameterSpec {
                        value: sigma,
                        min: 0.0,
                        max: f64::INFINITY,
                        vary: true,
                        expr: None,
                        scale: None,
                    },
                );
                m
            },
        };
        FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![node],
            expr_edges: vec![],
        }
    }

    fn synthetic_gaussian(n: usize, amp: f64, ctr: f64, sig: f64) -> (Vec<f64>, Vec<f64>) {
        let x: Vec<f64> = (0..n)
            .map(|i| -5.0 + 10.0 * i as f64 / (n - 1) as f64)
            .collect();
        let y: Vec<f64> = x
            .iter()
            .map(|&xi| amp * (-(xi - ctr).powi(2) / (2.0 * sig * sig)).exp())
            .collect();
        (x, y)
    }

    // ── is_separable ─────────────────────────────────────────────────────────

    #[test]
    fn is_separable_gaussian() {
        let graph = gaussian_graph(1.0, 0.0, 1.0);
        assert!(spectrafit_varpro::is_separable(&graph));
    }

    #[test]
    fn is_separable_all_models() {
        use spectrafit_types::{FitGraphSpec, ModelNodeSpec, ModelTypeStr};
        for mt in &[
            ModelTypeStr::Gaussian,
            ModelTypeStr::Lorentzian,
            ModelTypeStr::Voigt,
            ModelTypeStr::Constant,
            ModelTypeStr::Linear,
            ModelTypeStr::ArctanStep,
            ModelTypeStr::TanhStep,
            ModelTypeStr::ErfcStep,
            ModelTypeStr::PseudoVoigt,
            ModelTypeStr::Fano,
        ] {
            let graph = FitGraphSpec {
                nodes: vec![ModelNodeSpec {
                    id: "n0".into(),
                    model_type: mt.clone(),
                    dataset_index: None,
                    parameters: HashMap::new(),
                }],
                expr_edges: vec![],
                schema_version: "0.1".into(),
            };
            assert!(
                spectrafit_varpro::is_separable(&graph),
                "{mt:?} should be separable"
            );
        }
    }

    // ── GraphSeparableModel construction ─────────────────────────────────────

    #[test]
    fn build_separable_model_gaussian() {
        use spectrafit_types::ParameterSpec;
        use spectrafit_varpro::model::GraphSeparableModel;

        let graph = gaussian_graph(1.0, 0.0, 1.0);
        let (x, y) = synthetic_gaussian(64, 2.0, 0.5, 0.8);
        let dataset = MeasurementSpec {
            schema_version: None,
            label: None,
            x: vec![x],
            y,
            sigma: None,
        };

        let mut params: HashMap<String, ParameterSpec> = HashMap::new();
        params.insert(
            "g0.amplitude".into(),
            ParameterSpec {
                value: 1.0,
                min: 0.0,
                max: f64::INFINITY,
                vary: true,
                expr: None,
                scale: None,
            },
        );
        params.insert(
            "g0.center".into(),
            ParameterSpec {
                value: 0.0,
                min: f64::NEG_INFINITY,
                max: f64::INFINITY,
                vary: true,
                expr: None,
                scale: None,
            },
        );
        params.insert(
            "g0.sigma".into(),
            ParameterSpec {
                value: 1.0,
                min: 0.0,
                max: f64::INFINITY,
                vary: true,
                expr: None,
                scale: None,
            },
        );

        let model = GraphSeparableModel::new(&graph, &dataset, &params);
        assert!(
            model.is_ok(),
            "Model construction failed: {:?}",
            model.err()
        );
        let m = model.unwrap();
        // alpha = [center, sigma] (amplitude is the linear coeff)
        assert_eq!(m.alpha_keys.len(), 2);
    }

    // ── solve_varpro end-to-end ───────────────────────────────────────────────

    #[test]
    fn solve_varpro_gaussian_recovers_params() {
        use approx::assert_relative_eq;
        use spectrafit_types::ParameterSpec;

        let true_amp = 3.0_f64;
        let true_ctr = 1.2_f64;
        let true_sig = 0.6_f64;

        let graph = gaussian_graph(1.0, 0.0, 1.0);
        let (x, y) = synthetic_gaussian(128, true_amp, true_ctr, true_sig);
        let dataset = MeasurementSpec {
            schema_version: None,
            label: None,
            x: vec![x],
            y,
            sigma: None,
        };

        let mut params: HashMap<String, ParameterSpec> = HashMap::new();
        params.insert(
            "g0.amplitude".into(),
            ParameterSpec {
                value: 1.0,
                min: 0.0,
                max: f64::INFINITY,
                vary: true,
                expr: None,
                scale: None,
            },
        );
        params.insert(
            "g0.center".into(),
            ParameterSpec {
                value: 0.0,
                min: f64::NEG_INFINITY,
                max: f64::INFINITY,
                vary: true,
                expr: None,
                scale: None,
            },
        );
        params.insert(
            "g0.sigma".into(),
            ParameterSpec {
                value: 1.0,
                min: 0.0,
                max: f64::INFINITY,
                vary: true,
                expr: None,
                scale: None,
            },
        );

        let options = FitOptionsSpec {
            schema_version: None,
            solver: "varpro".into(),
            max_iterations: 200,
            tolerance: 1e-10,
            delta0: None,
            max_delta: None,
            eta: None,
        };

        let result = spectrafit_varpro::solve_varpro(&graph, &[dataset], &params, &options);
        assert!(result.is_ok(), "solve_varpro failed: {:?}", result.err());
        let r = result.unwrap();

        let center = r.parameters["g0.center"].value;
        let sigma = r.parameters["g0.sigma"].value;
        let amplitude = r.parameters["g0.amplitude"].value;

        assert_relative_eq!(center, true_ctr, epsilon = 1e-3);
        assert_relative_eq!(sigma, true_sig, epsilon = 1e-3);
        assert_relative_eq!(amplitude, true_amp, epsilon = 1e-3);
    }
}
