//! 2-D round-trip fit (U2 / R4): a single Gaussian2D node fit against synthetic
//! 2-D data must recover the generating parameters from a perturbed start.
//!
//! This is the real end-to-end spec the graph-crate `gaussian2d_round_trip_fit`
//! placeholder could not be (the graph crate has no solver dependency). It
//! exercises the strided-`x` (`n_dims == 2`) path through `point_major_x`,
//! `LmProblem` residual/Jacobian sizing (point count = `y.len()`, NOT the
//! `n_points * n_dims` coordinate length), and the post-fit DOF.

use std::collections::HashMap;

use spectrafit_solver::fit;
use spectrafit_types::{
    FitGraphSpec, FitOptionsSpec, MeasurementSpec, ModelNodeSpec, ModelTypeStr, ParameterSpec,
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

fn options(solver: &str) -> FitOptionsSpec {
    FitOptionsSpec {
        schema_version: None,
        solver: solver.to_string(),
        max_iterations: 200,
        tolerance: 1e-10,
        delta0: None,
        max_delta: None,
        eta: None,
    }
}

/// Closed-form Gaussian2D, mirroring the kernel:
/// `a * exp(-((x-cx)^2 / (2 sx^2) + (y-cy)^2 / (2 sy^2)))`.
fn gaussian2d(x: f64, y: f64, a: f64, cx: f64, cy: f64, sx: f64, sy: f64) -> f64 {
    let dx = (x - cx) / sx;
    let dy = (y - cy) / sy;
    a * (-0.5 * (dx * dx + dy * dy)).exp()
}

/// Single-Gaussian2D graph with a perturbed start; the truth is recovered.
fn build(start: [f64; 5]) -> FitGraphSpec {
    let [a, cx, cy, sx, sy] = start;
    let mut params = HashMap::new();
    params.insert("amplitude".into(), param(a, true));
    params.insert("center_x".into(), param(cx, true));
    params.insert("center_y".into(), param(cy, true));
    params.insert("sigma_x".into(), param(sx, true));
    params.insert("sigma_y".into(), param(sy, true));
    FitGraphSpec {
        schema_version: "0.1".into(),
        nodes: vec![ModelNodeSpec {
            id: "g2".into(),
            model_type: ModelTypeStr::Gaussian2D,
            dataset_index: None,
            parameters: params,
        }],
        expr_edges: vec![],
    }
}

#[test]
fn gaussian2d_round_trip_recovers_truth() {
    // True generating parameters.
    let (a, cx, cy, sx, sy) = (3.0_f64, 0.5_f64, -1.0_f64, 1.0_f64, 1.5_f64);

    // 7x7 grid, flattened into the per-dimension layout MeasurementSpec expects:
    // x[0] = all x-coords (point order), x[1] = all y-coords (point order).
    // `point_major_x` interleaves these into [xᵢ, yᵢ] for the Gaussian2D node.
    let mut xs = Vec::new();
    let mut ys = Vec::new();
    let mut y_obs = Vec::new();
    for i in 0..7 {
        for j in 0..7 {
            let xi = -3.0 + i as f64;
            let yj = -4.0 + 1.0 * j as f64;
            xs.push(xi);
            ys.push(yj);
            y_obs.push(gaussian2d(xi, yj, a, cx, cy, sx, sy));
        }
    }
    assert_eq!(y_obs.len(), 49);

    let ds = MeasurementSpec {
        schema_version: None,
        x: vec![xs, ys], // two dimensions, per-point coordinate rows
        y: y_obs,
        sigma: None,
        label: None,
    };

    // Perturb the start away from truth.
    let graph = build([2.0, 0.0, -0.5, 1.4, 1.0]);

    let res = fit(&graph, vec![ds], &options("lm")).expect("2-D fit");
    assert!(res.success, "2-D fit did not converge: {}", res.message);

    let got = |k: &str| res.parameters.get(k).expect(k).value;
    let truth = [
        ("g2.amplitude", a),
        ("g2.center_x", cx),
        ("g2.center_y", cy),
        ("g2.sigma_x", sx),
        ("g2.sigma_y", sy),
    ];
    for (key, t) in truth {
        let v = got(key);
        let rel = (v - t).abs() / t.abs().max(1.0);
        assert!(
            rel < 1e-3,
            "param {key}: got {v}, truth {t}, rel {rel} >= 1e-3"
        );
    }

    // Noiseless data → essentially perfect fit.
    assert!(
        res.r_squared > 1.0 - 1e-9,
        "expected near-perfect r²; got {}",
        res.r_squared
    );
}
