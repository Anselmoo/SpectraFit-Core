//! Parity harness: the faer-native trust-region core (the default `solver =
//! "lm"`) must match the proven `levenberg-marquardt` crate (`solver =
//! "lm-legacy"`) on the same problems, at the same tolerance. This gated
//! flipping the default to faer (M5) and gates deleting the legacy dependency
//! (M8).
//!
//! Asserts, per case:
//! * every free parameter agrees (tight relative/absolute tolerance),
//! * χ² agrees,
//! * the faer path does not blow up the work budget (`n_func_evals`) — the
//!   whole point is "fewer iterations, faster", so faer must not regress into
//!   many-more-iterations.
//!
//! M2 covers the normal-equations regime (`m ≫ p`); the SVD-regime
//! 50-peak/150-param case is added in M3 once that path is wired.

use std::collections::HashMap;

use spectrafit_solver::fit;
use spectrafit_types::{
    FitGraphSpec, FitOptionsSpec, FitResultSpec, MeasurementSpec, ModelNodeSpec, ModelTypeStr,
    ParameterSpec,
};

fn param(value: f64, vary: bool) -> ParameterSpec {
    ParameterSpec {
        value,
        min: f64::NEG_INFINITY,
        max: f64::INFINITY,
        vary,
        expr: None,
        scale: None,
    }
}

fn bounded(value: f64, min: f64, max: f64) -> ParameterSpec {
    ParameterSpec {
        value,
        min,
        max,
        vary: true,
        expr: None,
        scale: None,
    }
}

fn options(solver: &str) -> FitOptionsSpec {
    FitOptionsSpec {
        schema_version: None,
        solver: solver.to_string(),
        max_iterations: 200,
        tolerance: 1e-8,
        delta0: None,
        max_delta: None,
        eta: None,
    }
}

fn gaussian(x: f64, a: f64, c: f64, s: f64) -> f64 {
    a * (-(x - c).powi(2) / (2.0 * s * s)).exp()
}

/// Run a graph/dataset through both engines and assert parity.
fn assert_parity(
    label: &str,
    graph: &FitGraphSpec,
    dataset: MeasurementSpec,
    value_eps: f64,
    budget_ratio: f64,
) -> (FitResultSpec, FitResultSpec) {
    let legacy = fit(graph, vec![dataset.clone()], &options("lm-legacy")).expect("legacy fit");
    let faer = fit(graph, vec![dataset], &options("lm")).expect("faer fit");

    assert!(
        legacy.success,
        "[{label}] legacy did not converge: {}",
        legacy.message
    );
    assert!(
        faer.success,
        "[{label}] faer did not converge: {}",
        faer.message
    );

    for (key, lp) in &legacy.parameters {
        if !lp.vary {
            continue;
        }
        let fp = faer
            .parameters
            .get(key)
            .unwrap_or_else(|| panic!("[{label}] faer missing param {key}"));
        let diff = (lp.value - fp.value).abs();
        let tol = value_eps * lp.value.abs().max(1.0);
        assert!(
            diff <= tol,
            "[{label}] param {key}: legacy={} faer={} |Δ|={diff} > {tol}",
            lp.value,
            fp.value
        );
    }

    // χ² agreement (both are tiny for clean data; compare absolute + relative).
    let chi2_diff = (legacy.chi2 - faer.chi2).abs();
    let chi2_tol = 1e-6 * legacy.chi2.abs().max(1e-9);
    assert!(
        chi2_diff <= chi2_tol,
        "[{label}] chi2: legacy={} faer={} |Δ|={chi2_diff} > {chi2_tol}",
        legacy.chi2,
        faer.chi2
    );

    // Work budget: faer must not need dramatically more residual evaluations.
    let lf = legacy.n_func_evals.unwrap_or(0);
    let ff = faer.n_func_evals.unwrap_or(0);
    assert!(
        ff <= (lf as f64 * budget_ratio).ceil() as u64 + 5,
        "[{label}] faer n_func_evals={ff} regressed vs legacy={lf} (ratio {budget_ratio})"
    );

    (legacy, faer)
}

fn grid(n: usize, lo: f64, hi: f64) -> Vec<f64> {
    (0..n)
        .map(|i| lo + (hi - lo) * i as f64 / (n - 1) as f64)
        .collect()
}

#[test]
fn parity_single_gaussian() {
    let (true_a, true_c, true_s) = (5.0, 2.0, 0.5);
    let x = grid(80, -1.0, 5.0);
    let y: Vec<f64> = x
        .iter()
        .map(|&xi| gaussian(xi, true_a, true_c, true_s))
        .collect();

    let mut params = HashMap::new();
    params.insert("amplitude".into(), param(4.0, true));
    params.insert("center".into(), param(1.8, true));
    params.insert("sigma".into(), param(0.6, true));
    let graph = FitGraphSpec {
        schema_version: "0.1".into(),
        nodes: vec![ModelNodeSpec {
            id: "g".into(),
            model_type: ModelTypeStr::Gaussian,
            dataset_index: None,
            parameters: params,
        }],
        expr_edges: vec![],
    };
    let ds = MeasurementSpec {
        schema_version: None,
        x: vec![x],
        y,
        sigma: None,
        label: None,
    };
    assert_parity("single_gaussian", &graph, ds, 1e-6, 1.5);
}

#[test]
fn parity_two_gaussians() {
    let x = grid(120, -4.0, 4.0);
    let y: Vec<f64> = x
        .iter()
        .map(|&xi| gaussian(xi, 5.0, -1.0, 0.6) + gaussian(xi, 3.0, 1.2, 0.5))
        .collect();

    let mut g1 = HashMap::new();
    g1.insert("amplitude".into(), param(4.0, true));
    g1.insert("center".into(), param(-0.8, true));
    g1.insert("sigma".into(), param(0.7, true));
    let mut g2 = HashMap::new();
    g2.insert("amplitude".into(), param(2.5, true));
    g2.insert("center".into(), param(1.0, true));
    g2.insert("sigma".into(), param(0.6, true));
    let graph = FitGraphSpec {
        schema_version: "0.1".into(),
        nodes: vec![
            ModelNodeSpec {
                id: "a".into(),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: None,
                parameters: g1,
            },
            ModelNodeSpec {
                id: "b".into(),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: None,
                parameters: g2,
            },
        ],
        expr_edges: vec![],
    };
    let ds = MeasurementSpec {
        schema_version: None,
        x: vec![x],
        y,
        sigma: None,
        label: None,
    };
    assert_parity("two_gaussians", &graph, ds, 1e-5, 1.5);
}

#[test]
fn parity_gaussian_plus_constant() {
    let x = grid(100, -3.0, 3.0);
    let y: Vec<f64> = x
        .iter()
        .map(|&xi| gaussian(xi, 4.0, 0.0, 0.8) + 1.5)
        .collect();

    let mut g = HashMap::new();
    g.insert("amplitude".into(), param(3.0, true));
    g.insert("center".into(), param(0.3, true));
    g.insert("sigma".into(), param(1.0, true));
    let mut c = HashMap::new();
    c.insert("c".into(), param(0.5, true));
    let graph = FitGraphSpec {
        schema_version: "0.1".into(),
        nodes: vec![
            ModelNodeSpec {
                id: "peak".into(),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: None,
                parameters: g,
            },
            ModelNodeSpec {
                id: "bg".into(),
                model_type: ModelTypeStr::Constant,
                dataset_index: None,
                parameters: c,
            },
        ],
        expr_edges: vec![],
    };
    let ds = MeasurementSpec {
        schema_version: None,
        x: vec![x],
        y,
        sigma: None,
        label: None,
    };
    assert_parity("gaussian_plus_constant", &graph, ds, 1e-5, 1.5);
}

#[test]
fn parity_sigma_weighted() {
    let x = grid(100, -2.0, 4.0);
    let y: Vec<f64> = x.iter().map(|&xi| gaussian(xi, 6.0, 1.0, 0.7)).collect();
    let sigma: Vec<f64> = (0..x.len()).map(|i| 0.5 + 0.02 * i as f64).collect();

    let mut params = HashMap::new();
    params.insert("amplitude".into(), param(5.0, true));
    params.insert("center".into(), param(0.7, true));
    params.insert("sigma".into(), param(0.9, true));
    let graph = FitGraphSpec {
        schema_version: "0.1".into(),
        nodes: vec![ModelNodeSpec {
            id: "g".into(),
            model_type: ModelTypeStr::Gaussian,
            dataset_index: None,
            parameters: params,
        }],
        expr_edges: vec![],
    };
    let ds = MeasurementSpec {
        schema_version: None,
        x: vec![x],
        y,
        sigma: Some(sigma),
        label: None,
    };
    assert_parity("sigma_weighted", &graph, ds, 1e-5, 1.5);
}

/// On-demand wall-time comparison (not a CI gate — timing is machine-dependent).
/// Run with: `cargo test -p spectrafit-solver --test parity --release -- --ignored --nocapture`
#[test]
#[ignore = "timing spot-check; run manually with --ignored --nocapture"]
fn timing_large_n_single_gaussian() {
    let n = 50_000;
    let x = grid(n, -5.0, 5.0);
    let y: Vec<f64> = x.iter().map(|&xi| gaussian(xi, 5.0, 0.3, 0.9)).collect();
    let build = || {
        let mut params = HashMap::new();
        params.insert("amplitude".into(), param(4.0, true));
        params.insert("center".into(), param(0.0, true));
        params.insert("sigma".into(), param(1.2, true));
        FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![ModelNodeSpec {
                id: "g".into(),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: None,
                parameters: params,
            }],
            expr_edges: vec![],
        }
    };
    let ds = || MeasurementSpec {
        schema_version: None,
        x: vec![x.clone()],
        y: y.clone(),
        sigma: None,
        label: None,
    };
    for solver in ["lm-legacy", "lm"] {
        let t0 = std::time::Instant::now();
        let r = fit(&build(), vec![ds()], &options(solver)).unwrap();
        let dt = t0.elapsed();
        println!(
            "[timing] solver={solver:<9} {:?}  iters={} nfev={:?} chi2={:.3e} success={}",
            dt, r.n_iter, r.n_func_evals, r.chi2, r.success
        );
    }
}

#[test]
fn parity_bounded() {
    let x = grid(80, -1.0, 5.0);
    let y: Vec<f64> = x.iter().map(|&xi| gaussian(xi, 5.0, 2.0, 0.5)).collect();

    let mut params = HashMap::new();
    // amplitude bounded in [0, 10]; sigma bounded in [0.1, 3] — active reflection.
    params.insert("amplitude".into(), bounded(4.0, 0.0, 10.0));
    params.insert("center".into(), param(1.8, true));
    params.insert("sigma".into(), bounded(0.6, 0.1, 3.0));
    let graph = FitGraphSpec {
        schema_version: "0.1".into(),
        nodes: vec![ModelNodeSpec {
            id: "g".into(),
            model_type: ModelTypeStr::Gaussian,
            dataset_index: None,
            parameters: params,
        }],
        expr_edges: vec![],
    };
    let ds = MeasurementSpec {
        schema_version: None,
        x: vec![x],
        y,
        sigma: None,
        label: None,
    };
    assert_parity("bounded", &graph, ds, 1e-5, 1.5);
}

#[test]
fn varpro_rejects_tied_graph() {
    // VarPro cannot honour expr_edges (it never applies the tied-plan), so a
    // tied graph must be rejected rather than silently fit wrong.
    let mut g1 = HashMap::new();
    g1.insert("amplitude".into(), param(2.0, true));
    g1.insert("center".into(), param(-1.0, true));
    g1.insert("sigma".into(), param(0.5, true));
    let mut g2 = HashMap::new();
    g2.insert("amplitude".into(), param(1.0, true));
    g2.insert("center".into(), param(1.0, true));
    g2.insert("sigma".into(), param(0.5, false));
    let graph = FitGraphSpec {
        schema_version: "0.1".into(),
        nodes: vec![
            ModelNodeSpec {
                id: "a".into(),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: None,
                parameters: g1,
            },
            ModelNodeSpec {
                id: "b".into(),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: None,
                parameters: g2,
            },
        ],
        expr_edges: vec![spectrafit_types::ExprEdge {
            target_node: "b".into(),
            target_param: "sigma".into(),
            expression: "a.sigma".into(),
        }],
    };
    let x = grid(40, -3.0, 3.0);
    let y = vec![0.0; 40];
    let ds = MeasurementSpec {
        schema_version: None,
        x: vec![x],
        y,
        sigma: None,
        label: None,
    };
    let res = fit(&graph, vec![ds], &options("varpro"));
    assert!(
        res.is_err(),
        "varpro must reject expr_edges, got {:?}",
        res.map(|r| r.success)
    );
}

#[test]
fn trf_converges_within_bounds() {
    // Bounded Gaussian recovery via the real Trust-Region-Reflective solver
    // (Coleman–Li bound scaling). True params sit inside the box.
    let x = grid(80, -1.0, 5.0);
    let y: Vec<f64> = x.iter().map(|&xi| gaussian(xi, 5.0, 2.0, 0.5)).collect();

    let mut params = HashMap::new();
    params.insert("amplitude".into(), bounded(3.0, 0.0, 10.0));
    params.insert("center".into(), bounded(1.5, -1.0, 5.0));
    params.insert("sigma".into(), bounded(0.8, 0.1, 3.0));
    let graph = FitGraphSpec {
        schema_version: "0.1".into(),
        nodes: vec![ModelNodeSpec {
            id: "g".into(),
            model_type: ModelTypeStr::Gaussian,
            dataset_index: None,
            parameters: params,
        }],
        expr_edges: vec![],
    };
    let ds = MeasurementSpec {
        schema_version: None,
        x: vec![x],
        y,
        sigma: None,
        label: None,
    };
    let r = fit(&graph, vec![ds], &options("trf")).expect("trf fit");
    assert!(r.success, "trf should converge: {}", r.message);
    // Recovered params, and all within their bounds.
    let a = r.parameters["g.amplitude"].value;
    let c = r.parameters["g.center"].value;
    let s = r.parameters["g.sigma"].value;
    assert!((a - 5.0).abs() < 1e-2, "amplitude {a}");
    assert!((c - 2.0).abs() < 1e-2, "center {c}");
    assert!((s - 0.5).abs() < 1e-2, "sigma {s}");
    assert!((0.0..=10.0).contains(&a) && (-1.0..=5.0).contains(&c) && (0.1..=3.0).contains(&s));
    assert!(r.chi2 < 1e-6, "trf chi2 {}", r.chi2);
}

#[test]
fn parity_many_peaks_svd_regime() {
    // 15 Gaussians → 45 free params (> 40) ⇒ select_regime picks SvdSecular.
    // Clean, well-separated peaks with a small initial perturbation so both
    // solvers land in the same basin; parity then pins the SVD step.
    const N_PEAKS: usize = 15;
    let centers: Vec<f64> = (0..N_PEAKS).map(|k| -8.4 + 1.2 * k as f64).collect();
    let amps: Vec<f64> = (0..N_PEAKS).map(|k| 1.5 + 0.1 * k as f64).collect();
    let sigma = 0.45;

    let x = grid(500, -10.0, 10.0);
    let y: Vec<f64> = x
        .iter()
        .map(|&xi| {
            (0..N_PEAKS)
                .map(|k| gaussian(xi, amps[k], centers[k], sigma))
                .sum()
        })
        .collect();

    let nodes: Vec<ModelNodeSpec> = (0..N_PEAKS)
        .map(|k| {
            let mut p = HashMap::new();
            // Small perturbation from truth.
            p.insert("amplitude".into(), param(amps[k] * 0.97, true));
            p.insert("center".into(), param(centers[k] + 0.04, true));
            p.insert("sigma".into(), param(sigma * 1.04, true));
            ModelNodeSpec {
                id: format!("p{k}"),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: None,
                parameters: p,
            }
        })
        .collect();
    let graph = FitGraphSpec {
        schema_version: "0.1".into(),
        nodes,
        expr_edges: vec![],
    };
    let ds = MeasurementSpec {
        schema_version: None,
        x: vec![x],
        y,
        sigma: None,
        label: None,
    };
    // Looser value tol (45 params) and a lenient work budget — the SVD step is
    // correct but not yet iteration-optimised (factorises per λ-trial).
    let (legacy, faer) = assert_parity("many_peaks_svd", &graph, ds, 1e-3, 8.0);
    assert!(faer.parameters.len() == legacy.parameters.len());
    assert!(
        faer.chi2 < 1e-6,
        "faer chi2 should be ~0 for clean data: {}",
        faer.chi2
    );
}

#[test]
fn new_trust_region_solvers_recover_single_gaussian_end_to_end() {
    // Drive dogleg and newton-cg through the full fit() dispatch + LmProblem +
    // post-fit path (not just the standalone subproblem unit tests) and confirm
    // each recovers a single Gaussian to ~machine precision.
    let (true_a, true_c, true_s) = (5.0, 2.0, 0.5);
    let x = grid(80, -1.0, 5.0);
    let y: Vec<f64> = x
        .iter()
        .map(|&xi| gaussian(xi, true_a, true_c, true_s))
        .collect();

    let make_graph = || {
        let mut params = HashMap::new();
        params.insert("amplitude".into(), param(4.0, true));
        params.insert("center".into(), param(1.8, true));
        params.insert("sigma".into(), param(0.6, true));
        FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![ModelNodeSpec {
                id: "g".into(),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: None,
                parameters: params,
            }],
            expr_edges: vec![],
        }
    };
    let ds = MeasurementSpec {
        schema_version: None,
        x: vec![x],
        y,
        sigma: None,
        label: None,
    };

    for solver in ["dogleg", "newton-cg"] {
        let res = fit(&make_graph(), vec![ds.clone()], &options(solver))
            .unwrap_or_else(|e| panic!("[{solver}] fit error: {e:?}"));
        assert!(res.success, "[{solver}] did not converge: {}", res.message);
        let a = res.parameters["g.amplitude"].value;
        let c = res.parameters["g.center"].value;
        let s = res.parameters["g.sigma"].value;
        assert!((a - true_a).abs() < 1e-4, "[{solver}] amplitude {a}");
        assert!((c - true_c).abs() < 1e-4, "[{solver}] center {c}");
        // σ is recovered up to its sign (the model depends on σ²).
        assert!((s.abs() - true_s).abs() < 1e-4, "[{solver}] sigma {s}");
        assert!(res.chi2 < 1e-8, "[{solver}] chi2 {}", res.chi2);
    }
}
