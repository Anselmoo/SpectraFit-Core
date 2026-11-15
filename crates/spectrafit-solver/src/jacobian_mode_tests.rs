//! `FitOptionsSpec.jacobian` (#93): `"finite_difference"` forces the graph-level
//! forward-difference Jacobian for every kernel and every LM-family front end;
//! `"analytic"` (the default) leaves the executor Jacobian untouched.
//!
//! The finite-difference reference below is written independently of
//! [`LmProblem::fd_weighted_jacobian_rowmajor`]: it rebuilds the node buffers
//! from a flat `"node.param" -> value` map for every perturbation, applies the
//! step-direction and `Parameter.scale` rules itself, and never touches the
//! problem's own parameter state. It deliberately evaluates residuals through
//! the production evaluator `residuals_compiled_indexed_into`: a forward
//! quotient divides by `h ~ 1e-7`, so a one-ulp difference between two
//! evaluation paths (batched `eval_slice_into` versus scalar `eval`) would show
//! up as a ~1e-9 relative difference and hide the property under test.
//!
//! Forward difference: Nocedal & Wright, *Numerical Optimization*, 2nd ed.,
//! §8.1, eq. (8.1). MINPACK `fdjac2` (Moré, Garbow & Hillstrom, ANL-80-74,
//! 1980), behind `lmfit`'s `leastsq`, uses the same forward difference with a
//! different step.

use std::cell::RefCell;
use std::collections::HashMap;

use faer::Mat;
use levenberg_marquardt::LeastSquaresProblem;
use nalgebra::DVector;
use spectrafit_graph::{
    jacobian_compiled_indexed_weighted_into, residuals_compiled_indexed_into, CompiledGraph,
};
use spectrafit_levenberg_marquardt::TrustRegionProblem;
use spectrafit_types::{FitGraphSpec, JacobianMode, ModelNodeSpec, ModelTypeStr, ParameterSpec};

use crate::lm_problem::LmProblem;

/// Relative tolerance of acceptance item 1 (package 06).
const REL_TOL: f64 = 1e-12;

/// Number of points on the 1-D grid of every fixture.
const N_POINTS_1D: usize = 25;

/// One evaluation fixture per kernel: parameter values (all free, unbounded),
/// the coordinate grid (point-major), and the coordinate dimensionality.
struct KernelFixture {
    params: Vec<(&'static str, f64)>,
    x: Vec<f64>,
}

fn grid_1d(lo: f64, hi: f64) -> Vec<f64> {
    (0..N_POINTS_1D)
        .map(|i| lo + (hi - lo) * i as f64 / (N_POINTS_1D - 1) as f64)
        .collect()
}

/// Point-major tensor grid with `n` points per axis over `[lo, hi]^dims`.
fn grid_nd(dims: usize, n: usize, lo: f64, hi: f64) -> Vec<f64> {
    let axis: Vec<f64> = (0..n)
        .map(|i| lo + (hi - lo) * i as f64 / (n - 1) as f64)
        .collect();
    let total = n.pow(dims as u32);
    let mut out = Vec::with_capacity(total * dims);
    for flat in 0..total {
        let mut rem = flat;
        for _ in 0..dims {
            out.push(axis[rem % n]);
            rem /= n;
        }
    }
    out
}

/// The fixture for every model type. An exhaustive `match`: a new
/// `ModelTypeStr` variant fails to compile here until it has a fixture, so the
/// per-kernel coverage of this file cannot silently fall behind the manifest.
/// Values are smooth interior points of each kernel's domain (no parameter at
/// zero, no grid point on a kink).
fn fixture(model: &ModelTypeStr) -> KernelFixture {
    use ModelTypeStr as M;
    let peak = |extra: &[(&'static str, f64)]| {
        let mut p = vec![("amplitude", 3.0), ("center", 0.2), ("sigma", 0.9)];
        p.extend_from_slice(extra);
        p
    };
    let (params, x) = match model {
        M::Gaussian | M::Lorentzian | M::ArctanStep | M::TanhStep | M::ErfcStep => {
            (peak(&[]), grid_1d(-3.0, 3.0))
        }
        M::Gaussian2D => (
            vec![
                ("amplitude", 2.0),
                ("center_x", 0.1),
                ("center_y", -0.2),
                ("sigma_x", 1.0),
                ("sigma_y", 1.3),
            ],
            grid_nd(2, 5, -2.0, 2.0),
        ),
        M::GaussianNd => (
            vec![
                ("amplitude", 1.5),
                ("center_0", 0.1),
                ("center_1", -0.1),
                ("center_2", 0.2),
                ("sigma_0", 1.0),
                ("sigma_1", 1.2),
                ("sigma_2", 0.9),
            ],
            grid_nd(3, 3, -1.5, 1.5),
        ),
        M::Voigt | M::PseudoVoigt => (peak(&[("fraction", 0.4)]), grid_1d(-3.0, 3.0)),
        M::Constant => (vec![("c", 1.7)], grid_1d(-3.0, 3.0)),
        M::Linear => (vec![("slope", 0.5), ("intercept", 1.2)], grid_1d(-3.0, 3.0)),
        M::Quadratic => (
            vec![("amplitude", 0.7), ("center", 0.3), ("offset", 1.1)],
            grid_1d(-3.0, 3.0),
        ),
        M::Fano => (
            vec![
                ("amplitude", 2.0),
                ("center", 0.1),
                ("gamma", 0.9),
                ("q", 1.5),
            ],
            grid_1d(-3.0, 3.0),
        ),
        M::DoubleExponential => (
            vec![("A1", 2.0), ("lam1", 0.8), ("A2", 1.0), ("lam2", 0.2)],
            grid_1d(0.0, 5.0),
        ),
        M::TrueVoigt => (peak(&[("gamma", 0.4)]), grid_1d(-3.0, 3.0)),
        M::SkewedGaussian => (peak(&[("gamma", 1.5)]), grid_1d(-3.0, 3.0)),
        M::ExpGaussian => (peak(&[("gamma", 1.2)]), grid_1d(-3.0, 3.0)),
        M::DoniachSunjic => (peak(&[("gamma", 0.2)]), grid_1d(-3.0, 3.0)),
        M::LogNormal => (
            vec![("amplitude", 2.0), ("center", 1.5), ("sigma", 0.4)],
            grid_1d(0.3, 5.0),
        ),
        M::Pearson7 => (peak(&[("m", 1.8)]), grid_1d(-3.0, 3.0)),
        M::SplitGaussian => (
            vec![
                ("amplitude", 3.0),
                ("center", 0.2),
                ("sigma_l", 0.8),
                ("sigma_r", 1.3),
            ],
            grid_1d(-3.0, 3.0),
        ),
        M::Moffat => (peak(&[("beta", 2.5)]), grid_1d(-3.0, 3.0)),
        M::StudentsT => (peak(&[("nu", 4.0)]), grid_1d(-3.0, 3.0)),
        M::SplitPearson7 => (
            vec![
                ("amplitude", 3.0),
                ("center", 0.2),
                ("sigma_l", 0.8),
                ("sigma_r", 1.2),
                ("m_l", 1.5),
                ("m_r", 2.5),
            ],
            grid_1d(-3.0, 3.0),
        ),
        M::BreitWigner => (peak(&[("q", 2.0)]), grid_1d(-3.0, 3.0)),
        M::AsymIr => (peak(&[("k", 0.5)]), grid_1d(-3.0, 3.0)),
        M::HarmonicIr => (
            vec![("amplitude", 2.0), ("center", 1.5), ("sigma", 0.3)],
            grid_1d(0.5, 3.0),
        ),
        M::Tauc => (
            vec![("amplitude", 2.0), ("e_gap", 1.0), ("exponent", 0.5)],
            grid_1d(1.2, 4.0),
        ),
        M::CauchyDispersion => (
            vec![("a", 1.5), ("b", 0.02), ("c", 0.001)],
            grid_1d(0.4, 1.0),
        ),
        M::Kww => (
            vec![("amplitude", 2.0), ("tau", 1.5), ("beta", 0.7)],
            grid_1d(0.1, 5.0),
        ),
        M::SaturatingExponential => (vec![("amplitude", 2.0), ("rate", 0.6)], grid_1d(0.0, 5.0)),
        M::PowerSaturation => (vec![("amplitude", 2.0), ("rate", 0.3)], grid_1d(0.0, 5.0)),
        M::PowerLawOffset => (
            vec![("amplitude", 2.0), ("offset", 1.5), ("shape", 1.2)],
            grid_1d(0.0, 5.0),
        ),
        M::Mgh09Rational => (
            vec![
                ("amplitude", 0.2),
                ("num_lin", 0.2),
                ("den_lin", 0.12),
                ("den_const", 0.14),
            ],
            grid_1d(0.1, 4.0),
        ),
        M::RationalCubic => (
            vec![
                ("a0", 1.0),
                ("a1", 0.5),
                ("a2", 0.1),
                ("a3", 0.01),
                ("b1", 0.05),
                ("b2", 0.01),
                ("b3", 0.001),
            ],
            grid_1d(0.0, 3.0),
        ),
        M::GeneralisedLogistic => (
            vec![
                ("amplitude", 70.0),
                ("shift", 2.5),
                ("rate", 0.07),
                ("shape", 1.3),
            ],
            grid_1d(1.0, 50.0),
        ),
        M::ExpOverLinear => (
            vec![("rate", 0.19), ("lin_const", 0.006), ("lin_slope", 0.01)],
            grid_1d(0.5, 6.0),
        ),
    };
    KernelFixture { params, x }
}

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

fn single_node_graph(model: &ModelTypeStr, params: &[(&'static str, f64)]) -> FitGraphSpec {
    FitGraphSpec {
        schema_version: "0.1".into(),
        nodes: vec![ModelNodeSpec {
            id: "n".into(),
            model_type: model.clone(),
            dataset_index: None,
            parameters: params
                .iter()
                .map(|&(name, v)| (name.to_string(), free_param(v)))
                .collect(),
        }],
        expr_edges: vec![],
    }
}

/// `"node.param" -> value` for every parameter of `cg` (free and fixed).
fn flat_params(graph: &FitGraphSpec) -> HashMap<String, f64> {
    graph
        .nodes
        .iter()
        .flat_map(|n| {
            n.parameters
                .iter()
                .map(move |(p, spec)| (format!("{}.{}", n.id, p), spec.value))
        })
        .collect()
}

/// Build an `LmProblem` the way `dispatch::fit` does, with the given mode,
/// bounds and scales (in `cg.free_keys` order) and per-point `sigma`.
fn problem<'a>(
    cg: &'a CompiledGraph,
    all_params: &HashMap<String, f64>,
    (bounds, scales): (Vec<(f64, f64)>, Vec<f64>),
    (x, y, sigma): (Vec<f64>, Vec<f64>, Vec<f64>),
    mode: JacobianMode,
) -> LmProblem<'a> {
    let free_keys = cg.free_keys.clone();
    let node_param_bufs: Vec<Vec<f64>> = (0..cg.nodes.len())
        .map(|i| cg.node_params(i, all_params).expect("node params"))
        .collect();
    let mut free_to_node_param = vec![(0usize, 0usize); free_keys.len()];
    for (node_idx, pairs) in cg.node_free_cols.iter().enumerate() {
        for &(local_idx, col) in pairs {
            free_to_node_param[col] = (node_idx, local_idx);
        }
    }
    let tied_to_node_param: Vec<(usize, usize)> = cg
        .tied_plan
        .order
        .iter()
        .map(|tp| {
            let (nid, pname) = tp.target.split_once('.').expect("node.param");
            let ni = cg.nodes.iter().position(|n| n.id == nid).expect("node");
            let pos = cg.nodes[ni]
                .param_names
                .iter()
                .position(|p| p == pname)
                .expect("param");
            (ni, pos)
        })
        .collect();
    let init: Vec<f64> = free_keys
        .iter()
        .zip(scales.iter())
        .map(|(k, &s)| all_params[k] / s)
        .collect();
    let n_free = free_keys.len();
    let n_points = y.len();
    LmProblem {
        compiled: cg,
        free_keys,
        bounds,
        all_params: all_params.clone(),
        node_param_bufs,
        free_to_node_param,
        tied_to_node_param,
        x_concat: x,
        y_concat: y,
        params: DVector::from_vec(init),
        scales,
        sigma,
        jacobian_mode: mode,
        residual_buf: RefCell::new(vec![0.0; n_points]),
        jacobian_buf: RefCell::new(vec![0.0; n_points * n_free]),
        residual_count: RefCell::new(0),
        jacobian_count: RefCell::new(0),
        residual_time_ns: RefCell::new(0),
        jacobian_time_ns: RefCell::new(0),
    }
}

/// Weighted residuals `(y_hat - y) / sigma` at the flat parameter map `flat`.
fn residuals_at(
    cg: &CompiledGraph,
    flat: &HashMap<String, f64>,
    x: &[f64],
    y: &[f64],
    sigma: &[f64],
) -> Vec<f64> {
    let bufs: Vec<Vec<f64>> = (0..cg.nodes.len())
        .map(|i| cg.node_params(i, flat).expect("node params"))
        .collect();
    let mut out = vec![0.0; y.len()];
    residuals_compiled_indexed_into(cg, &bufs, x, y, sigma, &mut out).expect("residuals");
    out
}

/// Independent forward-difference reference of the weighted Jacobian with
/// respect to the optimiser's scaled variable `theta'_k = theta_k / s_k`, row
/// major `[i * n_free + k]`. Step `h = sqrt(eps) * max(|theta'_k|, 1)` (#92;
/// Dennis and Schnabel 1996, §5.4), flipped to a backward step when the forward
/// step would leave the upper bound (bounds are physical, so the test is on
/// `(theta'_k + h) * s_k`); when the interval is narrower than the step in both
/// directions, the step goes into the side with more room, by that room. The
/// quotient divides by the step actually taken in the scaled variable. Graphs
/// here are untied.
fn fd_reference(
    cg: &CompiledGraph,
    flat0: &HashMap<String, f64>,
    bounds: &[(f64, f64)],
    scales: &[f64],
    (x, y, sigma): (&[f64], &[f64], &[f64]),
) -> Vec<f64> {
    let n_free = cg.free_keys.len();
    let r0 = residuals_at(cg, flat0, x, y, sigma);
    let mut jac = vec![0.0; y.len() * n_free];
    for (k, key) in cg.free_keys.iter().enumerate() {
        let s = scales[k];
        let theta_scaled = flat0[key] / s;
        let mut h = f64::EPSILON.sqrt() * theta_scaled.abs().max(1.0);
        let (lo, hi) = bounds[k];
        if hi.is_finite() && (theta_scaled + h) * s > hi {
            if lo.is_finite() && (theta_scaled - h) * s < lo {
                let up = hi / s - theta_scaled;
                let down = theta_scaled - lo / s;
                h = if up >= down { up } else { -down };
            } else {
                h = -h;
            }
        }
        let mut flat = flat0.clone();
        // Every free parameter is re-derived from its scaled value, as the
        // optimiser hands the problem scaled values (`theta' * s`).
        for (j, kj) in cg.free_keys.iter().enumerate() {
            let tj = flat0[kj] / scales[j];
            let tj = if j == k { tj + h } else { tj };
            flat.insert(kj.clone(), tj * scales[j]);
        }
        let rp = residuals_at(cg, &flat, x, y, sigma);
        let step = ((theta_scaled + h) * s) / s - theta_scaled;
        for i in 0..y.len() {
            jac[i * n_free + k] = if step == 0.0 {
                0.0
            } else {
                (rp[i] - r0[i]) / step
            };
        }
    }
    jac
}

fn assert_rel_eq(got: &[f64], want: &[f64], what: &str) {
    assert_eq!(got.len(), want.len(), "{what}: shape");
    for (idx, (&g, &w)) in got.iter().zip(want.iter()).enumerate() {
        let ok = g == w || (g - w).abs() <= REL_TOL * g.abs().max(w.abs());
        assert!(ok, "{what}: element {idx}: got {g:e}, reference {w:e}");
    }
}

fn faer_rowmajor(m: &Mat<f64>) -> Vec<f64> {
    let mut out = Vec::with_capacity(m.nrows() * m.ncols());
    for i in 0..m.nrows() {
        for j in 0..m.ncols() {
            out.push(m[(i, j)]);
        }
    }
    out
}

fn nalgebra_rowmajor(m: &nalgebra::DMatrix<f64>) -> Vec<f64> {
    let mut out = Vec::with_capacity(m.nrows() * m.ncols());
    for i in 0..m.nrows() {
        for j in 0..m.ncols() {
            out.push(m[(i, j)]);
        }
    }
    out
}

/// Data for a fixture: observations offset from the model so residuals are
/// non-trivial, and a non-unit, point-dependent sigma so the weighting is
/// exercised.
fn data_for(cg: &CompiledGraph, flat: &HashMap<String, f64>, x: &[f64]) -> (Vec<f64>, Vec<f64>) {
    let n = x.len() / cg.n_dims().expect("n_dims");
    let ones = vec![1.0; n];
    let zeros = vec![0.0; n];
    let model = residuals_at(cg, flat, x, &zeros, &ones);
    let y: Vec<f64> = model
        .iter()
        .enumerate()
        .map(|(i, m)| m + 0.05 * ((i % 7) as f64 - 3.0))
        .collect();
    let sigma: Vec<f64> = (0..n).map(|i| 0.5 + 0.01 * i as f64).collect();
    (y, sigma)
}

/// Acceptance 1, per kernel: in `finite_difference` mode both front ends
/// (`TrustRegionProblem::jacobian_into` for lm/trf/geodesic/dogleg/newton-cg,
/// `LeastSquaresProblem::jacobian` for lm-legacy) return the forward-difference
/// Jacobian, equal to the independent reference to 1e-12 relative.
#[test]
fn finite_difference_mode_matches_independent_reference_for_every_kernel() {
    for model in ModelTypeStr::ALL {
        let fx = fixture(model);
        let graph = single_node_graph(model, &fx.params);
        let cg = CompiledGraph::compile(&graph).expect("fixture graph compiles");
        let flat = flat_params(&graph);
        let (y, sigma) = data_for(&cg, &flat, &fx.x);
        let n_free = cg.free_keys.len();
        let bounds = vec![(f64::NEG_INFINITY, f64::INFINITY); n_free];
        let scales = vec![1.0; n_free];
        let want = fd_reference(&cg, &flat, &bounds, &scales, (&fx.x, &y, &sigma));

        let mut p = problem(
            &cg,
            &flat,
            (bounds.clone(), scales.clone()),
            (fx.x.clone(), y.clone(), sigma.clone()),
            JacobianMode::FiniteDifference,
        );
        let mut jac = Mat::<f64>::zeros(y.len(), n_free);
        p.jacobian_into(jac.as_mut()).expect("jacobian_into");
        assert_rel_eq(
            &faer_rowmajor(&jac),
            &want,
            &format!("{} jacobian_into", model.as_str()),
        );

        let legacy = LeastSquaresProblem::jacobian(&p).expect("legacy jacobian");
        assert_rel_eq(
            &nalgebra_rowmajor(&legacy),
            &want,
            &format!("{} lm-legacy jacobian", model.as_str()),
        );
    }
}

/// Acceptance 2, per kernel: the default `analytic` mode returns exactly the
/// executor's per-kernel Jacobian on both front ends (bit-identical), so the
/// default path is unchanged by the option.
#[test]
fn analytic_mode_is_the_unchanged_executor_jacobian_for_every_kernel() {
    for model in ModelTypeStr::ALL {
        let fx = fixture(model);
        let graph = single_node_graph(model, &fx.params);
        let cg = CompiledGraph::compile(&graph).expect("fixture graph compiles");
        let flat = flat_params(&graph);
        let (y, sigma) = data_for(&cg, &flat, &fx.x);
        let n_free = cg.free_keys.len();

        let bufs: Vec<Vec<f64>> = (0..cg.nodes.len())
            .map(|i| cg.node_params(i, &flat).expect("node params"))
            .collect();
        let mut want = Vec::new();
        jacobian_compiled_indexed_weighted_into(&cg, &bufs, &fx.x, &sigma, &mut want)
            .expect("executor jacobian");

        let mut p = problem(
            &cg,
            &flat,
            (
                vec![(f64::NEG_INFINITY, f64::INFINITY); n_free],
                vec![1.0; n_free],
            ),
            (fx.x.clone(), y.clone(), sigma.clone()),
            JacobianMode::Analytic,
        );
        let mut jac = Mat::<f64>::zeros(y.len(), n_free);
        p.jacobian_into(jac.as_mut()).expect("jacobian_into");
        assert_eq!(
            faer_rowmajor(&jac),
            want,
            "{}: analytic jacobian_into must be the executor Jacobian bit for bit",
            model.as_str()
        );
        let legacy = LeastSquaresProblem::jacobian(&p).expect("legacy jacobian");
        assert_eq!(
            nalgebra_rowmajor(&legacy),
            want,
            "{}: analytic lm-legacy jacobian must be the executor Jacobian bit for bit",
            model.as_str()
        );
    }
}

/// The forced FD path honours `Parameter.scale` (it differentiates the scaled
/// working variable) and the backward-step rule at an upper bound, exactly as
/// the independent reference does.
#[test]
fn finite_difference_mode_honours_scale_and_upper_bound_step_flip() {
    let model = ModelTypeStr::Gaussian;
    let fx = fixture(&model);
    let graph = single_node_graph(&model, &fx.params);
    let cg = CompiledGraph::compile(&graph).expect("compiles");
    let flat = flat_params(&graph);
    let (y, sigma) = data_for(&cg, &flat, &fx.x);
    let n_free = cg.free_keys.len();
    let mut bounds = vec![(f64::NEG_INFINITY, f64::INFINITY); n_free];
    let mut scales = vec![1.0; n_free];
    for (k, key) in cg.free_keys.iter().enumerate() {
        match key.as_str() {
            // Upper bound just above the value: the forward step would leave
            // the box, so the step must flip to a backward one.
            "n.amplitude" => bounds[k] = (f64::NEG_INFINITY, flat[key] + 1e-9),
            "n.sigma" => scales[k] = 2.5,
            _ => {}
        }
    }
    let want = fd_reference(&cg, &flat, &bounds, &scales, (&fx.x, &y, &sigma));
    let mut p = problem(
        &cg,
        &flat,
        (bounds, scales),
        (fx.x.clone(), y.clone(), sigma),
        JacobianMode::FiniteDifference,
    );
    let mut jac = Mat::<f64>::zeros(y.len(), n_free);
    p.jacobian_into(jac.as_mut()).expect("jacobian_into");
    assert_rel_eq(&faer_rowmajor(&jac), &want, "scaled + bounded gaussian");
}

/// The FD Jacobian leaves the problem's working state untouched: computing it
/// must not move the optimiser's parameters or the node buffers.
#[test]
fn finite_difference_jacobian_does_not_move_the_problem_state() {
    let model = ModelTypeStr::Gaussian;
    let fx = fixture(&model);
    let graph = single_node_graph(&model, &fx.params);
    let cg = CompiledGraph::compile(&graph).expect("compiles");
    let flat = flat_params(&graph);
    let (y, sigma) = data_for(&cg, &flat, &fx.x);
    let n_free = cg.free_keys.len();
    let mut p = problem(
        &cg,
        &flat,
        (
            vec![(f64::NEG_INFINITY, f64::INFINITY); n_free],
            vec![0.3; n_free],
        ),
        (fx.x.clone(), y.clone(), sigma),
        JacobianMode::FiniteDifference,
    );
    let params_before = p.params.clone();
    let bufs_before = p.node_param_bufs.clone();
    let mut jac = Mat::<f64>::zeros(y.len(), n_free);
    p.jacobian_into(jac.as_mut()).expect("jacobian_into");
    let _ = LeastSquaresProblem::jacobian(&p).expect("legacy jacobian");
    assert_eq!(p.params, params_before, "working parameters must not move");
    assert_eq!(p.node_param_bufs, bufs_before, "node buffers must not move");
}

/// A tied graph already used the FD Jacobian in the default mode; the switch
/// keeps that (forced OR tied), and the forced mode on a tied graph gives the
/// same matrix.
#[test]
fn tied_graph_uses_fd_in_both_modes() {
    let mut graph = single_node_graph(
        &ModelTypeStr::Gaussian,
        &[("amplitude", 3.0), ("center", 0.2), ("sigma", 0.9)],
    );
    graph.nodes.push(ModelNodeSpec {
        id: "m".into(),
        model_type: ModelTypeStr::Gaussian,
        dataset_index: None,
        parameters: [
            ("amplitude".to_string(), free_param(1.0)),
            ("center".to_string(), free_param(1.1)),
            ("sigma".to_string(), free_param(0.7)),
        ]
        .into_iter()
        .collect(),
    });
    graph.expr_edges.push(spectrafit_types::ExprEdge {
        target_node: "m".into(),
        target_param: "amplitude".into(),
        expression: "0.5 * n.amplitude".into(),
    });
    let cg = CompiledGraph::compile(&graph).expect("compiles");
    assert!(!cg.tied_plan.is_empty());
    let flat = flat_params(&graph);
    let x = grid_1d(-3.0, 3.0);
    let (y, sigma) = data_for(&cg, &flat, &x);
    let n_free = cg.free_keys.len();
    let setup = || {
        (
            vec![(f64::NEG_INFINITY, f64::INFINITY); n_free],
            vec![1.0; n_free],
        )
    };
    let mut forced = problem(
        &cg,
        &flat,
        setup(),
        (x.clone(), y.clone(), sigma.clone()),
        JacobianMode::FiniteDifference,
    );
    let mut default = problem(
        &cg,
        &flat,
        setup(),
        (x, y.clone(), sigma),
        JacobianMode::Analytic,
    );
    let p0: Vec<f64> = forced.params.iter().copied().collect();
    forced.set_free_and_tied(&p0);
    default.set_free_and_tied(&p0);
    assert!(forced.uses_fd_jacobian() && default.uses_fd_jacobian());
    let mut a = Mat::<f64>::zeros(y.len(), n_free);
    let mut b = Mat::<f64>::zeros(y.len(), n_free);
    forced.jacobian_into(a.as_mut()).expect("forced");
    default.jacobian_into(b.as_mut()).expect("default");
    assert_eq!(faer_rowmajor(&a), faer_rowmajor(&b));
}

/// The option is read in exactly one place: `fd_jacobian_forced` is true only
/// for the `finite_difference` mode, and an untied graph uses the analytic
/// Jacobian unless forced.
#[test]
fn switch_point_reads_the_option() {
    let model = ModelTypeStr::Gaussian;
    let fx = fixture(&model);
    let graph = single_node_graph(&model, &fx.params);
    let cg = CompiledGraph::compile(&graph).expect("compiles");
    let flat = flat_params(&graph);
    let (y, sigma) = data_for(&cg, &flat, &fx.x);
    let n_free = cg.free_keys.len();
    for (mode, forced) in [
        (JacobianMode::Analytic, false),
        (JacobianMode::FiniteDifference, true),
    ] {
        let p = problem(
            &cg,
            &flat,
            (
                vec![(f64::NEG_INFINITY, f64::INFINITY); n_free],
                vec![1.0; n_free],
            ),
            (fx.x.clone(), y.clone(), sigma.clone()),
            mode,
        );
        assert_eq!(p.fd_jacobian_forced(), forced);
        assert_eq!(p.uses_fd_jacobian(), forced);
    }
}
