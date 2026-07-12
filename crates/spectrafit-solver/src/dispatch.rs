//! `fit()` — the public solver entry point and dispatcher.
//!
//! Parses [`FitOptionsSpec::solver`] into a [`Solver`] and routes it: `irls`,
//! `global` and `varpro` dispatch early to their own module/crate, while the
//! Levenberg–Marquardt family (`lm`/`trf`/`geodesic`/`lm-legacy`, and `auto`'s
//! non-VarPro case) runs the shared pre-solve, solve and post-fit path here.
//!
//! Steps (LM-family path):
//!   1. Compile the graph → get `free_keys`
//!   2. Extract initial parameter vector + bounds
//!   3. Evaluate the model *before* optimisation (`init_fit`)
//!   4. Run `LevenbergMarquardt::minimize`
//!   5. Compute post-fit statistics: χ², reduced-χ², R², DOF, AIC, BIC
//!   6. Compute covariance matrix: (J_wᵀ J_w)⁻¹ when σ is user-supplied, else (JᵀJ)⁻¹ · (χ²/DOF)
//!   7. Assemble and return `FitResultSpec`

use std::cell::RefCell;
use std::collections::HashMap;

use levenberg_marquardt::LevenbergMarquardt;
use nalgebra::DVector;
use spectrafit_graph::{compiler::CompiledGraph, evaluate_compiled};
use spectrafit_types::{
    CoreError, FitGraphSpec, FitOptionsSpec, FitResultSpec, MeasurementSpec, TerminationReason,
};
use spectrafit_varpro;

use crate::error::SolverError;
use crate::global::{solve_global, DeConfig};
use crate::irls::{solve_irls, WeightFn};
use crate::postfit;
use crate::problem::LmProblem;

/// Flatten one dataset's `dims × points` coordinates into the **point-major**
/// (stride = n_dims) layout the executor's `coord_layout` expects: point `i`
/// occupies `x[i*n_dims .. (i+1)*n_dims]`. For the 1-D case this is exactly
/// `ds.x[0]`, so existing behaviour is unchanged; for n-D it interleaves the
/// per-dimension coordinate rows so a Gaussian2D node receives `[xᵢ, yᵢ]`.
pub(crate) fn point_major_x(ds: &MeasurementSpec) -> Vec<f64> {
    let n_dims = ds.x.len();
    if n_dims == 0 {
        return Vec::new();
    }
    let n_points = ds.x[0].len();
    let mut out = Vec::with_capacity(n_points * n_dims);
    for i in 0..n_points {
        for dim in &ds.x {
            out.push(dim[i]);
        }
    }
    out
}

// ---------------------------------------------------------------------------
// Solver dispatch
// ---------------------------------------------------------------------------

/// Every solver [`fit`] can dispatch to, parsed once from
/// [`FitOptionsSpec::solver`]. This enum + [`Solver::parse`] + the single match
/// in [`fit`] is the *one place* that answers "which solvers exist and where
/// does each one run":
///
/// * [`Lm`](Solver::Lm) / [`Trf`](Solver::Trf) / [`Geodesic`](Solver::Geodesic) /
///   [`LmLegacy`](Solver::LmLegacy) — the Levenberg–Marquardt family. All run the
///   shared pre-solve + solve below: the first three on the faer
///   `spectrafit-levenberg-marquardt` core (TRF = Coleman–Li bound scaling,
///   geodesic = Transtrum acceleration), `LmLegacy` on the nalgebra oracle.
/// * [`Irls`](Solver::Irls) / [`Global`](Solver::Global) / [`Varpro`](Solver::Varpro)
///   — distinct algorithms that dispatch early to their own module/crate.
/// * [`Auto`](Solver::Auto) — VarPro when the graph is separable, unconstrained
///   and untied (see [`graph_prefers_varpro`]), otherwise the faer LM family.
#[derive(Debug, Clone, Copy, PartialEq)]
enum Solver {
    /// Default faer Levenberg–Marquardt.
    Lm,
    /// nalgebra `levenberg-marquardt` parity oracle.
    LmLegacy,
    /// Trust-Region-Reflective (Coleman–Li bound scaling on the faer LM core).
    Trf,
    /// Geodesic acceleration on the faer LM core.
    Geodesic,
    /// Powell's dogleg trust-region method.
    Dogleg,
    /// Matrix-free Newton-CG (Steihaug–Toint) trust-region method.
    NewtonCg,
    /// Iteratively-reweighted least squares (robust loss).
    Irls(WeightFn),
    /// Differential Evolution (global search).
    Global,
    /// Variable Projection (separable nonlinear least squares).
    Varpro,
    /// Choose from the graph shape at run time.
    Auto,
}

impl Solver {
    /// Parse the `FitOptionsSpec.solver` string. Unrecognised strings fall back
    /// to the faer LM default, matching the historical `!= "lm-legacy"` behaviour.
    fn parse(s: &str) -> Self {
        match s {
            "lm-legacy" => Solver::LmLegacy,
            "trf" => Solver::Trf,
            "geodesic" | "lm-geodesic" => Solver::Geodesic,
            "dogleg" => Solver::Dogleg,
            "newton-cg" | "newton_cg" | "newtoncg" | "steihaug" => Solver::NewtonCg,
            "global" => Solver::Global,
            "varpro" => Solver::Varpro,
            "auto" => Solver::Auto,
            _ if s.starts_with("irls") => {
                let name = s.split_once(':').map(|(_, name)| name).unwrap_or("huber");
                Solver::Irls(WeightFn::from_str(name))
            }
            _ => Solver::Lm,
        }
    }
}

/// Whether a graph carries any tied parameters — a constraint expression from a
/// graph `expr_edge` OR a per-parameter `Parameter.expr`. VarPro reconstructs
/// parameters from the linear/nonlinear split and never applies the `TiedPlan`,
/// so a tied graph must never be routed to / accepted by VarPro on EITHER surface
/// (CX-VPE-01: checking `expr_edges` alone silently dropped `Parameter.expr` ties).
fn graph_has_tied_params(graph: &FitGraphSpec) -> bool {
    !graph.expr_edges.is_empty()
        || graph
            .nodes
            .iter()
            .any(|n| n.parameters.values().any(|p| p.expr.is_some()))
}

/// Whether `solver="auto"` should choose VarPro: the graph is separable, every
/// nonlinear parameter is unconstrained (VarPro ignores bounds), and there are no
/// tied parameters (via `expr_edges` or `Parameter.expr`; VarPro cannot honour them).
fn graph_prefers_varpro(graph: &FitGraphSpec) -> bool {
    !graph_has_tied_params(graph)
        // VarPro stacks all datasets and is not dataset_index-aware, so it must
        // not be auto-selected for simultaneous multi-dataset ("global analysis")
        // graphs — those need the LM-family scoped executor path.
        && graph.nodes.iter().all(|n| n.dataset_index.is_none())
        && spectrafit_varpro::is_separable(graph)
        && graph.nodes.iter().all(|n| {
            n.parameters
                .iter()
                // amplitude is the linear coeff VarPro projects out; skip it BY NAME
                // (HashMap order is non-deterministic, so positional `.skip(1)` could
                // drop an arbitrary nonlinear param and miss its bounds — silent bound
                // violation when that param is bounded but amplitude is not).
                .filter(|(name, _)| name.as_str() != "amplitude")
                .filter(|(_, p)| p.vary)
                .all(|(_, p)| p.min.is_infinite() && p.max.is_infinite())
        })
}

/// Build the `ParameterSpec` map and run VarPro. Shared by the explicit
/// `solver="varpro"` arm and the `solver="auto"`→VarPro arm.
fn solve_varpro_path(
    graph: &FitGraphSpec,
    datasets: &[MeasurementSpec],
    options: &FitOptionsSpec,
) -> Result<FitResultSpec, CoreError> {
    let mut param_specs: HashMap<String, spectrafit_types::ParameterSpec> = HashMap::new();
    for node in &graph.nodes {
        for (pname, pspec) in &node.parameters {
            param_specs.insert(format!("{}.{}", node.id, pname), pspec.clone());
        }
    }
    spectrafit_varpro::solve_varpro(graph, datasets, &param_specs, options)
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/// Run a Levenberg-Marquardt fit of `graph` against `datasets`.
///
/// Returns a fully populated [`FitResultSpec`] including parameter values,
/// standard errors, covariance matrix, and goodness-of-fit statistics.
pub fn fit(
    graph: &FitGraphSpec,
    datasets: Vec<MeasurementSpec>,
    options: &FitOptionsSpec,
) -> Result<FitResultSpec, CoreError> {
    // Run faer's dense kernels serially for the whole fit (solve loop AND the
    // post-fit covariance/condition-number). Our matrices are skinny (p ≲ 150),
    // so faer's default Rayon dispatch costs more in thread-pool wake-up than the
    // arithmetic — measured ~4–6× slowdown, including the n×p post-fit Gram/SVD.
    // The data-parallelism that pays off lives in the graph executor's own Rayon
    // path (over points). faer is solver-internal in this workspace, so setting
    // the global policy here is safe.
    faer::set_global_parallelism(faer::Par::Seq);

    // ── 0. Solver dispatch ───────────────────────────────────────────────────
    // Route the non-LM-family solvers to their own module/crate; the LM family
    // (Lm/LmLegacy/Trf/Geodesic, and Auto's non-VarPro case) falls through to the
    // shared pre-solve + solve below.
    let solver = Solver::parse(&options.solver);
    match solver {
        Solver::Irls(weight) => {
            return solve_irls(graph, datasets, options, weight, 20, options.tolerance);
        }
        Solver::Global => {
            // Honour the caller's iteration budget: map `max_iterations` onto the
            // number of DE generations. Without this the 500-generation budget the
            // benchmark passes for pathological cases was silently dropped and DE
            // ran with the 100-generation default.
            let config = DeConfig {
                max_gen: if options.max_iterations > 0 {
                    options.max_iterations as usize
                } else {
                    DeConfig::default().max_gen
                },
                ..DeConfig::default()
            };
            return solve_global(graph, datasets, options, config);
        }
        Solver::Varpro => {
            // Explicit VarPro: require separability, and reject tied params from
            // EITHER surface (expr_edges or Parameter.expr) — VarPro reconstructs
            // parameters from the linear/nonlinear split and never applies the
            // tied-plan, so a tie would be silently dropped (CX-VPE-01).
            if !spectrafit_varpro::is_separable(graph) {
                return Err(SolverError::VarproNotSeparable.into());
            }
            if graph_has_tied_params(graph) {
                return Err(SolverError::VarproExprEdgesUnsupported.into());
            }
            // VarPro stacks all datasets into one synthetic spec and is not
            // dataset_index-aware, so a per-dataset (local) node would silently
            // contribute to every dataset. Reject rather than mis-scope; the
            // LM-family solvers honour dataset_index (simultaneous global analysis).
            if graph.nodes.iter().any(|n| n.dataset_index.is_some()) {
                return Err(SolverError::VarproDatasetScopingUnsupported.into());
            }
            // VarPro builds its own result outside `assemble_result`, so apply the
            // shared success guards (off-domain runaway + degenerate collapse) here
            // — otherwise a degenerate VarPro fit would report false success.
            let mut result = solve_varpro_path(graph, &datasets, options)?;
            let x_all: Vec<f64> = datasets.iter().flat_map(point_major_x).collect();
            let y_all: Vec<f64> = datasets
                .iter()
                .flat_map(|ds| ds.y.iter().copied())
                .collect();
            let final_flat: HashMap<String, f64> = result
                .parameters
                .iter()
                .map(|(k, p)| (k.clone(), p.value))
                .collect();
            let vp_free_keys: Vec<String> = result
                .parameters
                .iter()
                .filter(|(_, p)| p.vary)
                .map(|(k, _)| k.clone())
                .collect();
            let (s, m) = postfit::apply_postfit_guards(
                graph,
                &vp_free_keys,
                &final_flat,
                &x_all,
                &y_all,
                result.r_squared,
                vp_free_keys.len(),
                result.success,
                result.message.clone(),
            );
            result.success = s;
            result.message = m;
            return Ok(result);
        }
        Solver::Auto if graph_prefers_varpro(graph) => {
            return solve_varpro_path(graph, &datasets, options);
        }
        // LM family + the Δ-radius methods (and Auto without VarPro) flow through
        // to the shared pre-solve + solve below.
        Solver::Lm
        | Solver::LmLegacy
        | Solver::Trf
        | Solver::Geodesic
        | Solver::Dogleg
        | Solver::NewtonCg
        | Solver::Auto => {}
    }

    // ── 1. Compile graph ────────────────────────────────────────────────────
    let mut cg = CompiledGraph::compile(graph)?;
    // Per-dataset point boundaries (cumulative, len = n_datasets + 1) so the
    // executor can scope a node with `dataset_index = Some(i)` to dataset i's
    // contiguous point-range — the primitive for simultaneous multi-dataset
    // ("global analysis") fits. Left as the single-range no-op for one dataset.
    cg.dataset_offsets = {
        let mut offs = Vec::with_capacity(datasets.len() + 1);
        let mut acc = 0usize;
        offs.push(0);
        for ds in &datasets {
            acc += ds.y.len();
            offs.push(acc);
        }
        offs
    };
    let free_keys = cg.free_keys.clone();

    // ── 2. Build flat map of ALL parameters (free + fixed) ─────────────────
    let mut all_params: HashMap<String, f64> = HashMap::new();
    for node in &graph.nodes {
        for (pname, pspec) in &node.parameters {
            let key = format!("{}.{}", node.id, pname);
            all_params.insert(key, pspec.value);
        }
    }

    // ── 3. Extract initial values + bounds for free params ──────────────────
    let mut init_vals: Vec<f64> = Vec::with_capacity(free_keys.len());
    let mut bounds: Vec<(f64, f64)> = Vec::with_capacity(free_keys.len());
    // Per-free-parameter scale factors. `Parameter.scale` is plumbed through the
    // schema but never consumed by any solver today; `scales[i]` collects the
    // requested factor (defaulting to 1.0) so the scale-normalization hook below
    // can rescale the optimiser's view of each parameter once wired in.
    let mut scales: Vec<f64> = Vec::with_capacity(free_keys.len());

    for key in &free_keys {
        // key = "node_id.param_name"
        let (node_id, param_name) = key
            .split_once('.')
            .ok_or_else(|| SolverError::Dispatch(format!("malformed free key: '{}'", key)))?;

        let node = graph
            .nodes
            .iter()
            .find(|n| n.id == node_id)
            .ok_or_else(|| SolverError::Dispatch(format!("node '{}' not found", node_id)))?;

        let pspec = node.parameters.get(param_name).ok_or_else(|| {
            SolverError::Dispatch(format!(
                "param '{}' not found in node '{}'",
                param_name, node_id
            ))
        })?;

        init_vals.push(pspec.value);
        bounds.push((pspec.min, pspec.max));
        // A non-finite or non-positive scale is meaningless for normalization;
        // fall back to the identity (1.0) so it is a no-op.
        let s = pspec.scale.unwrap_or(1.0);
        scales.push(if s.is_finite() && s > 0.0 { s } else { 1.0 });
    }

    let init_vals_clone = init_vals.clone();
    // The solver optimises the scaled working variable θ'_i = θ_i / s_i, so its
    // starting point is the physical initial value divided by the scale factor
    // (a no-op when s_i = 1.0). `node_param_bufs` is still seeded from the
    // physical `init_vals_clone` below.
    let init_params = DVector::from_vec(
        init_vals
            .iter()
            .zip(scales.iter())
            .map(|(&v, &s)| v / s)
            .collect::<Vec<f64>>(),
    );

    // ── 4. Build per-point sigma vector (default = 1.0) ─────────────────────
    let sigma: Vec<f64> = datasets
        .iter()
        .flat_map(|ds| {
            let n = ds.y.len();
            match &ds.sigma {
                Some(s) => s.clone(),
                None => vec![1.0_f64; n],
            }
        })
        .collect();

    // ── 5. Concatenated x and y for all datasets (cached in the problem) ────
    // Point-major (stride = n_dims) so the executor reads each point's full
    // coordinate; 1-D reduces to the old per-dataset `ds.x[0]` concatenation.
    let x_all: Vec<f64> = datasets.iter().flat_map(point_major_x).collect();

    let y_all: Vec<f64> = datasets
        .iter()
        .flat_map(|ds| ds.y.iter().copied())
        .collect();

    // ── 6. Evaluate initial model (before optimisation) ─────────────────────
    let init_fit = evaluate_compiled(&cg, &all_params, &x_all)?;

    // ── 7. Build index-based node param buffers ──────────────────────────────
    // node_param_bufs[i]: current param values for cg.nodes[i], in model
    // param_names() order.  Fixed params are pre-filled and never changed.
    // Free params are updated in-place by LmProblem::set_params().
    let mut node_param_bufs: Vec<Vec<f64>> = (0..cg.nodes.len())
        .map(|i| {
            cg.node_params(i, &all_params)
                .unwrap_or_else(|_| vec![0.0; cg.nodes[i].param_names.len()])
        })
        .collect();

    // free_to_node_param: maps free-key index → (node_idx, param_pos_in_node).
    // Derived directly from cg.node_free_cols which was built during compile().
    let free_to_node_param: Vec<(usize, usize)> = {
        // Invert node_free_cols: for each free_key index (col), find the
        // (node_idx, local_param_idx) pair.
        let mut mapping = vec![(0usize, 0usize); cg.free_keys.len()];
        for (node_idx, pairs) in cg.node_free_cols.iter().enumerate() {
            for &(local_idx, col) in pairs {
                mapping[col] = (node_idx, local_idx);
            }
        }
        mapping
    };

    // Apply initial bounds clamping to node_param_bufs for free params.
    for (i, &(node_idx, param_pos)) in free_to_node_param.iter().enumerate() {
        let (lo, hi) = bounds[i];
        node_param_bufs[node_idx][param_pos] = init_vals_clone[i].clamp(lo, hi);
    }

    // Map each tied target (in `tied_plan.order`) to its `(node_idx, param_pos)`
    // slot in `node_param_bufs`, so the solver can write each recomputed tied
    // value back. Empty when the graph declares no ties (`expr_edges` or `Parameter.expr`).
    let tied_to_node_param: Vec<(usize, usize)> =
        cg.tied_plan
            .order
            .iter()
            .map(|tp| {
                let (nid, pname) = tp.target.split_once('.').ok_or_else(|| {
                    SolverError::MalformedTiedTarget(tp.target.clone())
                })?;
                let ni = cg.nodes.iter().position(|n| n.id == nid).ok_or_else(|| {
                    SolverError::TiedTargetNodeMissing(nid.to_string())
                })?;
                let pos = cg.nodes[ni]
                    .param_names
                    .iter()
                    .position(|p| p == pname)
                    .ok_or_else(|| SolverError::TiedTargetParamMissing(pname.to_string()))?;
                Ok::<(usize, usize), CoreError>((ni, pos))
            })
            .collect::<Result<_, _>>()?;

    // ── 7b. Per-parameter scale normalization (Parameter.scale → LM step) ─────
    //
    // `Parameter.scale` lets a caller request that a parameter be optimised in
    // rescaled units (e.g. an amplitude ~1e6 alongside a width ~1e-3). The solver
    // operates on the rescaled variable `θ'_i = θ_i / s_i`, which equalises the
    // columns of the Jacobian and thereby reshapes — and typically improves — the
    // conditioning of `JᵀJ` (see the condition-number computation in §11). The
    // wiring is now end-to-end:
    //   1. `init_params` (above) is the physical start divided by `scales[i]`,
    //   2. `LmProblem` carries `scales`; `set_params`/`params` translate between
    //      scaled (optimiser) and physical (`node_param_bufs`) coordinates and the
    //      analytic/FD Jacobian columns are multiplied by `scales[i]` (chain rule),
    //   3. `node_param_bufs` — and hence `to_flat` / the reported result — is
    //      always physical, so the converged values come back in real units.
    // The post-fit condition number (§11 of postfit) applies the same column
    // scaling so it reflects the optimiser's effective conditioning.
    //
    // With all-default (None ⇒ 1.0) scales every step above is an exact
    // arithmetic no-op, so a fit without any `scale` set is byte-for-byte
    // unchanged — the parity oracle (`tests/parity.rs`) pins this.
    debug_assert_eq!(
        scales.len(),
        free_keys.len(),
        "one scale factor per free parameter"
    );

    // ── 8. Construct problem and run LM ──────────────────────────────────────
    let mut problem = LmProblem {
        compiled: &cg,
        datasets: &datasets,
        free_keys: free_keys.clone(),
        bounds: bounds.clone(),
        all_params: all_params.clone(),
        node_param_bufs,
        free_to_node_param,
        tied_to_node_param,
        x_concat: x_all.clone(),
        y_concat: y_all.clone(),
        params: init_params,
        scales: scales.clone(),
        sigma,
        residual_buf: RefCell::new(vec![0.0; y_all.len()]),
        // One Jacobian row per data point (residual), not per coordinate: size by
        // the point count (y_all.len()), which equals x_all.len() only in 1-D.
        jacobian_buf: RefCell::new(vec![0.0; y_all.len() * free_keys.len()]),
        residual_count: RefCell::new(0),
        jacobian_count: RefCell::new(0),
        residual_time_ns: RefCell::new(0),
        jacobian_time_ns: RefCell::new(0),
    };

    // Initialise tied parameters from the starting free values. `node_param_bufs`
    // was seeded with the tied-target *placeholders* (their spec `value`, e.g.
    // 0.0); without this the first residual/Jacobian would evaluate the model
    // with stale tied values. No-op for graphs without ties (`expr_edges` or `Parameter.expr`).
    if problem.has_tied() {
        let p0: Vec<f64> = problem.params.iter().copied().collect();
        problem.set_free_and_tied(&p0);
    }

    // `patience` controls max function evaluations = patience * (n_params + 1)
    let patience = (options.max_iterations as usize).max(1);

    // Solver engine selection. The faer-native trust-region core is the default
    // for every LM-family solver string (`"lm"`, `"auto"`, `"lm-faer"`); the
    // proven `levenberg-marquardt` (nalgebra) crate is retained as the
    // `"lm-legacy"` oracle for parity testing until it is removed (M8).
    let tol = if options.tolerance > 0.0 {
        options.tolerance
    } else {
        1e-8
    };
    let max_nfev = patience.saturating_mul(free_keys.len() + 1);
    let _solve_t0 = std::time::Instant::now();
    let (
        mut result_problem,
        n_iter_val,
        success_val,
        message_val,
        cost_history,
        gradient_norm_history,
        params_history,
    ) = match solver {
        Solver::LmLegacy => {
            // Retained nalgebra `levenberg-marquardt` crate — the parity oracle.
            // It does not expose a per-iteration trajectory, so the history stays
            // empty (the benchmark layer reconstructs a labelled proxy).
            let lm = LevenbergMarquardt::new().with_patience(patience);
            let lm = if options.tolerance > 0.0 {
                lm.with_tol(options.tolerance)
            } else {
                lm
            };
            let (rp, report) = lm.minimize(problem);
            (
                rp,
                report.number_of_evaluations as u64,
                report.termination.was_successful(),
                map_termination(&report.termination).as_str().to_string(),
                Vec::new(),
                Vec::new(),
                Vec::new(),
            )
        }
        Solver::Dogleg | Solver::NewtonCg => {
            // Explicit Δ-radius trust-region methods on the shared framework loop.
            // `Report`/`Termination` are the same types the faer LM core returns.
            // Cycle 8.2 — power-user knobs for the TR core. Each `Option<f64>` on
            // `FitOptionsSpec` keeps the library default when `None`, so the wire
            // surface remains backward-compatible. The TR driver clamps `delta0`
            // and `max_delta` internally; we just pass through what the caller set.
            let mut cfg = spectrafit_dogleg::TrustRegionConfig {
                ftol: tol,
                xtol: tol,
                gtol: tol,
                max_nfev,
                ..Default::default()
            };
            if let Some(d0) = options.delta0 {
                cfg.delta0 = d0;
            }
            if let Some(md) = options.max_delta {
                cfg.max_delta = md;
            }
            if let Some(e) = options.eta {
                cfg.eta = e;
            }
            let report = if solver == Solver::Dogleg {
                spectrafit_dogleg::minimize(&mut problem, &cfg)
            } else {
                spectrafit_newton_cg::minimize(&mut problem, &cfg)
            };
            let msg = faer_termination_str(report.termination).to_string();
            (
                problem,
                report.n_iter as u64,
                report.termination.was_successful(),
                msg,
                report.cost_history,
                report.gradient_norm_history,
                report.params_history,
            )
        }
        // LM family: lm / trf / geodesic / auto on the faer LM core. Regime-adaptive
        // (normal equations for tall-skinny, SVD/secular for many-parameter), with
        // Moré column scaling applied inside the driver.
        _ => {
            let cfg = spectrafit_levenberg_marquardt::StrategyConfig {
                kind: spectrafit_levenberg_marquardt::select_regime(y_all.len(), free_keys.len()),
                ftol: tol,
                xtol: tol,
                gtol: tol,
                max_nfev,
                // `solver="geodesic"` (Transtrum acceleration) — faster on sloppy /
                // degenerate multi-peak surfaces; otherwise plain faer LM.
                geodesic: solver == Solver::Geodesic,
                // `solver="trf"` (Trust-Region-Reflective) — Coleman–Li bound scaling
                // so steps shrink near active bounds. `solver="auto"` that did not
                // route to VarPro also lands here as TRF: the solver bake-off
                // (python/extras/publication/solver_bakeoff.md) showed TRF is the
                // fastest LM-family strategy at top accuracy across nearly every
                // problem class, so it is the data-driven default for `auto`.
                bound_scaling: solver == Solver::Trf || solver == Solver::Auto,
                ..Default::default()
            };
            let report = spectrafit_levenberg_marquardt::minimize(&mut problem, &cfg);
            let msg = faer_termination_str(report.termination).to_string();
            (
                problem,
                report.n_iter as u64,
                report.termination.was_successful(),
                msg,
                report.cost_history,
                report.gradient_norm_history,
                report.params_history,
            )
        }
    };
    let solve_ns = _solve_t0.elapsed().as_nanos();

    postfit::assemble_result(
        &mut result_problem,
        &cg,
        graph,
        &datasets,
        &x_all,
        &y_all,
        init_fit,
        n_iter_val,
        success_val,
        message_val,
        solve_ns,
        cost_history,
        gradient_norm_history,
        params_history,
    )
}

// ---------------------------------------------------------------------------
// Private helpers
// ---------------------------------------------------------------------------

/// Stable snake_case message for a faer-native [`spectrafit_levenberg_marquardt::Termination`].
fn faer_termination_str(t: spectrafit_levenberg_marquardt::Termination) -> &'static str {
    use spectrafit_levenberg_marquardt::Termination as T;
    match t {
        T::Gtol => "converged_gtol",
        T::Ftol => "converged_ftol",
        T::Xtol => "converged_xtol",
        T::ResidualsZero => "residuals_zero",
        T::MaxEval => "max_iterations",
        T::NoImprovement => "no_improvement_possible",
        T::NumericalError => "numerical_error",
    }
}

/// Map the `levenberg_marquardt` crate's `TerminationReason` onto our own
/// stable enum so callers get a deterministic snake_case string, not a
/// debug-format blob that changes with crate versions.
fn map_termination(lm: &levenberg_marquardt::TerminationReason) -> TerminationReason {
    use levenberg_marquardt::TerminationReason as L;
    match lm {
        L::ResidualsZero => TerminationReason::ResidualsZero,
        L::Orthogonal => TerminationReason::Orthogonal,
        L::Converged { .. } => TerminationReason::Converged,
        L::LostPatience => TerminationReason::MaxIterations,
        L::NoImprovementPossible(_) => TerminationReason::NoImprovementPossible,
        L::NoParameters => TerminationReason::NoParameters,
        L::NoResiduals => TerminationReason::NoResiduals,
        L::WrongDimensions(_) => TerminationReason::WrongDimensions,
        L::Numerical(_) => TerminationReason::NumericalError,
        L::User(_) => TerminationReason::UserCancelled,
    }
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
    use std::collections::HashMap;

    // ── helpers ──────────────────────────────────────────────────────────────

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

    fn default_options() -> FitOptionsSpec {
        FitOptionsSpec {
            schema_version: None,
            solver: "lm".to_string(),
            max_iterations: 200,
            tolerance: 1e-8,
            delta0: None,
            max_delta: None,
            eta: None,
        }
    }

    /// Analytical Gaussian: A · exp(−(x−c)² / (2σ²))
    fn gaussian(x: f64, amplitude: f64, center: f64, sigma: f64) -> f64 {
        amplitude * (-(x - center).powi(2) / (2.0 * sigma * sigma)).exp()
    }

    // ── Test 1: Gaussian parameter recovery ──────────────────────────────────

    #[test]
    fn test_gaussian_recovery() {
        // True parameters
        let (true_a, true_c, true_s) = (5.0_f64, 2.0_f64, 0.5_f64);

        // x grid: 50 points in [−1, 5]
        let n = 50usize;
        let x: Vec<f64> = (0..n)
            .map(|i| -1.0 + 6.0 * i as f64 / (n - 1) as f64)
            .collect();
        let y: Vec<f64> = x
            .iter()
            .map(|&xi| gaussian(xi, true_a, true_c, true_s))
            .collect();

        // Graph with perturbed initial params
        let mut params: HashMap<String, ParameterSpec> = HashMap::new();
        params.insert("amplitude".into(), make_param(4.0, true));
        params.insert("center".into(), make_param(1.8, true));
        params.insert("sigma".into(), make_param(0.6, true));

        let graph = FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![ModelNodeSpec {
                id: "g1".into(),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: None,
                parameters: params,
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

        let result = fit(&graph, vec![dataset], &default_options()).expect("fit should not error");

        assert!(
            result.success,
            "LM should converge; message: {}",
            result.message
        );
        assert!(
            result.n_iter > 0,
            "should have done at least one evaluation"
        );
        assert!(
            result.chi2 < 1e-10,
            "chi2 = {} should be near zero",
            result.chi2
        );

        let a = result.parameters["g1.amplitude"].value;
        let c = result.parameters["g1.center"].value;
        let s = result.parameters["g1.sigma"].value;

        assert_relative_eq!(a, true_a, max_relative = 0.01);
        assert_relative_eq!(c, true_c, max_relative = 0.01);
        assert_relative_eq!(s, true_s, max_relative = 0.01);
    }

    // ── Test 2: Constant model trivial fit ────────────────────────────────────

    #[test]
    fn test_constant_recovery() {
        let n = 20usize;
        let x: Vec<f64> = (0..n).map(|i| i as f64 / (n - 1) as f64).collect();
        // Tiny deterministic "noise" to avoid a perfectly flat problem
        let y: Vec<f64> = x
            .iter()
            .enumerate()
            .map(|(i, _)| 3.0 + 1e-6 * (i as f64 * 0.1).sin())
            .collect();

        let mut params: HashMap<String, ParameterSpec> = HashMap::new();
        params.insert("c".into(), make_param(0.0, true)); // start far from 3

        let graph = FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![ModelNodeSpec {
                id: "const1".into(),
                model_type: ModelTypeStr::Constant,
                dataset_index: None,
                parameters: params,
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

        let result = fit(&graph, vec![dataset], &default_options()).expect("fit should not error");

        assert!(
            result.success,
            "LM should converge; message: {}",
            result.message
        );

        let c_val = result.parameters["const1.c"].value;
        assert!(
            (c_val - 3.0).abs() < 1e-4,
            "recovered constant = {}, expected ≈ 3.0",
            c_val
        );
    }

    // ── SP-2: N-D (gaussian_nd) end-to-end fits ───────────────────────────────
    //
    // The compiler infers D from the node's `center_<i>` parameters and builds a
    // `GaussianND` of that dimensionality; the N-D-general executor strides the
    // coordinate buffer at stride D and the LM solver recovers every parameter.
    // Both 3-D and 5-D run, so "arbitrary N" is exercised, not extrapolated.
    fn run_gaussian_nd_recovery(d: usize) {
        let amp = 3.0_f64;
        let centers: Vec<f64> = (0..d).map(|i| -1.0 + 0.5 * i as f64).collect();
        let sigmas: Vec<f64> = (0..d).map(|i| 0.8 + 0.1 * i as f64).collect();

        // Keep the grid tiny so d=5 stays cheap (5^5 = 3125 points).
        let axis_n = if d <= 3 { 7 } else { 5 };
        let axis: Vec<f64> = (0..axis_n)
            .map(|i| -3.0 + 6.0 * i as f64 / (axis_n - 1) as f64)
            .collect();
        // Cartesian product of the axis over d dimensions → point coordinates.
        let mut coords: Vec<Vec<f64>> = vec![vec![]];
        for _dim in 0..d {
            let mut next = Vec::with_capacity(coords.len() * axis.len());
            for prefix in &coords {
                for &a in &axis {
                    let mut p = prefix.clone();
                    p.push(a);
                    next.push(p);
                }
            }
            coords = next;
        }
        let g = |pt: &[f64]| -> f64 {
            let mut z = 0.0;
            for i in 0..d {
                let dx = pt[i] - centers[i];
                z -= dx * dx / (2.0 * sigmas[i] * sigmas[i]);
            }
            amp * z.exp()
        };
        let y: Vec<f64> = coords.iter().map(|pt| g(pt)).collect();
        let n_points = coords.len();
        // Dimension-major x: x[dim] is the coordinate array for axis `dim`.
        let x: Vec<Vec<f64>> = (0..d)
            .map(|dim| (0..n_points).map(|p| coords[p][dim]).collect())
            .collect();

        let mut params: HashMap<String, ParameterSpec> = HashMap::new();
        params.insert("amplitude".into(), make_param(2.0, true));
        for (i, &center) in centers.iter().enumerate() {
            params.insert(format!("center_{i}"), make_param(center + 0.3, true));
            params.insert(format!("sigma_{i}"), make_param(1.0, true));
        }
        let graph = FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![ModelNodeSpec {
                id: "gnd".into(),
                model_type: ModelTypeStr::GaussianNd,
                dataset_index: None,
                parameters: params,
            }],
            expr_edges: vec![],
        };
        let dataset = MeasurementSpec {
            schema_version: None,
            x,
            y,
            sigma: None,
            label: None,
        };
        let result =
            fit(&graph, vec![dataset], &default_options()).expect("N-D fit should not error");
        assert!(result.success, "LM should converge on {d}-D; msg: {}", result.message);
        let p = &result.parameters;
        assert_relative_eq!(p["gnd.amplitude"].value, amp, max_relative = 0.02);
        for i in 0..d {
            assert_relative_eq!(
                p[&format!("gnd.center_{i}")].value,
                centers[i],
                epsilon = 0.05
            );
            assert_relative_eq!(
                p[&format!("gnd.sigma_{i}")].value,
                sigmas[i],
                epsilon = 0.05
            );
        }
    }

    #[test]
    fn gaussian_nd_fit_recovers_3d() {
        run_gaussian_nd_recovery(3);
    }

    #[test]
    fn gaussian_nd_fit_recovers_5d_arbitrary_n() {
        run_gaussian_nd_recovery(5);
    }

    // ── TDD: tied-parameter (expr_edge) end-to-end fit ────────────────────────
    //
    // The compiler builds a dependency-ordered `tied_plan` (parse +
    // topo-order + cycle-detection). The LM solver loop calls `TiedPlan::apply`
    // on every iteration, so tied parameters are recomputed from `expr_edges` and
    // `Parameter.expr` at each step. These tests run unconditionally and pass.

    /// Build a two-Gaussian graph where `g2.amplitude = k * g1.amplitude`.
    ///
    /// The tie is expressed through the top-level `expr_edge` list only.
    /// `ParameterSpec.expr` is intentionally `None` on the tied amplitude so
    /// this helper exercises the legacy `expr_edge` path without triggering the
    /// `DuplicateExprTarget` error that T1 introduced when both routes target
    /// the same parameter.
    fn tied_two_gaussian_graph(k: f64) -> FitGraphSpec {
        let mut g1: HashMap<String, ParameterSpec> = HashMap::new();
        g1.insert("amplitude".into(), make_param(4.0, true));
        g1.insert("center".into(), make_param(-1.0, true));
        g1.insert("sigma".into(), make_param(0.5, true));

        let mut g2: HashMap<String, ParameterSpec> = HashMap::new();
        // `vary = false`, `expr = None` — the tie lives in expr_edges below.
        g2.insert("amplitude".into(), make_param(0.0, false));
        g2.insert("center".into(), make_param(1.0, true));
        g2.insert("sigma".into(), make_param(0.5, true));

        FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![
                ModelNodeSpec {
                    id: "g1".into(),
                    model_type: ModelTypeStr::Gaussian,
                    dataset_index: None,
                    parameters: g1,
                },
                ModelNodeSpec {
                    id: "g2".into(),
                    model_type: ModelTypeStr::Gaussian,
                    dataset_index: None,
                    parameters: g2,
                },
            ],
            expr_edges: vec![spectrafit_types::ExprEdge {
                target_node: "g2".into(),
                target_param: "amplitude".into(),
                expression: format!("{} * g1.amplitude", k),
            }],
        }
    }

    /// A tied fit recovers `g2.amplitude == k * g1.amplitude` (wired in M6).
    #[test]
    fn test_tied_amplitude_fit_recovers_ratio() {
        let k = 0.5_f64;
        let (true_a, true_s) = (5.0_f64, 0.5_f64);
        let n = 80usize;
        let x: Vec<f64> = (0..n)
            .map(|i| -3.0 + 6.0 * i as f64 / (n - 1) as f64)
            .collect();
        let y: Vec<f64> = x
            .iter()
            .map(|&xi| gaussian(xi, true_a, -1.0, true_s) + gaussian(xi, k * true_a, 1.0, true_s))
            .collect();

        let graph = tied_two_gaussian_graph(k);
        let dataset = MeasurementSpec {
            schema_version: None,
            x: vec![x],
            y,
            sigma: None,
            label: None,
        };
        let result = fit(&graph, vec![dataset], &default_options()).unwrap();

        assert!(
            result.success,
            "tied fit should converge: {}",
            result.message
        );
        let a1 = result.parameters["g1.amplitude"].value;
        let a2 = result.parameters["g2.amplitude"].value;
        // The tied plan enforces the ratio exactly each iteration…
        assert_relative_eq!(a2, k * a1, epsilon = 1e-9);
        // …and the free amplitude is recovered.
        assert_relative_eq!(a1, true_a, max_relative = 1e-3);
    }

    /// End-to-end proof that a `Parameter.expr`-only tie (no `expr_edge`) is
    /// honoured by the solver — the tied parameter tracks its derived value at
    /// the converged solution, not its initial placeholder.
    ///
    /// The graph expresses `g2.amplitude = 0.5 * g1.amplitude` purely through
    /// `ParameterSpec.expr`; the `expr_edges` list is intentionally **empty**.
    /// T1 folds `Parameter.expr` into the compiled `TiedPlan`, and the solver
    /// calls `set_free_and_tied` each iteration, so `g2.amplitude` is recomputed
    /// from the current `g1.amplitude` on every step.
    #[test]
    fn test_param_expr_fit_recovers_derived_value() {
        let k = 0.5_f64;
        let (true_a, true_s) = (5.0_f64, 0.5_f64);
        let n = 80usize;
        let x: Vec<f64> = (0..n)
            .map(|i| -3.0 + 6.0 * i as f64 / (n - 1) as f64)
            .collect();
        // Synthesise data from the known-true parameters consistent with the tie.
        let y: Vec<f64> = x
            .iter()
            .map(|&xi| {
                gaussian(xi, true_a, -1.0, true_s) + gaussian(xi, k * true_a, 1.0, true_s)
            })
            .collect();

        // Build a graph identical to `tied_two_gaussian_graph(k)` **except** the
        // `expr_edges` list is empty — the tie lives solely in `Parameter.expr`.
        let mut g1: HashMap<String, ParameterSpec> = HashMap::new();
        g1.insert("amplitude".into(), make_param(4.0, true));
        g1.insert("center".into(), make_param(-1.0, true));
        g1.insert("sigma".into(), make_param(0.5, true));

        let mut g2: HashMap<String, ParameterSpec> = HashMap::new();
        let mut tied_amp = make_param(0.0, false);
        tied_amp.expr = Some(format!("{} * g1.amplitude", k));
        g2.insert("amplitude".into(), tied_amp);
        g2.insert("center".into(), make_param(1.0, true));
        g2.insert("sigma".into(), make_param(0.5, true));

        let graph = FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![
                ModelNodeSpec {
                    id: "g1".into(),
                    model_type: ModelTypeStr::Gaussian,
                    dataset_index: None,
                    parameters: g1,
                },
                ModelNodeSpec {
                    id: "g2".into(),
                    model_type: ModelTypeStr::Gaussian,
                    dataset_index: None,
                    parameters: g2,
                },
            ],
            // Intentionally empty — the tie is expressed only via Parameter.expr.
            expr_edges: vec![],
        };

        let dataset = MeasurementSpec {
            schema_version: None,
            x: vec![x],
            y,
            sigma: None,
            label: None,
        };
        let result = fit(&graph, vec![dataset], &default_options()).unwrap();

        assert!(
            result.success,
            "param-expr tied fit should converge: {}",
            result.message
        );
        let a1 = result.parameters["g1.amplitude"].value;
        let a2 = result.parameters["g2.amplitude"].value;
        // `g2.amplitude` must equal `k * g1.amplitude` at the solution — not
        // the initial placeholder (0.0).
        assert!(
            a2.abs() > 1e-6,
            "tied param must not be frozen at placeholder 0.0"
        );
        assert_relative_eq!(a2, k * a1, epsilon = 1e-9);
        // The free amplitude must recover the ground truth.
        assert_relative_eq!(a1, true_a, max_relative = 1e-3);
    }

    /// The tied parameter is excluded from the free set, so the solver reports
    /// DOF = n_points − n_free with n_free reduced by the tied count.
    #[test]
    fn test_tied_fit_reduces_free_param_count() {
        let graph = tied_two_gaussian_graph(0.5);
        let cg = CompiledGraph::compile(&graph).unwrap();
        // 6 params total, 1 tied (g2.amplitude) → 5 free.
        assert_eq!(cg.free_keys.len(), 5);
        assert_eq!(cg.tied_plan.len(), 1);
    }

    // ── Helper: build a well-conditioned single-Gaussian fit problem ──────────

    /// Returns a graph + dataset that recovers a clean Gaussian. `scale` is a
    /// base `Parameter.scale` factor (`None` ⇒ all parameters unset, i.e. 1.0).
    ///
    /// When `Some(base)`, a deliberately **non-uniform** scale is applied across
    /// the three parameters — `amplitude·base`, `center` unscaled, `sigma/base`.
    /// This is intentional: a *uniform* column scaling `J → J·(s·I)` multiplies
    /// `JᵀJ` by `s²` and leaves `κ(JᵀJ) = σ_max/σ_min` exactly invariant, so it
    /// could never change the reported conditioning. Spreading the scale across
    /// the columns changes their relative norms, which is what actually reshapes
    /// `κ(JᵀJ)` (see `parameter_scale_changes_effective_conditioning`).
    fn gaussian_fit_inputs(scale: Option<f64>) -> (FitGraphSpec, MeasurementSpec) {
        let (true_a, true_c, true_s) = (5.0_f64, 2.0_f64, 0.5_f64);
        let n = 50usize;
        let x: Vec<f64> = (0..n)
            .map(|i| -1.0 + 6.0 * i as f64 / (n - 1) as f64)
            .collect();
        let y: Vec<f64> = x
            .iter()
            .map(|&xi| gaussian(xi, true_a, true_c, true_s))
            .collect();

        let mk = |value: f64, scale: Option<f64>| ParameterSpec {
            value,
            min: f64::NEG_INFINITY,
            max: f64::INFINITY,
            vary: true,
            expr: None,
            scale,
        };
        // Non-uniform scale spread (see doc comment) so κ(JᵀJ) genuinely changes.
        let (sa, sc, ss) = match scale {
            None => (None, None, None),
            Some(base) => (Some(base), Some(1.0), Some(1.0 / base)),
        };
        let mut params: HashMap<String, ParameterSpec> = HashMap::new();
        params.insert("amplitude".into(), mk(4.0, sa));
        params.insert("center".into(), mk(1.8, sc));
        params.insert("sigma".into(), mk(0.6, ss));

        let graph = FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![ModelNodeSpec {
                id: "g1".into(),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: None,
                parameters: params,
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
        (graph, dataset)
    }

    // ── GREEN: condition number is computed end-to-end through the LM path ────

    #[test]
    fn condition_number_is_some_and_finite_after_gaussian_fit() {
        let (graph, dataset) = gaussian_fit_inputs(None);
        let result = fit(&graph, vec![dataset], &default_options()).expect("fit should not error");
        let cond = result
            .condition_number
            .expect("well-conditioned Gaussian fit should report a condition number");
        assert!(cond.is_finite(), "condition number must be finite: {cond}");
        assert!(cond >= 1.0, "condition number must be ≥ 1.0: {cond}");
    }

    // ── U3: Parameter.scale is wired into the LM step / Jacobian ──────────────

    #[test]
    fn parameter_scale_changes_effective_conditioning() {
        // Same problem, once unscaled and once with a deliberately non-uniform
        // `Parameter.scale` spread across the free parameters (see
        // `gaussian_fit_inputs`). With scale wired into the LM step and Jacobian,
        // the reported condition number must differ — the per-column scaling
        // reshapes the columns of J and hence κ(JᵀJ). (A *uniform* scale would be
        // κ-invariant, which is why the helper spreads it across columns.)
        let (g_unscaled, d_unscaled) = gaussian_fit_inputs(None);
        let (g_scaled, d_scaled) = gaussian_fit_inputs(Some(1000.0));

        let r_unscaled =
            fit(&g_unscaled, vec![d_unscaled], &default_options()).expect("unscaled fit");
        let r_scaled = fit(&g_scaled, vec![d_scaled], &default_options()).expect("scaled fit");

        let c0 = r_unscaled
            .condition_number
            .expect("unscaled fit should report κ");
        let c1 = r_scaled
            .condition_number
            .expect("scaled fit should report κ");
        assert!(
            (c0 - c1).abs() > 1e-6,
            "Parameter.scale should change effective conditioning: κ_unscaled={c0}, κ_scaled={c1}"
        );
    }

    #[test]
    fn parameter_scale_of_one_is_a_bitwise_no_op() {
        // The parity contract: `scale = Some(1.0)` on every free parameter must be
        // byte-for-byte identical to `scale = None` (the un-scaled path). Every
        // scaling operation reduces to multiply/divide by 1.0, which is exact in
        // IEEE-754, so the reported κ — and the recovered parameters — must match
        // to the last bit, not merely within a tolerance.
        let (g_none, d_none) = gaussian_fit_inputs(None);
        let g_one = {
            let mut g = g_none.clone();
            for p in g.nodes[0].parameters.values_mut() {
                p.scale = Some(1.0);
            }
            g
        };

        let r_none = fit(&g_none, vec![d_none.clone()], &default_options()).expect("none fit");
        let r_one = fit(&g_one, vec![d_none], &default_options()).expect("scale=1 fit");

        assert_eq!(
            r_none.condition_number, r_one.condition_number,
            "scale=Some(1.0) must reproduce the un-scaled κ bit-for-bit"
        );
        for (key, p_none) in &r_none.parameters {
            let p_one = &r_one.parameters[key];
            assert_eq!(
                p_none.value, p_one.value,
                "scale=1 changed converged value of {key}: {} vs {}",
                p_none.value, p_one.value
            );
        }
    }

    // ── auto-routing: non-VarPro graph → TRF ─────────────────────────────────

    #[test]
    fn auto_routes_to_trf_for_bounded_graph() {
        // A bounded sigma disqualifies the graph from VarPro (graph_prefers_varpro
        // requires unconstrained nonlinear params), so `solver="auto"` must fall
        // through to TRF. Assert auto's result is identical to an explicit trf fit
        // (and that graph_prefers_varpro is indeed false for this graph).
        let (true_a, true_c, true_s) = (5.0_f64, 2.0_f64, 0.5_f64);
        let n = 60usize;
        let x: Vec<f64> = (0..n)
            .map(|i| -1.0 + 6.0 * i as f64 / (n - 1) as f64)
            .collect();
        let y: Vec<f64> = x
            .iter()
            .map(|&xi| gaussian(xi, true_a, true_c, true_s))
            .collect();

        let bounded = |value: f64, min: f64, max: f64| ParameterSpec {
            value,
            min,
            max,
            vary: true,
            expr: None,
            scale: None,
        };
        let mut params: HashMap<String, ParameterSpec> = HashMap::new();
        params.insert("amplitude".into(), bounded(4.0, 0.0, f64::INFINITY));
        params.insert("center".into(), make_param(1.8, true));
        params.insert("sigma".into(), bounded(0.6, 1e-6, 10.0)); // finite → not varpro-eligible
        let graph = FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![ModelNodeSpec {
                id: "g1".into(),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: None,
                parameters: params,
            }],
            expr_edges: vec![],
        };
        assert!(
            !graph_prefers_varpro(&graph),
            "bounded sigma must disqualify the graph from VarPro"
        );
        let data = MeasurementSpec {
            schema_version: None,
            x: vec![x],
            y,
            sigma: None,
            label: None,
        };
        let opts = |s: &str| FitOptionsSpec {
            solver: s.to_string(),
            ..default_options()
        };
        let r_auto = fit(&graph, vec![data.clone()], &opts("auto")).expect("auto fit");
        let r_trf = fit(&graph, vec![data], &opts("trf")).expect("trf fit");
        // auto routed to TRF → bit-for-bit the same outcome.
        assert_eq!(
            r_auto.n_iter, r_trf.n_iter,
            "auto should match trf iterations"
        );
        assert_relative_eq!(r_auto.chi2, r_trf.chi2, max_relative = 1e-12);
        for key in ["g1.amplitude", "g1.center", "g1.sigma"] {
            assert_relative_eq!(
                r_auto.parameters[key].value,
                r_trf.parameters[key].value,
                max_relative = 1e-12
            );
        }
    }

    // ── degenerate peak-collapse guard ───────────────────────────────────────

    #[test]
    fn degenerate_peak_collapse_is_flagged_unsuccessful() {
        // Narrow Gaussian (true centre 7) fit from centre=0 on the flat tail:
        // local LM stalls and collapses the amplitude to ~0 (R² < 0). The
        // degenerate-fit guard must downgrade success to false.
        let n = 200usize;
        let x: Vec<f64> = (0..n).map(|i| 10.0 * i as f64 / (n - 1) as f64).collect();
        let y: Vec<f64> = x.iter().map(|&xi| gaussian(xi, 3.0, 7.0, 0.3)).collect();

        let bounded = |value: f64, min: f64, max: f64| ParameterSpec {
            value,
            min,
            max,
            vary: true,
            expr: None,
            scale: None,
        };
        let mut params: HashMap<String, ParameterSpec> = HashMap::new();
        params.insert("amplitude".into(), bounded(1.0, 0.0, f64::INFINITY));
        params.insert("center".into(), make_param(0.0, true)); // far from 7, flat region
        params.insert("sigma".into(), bounded(0.3, 1e-6, f64::INFINITY));
        let graph = FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![ModelNodeSpec {
                id: "g1".into(),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: None,
                parameters: params,
            }],
            expr_edges: vec![],
        };
        let data = MeasurementSpec {
            schema_version: None,
            x: vec![x],
            y,
            sigma: None,
            label: None,
        };
        let r = fit(&graph, vec![data], &default_options()).expect("fit runs");
        assert!(
            !r.success,
            "a collapsed-peak fit (R²<0, amplitude≈0) must be flagged unsuccessful, got success=true r2={}",
            r.r_squared
        );
        assert!(
            r.message.contains("degenerate_fit"),
            "expected degenerate_fit message, got {:?}",
            r.message
        );
    }

    // ── VarPro rejects dataset_index scoping (it is not scope-aware) ──────────

    #[test]
    fn varpro_rejects_dataset_index_scoped_graph() {
        let mut params: HashMap<String, ParameterSpec> = HashMap::new();
        params.insert("amplitude".into(), make_param(1.0, true));
        params.insert("center".into(), make_param(0.0, true));
        params.insert("sigma".into(), make_param(1.0, true));
        let graph = FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![ModelNodeSpec {
                id: "g1".into(),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: Some(0), // per-dataset local node
                parameters: params,
            }],
            expr_edges: vec![],
        };
        let x: Vec<f64> = (0..10).map(|i| i as f64).collect();
        let data = MeasurementSpec {
            schema_version: None,
            x: vec![x],
            y: vec![0.0; 10],
            sigma: None,
            label: None,
        };
        let opts = FitOptionsSpec {
            solver: "varpro".into(),
            ..default_options()
        };
        let err = fit(&graph, vec![data], &opts);
        assert!(
            err.is_err(),
            "varpro must reject dataset_index-scoped graphs rather than mis-scope them"
        );
        let msg = format!("{:?}", err.unwrap_err());
        assert!(
            msg.contains("dataset_index"),
            "error should mention dataset_index, got {msg}"
        );
    }

    // ── CX-VPE-01: VarPro routing must honour `Parameter.expr` ties ───────────

    /// Two unbounded, separable Gaussians. When `tie` is set, `g2.sigma` is tied
    /// to `g1.sigma` via `Parameter.expr` (no `expr_edge`), so the graph is
    /// VarPro-eligible on every axis EXCEPT the tie — isolating the tie check.
    fn two_gaussian_param_expr_graph(tie: bool) -> FitGraphSpec {
        let mut g1: HashMap<String, ParameterSpec> = HashMap::new();
        g1.insert("amplitude".into(), make_param(5.0, true));
        g1.insert("center".into(), make_param(-1.0, true));
        g1.insert("sigma".into(), make_param(0.5, true));

        let mut g2: HashMap<String, ParameterSpec> = HashMap::new();
        g2.insert("amplitude".into(), make_param(3.0, true));
        g2.insert("center".into(), make_param(1.5, true));
        // tied => vary=false and value derived from g1.sigma via Parameter.expr.
        let mut sig2 = make_param(0.5, !tie);
        if tie {
            sig2.expr = Some("g1.sigma".into());
        }
        g2.insert("sigma".into(), sig2);

        FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![
                ModelNodeSpec {
                    id: "g1".into(),
                    model_type: ModelTypeStr::Gaussian,
                    dataset_index: None,
                    parameters: g1,
                },
                ModelNodeSpec {
                    id: "g2".into(),
                    model_type: ModelTypeStr::Gaussian,
                    dataset_index: None,
                    parameters: g2,
                },
            ],
            expr_edges: vec![],
        }
    }

    #[test]
    fn graph_prefers_varpro_false_for_param_expr_tie() {
        // CX-VPE-01 regression: an otherwise VarPro-eligible (separable, single
        // dataset, all nonlinear params unbounded) graph whose ONLY tie lives in
        // `Parameter.expr` must NOT auto-route to VarPro (which would silently drop
        // the tie). Before the fix this returned true (only `expr_edges` checked).
        let graph = two_gaussian_param_expr_graph(true);
        assert!(
            !graph_prefers_varpro(&graph),
            "a Parameter.expr tie must disqualify the graph from VarPro auto-routing"
        );
    }

    #[test]
    fn graph_prefers_varpro_true_for_untied_unbounded_separable() {
        // Positive control: the SAME unbounded separable graph WITHOUT a tie stays
        // VarPro-eligible — the fix must not over-reject untied graphs.
        let graph = two_gaussian_param_expr_graph(false);
        assert!(
            graph_prefers_varpro(&graph),
            "an untied, unbounded, separable graph must remain VarPro-eligible"
        );
    }

    #[test]
    fn varpro_explicit_rejects_param_expr_tie() {
        // Explicit solver="varpro" on a `Parameter.expr`-tied graph must return the
        // tied-params-unsupported error, NOT a silently-wrong success.
        let graph = two_gaussian_param_expr_graph(true);
        let n = 64usize;
        let x: Vec<f64> = (0..n)
            .map(|i| -3.0 + 6.0 * i as f64 / (n - 1) as f64)
            .collect();
        let y: Vec<f64> = x
            .iter()
            .map(|&xi| gaussian(xi, 5.0, -1.0, 0.5) + gaussian(xi, 3.0, 1.5, 0.5))
            .collect();
        let data = MeasurementSpec {
            schema_version: None,
            x: vec![x],
            y,
            sigma: None,
            label: None,
        };
        let opts = FitOptionsSpec {
            solver: "varpro".into(),
            ..default_options()
        };
        let msg = format!(
            "{}",
            fit(&graph, vec![data], &opts).expect_err(
                "solver='varpro' with a Parameter.expr tie must error, not drop the tie"
            )
        );
        assert!(
            msg.contains("tied parameters") || msg.contains("Parameter.expr"),
            "error should name the tied-params limitation, got: {msg}"
        );
    }

    /// S1 regression: a node with an UNBOUNDED amplitude but a BOUNDED nonlinear
    /// param (sigma) must NOT auto-route to VarPro (which ignores bounds). The old
    /// positional `.skip(1)` over a HashMap could skip sigma instead of amplitude
    /// and wrongly green-light VarPro — a silent bound violation.
    #[test]
    fn graph_with_unbounded_amplitude_but_bounded_sigma_is_not_varpro() {
        let bounded_sigma = ParameterSpec {
            value: 0.6,
            min: 0.1,
            max: 2.0,
            vary: true,
            expr: None,
            scale: None,
        };
        let mut params: HashMap<String, ParameterSpec> = HashMap::new();
        params.insert("amplitude".into(), make_param(4.0, true)); // unbounded linear coeff
        params.insert("center".into(), make_param(0.0, true)); // unbounded
        params.insert("sigma".into(), bounded_sigma); // BOUNDED nonlinear param
        let graph = FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![ModelNodeSpec {
                id: "g1".into(),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: None,
                parameters: params,
            }],
            expr_edges: vec![],
        };
        assert!(
            !graph_prefers_varpro(&graph),
            "a bounded nonlinear param must block VarPro auto-routing (bounds would be ignored)"
        );
    }

    // ------------------------------------------------------------------
    // A2 follow-up: typed SolverError variants reach the boundary
    // ------------------------------------------------------------------

    /// Build a minimal 1-D Gaussian graph + dataset for VarPro-rejection tests.
    fn make_varpro_inputs() -> (FitGraphSpec, MeasurementSpec) {
        let mut params: HashMap<String, ParameterSpec> = HashMap::new();
        params.insert("amplitude".into(), make_param(1.0, true));
        params.insert("center".into(), make_param(0.0, true));
        params.insert("sigma".into(), make_param(1.0, true));
        let graph = FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![ModelNodeSpec {
                id: "g1".into(),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: None,
                parameters: params,
            }],
            expr_edges: vec![],
        };
        let x: Vec<f64> = (0..10).map(|i| i as f64 * 0.1).collect();
        let y: Vec<f64> = x.iter().map(|&xi| gaussian(xi, 1.0, 0.0, 1.0)).collect();
        let dataset = MeasurementSpec {
            schema_version: None,
            x: vec![x],
            y,
            sigma: None,
            label: None,
        };
        (graph, dataset)
    }

    /// VarPro with expr_edges must surface the typed
    /// `SolverError::VarproExprEdgesUnsupported` variant via the CoreError
    /// boundary conversion.
    #[test]
    fn varpro_with_expr_edges_emits_solver_error_variant() {
        use spectrafit_types::ExprEdge;

        let (mut graph, dataset) = make_varpro_inputs();
        // Tie one parameter to force the expr_edge check to fail.
        graph.nodes[0]
            .parameters
            .insert("amplitude".to_string(), make_param(1.0, false));
        graph.expr_edges.push(ExprEdge {
            target_node: "g1".to_string(),
            target_param: "amplitude".to_string(),
            expression: "2.0".to_string(),
        });

        let mut options = default_options();
        options.solver = "varpro".to_string();
        let err = fit(&graph, vec![dataset], &options).unwrap_err();
        let expected: CoreError = SolverError::VarproExprEdgesUnsupported.into();
        assert_eq!(format!("{err}"), format!("{expected}"));
    }

    /// VarPro with a `dataset_index`-scoped node must surface the typed
    /// `SolverError::VarproDatasetScopingUnsupported` variant.
    #[test]
    fn varpro_with_dataset_index_emits_solver_error_variant() {
        let (mut graph, dataset) = make_varpro_inputs();
        graph.nodes[0].dataset_index = Some(0);

        let mut options = default_options();
        options.solver = "varpro".to_string();
        let err = fit(&graph, vec![dataset], &options).unwrap_err();
        let expected: CoreError = SolverError::VarproDatasetScopingUnsupported.into();
        assert_eq!(format!("{err}"), format!("{expected}"));
    }
}
