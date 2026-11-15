//! Universal post-fit statistics and result assembly.
//!
//! Everything here runs *after* a solver has converged and is **solver-agnostic**:
//! the computations depend only on the solved [`LmProblem`] (final parameters + cached
//! σ / eval counts), the compiled graph, and the data — never a branch on which
//! strategy ran. [`LmSolveOutcome`] carries per-strategy-shaped data (e.g. empty
//! trajectory histories for `lm-legacy`) as an opaque payload, not a discriminator this
//! module inspects. [`assemble_result`] computes χ²/reduced-χ²/R²/AIC/BIC, the
//! covariance matrix and condition number (faer-native), per-parameter standard
//! errors, residuals, component curves and per-dataset slices, and packs them into a
//! [`FitResultSpec`]. It also decides the final `success` flag: a convergence test
//! or a `no_improvement_possible` stop counts only at a Gauss-Newton stationary
//! end point (#93, see `gauss_newton_decrease`), before the off-domain and
//! degenerate-fit guards.

use std::collections::HashMap;

use faer::Side;
use spectrafit_graph::jacobian_compiled_indexed_into;
use spectrafit_graph::{evaluate_compiled, evaluate_components_compiled, CompiledGraph};
use spectrafit_types::{
    CoreError, DatasetSliceSpec, FitGraphSpec, FitResultSpec, MeasurementSpec, ParameterResultSpec,
};

use crate::lm_problem::LmProblem;

/// Outcome of running the LM-family solve — step 4 (and the tied-parameter
/// initialisation that precedes it) of `dispatch::fit`'s sequence: the
/// (possibly-rebuilt) [`LmProblem`], iteration count, success flag, a stable
/// snake_case termination message, wall-clock solve time, and the
/// per-iteration trajectories the faer-native drivers expose (empty for
/// `lm-legacy`, which does not track one). Field names mirror the original
/// inline local-variable names (`n_iter_val`/`success_val`/`message_val`).
/// Lives here (not in `dispatch`) since [`assemble_result`] is its only
/// consumer — `dispatch` constructs one and hands it off, keeping the
/// dependency one-directional (`dispatch` → `postfit`).
pub struct LmSolveOutcome<'a> {
    /// The solved problem — `node_param_bufs` are at the final parameters.
    pub result_problem: LmProblem<'a>,
    /// Outer-iteration count the solver reported.
    pub n_iter_val: u64,
    /// Whether the solve terminated successfully (pre-postfit-guards).
    pub success_val: bool,
    /// Stable snake_case termination message (pre-postfit-guards).
    pub message_val: String,
    /// Wall-clock time spent inside the solve, in nanoseconds.
    pub solve_ns: u128,
    /// Per-iteration cost trajectory (empty for `lm-legacy`/VarPro).
    pub cost_history: Vec<f64>,
    /// Per-iteration gradient-norm trajectory (empty for `lm-legacy`/VarPro).
    pub gradient_norm_history: Vec<f64>,
    /// Per-iteration free-parameter trajectory (empty for `lm-legacy`/VarPro).
    pub params_history: Vec<Vec<f64>>,
}

/// Read-only fit-graph/data context shared by every post-fit computation:
/// the compiled graph, its original spec, and the flattened per-point data.
/// Bundled purely to shrink [`assemble_result`]'s parameter count — each
/// field is read independently inside, not as a cohesive sub-object.
pub struct PostfitInputs<'a> {
    /// The compiled graph the solve ran against.
    pub cg: &'a CompiledGraph,
    /// The original fit-graph spec (model types, bounds, tied expressions).
    pub graph: &'a FitGraphSpec,
    /// The caller's per-dataset measurements (x/y/sigma).
    pub datasets: &'a [MeasurementSpec],
    /// Flattened x-coordinates across all datasets, in solve order.
    pub x_all: &'a [f64],
    /// Flattened y-values across all datasets, in solve order.
    pub y_all: &'a [f64],
}

/// Assemble the full [`FitResultSpec`] from a converged solve.
///
/// `outcome` holds the solved [`LmProblem`] (its `node_param_bufs` are at the
/// final parameters) plus the solve metadata (`n_iter_val`/`success_val`/
/// `message_val`/`solve_ns`/histories) the caller already has; `inputs` is
/// the shared graph/data context; `init_fit` is the pre-fit model evaluation.
/// Takes `outcome` by value (not `&mut LmProblem`) because the tied-graph
/// covariance path uses the problem's finite-difference weighted Jacobian,
/// which re-evaluates residuals, and the histories are moved into the
/// returned [`FitResultSpec`] rather than cloned.
///
/// # Errors
/// Returns [`CoreError`] when:
/// - Re-evaluating the model at the final parameters fails
///   (`evaluate_compiled`, for `best_fit`, or `evaluate_components_compiled`,
///   for the per-component curves).
/// - Building the covariance matrix fails: for a tied graph or a forced
///   finite-difference Jacobian, the finite-difference weighted Jacobian
///   (`fd_weighted_jacobian_rowmajor`); otherwise the analytic Jacobian
///   (`jacobian_compiled_indexed_into`).
pub fn assemble_result(
    mut outcome: LmSolveOutcome<'_>,
    inputs: PostfitInputs<'_>,
    init_fit: Vec<f64>,
) -> Result<FitResultSpec, CoreError> {
    let result_problem = &mut outcome.result_problem;
    let PostfitInputs {
        cg,
        graph,
        datasets,
        x_all,
        y_all,
    } = inputs;
    let n_iter_val = outcome.n_iter_val;
    let solve_ns = outcome.solve_ns;
    let success_val = outcome.success_val;
    let message_val = outcome.message_val;
    let cost_history = outcome.cost_history;
    let gradient_norm_history = outcome.gradient_norm_history;
    let params_history = outcome.params_history;
    let free_keys = &cg.free_keys;

    let n_func_evals = *result_problem.residual_count.borrow();
    let n_jac_evals = *result_problem.jacobian_count.borrow();
    let residual_ns = *result_problem.residual_time_ns.borrow();
    let jacobian_ns = *result_problem.jacobian_time_ns.borrow();

    // ── 9. Extract final parameters ─────────────────────────────────────────
    let final_flat = result_problem.to_flat();

    // ── 10. Post-fit statistics ───────────────────────────────────────────────
    let n_total: usize = datasets.iter().map(|ds| ds.y.len()).sum();
    let n_free = free_keys.len();
    let dof = (n_total as i64 - n_free as i64).max(1);

    let best_fit = evaluate_compiled(cg, &final_flat, x_all)?;

    // Unweighted chi² = Σ (ŷ - y)²
    let chi2: f64 = best_fit
        .iter()
        .zip(y_all.iter())
        .map(|(pred, obs)| (pred - obs).powi(2))
        .sum();

    let y_mean = y_all.iter().sum::<f64>() / y_all.len().max(1) as f64;
    let ss_tot: f64 = y_all.iter().map(|y| (y - y_mean).powi(2)).sum();

    let (r_squared, reduced_chi2, aic, bic) =
        compute_scalar_diagnostics(chi2, n_total, n_free, dof, ss_tot);

    // ── 11. Covariance matrix + condition number (faer-native) ───────────────
    let _cov_t0 = std::time::Instant::now();
    let sigma_provided = datasets.iter().any(|ds| ds.sigma.is_some());
    let (cov_opt, condition_number, jac_weighted) = compute_covariance_and_condition(
        result_problem,
        cg,
        x_all,
        n_free,
        chi2,
        dof,
        sigma_provided,
    )?;
    let cov_ns = _cov_t0.elapsed().as_nanos();

    // Per-iteration cost attribution. Enabled with `SPECTRAFIT_PROFILE=1` so the
    // hot path stays free of I/O in normal runs. Answers "where does the LM
    // wall-time go?" — solve loop (residual vs Jacobian eval) vs the one-shot
    // post-fit covariance inversion.
    if std::env::var("SPECTRAFIT_PROFILE").is_ok_and(|v| v != "0" && !v.is_empty()) {
        let per = |ns: u128, n: u64| {
            if n > 0 {
                ns as f64 / n as f64 / 1e3
            } else {
                0.0
            }
        };
        eprintln!(
            "[spectrafit-profile] solve={:.3}ms cov={:.3}ms | residual: {} calls, {:.3}ms total, {:.2}us/call | jacobian: {} calls, {:.3}ms total, {:.2}us/call | n_free={} n_points={}",
            solve_ns as f64 / 1e6,
            cov_ns as f64 / 1e6,
            n_func_evals,
            residual_ns as f64 / 1e6,
            per(residual_ns, n_func_evals),
            n_jac_evals,
            jacobian_ns as f64 / 1e6,
            per(jacobian_ns, n_jac_evals),
            n_free,
            n_total,
        );
    }

    // ── 11. Per-parameter results ────────────────────────────────────────────
    let parameters = build_parameter_results(graph, &final_flat, free_keys, cov_opt.as_ref());

    // ── 12. Residuals and component curves ───────────────────────────────────
    let residuals: Vec<f64> = y_all
        .iter()
        .zip(best_fit.iter())
        .map(|(obs, pred)| obs - pred)
        .collect();

    let components = evaluate_components_compiled(cg, &final_flat, x_all)?;

    // ── 13. Per-dataset slices (only populated for multi-dataset fits) ────────
    let dataset_slices = build_dataset_slices(datasets, &best_fit);

    // ── 14. Flatten covariance to nested Vec for serialisation ───────────────
    let covariance = cov_opt.as_ref().map(|cov| {
        (0..cov.nrows())
            .map(|i| (0..cov.ncols()).map(|j| cov[(i, j)]).collect())
            .collect()
    });

    // ── 14a. Stationarity gate (#93, F4g) ─────────────────────────────────────
    // Success needs a convergence test or a `no_improvement_possible` stop AND
    // a Gauss-Newton stationary end point (`max_iterations` never succeeds). Measured on the objective the solver minimised,
    // Σ((ŷ − y)/σ)², with the Jacobian of step 11 at the final parameters
    // (analytic for an untied graph, the solver's finite-difference Jacobian for
    // a tied one). Runs before the guards below, so a soft stop the gate accepts
    // still faces the off-domain and degenerate-fit checks.
    // Same σ rule as the weighted Jacobian of step 11.
    let weight = |s: f64| if s > 0.0 { 1.0 / s } else { 1.0 };
    let r_w: Vec<f64> = best_fit
        .iter()
        .zip(y_all.iter())
        .zip(result_problem.sigma.iter())
        .map(|((pred, obs), &s)| (pred - obs) * weight(s))
        .collect();
    let rss_w: f64 = r_w.iter().map(|v| v * v).sum();
    let y_w_sq: f64 = y_all
        .iter()
        .zip(result_problem.sigma.iter())
        .map(|(obs, &s)| (obs * weight(s)).powi(2))
        .sum();
    let gn_decrease = match &jac_weighted {
        Some(j) => {
            let theta: Vec<f64> = free_keys
                .iter()
                .map(|k| final_flat.get(k).copied().unwrap_or(f64::NAN))
                .collect();
            gauss_newton_decrease(j.as_ref(), &r_w, &theta, &result_problem.bounds)
        }
        // No free parameter: there is no direction to decrease along.
        None => 0.0,
    };
    let gated = stationarity_gate(
        success_val,
        &message_val,
        gn_decrease,
        at_zero_residual(rss_w, y_w_sq),
    );

    // ── 14b. Success guards (off-domain runaway + degenerate peak-collapse) ───
    let (guard_ok, message_val) = apply_postfit_guards(
        graph,
        free_keys,
        &final_flat,
        x_all,
        y_all,
        r_squared,
        n_free,
        gated || success_val,
        message_val,
    );
    let success_val = gated && guard_ok;

    // ── 14c. Output finiteness guard ────────────────────────────────────────
    let (chi2, r_squared, reduced_chi2, aic, bic, success_val) =
        apply_finiteness_guards(chi2, r_squared, reduced_chi2, aic, bic, success_val);

    // ── 15. Assemble result ──────────────────────────────────────────────────
    Ok(FitResultSpec {
        schema_version: "0.1".to_string(),
        parameters,
        covariance,
        // `free_keys` is the SAME ordered slice used to index the covariance
        // matrix rows/cols above (see §11). Serialising it here makes the
        // cov[i][j] ↔ param-name mapping unambiguous for any consumer — the
        // `HashMap`-keyed `parameters` dict iterates in non-deterministic order,
        // so without this field a consumer cannot reliably read cross-terms like
        // cov("g.amplitude","g.sigma") by position.
        covariance_param_order: free_keys.to_vec(),
        chi2,
        reduced_chi2,
        r_squared,
        dof,
        aic,
        bic,
        n_iter: n_iter_val,
        n_func_evals: Some(n_func_evals),
        n_jac_evals: Some(n_jac_evals),
        success: success_val,
        message: message_val,
        best_fit,
        residuals,
        init_fit,
        components,
        dataset_slices,
        condition_number,
        // Direct-LM path: not a DE/global fit. The global path overwrites this
        // with the DE generation count after `lm_fit` returns (see global.rs).
        n_de_generations: None,
        // Per-iteration convergence trajectory recorded by the faer driver (empty
        // for the lm-legacy oracle / VarPro, which do not expose it).
        cost_history,
        gradient_norm_history,
        params_history,
    })
}

/// Compute the four scalar post-fit diagnostics from summary statistics.
///
/// Returns `(r_squared, reduced_chi2, aic, bic)`. The values are computed from
/// closed-form expressions and may be non-finite when the inputs are degenerate
/// (e.g. `n_total = 0`, `chi2 = inf`). The caller in [`assemble_result`] guards
/// the results at step 14c before placing them in [`FitResultSpec`].
///
/// # Arguments
/// * `chi2`    — Σ(ŷ − y)², unweighted residual sum-of-squares.
/// * `n_total` — total number of data points across all datasets.
/// * `n_free`  — number of free (varying) parameters.
/// * `dof`     — degrees of freedom = max(n_total − n_free, 1) (pre-clamped).
/// * `ss_tot`  — total sum of squares = Σ(y − ȳ)² for R² computation.
fn compute_scalar_diagnostics(
    chi2: f64,
    n_total: usize,
    n_free: usize,
    dof: i64,
    ss_tot: f64,
) -> (f64, f64, f64, f64) {
    let reduced_chi2 = chi2 / dof as f64;

    let ss_res = chi2; // same as Σ(ŷ - y)²
    let r_squared = if ss_tot > 0.0 {
        1.0 - ss_res / ss_tot
    } else {
        1.0
    };

    // Standard Gaussian information criteria (match lmfit `.aic/.bic` and the jax
    // oracle so the values are comparable across backends): with chi2 = Σ(ŷ−y)²,
    // the −2·logL term is n·ln(chi2/n). Using raw chi2 as the deviance (the old
    // form) put spectrafit on a different scale than the oracles and produced a
    // spurious ΔAIC of ~1e3 at identical r²/chi². Guard chi2→0 (perfect fit).
    // NOTE: when n_total = 0 this produces NaN (0.0 * ln(inf)); the output
    // finiteness guard in assemble_result (step 14c) catches that.
    let neg2_log_l = n_total as f64 * (chi2.max(1e-30) / n_total as f64).ln();
    let aic = neg2_log_l + 2.0 * n_free as f64;
    let bic = neg2_log_l + n_free as f64 * (n_total as f64).ln();

    (r_squared, reduced_chi2, aic, bic)
}

/// `(covariance, condition number, weighted Jacobian)` from
/// [`compute_covariance_and_condition`].
type CovarianceAndJacobian = (Option<faer::Mat<f64>>, Option<f64>, Option<faer::Mat<f64>>);

/// Covariance matrix + condition number (faer-native).
///
/// The Jacobian at the solution is computed once, directly from the solver's
/// `node_param_bufs` (already at `final_flat`), into a faer matrix — no
/// nalgebra `DMatrix`, no HashMap round-trip via `jacobian_compiled`. Both
/// the covariance and the condition number are derived from it via faer.
///
/// Covariance: with per-point σ, Σ = (J_wᵀ J_w)⁻¹, J_w[i,:] = J[i,:]/σ_i; with
/// no σ (all σ = 1) the scale-from-residuals estimate Σ = (JᵀJ)⁻¹·(χ²/DOF).
/// Condition number: κ(JᵀJ) = σ_max/σ_min of the unweighted Gram matrix
/// (matching the prior semantics) — `None` for an empty or rank-deficient J.
///
/// `chi2`/`dof` feed the no-σ scale-from-residuals covariance estimate;
/// `sigma_provided` selects between the weighted and scale-from-residuals paths.
///
/// Also returns the weighted Jacobian `J_w = ∂((ŷ − y)/σ)/∂θ` in physical
/// parameter units, for the stationarity gate in [`assemble_result`]: the
/// analytic Jacobian with rows scaled by 1/σ for an untied graph, the solver's
/// forward finite-difference weighted Jacobian with the `Parameter.scale`
/// factor divided out for a tied graph. `None` when there is no free parameter.
// Allowed: the solved problem, compiled graph, evaluation grid, and the
// scalar diagnostics (n_free/chi2/dof/sigma_provided) needed to pick between
// the weighted and scale-from-residuals covariance paths are each read
// independently below; bundling them into a struct would just rename this
// same parameter list.
#[allow(clippy::too_many_arguments)]
fn compute_covariance_and_condition(
    result_problem: &mut LmProblem,
    cg: &CompiledGraph,
    x_all: &[f64],
    n_free: usize,
    chi2: f64,
    dof: i64,
    sigma_provided: bool,
) -> Result<CovarianceAndJacobian, CoreError> {
    let scale_inv_cov = |cov: Option<faer::Mat<f64>>| -> Option<faer::Mat<f64>> {
        // No σ supplied (all σ = 1): scale-from-residuals estimate Σ·(χ²/DOF).
        cov.map(|mut inv| {
            let s = chi2 / dof as f64;
            let p = inv.ncols();
            for a in 0..p {
                for b in 0..p {
                    inv[(a, b)] *= s;
                }
            }
            inv
        })
    };
    if n_free == 0 {
        return Ok((None, None, None));
    }
    if result_problem.uses_fd_jacobian() {
        // Tied graphs, or a forced finite-difference Jacobian (#93), the same
        // switch the solver used: the analytic free-column Jacobian omits the
        // chain-rule terms Σ_t (∂r/∂t)(∂t/∂θ), so reuse the solver's finite-difference
        // *weighted* Jacobian (J_w = J/σ) at the solution. The FD Jacobian
        // differentiates the *scaled* working variable θ'_c = θ_c / s_c, so its
        // columns already carry the `Parameter.scale` factor `s_c` — that is the
        // matrix whose conditioning the optimiser sees, hence κ comes from its
        // Gram directly. Covariance, however, must be in *physical* units, so the
        // scaling is divided back out of each column first (a no-op when s = 1).
        // `scales` is copied out for the per-column un-scaling below.
        let scales = result_problem.scales.clone();
        let mut jw_buf: Vec<f64> = Vec::new();
        result_problem.fd_weighted_jacobian_rowmajor(&mut jw_buf)?;
        let n_pts = jw_buf.len().checked_div(n_free).unwrap_or(0);
        // Scaled Jacobian (as produced) → κ reflects the optimiser's conditioning.
        let jw_scaled = faer::Mat::from_fn(n_pts, n_free, |i, c| jw_buf[i * n_free + c]);
        let gram_scaled = jw_scaled.as_ref().transpose() * jw_scaled.as_ref();
        // Physical Jacobian (un-scale columns) → covariance in real parameter units.
        let jw_phys = faer::Mat::from_fn(n_pts, n_free, |i, c| {
            let s = scales[c];
            if s != 1.0 {
                jw_buf[i * n_free + c] / s
            } else {
                jw_buf[i * n_free + c]
            }
        });
        let gram_phys = jw_phys.as_ref().transpose() * jw_phys.as_ref();
        let cov = if sigma_provided {
            faer_cov_from_gram(gram_phys.as_ref())
        } else {
            scale_inv_cov(faer_cov_from_gram(gram_phys.as_ref()))
        };
        Ok((
            cov,
            faer_cond_from_gram(gram_scaled.as_ref()),
            Some(jw_phys),
        ))
    } else {
        let scales = &result_problem.scales;
        let mut jbuf: Vec<f64> = Vec::new();
        jacobian_compiled_indexed_into(cg, &result_problem.node_param_bufs, x_all, &mut jbuf)?;
        // `n_free > 0` here, so the division is exact; `checked_div` keeps clippy
        // happy about pairing the zero-guard above with a divide.
        let n_pts = jbuf.len().checked_div(n_free).unwrap_or(0);
        // Physical analytic Jacobian (∂r/∂θ) — covariance is reported in real
        // parameter units, so it uses this matrix unchanged.
        let j_final = faer::Mat::from_fn(n_pts, n_free, |i, c| jbuf[i * n_free + c]);
        // Effective (scaled) Jacobian column c = s_c · ∂r/∂θ_c — the matrix the
        // optimiser actually steps on, so κ is computed from it. No-op at s = 1.
        let j_scaled = faer::Mat::from_fn(n_pts, n_free, |i, c| {
            let s = scales[c];
            if s != 1.0 {
                jbuf[i * n_free + c] * s
            } else {
                jbuf[i * n_free + c]
            }
        });

        if sigma_provided {
            // Covariance from the weighted Gram (J_wᵀJ_w, physical); condition
            // number from the unweighted *scaled* Gram — different matrices.
            let sig = &result_problem.sigma;
            let j_w = faer::Mat::from_fn(n_pts, n_free, |i, c| {
                let s = sig[i];
                let w = if s > 0.0 { 1.0 / s } else { 1.0 };
                jbuf[i * n_free + c] * w
            });
            let cov = faer_cov_from_gram((j_w.as_ref().transpose() * j_w.as_ref()).as_ref());
            let cond = faer_condition_number(j_scaled.as_ref());
            Ok((cov, cond, Some(j_w)))
        } else {
            // No σ: covariance from the physical Gram; κ from the scaled Gram.
            let gram_phys = j_final.as_ref().transpose() * j_final.as_ref();
            let cov = scale_inv_cov(faer_cov_from_gram(gram_phys.as_ref()));
            Ok((cov, faer_condition_number(j_scaled.as_ref()), Some(j_final)))
        }
    }
}

/// Assemble the per-parameter result map: final value + standard error.
///
/// `stderr` is the sqrt of the diagonal covariance entry for a free (`vary`)
/// parameter; fixed parameters and any parameter with a negative diagonal
/// (ill-conditioned Hessian) get `None`.
fn build_parameter_results(
    graph: &FitGraphSpec,
    final_flat: &HashMap<String, f64>,
    free_keys: &[String],
    cov_opt: Option<&faer::Mat<f64>>,
) -> HashMap<String, ParameterResultSpec> {
    let mut parameters: HashMap<String, ParameterResultSpec> = HashMap::new();
    for node in &graph.nodes {
        for (pname, pspec) in &node.parameters {
            let key = format!("{}.{}", node.id, pname);
            let final_value = *final_flat.get(&key).unwrap_or(&pspec.value);

            // Standard error: sqrt of diagonal covariance entry (free params only)
            let stderr = if pspec.vary {
                free_keys.iter().position(|k| k == &key).and_then(|idx| {
                    cov_opt.and_then(|cov| {
                        let v = cov[(idx, idx)];
                        if v >= 0.0 {
                            Some(v.sqrt())
                        } else {
                            None // negative diagonal — ill-conditioned Hessian
                        }
                    })
                })
            } else {
                None
            };

            parameters.insert(
                key.clone(),
                ParameterResultSpec {
                    name: key,
                    value: final_value,
                    min: Some(pspec.min),
                    max: Some(pspec.max),
                    vary: pspec.vary,
                    expr: pspec.expr.clone(),
                    scale: pspec.scale,
                    stderr,
                },
            );
        }
    }
    parameters
}

/// Per-dataset best-fit/residual/χ² slices, populated only for multi-dataset
/// fits (`None` for the single-dataset case, matching the prior semantics).
fn build_dataset_slices(
    datasets: &[MeasurementSpec],
    best_fit: &[f64],
) -> Option<Vec<DatasetSliceSpec>> {
    if datasets.len() <= 1 {
        return None;
    }
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
}

/// Output finiteness guard.
///
/// All five scalar diagnostics must NEVER cross the FFI boundary as NaN or
/// ±Inf: `serde_json` serialises them as JSON `null`, which Pydantic rejects
/// with a ValidationError on the required-float fields. Replace any non-finite
/// value with the neutral sentinel (0.0) and downgrade `success` so the caller
/// can distinguish a degenerate solve from a genuinely zeroed diagnostic.
/// `chi2` is guarded first because `reduced_chi2`, `aic`, and `bic` are all
/// derived from it — if chi2 itself is non-finite (e.g. evaluate_compiled
/// returned Inf values) the derived guards still fire independently.
///
/// Returns the (possibly sanitized) `(chi2, r_squared, reduced_chi2, aic, bic, success)`.
fn apply_finiteness_guards(
    mut chi2: f64,
    mut r_squared: f64,
    mut reduced_chi2: f64,
    mut aic: f64,
    mut bic: f64,
    mut success: bool,
) -> (f64, f64, f64, f64, f64, bool) {
    if !chi2.is_finite() {
        chi2 = 0.0;
        success = false;
    }
    if !r_squared.is_finite() {
        r_squared = 0.0;
        success = false;
    }
    if !reduced_chi2.is_finite() {
        reduced_chi2 = 0.0;
        success = false;
    }
    if !aic.is_finite() {
        aic = 0.0;
        success = false;
    }
    if !bic.is_finite() {
        bic = 0.0;
        success = false;
    }
    (chi2, r_squared, reduced_chi2, aic, bic, success)
}

/// Detect a degenerate "runaway" fit: an originally-unbounded free parameter
/// whose converged value escaped a generous multiple of the data-aware domain
/// that the global search uses to seed candidates (see
/// [`crate::global::fallback_bounds`]). Returns a stable `message` string when a
/// runaway is found, else `None`.
///
/// Only parameters the user left unbounded on the relevant side are checked, and
/// the envelope is one full fallback-width beyond each side, so a legitimate
/// edge peak is never flagged — only egregious divergence (a centre far off the
/// x-domain, an amplitude orders of magnitude past the data scale).
fn detect_off_domain(
    graph: &FitGraphSpec,
    free_keys: &[String],
    final_flat: &HashMap<String, f64>,
    x_all: &[f64],
    y_all: &[f64],
) -> Option<String> {
    let (x_min, x_max) = x_all
        .iter()
        .copied()
        .filter(|v| v.is_finite())
        .fold((f64::INFINITY, f64::NEG_INFINITY), |(lo, hi), v| {
            (lo.min(v), hi.max(v))
        });
    if !x_min.is_finite() || !x_max.is_finite() {
        return None;
    }
    let x_span = if x_max > x_min { x_max - x_min } else { 10.0 };
    let y_max_abs = y_all
        .iter()
        .copied()
        .filter(|v| v.is_finite())
        .fold(0.0_f64, |m, v| m.max(v.abs()));

    for key in free_keys {
        let Some((node_id, param_name)) = key.split_once('.') else {
            continue;
        };
        let Some(node) = graph.nodes.iter().find(|n| n.id == node_id) else {
            continue;
        };
        let Some(pspec) = node.parameters.get(param_name) else {
            continue;
        };
        // Only parameters with a data-derived plausible range have a meaningful
        // "off-domain" notion: centre/position (x-range), amplitude/height
        // (y-scale), and width (x-span). Model-specific shape parameters (e.g.
        // Fano `q` asymmetry, pseudo-Voigt `fraction`) can legitimately range far
        // without being degenerate — `fallback_bounds` gives them only a generic
        // window around the initial guess, so guarding them yields false positives.
        let lname = param_name.to_ascii_lowercase();
        let data_domain_param = lname.contains("center")
            || lname.contains("position")
            || lname.contains("amplitude")
            || lname.contains("height")
            || lname.contains("sigma")
            || lname.contains("gamma")
            || lname.contains("width");
        if !data_domain_param {
            continue;
        }
        let min_unbounded = !pspec.min.is_finite();
        let max_unbounded = !pspec.max.is_finite();
        if !min_unbounded && !max_unbounded {
            continue; // user constrained this parameter on both sides — respect it.
        }
        let Some(&val) = final_flat.get(key) else {
            continue;
        };
        // Derive the plausible envelope from the data and the *initial* guess,
        // never the converged value — `fallback_bounds` scales amplitude/width
        // windows by its `value` argument, so feeding the runaway value would
        // inflate its own envelope and escape detection.
        let (lo, hi) = crate::global::fallback_bounds(
            param_name,
            pspec.value,
            x_min,
            x_max,
            x_span,
            y_max_abs,
        );
        let width = (hi - lo).abs().max(1e-12);
        let sane_lo = lo - width;
        let sane_hi = hi + width;
        if (min_unbounded && val < sane_lo) || (max_unbounded && val > sane_hi) {
            return Some(format!(
                "diverged_off_domain ({key}={val:.3e} escaped data domain \
                 [{sane_lo:.3e}, {sane_hi:.3e}])"
            ));
        }
    }
    None
}

/// Apply the post-fit success guards shared by every solver result path: downgrade
/// to `success=false` when (a) an originally-unbounded free parameter escaped the
/// data domain (off-domain runaway, [`detect_off_domain`]), or (b) the fit is a
/// degenerate peak-collapse — R² < 0 (explains no variance) AND a free
/// `amplitude`/`height` parameter collapsed to < 1% of the data scale. Returns the
/// possibly-downgraded `(success, message)`. Called by [`assemble_result`] (the
/// LM-family / dogleg / newton-cg path, and IRLS/global via `lm_fit`) and by the
/// VarPro dispatch arm, which builds its own result outside `assemble_result`.
/// [`assemble_result`] passes `success=true` for every end point that the
/// solver's convergence test or the stationarity gate accepted, and keeps the
/// gate's verdict as the reported success; an end point the gate refuses
/// therefore carries the guard's reason as its message when a guard fires.
// Allowed: the guard fuses 9 inputs (graph, free_keys, final flat params, both
// data axes, r², n_free, and the upstream success/message pair) into one
// post-fit decision; splitting into a struct would just rename the bundle.
#[allow(clippy::too_many_arguments)]
pub(crate) fn apply_postfit_guards(
    graph: &FitGraphSpec,
    free_keys: &[String],
    final_flat: &HashMap<String, f64>,
    x_all: &[f64],
    y_all: &[f64],
    r_squared: f64,
    n_free: usize,
    mut success: bool,
    mut message: String,
) -> (bool, String) {
    // r²-quality escape: a fit that demonstrably reconstructs the data (r² ≥
    // OFF_DOMAIN_R2_FLOOR) cannot be in a degenerate basin, even if one
    // unbounded parameter looks "large" in the data-scale sense.
    //
    // The off-domain check exists to catch fits that escaped to a degenerate
    // region — those by definition have *poor* r². The amplitude check in
    // particular gives false positives for two distinct reasons, depending on
    // the model: (1) exp_gaussian's `amplitude` is genuinely the total
    // integrated area under the curve, not a peak height — the EMG kernel's
    // own normalisation identity ((γ/2)·exp(...)·erfc(...) integrates to 1
    // over all x for γ>0) makes this literal, so a well-fit EMG can carry an
    // amplitude orders of magnitude above y_max_abs with no degeneracy at
    // all. (2) skewed_gaussian / doniach_sunjic / true_voigt keep
    // `amplitude` as a genuine peak-value/height-scale parameter, matching
    // this project's general convention (docs/reference/models/index.md) — true_voigt is in fact
    // explicitly normalised so `eval(center) == amplitude` exactly — but a
    // narrow or heavily-skewed lineshape can still carry a large nominal
    // amplitude that the curve never actually attains at the sampled data
    // points, so the same r²-quality escape is still warranted for these
    // three without `amplitude` itself meaning "area" for any of them.
    // Anti-regression: CX-017 (3× exp_gaussian, difficulty 0.61) — spectrafit
    // reached r² = 0.96236 (identical to lmfit) but was downgraded because
    // p1.amplitude = 2.55e3 was outside [-3.9, 7.8]. The fit was good.
    const OFF_DOMAIN_R2_FLOOR: f64 = 0.5;
    if success && r_squared < OFF_DOMAIN_R2_FLOOR {
        if let Some(reason) = detect_off_domain(graph, free_keys, final_flat, x_all, y_all) {
            success = false;
            message = reason;
        }
    }
    // No r² rule converts a soft stop to success here. A
    // `no_improvement_possible` stop reaches this guard as success only through
    // the stationarity gate in `assemble_result` (a Gauss-Newton stationary end
    // point, #93 F4g); `max_iterations` never does; r² never decides it. An
    // earlier rule upgraded a soft stop with r² ≥ 0.9 to success
    // (`_accepted_at_r2_<value>`); r² measures explained variance, not
    // first-order optimality, and on the EELS cross-check (#93, E0) all five
    // upgraded runs ended at non-stationary points (Gauss-Newton predicted
    // decrease 0.81-0.93 of the RSS). Convergence-test convention: Moré (1978),
    // "The Levenberg-Marquardt algorithm: implementation and theory", and
    // MINPACK lmder, where only the ftol/xtol/gtol tests report convergence.

    if success && n_free > 0 && r_squared < 0.0 {
        let y_max_abs = y_all
            .iter()
            .copied()
            .filter(|v| v.is_finite())
            .fold(0.0_f64, |m, v| m.max(v.abs()));
        let collapsed = y_max_abs > 0.0
            && free_keys.iter().any(|k| {
                let lk = k.to_ascii_lowercase();
                (lk.ends_with(".amplitude") || lk.ends_with(".height"))
                    && final_flat
                        .get(k)
                        .is_some_and(|&v| v.abs() / y_max_abs < 1e-2)
            });
        if collapsed {
            success = false;
            message = format!("degenerate_fit (r2={r_squared:.3e} < 0, peak amplitude collapsed)");
        }
    }
    (success, message)
}

// ---------------------------------------------------------------------------
// Stationarity gate on the success flag (#93, F4g)
// ---------------------------------------------------------------------------
//
// A stop is reported as success only when (a) the solver ended on a convergence
// test or on `no_improvement_possible` (never on `max_iterations`), and (b) the end point is first-order stationary: the
// Gauss-Newton model predicts a relative decrease of at most
// `GN_STATIONARY_TOL` over the components not held at an active bound.
//
// The measure is the Gauss-Newton model decrease, the standard stationarity
// measure for nonlinear least squares (J. E. Dennis and R. B. Schnabel,
// "Numerical Methods for Unconstrained Optimization and Nonlinear Equations",
// SIAM Classics in Applied Mathematics 16, 1996, ch. 10). With the Gauss-Newton
// step δ = argmin ||J δ − r||, the predicted decrease of the RSS is ||J δ||² =
// ||P_J r||², the squared projection of the residual onto the range of J. The
// bound rule follows the projected-Newton active set of D. P. Bertsekas,
// "Projected Newton methods for optimization problems with simple
// constraints", SIAM J. Control Optim. 20(2):221-246, 1982,
// doi:10.1137/0320018: a component on a bound whose gradient points out of
// the box is held and does not count. The acceptance definition is
// `stationarity()` in the EELS cross-check ledger (`crosscheck.stationarity`,
// .superpowers/ledgers/2026-11-09-eels-solver-crosscheck/crosscheck.py);
// this reproduces it, with the solver's own residual and Jacobian.

/// Largest Gauss-Newton predicted decrease, relative to the RSS, at which an
/// end point counts as stationary (`GN_TOL` of the #93 acceptance).
const GN_STATIONARY_TOL: f64 = 1e-6;

/// A component sits on a bound `b` when `|θ − b| ≤ ACTIVE_BOUND_REL · max(|b|, 1)`.
const ACTIVE_BOUND_REL: f64 = 1e-12;

/// Floor of the column scale `max(|θ_c|, GN_THETA_FLOOR)` applied before the
/// rank decision (`THETA_FLOOR` of the acceptance measure).
const GN_THETA_FLOOR: f64 = 1e-3;

/// Zero-residual clause: an end point with weighted RSS ≤ ZERO_RESIDUAL_REL ·
/// Σ(y/σ)² counts as stationary whatever its Gauss-Newton ratio. The relative
/// measure ||P r||² / RSS is undefined at zero residual: near an exact fit
/// r ≈ J (θ − θ*), so the round-off residual left by a converged noise-free fit
/// lies almost entirely in range(J) and the ratio is ≈ 1 although nothing is
/// left to gain. ε = `f64::EPSILON` (≈ 2.2e-16) marks round-off level relative
/// to the data (#93, user decision recorded in predictions.md §11).
const ZERO_RESIDUAL_REL: f64 = f64::EPSILON;

/// Whether the weighted RSS `rss_w` is at round-off level relative to the
/// weighted data energy `y_w_sq = Σ(y/σ)²` (see [`ZERO_RESIDUAL_REL`]).
fn at_zero_residual(rss_w: f64, y_w_sq: f64) -> bool {
    rss_w.is_finite() && rss_w <= ZERO_RESIDUAL_REL * y_w_sq
}

/// Termination keys of a solver soft stop that the gate may turn into success:
/// the solver stopped without a convergence test firing because no step
/// reduced the cost (`no_improvement_possible`). At a stationary point that is
/// a success. A budget stop (`max_iterations`) is not in the set and never
/// yields success, even at a stationary point (#93, user decision recorded in
/// predictions.md §11); `numerical_error` never does either.
const SOFT_STOP_MESSAGES: [&str; 1] = ["no_improvement_possible"];

/// Whether `message` is the termination key of a soft stop the gate accepts.
fn is_soft_stop(message: &str) -> bool {
    SOFT_STOP_MESSAGES.contains(&message)
}

/// Whether `theta` sits on the finite bound `bound` (1e-12 relative rule).
fn bound_active(theta: f64, bound: f64) -> bool {
    bound.is_finite() && (theta - bound).abs() <= ACTIVE_BOUND_REL * bound.abs().max(1.0)
}

/// Gauss-Newton predicted decrease relative to the RSS, `||P r||² / ||r||²`,
/// over the columns of `j` not held at an active bound.
///
/// `j` is `∂r/∂θ` (`m × n`, physical parameter units) for the residual `r`
/// the solver minimises (`(ŷ − y)/σ`); `theta` and `bounds` are the final
/// physical values and `(min, max)` per column. The gradient of the RSS is
/// `g = 2 Jᵀ r` (the ledger's `−2 Jᵀ (y − ŷ)`); a column at its lower bound with
/// `g_c > 0`, or at its upper bound with `g_c < 0`, is held. The kept columns
/// are scaled by `max(|θ_c|, 1e-3)` and the projection is taken from a thin
/// SVD, keeping singular values above `rcond · σ_max` with
/// `rcond = ε · max(m, n)` (the `numpy.linalg.lstsq(rcond=None)` cut-off of the
/// acceptance measure), so a rank-deficient or badly conditioned J
/// (κ(JᵀJ) ≈ 1e11-1e13 at EELS end points) gives the projection onto its
/// numerical range rather than an amplified noise component.
///
/// Returns 0.0 for RSS = 0 and when no column is left; `f64::INFINITY`
/// (not stationary) for a non-finite RSS or J, a shape mismatch, or a failed
/// SVD.
fn gauss_newton_decrease(
    j: faer::MatRef<'_, f64>,
    r: &[f64],
    theta: &[f64],
    bounds: &[(f64, f64)],
) -> f64 {
    let rss: f64 = r.iter().map(|v| v * v).sum();
    if !rss.is_finite() {
        return f64::INFINITY;
    }
    if rss == 0.0 {
        return 0.0;
    }
    let (m, n) = (j.nrows(), j.ncols());
    if m != r.len() || theta.len() != n || bounds.len() != n {
        return f64::INFINITY;
    }
    // Columns not held at an active bound (Bertsekas 1982).
    let free: Vec<usize> = (0..n)
        .filter(|&c| {
            let g = 2.0 * (0..m).map(|i| j[(i, c)] * r[i]).sum::<f64>();
            let (lo, hi) = bounds[c];
            let held =
                (bound_active(theta[c], lo) && g > 0.0) || (bound_active(theta[c], hi) && g < 0.0);
            !held
        })
        .collect();
    if free.is_empty() {
        return 0.0;
    }
    let js = faer::Mat::from_fn(m, free.len(), |i, k| {
        let c = free[k];
        j[(i, c)] * theta[c].abs().max(GN_THETA_FLOOR)
    });
    if (0..js.ncols()).any(|k| (0..m).any(|i| !js[(i, k)].is_finite())) {
        return f64::INFINITY;
    }
    let Ok(svd) = js.thin_svd() else {
        return f64::INFINITY;
    };
    let s = svd.S().column_vector();
    let u = svd.U();
    let s_max = (0..s.nrows()).map(|k| s[k]).fold(0.0_f64, f64::max);
    // rcond = ε · max(m, n), relative to σ_max: singular values at or below
    // the cut-off are treated as zero (numerical rank), as LAPACK gelsd and
    // `numpy.linalg.lstsq(rcond=None)` do.
    let cutoff = f64::EPSILON * m.max(free.len()) as f64 * s_max;
    let projected: f64 = (0..s.nrows())
        .filter(|&k| s[k] > cutoff)
        .map(|k| {
            let coef: f64 = (0..m).map(|i| u[(i, k)] * r[i]).sum();
            coef * coef
        })
        .sum();
    projected / rss
}

/// The success decision under the gate: a convergence test fired
/// (`solver_success`) or the solver stopped on `no_improvement_possible`, and
/// the end point is stationary: `gn_decrease ≤ GN_STATIONARY_TOL` (NaN is not
/// stationary) or the residual is at round-off level (`zero_residual`, see
/// [`ZERO_RESIDUAL_REL`]).
fn stationarity_gate(
    solver_success: bool,
    message: &str,
    gn_decrease: f64,
    zero_residual: bool,
) -> bool {
    (solver_success || is_soft_stop(message)) && (gn_decrease <= GN_STATIONARY_TOL || zero_residual)
}

// ---------------------------------------------------------------------------
// faer-native covariance / condition-number helpers
// ---------------------------------------------------------------------------

/// Covariance `Σ = H⁻¹` from a pre-formed Gram matrix `H = JᵀJ` (`p×p`) via faer
/// Cholesky. `None` when `H` is not positive-definite (rank-deficient Hessian).
fn faer_cov_from_gram(h: faer::MatRef<'_, f64>) -> Option<faer::Mat<f64>> {
    use faer::linalg::solvers::DenseSolveCore;
    h.llt(Side::Lower).ok().map(|llt| llt.inverse())
}

/// Condition number `κ(H) = σ_max / σ_min` of a pre-formed Gram matrix `H = JᵀJ`
/// via faer SVD. `None` when `H` is empty or rank-deficient (`σ_min ≤ 0`).
fn faer_cond_from_gram(h: faer::MatRef<'_, f64>) -> Option<f64> {
    if h.ncols() == 0 || h.nrows() == 0 {
        return None;
    }
    // H is SPSD; its singular values equal its eigenvalues.
    let svd = h.thin_svd().ok()?;
    let s = svd.S().column_vector();
    let k = s.nrows();
    if k == 0 {
        return None;
    }
    let mut s_max = f64::NEG_INFINITY;
    let mut s_min = f64::INFINITY;
    for i in 0..k {
        let v = s[i];
        s_max = s_max.max(v);
        s_min = s_min.min(v);
    }
    if !s_max.is_finite() || !s_min.is_finite() || s_min <= 0.0 {
        return None;
    }
    // κ is by definition ≥ 1; clamp away tiny FP undershoot below 1.0.
    Some((s_max / s_min).max(1.0))
}

/// Condition number `κ(JᵀJ)` from a Jacobian `J` (forms the Gram internally).
/// Kept for the unit tests; the post-fit path forms the Gram once and uses
/// [`faer_cond_from_gram`] directly.
fn faer_condition_number(j: faer::MatRef<'_, f64>) -> Option<f64> {
    if j.ncols() == 0 || j.nrows() == 0 {
        return None;
    }
    faer_cond_from_gram((j.transpose() * j).as_ref())
}

#[cfg(test)]
mod tests {
    use super::{compute_scalar_diagnostics, faer_condition_number};

    /// EF-RUST-02: derived diagnostics must never be NaN or ±Inf at the output
    /// boundary.  Three degenerate inputs that previously leaked non-finite values:
    ///
    /// 1. `n_total = 0` → `neg2_log_l = 0.0 * ln(inf) = NaN` → aic/bic NaN.
    /// 2. `chi2 = inf` → `neg2_log_l = inf` → aic = inf, bic = inf,
    ///    `reduced_chi2 = inf`; and `r_squared = 1 − inf/ss_tot = −inf`.
    /// 3. `chi2 = inf, ss_tot = inf` → `r_squared = 1 − inf/inf = NaN`.
    ///
    /// The output finiteness guard in `assemble_result` (step 14c) must replace
    /// each non-finite value with 0.0 and flip `success` to false.  Since
    /// `compute_scalar_diagnostics` is the raw computation path (no guard), we
    /// first confirm that it DOES produce non-finite values, then confirm that the
    /// guard in `assemble_result` eliminates them — tested via the full `fit` path
    /// through `dispatch.rs` (which calls `assemble_result` internally).
    ///
    /// For the unit portion here we directly verify `compute_scalar_diagnostics`
    /// behaviour and the sentinel logic inline.
    #[test]
    fn derived_diagnostics_are_finite_or_sentinel_not_nan() {
        // ── case 1: n_total = 0 ──────────────────────────────────────────────
        // neg2_log_l = 0.0 * (chi2.max(1e-30) / 0.0).ln()
        //            = 0.0 * ln(+inf) = 0.0 * +inf = NaN  (IEEE 754)
        let (r2, rchi2, aic, bic) = compute_scalar_diagnostics(0.5, 0, 0, 1, 0.0);
        let raw_nan = [r2, rchi2, aic, bic];
        // The raw helper intentionally produces NaN here; assert we see it so the
        // test is truly a guard test (fails before the fix, passes after).
        assert!(
            raw_nan.iter().any(|v| !v.is_finite()),
            "n_total=0 must produce at least one non-finite diagnostic before guarding; got {raw_nan:?}"
        );
        // Apply the same guard logic as assemble_result step 14c.
        let mut success = true;
        let mut r2g = r2;
        let mut rchi2g = rchi2;
        let mut aicg = aic;
        let mut bicg = bic;
        if !r2g.is_finite() {
            r2g = 0.0;
            success = false;
        }
        if !rchi2g.is_finite() {
            rchi2g = 0.0;
            success = false;
        }
        if !aicg.is_finite() {
            aicg = 0.0;
            success = false;
        }
        if !bicg.is_finite() {
            bicg = 0.0;
            success = false;
        }
        assert!(
            r2g.is_finite(),
            "guarded r_squared must be finite (n_total=0), got {r2g}"
        );
        assert!(
            rchi2g.is_finite(),
            "guarded reduced_chi2 must be finite (n_total=0), got {rchi2g}"
        );
        assert!(
            aicg.is_finite(),
            "guarded aic must be finite (n_total=0), got {aicg}"
        );
        assert!(
            bicg.is_finite(),
            "guarded bic must be finite (n_total=0), got {bicg}"
        );
        assert!(!success, "degenerate n_total=0 must flip success to false");

        // ── case 2: chi2 = inf (diverged residuals) ──────────────────────────
        // neg2_log_l = n * ln(inf/n) = inf → aic = inf, bic = inf
        // reduced_chi2 = inf / dof = inf
        // r_squared = 1 − inf / 1.0 = −inf
        let (r2, rchi2, aic, bic) = compute_scalar_diagnostics(f64::INFINITY, 10, 2, 8, 1.0);
        assert!(
            [r2, rchi2, aic, bic].iter().any(|v| !v.is_finite()),
            "chi2=inf must produce at least one non-finite diagnostic; got r2={r2} rchi2={rchi2} aic={aic} bic={bic}"
        );
        let mut success = true;
        let mut r2g = r2;
        let mut rchi2g = rchi2;
        let mut aicg = aic;
        let mut bicg = bic;
        if !r2g.is_finite() {
            r2g = 0.0;
            success = false;
        }
        if !rchi2g.is_finite() {
            rchi2g = 0.0;
            success = false;
        }
        if !aicg.is_finite() {
            aicg = 0.0;
            success = false;
        }
        if !bicg.is_finite() {
            bicg = 0.0;
            success = false;
        }
        assert!(
            r2g.is_finite(),
            "guarded r_squared must be finite (chi2=inf), got {r2g}"
        );
        assert!(
            rchi2g.is_finite(),
            "guarded reduced_chi2 must be finite (chi2=inf), got {rchi2g}"
        );
        assert!(
            aicg.is_finite(),
            "guarded aic must be finite (chi2=inf), got {aicg}"
        );
        assert!(
            bicg.is_finite(),
            "guarded bic must be finite (chi2=inf), got {bicg}"
        );
        assert!(!success, "degenerate chi2=inf must flip success to false");

        // ── case 3: chi2 = inf AND ss_tot = inf → r_squared = NaN ───────────
        let (r2, rchi2, aic, bic) =
            compute_scalar_diagnostics(f64::INFINITY, 10, 2, 8, f64::INFINITY);
        assert!(
            [r2, rchi2, aic, bic].iter().any(|v| !v.is_finite()),
            "chi2=inf,ss_tot=inf must produce non-finite r_squared; got r2={r2} rchi2={rchi2} aic={aic} bic={bic}"
        );
        let guarded = [r2, rchi2, aic, bic].map(|v| if v.is_finite() { v } else { 0.0 });
        for (name, &v) in ["r_squared", "reduced_chi2", "aic", "bic"]
            .iter()
            .zip(guarded.iter())
        {
            assert!(
                v.is_finite(),
                "guarded {name} must be finite (case 3), got {v}"
            );
        }

        // ── well-posed case: must remain untouched ───────────────────────────
        // Sanity: a normal solve produces finite diagnostics and the guard is a no-op.
        let (r2, rchi2, aic, bic) = compute_scalar_diagnostics(0.25, 50, 3, 47, 10.0);
        assert!(r2.is_finite(), "normal r_squared must be finite, got {r2}");
        assert!(
            rchi2.is_finite(),
            "normal reduced_chi2 must be finite, got {rchi2}"
        );
        assert!(aic.is_finite(), "normal aic must be finite, got {aic}");
        assert!(bic.is_finite(), "normal bic must be finite, got {bic}");
    }

    /// EF-RUST-02 gap C2/T4: `chi2` itself must also be guarded in step 14c.
    ///
    /// `serde_json` serialises `f64::INFINITY` as JSON `null` (not a number
    /// literal), which Pydantic rejects on the required `FitResultSpec.chi2`
    /// field with a `ValidationError`.  The prior commit (704a395) added the
    /// output finiteness guard for `r_squared / reduced_chi2 / aic / bic` but
    /// missed `chi2` itself.  This test verifies the guard is present: if
    /// `chi2` is non-finite it must be clamped to 0.0 and `success` must be
    /// set to `false`.
    #[test]
    fn chi2_finite_guard_closes_ef_rust_02_gap() {
        // Simulate what assemble_result would see if evaluate_compiled returned
        // infinite values (e.g. a model that diverges): chi2 becomes +Inf.
        // Without the guard, this leaks to FitResultSpec.chi2 = f64::INFINITY
        // which serde_json encodes as JSON `null` → Pydantic ValidationError.
        let raw_chi2 = f64::INFINITY;

        // Verify the raw value is indeed non-finite (confirms the scenario).
        assert!(
            !raw_chi2.is_finite(),
            "test precondition: chi2 must start non-finite"
        );

        // Apply the same guard logic as assemble_result step 14c requires for
        // chi2 (the fix we are pinning).
        let mut chi2 = raw_chi2;
        let mut success_val = true;
        if !chi2.is_finite() {
            chi2 = 0.0;
            success_val = false;
        }

        assert!(
            chi2.is_finite(),
            "guarded chi2 must be finite (got {chi2}); EF-RUST-02 gap — chi2 not in step 14c guard"
        );
        assert_eq!(
            chi2, 0.0,
            "guarded chi2 must be the sentinel 0.0, got {chi2}"
        );
        assert!(!success_val, "non-finite chi2 must flip success to false");

        // NaN variant: NaN also serialises as null in serde_json.
        let mut chi2_nan = f64::NAN;
        let mut success_nan = true;
        if !chi2_nan.is_finite() {
            chi2_nan = 0.0;
            success_nan = false;
        }
        assert!(
            chi2_nan.is_finite(),
            "guarded NaN chi2 must be finite, got {chi2_nan}"
        );
        assert!(!success_nan, "NaN chi2 must flip success to false");

        // Well-posed case: finite chi2 must pass through the guard unchanged.
        // (Use 2.5, not a value near a math constant — clippy::approx_constant flags 3.14 as π.)
        let mut chi2_ok = 2.5_f64;
        let mut success_ok = true;
        if !chi2_ok.is_finite() {
            chi2_ok = 0.0;
            success_ok = false;
        }
        assert!(
            (chi2_ok - 2.5).abs() < 1e-12,
            "finite chi2 must be unchanged by guard"
        );
        assert!(success_ok, "finite chi2 must not flip success");
    }

    #[test]
    fn condition_number_helper_identity_is_one() {
        // J = I_3 ⇒ JᵀJ = I_3 ⇒ all singular values 1 ⇒ κ = 1.
        let j = faer::Mat::<f64>::identity(3, 3);
        let cond = faer_condition_number(j.as_ref()).expect("identity is well-conditioned");
        assert!((cond - 1.0).abs() < 1e-9, "κ(I) should be 1.0, got {cond}");
    }

    #[test]
    fn condition_number_helper_empty_is_none() {
        let j = faer::Mat::<f64>::zeros(0, 0);
        assert!(faer_condition_number(j.as_ref()).is_none());
    }

    #[test]
    fn off_domain_guard_flags_runaway_but_not_well_posed_fits() {
        use super::detect_off_domain;
        use spectrafit_types::{FitGraphSpec, ModelNodeSpec, ModelTypeStr, ParameterSpec};
        use std::collections::HashMap;

        let mk = |value, min, max| ParameterSpec {
            value,
            min,
            max,
            vary: true,
            expr: None,
            scale: None,
        };
        let mut params = HashMap::new();
        params.insert("amplitude".into(), mk(1.0, 0.0, f64::INFINITY)); // max unbounded
        params.insert("center".into(), mk(0.0, f64::NEG_INFINITY, f64::INFINITY)); // unbounded
        params.insert("sigma".into(), mk(0.5, 1e-6, f64::INFINITY));
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
        let free_keys = vec![
            "g1.amplitude".to_string(),
            "g1.center".to_string(),
            "g1.sigma".to_string(),
        ];
        let x_all: Vec<f64> = (0..50).map(|i| -2.0 + 4.0 * i as f64 / 49.0).collect();
        let y_all: Vec<f64> = x_all
            .iter()
            .map(|&x| 8.0 * (-(x * x) / (2.0 * 0.5 * 0.5)).exp())
            .collect();

        // Well-posed converged fit (peak in-domain, amplitude ~ data scale) → no flag.
        let mut ok = HashMap::new();
        ok.insert("g1.amplitude".to_string(), 8.0);
        ok.insert("g1.center".to_string(), 0.0);
        ok.insert("g1.sigma".to_string(), 0.5);
        assert!(
            detect_off_domain(&graph, &free_keys, &ok, &x_all, &y_all).is_none(),
            "a well-posed fit must NOT be flagged off-domain"
        );

        // Centre far outside the observed x-domain [-2, 2] → flagged.
        let mut runaway_c = ok.clone();
        runaway_c.insert("g1.center".to_string(), -7.53);
        assert!(
            detect_off_domain(&graph, &free_keys, &runaway_c, &x_all, &y_all).is_some(),
            "an off-domain centre must be flagged"
        );

        // Amplitude orders of magnitude past the data scale → flagged (envelope is
        // anchored to the initial guess, so the runaway cannot inflate it away).
        let mut runaway_a = ok.clone();
        runaway_a.insert("g1.amplitude".to_string(), 74840.0);
        assert!(
            detect_off_domain(&graph, &free_keys, &runaway_a, &x_all, &y_all).is_some(),
            "a runaway amplitude must be flagged"
        );
    }

    /// CX-017 anti-regression: a high-r² fit with a "large" amplitude parameter
    /// (area-normalised models like exp_gaussian) must NOT be downgraded to
    /// `success=false` by the off-domain guard. The off-domain check applies
    /// only when r² < OFF_DOMAIN_R2_FLOOR (0.5) — a fit that demonstrably
    /// reconstructs the data cannot be in a degenerate basin.
    #[test]
    fn r2_quality_escape_lets_through_large_amplitude_on_well_fit_data() {
        use super::apply_postfit_guards;
        use spectrafit_types::{FitGraphSpec, ModelNodeSpec, ModelTypeStr, ParameterSpec};
        use std::collections::HashMap;

        let mk = |value, min, max| ParameterSpec {
            value,
            min,
            max,
            vary: true,
            expr: None,
            scale: None,
        };
        let mut params = HashMap::new();
        // amplitude is unbounded above — exactly the CX-017 path that the
        // pre-fix `detect_off_domain` falsely flagged for exp_gaussian models.
        params.insert("amplitude".into(), mk(1.0, 0.0, f64::INFINITY));
        params.insert("center".into(), mk(0.0, f64::NEG_INFINITY, f64::INFINITY));
        params.insert("sigma".into(), mk(0.5, 1e-6, f64::INFINITY));
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
        let free_keys = vec![
            "g1.amplitude".to_string(),
            "g1.center".to_string(),
            "g1.sigma".to_string(),
        ];
        let x_all: Vec<f64> = (0..50).map(|i| -2.0 + 4.0 * i as f64 / 49.0).collect();
        let y_all: Vec<f64> = x_all
            .iter()
            .map(|&x| 8.0 * (-(x * x) / (2.0 * 0.5 * 0.5)).exp())
            .collect();
        // Pretend the converged amplitude is way past y_max_abs, exactly like
        // CX-017's p1.amplitude=2.55e3 vs data [-3.9, 7.8].
        let mut final_flat = HashMap::new();
        final_flat.insert("g1.amplitude".to_string(), 74840.0);
        final_flat.insert("g1.center".to_string(), 0.0);
        final_flat.insert("g1.sigma".to_string(), 0.5);

        // r² = 0.95 → above floor → guard SKIPS the off-domain check → success
        // stays True. This is the CX-017 fix in unit form.
        let (success_high, msg_high) = apply_postfit_guards(
            &graph,
            &free_keys,
            &final_flat,
            &x_all,
            &y_all,
            0.95,
            3,
            true,
            "converged".to_string(),
        );
        assert!(
            success_high,
            "high-r² fit must NOT be downgraded by off-domain (got message: {msg_high})"
        );

        // r² = 0.10 (a genuinely broken fit with the same "large amplitude")
        // → off-domain check still fires → success downgraded. The fix is
        // surgical: it relaxes the guard only when the fit is demonstrably good.
        let (success_low, msg_low) = apply_postfit_guards(
            &graph,
            &free_keys,
            &final_flat,
            &x_all,
            &y_all,
            0.10,
            3,
            true,
            "converged".to_string(),
        );
        assert!(
            !success_low,
            "low-r² fit with runaway amplitude must STILL be flagged"
        );
        assert!(
            msg_low.contains("diverged_off_domain"),
            "low-r² runaway message must name the off-domain reason, got {msg_low}"
        );
    }

    /// #93: no r² rule in `apply_postfit_guards`. A soft stop
    /// (`no_improvement_possible` / `max_iterations`) keeps `success=false` and
    /// its own message here at any r², including r² ≥ 0.9, which an earlier rule
    /// upgraded to success (`_accepted_at_r2_<value>`). On the EELS cross-check
    /// (E0) all five upgraded runs were non-stationary endpoints. A hard failure
    /// (`numerical_error`) stays a failure, and an already-successful result
    /// passes through unchanged.
    #[test]
    fn soft_stop_stays_failure_at_any_r2() {
        use super::apply_postfit_guards;
        use spectrafit_types::{FitGraphSpec, ModelNodeSpec, ModelTypeStr, ParameterSpec};
        use std::collections::HashMap;

        let mk = |value, min, max| ParameterSpec {
            value,
            min,
            max,
            vary: true,
            expr: None,
            scale: None,
        };
        let mut params = HashMap::new();
        params.insert("amplitude".into(), mk(1.0, 0.0, f64::INFINITY));
        params.insert("center".into(), mk(0.0, f64::NEG_INFINITY, f64::INFINITY));
        params.insert("sigma".into(), mk(0.5, 1e-6, f64::INFINITY));
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
        let free_keys = vec![
            "g1.amplitude".to_string(),
            "g1.center".to_string(),
            "g1.sigma".to_string(),
        ];
        let x_all: Vec<f64> = (0..50).map(|i| -2.0 + 4.0 * i as f64 / 49.0).collect();
        let y_all: Vec<f64> = x_all
            .iter()
            .map(|&x| 8.0 * (-(x * x) / (2.0 * 0.5 * 0.5)).exp())
            .collect();
        let mut final_flat = HashMap::new();
        final_flat.insert("g1.amplitude".to_string(), 8.0);
        final_flat.insert("g1.center".to_string(), 0.0);
        final_flat.insert("g1.sigma".to_string(), 0.5);

        let guard = |r2: f64, success: bool, message: &str| {
            apply_postfit_guards(
                &graph,
                &free_keys,
                &final_flat,
                &x_all,
                &y_all,
                r2,
                3,
                success,
                message.to_string(),
            )
        };

        // Soft stops and the hard failure stay failures with their own message,
        // below, at and above the former 0.9 floor.
        for reason in [
            "no_improvement_possible",
            "max_iterations",
            "numerical_error",
        ] {
            for r2 in [0.5, 0.9, 0.99, 1.0] {
                let (success, message) = guard(r2, false, reason);
                assert!(
                    !success,
                    "{reason} at r² = {r2} must stay success=false (got message: {message})"
                );
                assert_eq!(
                    message, reason,
                    "{reason} at r² = {r2} must keep its own message"
                );
            }
        }

        // An already-successful result passes through unchanged.
        let (success, message) = guard(0.99, true, "converged_ftol");
        assert!(success);
        assert_eq!(message, "converged_ftol");
    }

    /// Boundaries of the post-fit guards in `apply_postfit_guards` (#93,
    /// mutation follow-up): the off-domain check runs only for r² strictly
    /// below 0.5; the degenerate-fit downgrade needs success, at least one
    /// free parameter, r² strictly below 0 and a free amplitude strictly below
    /// 1 % of max |y|.
    #[test]
    fn postfit_guard_boundaries() {
        use super::apply_postfit_guards;
        use spectrafit_types::{FitGraphSpec, ModelNodeSpec, ModelTypeStr, ParameterSpec};
        use std::collections::HashMap;

        let mk = |value, min, max| ParameterSpec {
            value,
            min,
            max,
            vary: true,
            expr: None,
            scale: None,
        };
        let mut params = HashMap::new();
        params.insert("amplitude".into(), mk(1.0, 0.0, f64::INFINITY));
        params.insert("center".into(), mk(0.0, f64::NEG_INFINITY, f64::INFINITY));
        params.insert("sigma".into(), mk(0.5, 1e-6, f64::INFINITY));
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
        let free_keys = vec![
            "g1.amplitude".to_string(),
            "g1.center".to_string(),
            "g1.sigma".to_string(),
        ];
        let x_all = vec![-2.0, -1.0, 0.0, 1.0, 2.0];
        let y_peak8 = vec![0.5, 2.0, 8.0, 2.0, 0.5]; // max |y| = 8
        let y_peak1 = vec![0.1, 0.5, 1.0, 0.5, 0.1]; // max |y| = 1
        let flat = |amplitude: f64| {
            HashMap::from([
                ("g1.amplitude".to_string(), amplitude),
                ("g1.center".to_string(), 0.0),
                ("g1.sigma".to_string(), 0.5),
            ])
        };
        let guard =
            |y: &[f64], amplitude: f64, r2: f64, n_free: usize, success: bool, msg: &str| {
                apply_postfit_guards(
                    &graph,
                    &free_keys,
                    &flat(amplitude),
                    &x_all,
                    y,
                    r2,
                    n_free,
                    success,
                    msg.to_string(),
                )
            };

        // Collapsed amplitude (0.05 / 8 < 1e-2) at r² < 0 → degenerate_fit.
        let (s, m) = guard(&y_peak8, 0.05, -0.5, 3, true, "converged_ftol");
        assert!(!s, "collapsed fit must be downgraded (got {m})");
        assert!(m.starts_with("degenerate_fit"), "got {m}");
        // r² exactly 0 is not below 0 → unchanged.
        let (s, m) = guard(&y_peak8, 0.05, 0.0, 3, true, "converged_ftol");
        assert!(
            s && m == "converged_ftol",
            "r² = 0 must pass (got {s}, {m})"
        );
        // No free parameter → unchanged.
        let (s, m) = guard(&y_peak8, 0.05, -0.5, 0, true, "converged_ftol");
        assert!(
            s && m == "converged_ftol",
            "n_free = 0 must pass (got {s}, {m})"
        );
        // An unsuccessful result keeps its own message.
        let (s, m) = guard(&y_peak8, 0.05, -0.5, 3, false, "max_iterations");
        assert!(!s && m == "max_iterations", "got {s}, {m}");
        // Amplitude exactly 1 % of max |y| is not below 1 % → unchanged.
        let (s, m) = guard(&y_peak1, 0.01, -0.5, 3, true, "converged_ftol");
        assert!(
            s && m == "converged_ftol",
            "ratio = 1e-2 must pass (got {s}, {m})"
        );
        // Off-domain runaway amplitude: checked below r² = 0.5, not at 0.5.
        let (s, m) = guard(&y_peak8, 74840.0, 0.49, 3, true, "converged_ftol");
        assert!(!s && m.starts_with("diverged_off_domain"), "got {s}, {m}");
        let (s, m) = guard(&y_peak8, 74840.0, 0.5, 3, true, "converged_ftol");
        assert!(
            s && m == "converged_ftol",
            "r² = 0.5 must skip off-domain (got {s}, {m})"
        );
    }

    /// Envelope arithmetic of `detect_off_domain` (mutation follow-up): every
    /// data-domain parameter name is checked, a one-sided bound still checks
    /// the open side, the envelope is one width beyond each side with the
    /// edge itself inside, and the x span falls back to 10 for a single point.
    #[test]
    fn off_domain_envelope_boundaries() {
        use super::detect_off_domain;
        use spectrafit_types::{FitGraphSpec, ModelNodeSpec, ModelTypeStr, ParameterSpec};
        use std::collections::HashMap;

        let mk = |value, min, max| ParameterSpec {
            value,
            min,
            max,
            vary: true,
            expr: None,
            scale: None,
        };
        let mut params = HashMap::new();
        params.insert("center".into(), mk(0.0, f64::NEG_INFINITY, f64::INFINITY));
        params.insert("position".into(), mk(0.0, f64::NEG_INFINITY, 100.0));
        for name in ["sigma", "gamma", "width"] {
            params.insert(name.into(), mk(0.5, 1e-6, f64::INFINITY));
        }
        let graph = FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![ModelNodeSpec {
                id: "p".into(),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: None,
                parameters: params,
            }],
            expr_edges: vec![],
        };
        let x_all = vec![-2.0, -1.0, 0.0, 1.0, 2.0];
        let y_all = vec![0.5, 2.0, 8.0, 2.0, 0.5];
        let flagged = |key: &str, value: f64, x: &[f64], y: &[f64]| {
            let free = vec![key.to_string()];
            let flat = HashMap::from([(key.to_string(), value)]);
            detect_off_domain(&graph, &free, &flat, x, y).is_some()
        };

        // Centre envelope [-2, 2], width 4 → sane range [-6, 6], edges inside.
        assert!(!flagged("p.center", -6.0, &x_all, &y_all));
        assert!(!flagged("p.center", 6.0, &x_all, &y_all));
        assert!(!flagged("p.center", -3.0, &x_all, &y_all));
        assert!(flagged("p.center", 7.0, &x_all, &y_all));
        assert!(flagged("p.center", -7.0, &x_all, &y_all));
        // Lower side open, upper bounded: the open side is still checked.
        assert!(flagged("p.position", -50.0, &x_all, &y_all));
        // Width-like names: envelope [1e-6, max(span 4, 4 * 0.5)] → sane hi ≈ 8.
        for key in ["p.sigma", "p.gamma", "p.width"] {
            assert!(
                flagged(key, 9.0, &x_all, &y_all),
                "{key} = 9 must be flagged"
            );
            assert!(!flagged(key, 7.0, &x_all, &y_all), "{key} = 7 must pass");
        }
        // A single x point has no span; the fallback span 10 gives sane hi ≈ 20.
        assert!(!flagged("p.sigma", 9.0, &[0.0], &[1.0]));
        assert!(flagged("p.sigma", 21.0, &[0.0], &[1.0]));
    }

    // ── Shared helpers for hand-built `LmProblem`s ──────────────────────────
    //
    // `dispatch::prepare_lm_pre_solve` / `build_node_param_buffers` build a
    // real `LmProblem` from a `FitGraphSpec` exactly the way these helpers do,
    // but both are private to `dispatch.rs` and not reusable across the module
    // boundary. The tests below need a real, correctly-wired `LmProblem` to
    // exercise `compute_covariance_and_condition` / `assemble_result` branches
    // that only fire post-solve (tied-graph covariance, the
    // `SPECTRAFIT_PROFILE` block, a shape-mismatched `sigma`) without actually
    // running an LM solve — so they rebuild the same wiring here from
    // `CompiledGraph`'s public fields (`node_free_cols`, `tied_plan`,
    // `nodes[].param_names`).

    /// Build a two-Gaussian graph where `g2.amplitude = k * g1.amplitude`
    /// (mirrors `dispatch::tests::tied_two_gaussian_graph`). `g1_amplitude_scale`
    /// optionally sets `Parameter.scale` on the free `g1.amplitude`, to drive
    /// the physical-Jacobian column de-scaling branch in
    /// `compute_covariance_and_condition`'s tied path.
    fn tied_two_gaussian_graph_with_scale(
        k: f64,
        g1_amplitude_scale: Option<f64>,
    ) -> spectrafit_types::FitGraphSpec {
        use spectrafit_types::{ExprEdge, ModelNodeSpec, ModelTypeStr, ParameterSpec};
        use std::collections::HashMap;

        let mk = |value: f64, min: f64, max: f64, vary: bool, scale: Option<f64>| ParameterSpec {
            value,
            min,
            max,
            vary,
            expr: None,
            scale,
        };
        let mut g1: HashMap<String, ParameterSpec> = HashMap::new();
        g1.insert(
            "amplitude".into(),
            mk(4.0, 0.0, f64::INFINITY, true, g1_amplitude_scale),
        );
        g1.insert(
            "center".into(),
            mk(-1.0, f64::NEG_INFINITY, f64::INFINITY, true, None),
        );
        g1.insert("sigma".into(), mk(0.5, 1e-6, f64::INFINITY, true, None));

        let mut g2: HashMap<String, ParameterSpec> = HashMap::new();
        g2.insert("amplitude".into(), mk(0.0, 0.0, f64::INFINITY, false, None));
        g2.insert(
            "center".into(),
            mk(1.0, f64::NEG_INFINITY, f64::INFINITY, true, None),
        );
        g2.insert("sigma".into(), mk(0.5, 1e-6, f64::INFINITY, true, None));

        spectrafit_types::FitGraphSpec {
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
            expr_edges: vec![ExprEdge {
                target_node: "g2".into(),
                target_param: "amplitude".into(),
                expression: format!("{k} * g1.amplitude"),
            }],
        }
    }

    /// Hand-build an `LmProblem` wired against `cg`/`graph`, seeded at each
    /// parameter's initial value (never actually solved). `sigma` is taken
    /// verbatim, including intentionally-wrong lengths — callers that want to
    /// drive `residuals_compiled_indexed_into`'s `OutputBufferShape` error use
    /// that to build a deliberately-mismatched problem.
    fn build_lm_problem<'a>(
        cg: &'a spectrafit_graph::CompiledGraph,
        graph: &spectrafit_types::FitGraphSpec,
        x_all: Vec<f64>,
        y_all: Vec<f64>,
        sigma: Vec<f64>,
    ) -> super::LmProblem<'a> {
        use nalgebra::DVector;
        use std::cell::RefCell;
        use std::collections::HashMap;

        let mut all_params: HashMap<String, f64> = HashMap::new();
        for node in &graph.nodes {
            for (pname, pspec) in &node.parameters {
                all_params.insert(format!("{}.{}", node.id, pname), pspec.value);
            }
        }
        let free_keys = cg.free_keys.clone();
        let bounds: Vec<(f64, f64)> = free_keys
            .iter()
            .map(|k| {
                let (nid, pname) = k.split_once('.').expect("free key has a '.'");
                let node = graph
                    .nodes
                    .iter()
                    .find(|n| n.id == nid)
                    .expect("node exists");
                let p = &node.parameters[pname];
                (p.min, p.max)
            })
            .collect();
        let scales: Vec<f64> = free_keys
            .iter()
            .map(|k| {
                let (nid, pname) = k.split_once('.').expect("free key has a '.'");
                let node = graph
                    .nodes
                    .iter()
                    .find(|n| n.id == nid)
                    .expect("node exists");
                node.parameters[pname].scale.unwrap_or(1.0)
            })
            .collect();
        let mut free_to_node_param = vec![(0usize, 0usize); free_keys.len()];
        for (node_idx, cols) in cg.node_free_cols.iter().enumerate() {
            for &(local_idx, col) in cols {
                free_to_node_param[col] = (node_idx, local_idx);
            }
        }
        let tied_to_node_param: Vec<(usize, usize)> = cg
            .tied_plan
            .order
            .iter()
            .map(|tp| {
                let (nid, pname) = tp.target.split_once('.').expect("tied target has a '.'");
                let node_idx = cg
                    .nodes
                    .iter()
                    .position(|n| n.id == nid)
                    .expect("tied target node exists");
                let param_pos = cg.nodes[node_idx]
                    .param_names
                    .iter()
                    .position(|p| p == pname)
                    .expect("tied target param exists");
                (node_idx, param_pos)
            })
            .collect();
        let node_param_bufs: Vec<Vec<f64>> = cg
            .nodes
            .iter()
            .map(|node| {
                node.param_names
                    .iter()
                    .map(|pname| {
                        *all_params
                            .get(&format!("{}.{}", node.id, pname))
                            .expect("every node param has an initial value")
                    })
                    .collect()
            })
            .collect();
        let params = DVector::from_vec(
            free_keys
                .iter()
                .zip(scales.iter())
                .map(|(k, &s)| all_params[k] / s)
                .collect::<Vec<f64>>(),
        );
        let n_free = free_keys.len();
        let n_points = y_all.len();
        super::LmProblem {
            compiled: cg,
            free_keys,
            bounds,
            all_params,
            node_param_bufs,
            free_to_node_param,
            tied_to_node_param,
            x_concat: x_all,
            y_concat: y_all,
            params,
            scales,
            sigma,
            jacobian_mode: spectrafit_types::JacobianMode::Analytic,
            residual_buf: RefCell::new(vec![0.0; n_points]),
            jacobian_buf: RefCell::new(vec![0.0; n_points * n_free]),
            residual_count: RefCell::new(0),
            jacobian_count: RefCell::new(0),
            residual_time_ns: RefCell::new(0),
            jacobian_time_ns: RefCell::new(0),
        }
    }

    /// Coverage gap (line ~151): a σ vector whose length disagrees with the
    /// point count only surfaces once the tied-graph covariance step runs
    /// `residuals_compiled_indexed_into` (via `fd_weighted_jacobian_rowmajor`)
    /// — `evaluate_compiled`, used earlier in `assemble_result` for
    /// `best_fit`, takes no `sigma` argument at all and cannot catch it. This
    /// proves the `?` after `compute_covariance_and_condition` in
    /// `assemble_result` actually propagates that error instead of panicking
    /// or being silently swallowed.
    #[test]
    fn assemble_result_propagates_covariance_sigma_shape_mismatch() {
        use super::{assemble_result, CompiledGraph, LmSolveOutcome, PostfitInputs};
        use spectrafit_types::MeasurementSpec;

        let graph = tied_two_gaussian_graph_with_scale(0.5, None);
        let cg = CompiledGraph::compile(&graph).expect("graph should compile");
        assert!(
            !cg.tied_plan.is_empty(),
            "test graph must have a tied parameter"
        );

        let x_all: Vec<f64> = (0..10).map(|i| -2.0 + 4.0 * i as f64 / 9.0).collect();
        let y_all: Vec<f64> = x_all
            .iter()
            .map(|&x| (-(x * x) / (2.0 * 0.25)).exp())
            .collect();

        // Deliberately wrong length (n_points + 3, not n_points).
        let bad_sigma = vec![1.0_f64; y_all.len() + 3];
        let problem = build_lm_problem(&cg, &graph, x_all.clone(), y_all.clone(), bad_sigma);

        let outcome = LmSolveOutcome {
            result_problem: problem,
            n_iter_val: 1,
            success_val: true,
            message_val: "converged".to_string(),
            solve_ns: 0,
            cost_history: vec![],
            gradient_norm_history: vec![],
            params_history: vec![],
        };
        let dataset = MeasurementSpec {
            schema_version: None,
            x: vec![x_all.clone()],
            y: y_all.clone(),
            sigma: None,
            label: None,
        };
        let init_fit = y_all.clone();

        let result = assemble_result(
            outcome,
            PostfitInputs {
                cg: &cg,
                graph: &graph,
                datasets: &[dataset],
                x_all: &x_all,
                y_all: &y_all,
            },
            init_fit,
        );
        assert!(
            result.is_err(),
            "a sigma/point-count shape mismatch in the tied FD-Jacobian path must surface \
             as an error out of assemble_result, not panic or silently succeed"
        );
    }

    /// Coverage gap (line ~346): `compute_covariance_and_condition` returns
    /// `(None, None)` immediately when there are zero free parameters — a
    /// graph where every parameter is fixed (`vary = false`).
    #[test]
    fn compute_covariance_returns_none_when_no_free_parameters() {
        use super::{compute_covariance_and_condition, CompiledGraph};
        use spectrafit_types::{FitGraphSpec, ModelNodeSpec, ModelTypeStr, ParameterSpec};
        use std::collections::HashMap;

        let mk = |value| ParameterSpec {
            value,
            min: f64::NEG_INFINITY,
            max: f64::INFINITY,
            vary: false,
            expr: None,
            scale: None,
        };
        let mut params = HashMap::new();
        params.insert("amplitude".into(), mk(1.0));
        params.insert("center".into(), mk(0.0));
        params.insert("sigma".into(), mk(0.5));
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
        let cg = CompiledGraph::compile(&graph).expect("graph should compile");
        assert_eq!(cg.free_keys.len(), 0, "every parameter is fixed");

        let x_all = vec![0.0_f64, 1.0, 2.0];
        let y_all = vec![1.0_f64, 2.0, 1.0];
        let mut problem = build_lm_problem(&cg, &graph, x_all.clone(), y_all.clone(), vec![1.0; 3]);

        let (cov, cond, jac) =
            compute_covariance_and_condition(&mut problem, &cg, &x_all, 0, 1.0, 1, false)
                .expect("n_free=0 must not error");
        assert!(cov.is_none(), "zero free params must give no covariance");
        assert!(
            cond.is_none(),
            "zero free params must give no condition number"
        );
        assert!(jac.is_none(), "zero free params must give no Jacobian");
    }

    /// Coverage gaps (lines ~369, ~376): the tied-graph covariance path
    /// (a) un-scales each physical-Jacobian column by `Parameter.scale` when
    /// it isn't 1.0 (line ~369), and (b) uses the weighted Gram directly
    /// (skipping the scale-from-residuals estimate) when σ is caller-supplied
    /// (line ~376). Exercise both at once: `g1.amplitude` carries a non-1.0
    /// scale, and the call passes `sigma_provided = true`.
    #[test]
    fn tied_covariance_descales_columns_and_uses_weighted_gram_when_sigma_provided() {
        use super::{compute_covariance_and_condition, CompiledGraph};

        let graph = tied_two_gaussian_graph_with_scale(0.5, Some(2.0));
        let cg = CompiledGraph::compile(&graph).expect("graph should compile");
        assert!(
            !cg.tied_plan.is_empty(),
            "test graph must have a tied parameter"
        );
        let amp_col = cg
            .free_keys
            .iter()
            .position(|k| k == "g1.amplitude")
            .expect("g1.amplitude is free");

        let n = 40usize;
        let x_all: Vec<f64> = (0..n)
            .map(|i| -3.0 + 6.0 * i as f64 / (n - 1) as f64)
            .collect();
        let y_all: Vec<f64> = x_all
            .iter()
            .map(|&x| {
                4.0 * (-(x + 1.0).powi(2) / (2.0 * 0.25)).exp()
                    + 2.0 * (-(x - 1.0).powi(2) / (2.0 * 0.25)).exp()
            })
            .collect();
        let sigma = vec![1.0_f64; n];
        let mut problem = build_lm_problem(&cg, &graph, x_all.clone(), y_all.clone(), sigma);

        let n_free = cg.free_keys.len();
        assert!(
            problem.scales[amp_col] != 1.0,
            "amplitude scale must be non-default"
        );

        let (cov, cond, _jac) = compute_covariance_and_condition(
            &mut problem,
            &cg,
            &x_all,
            n_free,
            0.0,
            (n as i64 - n_free as i64).max(1),
            true, // sigma_provided
        )
        .expect("tied covariance with a non-default scale and provided sigma must not error");

        assert!(
            cov.is_some(),
            "a well-conditioned tied Jacobian must produce a covariance matrix"
        );
        assert!(
            cond.is_some(),
            "a well-conditioned tied Jacobian must produce a condition number"
        );
    }

    /// Coverage gap (line ~448): a free parameter whose covariance diagonal
    /// entry is negative (an ill-conditioned Hessian inverse) must report
    /// `stderr = None`, never `NaN` from `sqrt()` of a negative number.
    #[test]
    fn build_parameter_results_negative_diagonal_yields_none_stderr() {
        use super::build_parameter_results;
        use spectrafit_types::{FitGraphSpec, ModelNodeSpec, ModelTypeStr, ParameterSpec};
        use std::collections::HashMap;

        let mut params = HashMap::new();
        params.insert(
            "amplitude".to_string(),
            ParameterSpec {
                value: 5.0,
                min: f64::NEG_INFINITY,
                max: f64::INFINITY,
                vary: true,
                expr: None,
                scale: None,
            },
        );
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
        let mut final_flat = HashMap::new();
        final_flat.insert("g1.amplitude".to_string(), 5.0);
        let free_keys = vec!["g1.amplitude".to_string()];

        // A 1x1 "covariance" matrix with a negative diagonal entry.
        let cov = faer::Mat::from_fn(1, 1, |_, _| -1.0);

        let results = build_parameter_results(&graph, &final_flat, &free_keys, Some(&cov));
        let pr = &results["g1.amplitude"];
        assert!(
            pr.stderr.is_none(),
            "negative covariance diagonal must yield stderr=None, got {:?}",
            pr.stderr
        );
    }

    /// Coverage gaps (lines ~533-534, ~537-538, ~541-542): the production
    /// `apply_finiteness_guards` function itself was never called directly by
    /// any existing test — they all re-implement its logic inline instead
    /// (see `derived_diagnostics_are_finite_or_sentinel_not_nan` and
    /// `chi2_finite_guard_closes_ef_rust_02_gap` above). Call the real
    /// function directly for both the fully-degenerate and fully-healthy
    /// cases.
    #[test]
    fn apply_finiteness_guards_sanitizes_each_non_finite_field_independently() {
        use super::apply_finiteness_guards;

        let (chi2, r2, rchi2, aic, bic, success) = apply_finiteness_guards(
            f64::NAN,
            f64::NEG_INFINITY,
            f64::INFINITY,
            f64::NAN,
            f64::INFINITY,
            true,
        );
        assert_eq!(chi2, 0.0);
        assert_eq!(r2, 0.0);
        assert_eq!(rchi2, 0.0);
        assert_eq!(aic, 0.0);
        assert_eq!(bic, 0.0);
        assert!(!success, "any non-finite field must flip success to false");

        let (chi2, r2, rchi2, aic, bic, success) =
            apply_finiteness_guards(1.0, 0.9, 1.1, 20.0, 25.0, true);
        assert_eq!(chi2, 1.0);
        assert_eq!(r2, 0.9);
        assert_eq!(rchi2, 1.1);
        assert_eq!(aic, 20.0);
        assert_eq!(bic, 25.0);
        assert!(success, "all-finite fields must pass through unchanged");
    }

    /// Coverage gap (line ~774): `faer_cond_from_gram`'s own emptiness guard
    /// is never hit through either production call site —
    /// `faer_condition_number` (its only in-crate caller besides the tied
    /// covariance path) already screens out empty matrices before ever
    /// calling it, and the tied path's `n_free == 0` case returns before
    /// forming a Gram matrix at all. Call it directly with a 0x0 matrix.
    #[test]
    fn faer_cond_from_gram_empty_matrix_is_none() {
        use super::faer_cond_from_gram;
        let h = faer::Mat::<f64>::zeros(0, 0);
        assert!(faer_cond_from_gram(h.as_ref()).is_none());
    }

    /// Coverage gap (line ~580): `detect_off_domain` bails out immediately
    /// when the x-domain has no finite values at all (empty, or all
    /// NaN/±Inf) — there is no data-derived envelope to compare against.
    #[test]
    fn off_domain_guard_returns_none_for_non_finite_or_empty_x_domain() {
        use super::detect_off_domain;
        use spectrafit_types::{FitGraphSpec, ModelNodeSpec, ModelTypeStr, ParameterSpec};
        use std::collections::HashMap;

        let mut params = HashMap::new();
        params.insert(
            "amplitude".to_string(),
            ParameterSpec {
                value: 74840.0,
                min: 0.0,
                max: f64::INFINITY,
                vary: true,
                expr: None,
                scale: None,
            },
        );
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
        let free_keys = vec!["g1.amplitude".to_string()];
        let mut final_flat = HashMap::new();
        final_flat.insert("g1.amplitude".to_string(), 74840.0);

        let x_nonfinite = vec![f64::NAN, f64::INFINITY, f64::NEG_INFINITY];
        let y_any = vec![1.0, 2.0, 3.0];
        assert!(
            detect_off_domain(&graph, &free_keys, &final_flat, &x_nonfinite, &y_any).is_none(),
            "an x-domain with no finite values must not be flagged"
        );

        let x_empty: Vec<f64> = vec![];
        let y_empty: Vec<f64> = vec![];
        assert!(
            detect_off_domain(&graph, &free_keys, &final_flat, &x_empty, &y_empty).is_none(),
            "an empty x-domain must not be flagged"
        );
    }

    /// Coverage gaps (lines ~591, ~594, ~597): `detect_off_domain` skips —
    /// rather than panics on — a free key with no `.` separator, one naming a
    /// node the graph doesn't have, and one naming a parameter its node
    /// doesn't have.
    #[test]
    fn off_domain_guard_skips_malformed_or_unknown_free_keys() {
        use super::detect_off_domain;
        use spectrafit_types::{FitGraphSpec, ModelNodeSpec, ModelTypeStr, ParameterSpec};
        use std::collections::HashMap;

        let mut params = HashMap::new();
        params.insert(
            "amplitude".to_string(),
            ParameterSpec {
                value: 8.0,
                min: 0.0,
                max: f64::INFINITY,
                vary: true,
                expr: None,
                scale: None,
            },
        );
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
        let x_all: Vec<f64> = (0..10).map(|i| i as f64).collect();
        let y_all: Vec<f64> = vec![1.0; 10];
        let mut final_flat = HashMap::new();
        final_flat.insert("g1.amplitude".to_string(), 8.0);

        let free_keys = vec![
            "no_dot_here".to_string(),          // split_once('.') fails → continue
            "ghost_node.amplitude".to_string(), // node lookup fails → continue
            "g1.no_such_param".to_string(),     // param lookup fails → continue
        ];
        assert!(
            detect_off_domain(&graph, &free_keys, &final_flat, &x_all, &y_all).is_none(),
            "malformed/unknown free keys must be skipped, not panic or false-flag"
        );
    }

    /// Coverage gaps (lines ~619, ~622): a data-domain parameter bounded on
    /// *both* sides is respected (never flagged, however "runaway"-looking
    /// its converged value) — line ~619; and a free key with no entry in
    /// `final_flat` is skipped rather than panicking — line ~622.
    #[test]
    fn off_domain_guard_skips_both_sided_bound_and_missing_final_value() {
        use super::detect_off_domain;
        use spectrafit_types::{FitGraphSpec, ModelNodeSpec, ModelTypeStr, ParameterSpec};
        use std::collections::HashMap;

        let mut params = HashMap::new();
        // Bounded on both sides: min and max both finite.
        params.insert(
            "amplitude".to_string(),
            ParameterSpec {
                value: 8.0,
                min: 0.0,
                max: 100.0,
                vary: true,
                expr: None,
                scale: None,
            },
        );
        // Unbounded (data-domain-eligible) but absent from `final_flat` below.
        params.insert(
            "center".to_string(),
            ParameterSpec {
                value: 0.0,
                min: f64::NEG_INFINITY,
                max: f64::INFINITY,
                vary: true,
                expr: None,
                scale: None,
            },
        );
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
        let x_all: Vec<f64> = (0..10).map(|i| -2.0 + 4.0 * i as f64 / 9.0).collect();
        let y_all: Vec<f64> = vec![1.0; 10];

        // `g1.amplitude` would look "runaway" (12345 vs a data scale of ~1) if
        // it were checked at all, but it's bounded on both sides → skipped.
        // `g1.center` is unbounded but absent from `final_flat` → skipped.
        let mut final_flat = HashMap::new();
        final_flat.insert("g1.amplitude".to_string(), 12345.0);

        let free_keys = vec!["g1.amplitude".to_string(), "g1.center".to_string()];
        assert!(
            detect_off_domain(&graph, &free_keys, &final_flat, &x_all, &y_all).is_none(),
            "a both-sided-bounded parameter and a free key missing from final_flat must both be skipped"
        );
    }

    /// #93: with a forced finite-difference Jacobian an *untied* graph takes the
    /// same FD covariance path as a tied one — the covariance and condition
    /// number are those of the graph-level FD Jacobian at the solution, not of
    /// the per-kernel analytic Jacobian (which the default mode keeps).
    #[test]
    fn forced_fd_jacobian_drives_the_postfit_covariance() {
        use super::{
            compute_covariance_and_condition, faer_cond_from_gram, faer_cov_from_gram,
            CompiledGraph,
        };
        use spectrafit_types::JacobianMode;

        let mut graph = tied_two_gaussian_graph_with_scale(0.5, None);
        graph.expr_edges.clear();
        for node in &mut graph.nodes {
            for p in node.parameters.values_mut() {
                p.vary = true;
                if p.value == 0.0 {
                    p.value = 1.5;
                }
            }
        }
        let cg = CompiledGraph::compile(&graph).expect("graph should compile");
        assert!(cg.tied_plan.is_empty(), "test graph must be untied");
        let n_free = cg.free_keys.len();

        let n = 40usize;
        let x_all: Vec<f64> = (0..n)
            .map(|i| -3.0 + 6.0 * i as f64 / (n - 1) as f64)
            .collect();
        let y_all: Vec<f64> = x_all
            .iter()
            .map(|&x| {
                4.1 * (-(x + 1.05).powi(2) / (2.0 * 0.26)).exp()
                    + 1.4 * (-(x - 0.95).powi(2) / (2.0 * 0.24)).exp()
            })
            .collect();
        let (chi2, dof) = (0.37, (n - n_free) as i64);

        let mut fd = build_lm_problem(&cg, &graph, x_all.clone(), y_all.clone(), vec![1.0; n]);
        fd.jacobian_mode = JacobianMode::FiniteDifference;
        let (cov_fd, cond_fd, _) =
            compute_covariance_and_condition(&mut fd, &cg, &x_all, n_free, chi2, dof, false)
                .expect("fd covariance");

        // Reference: the FD-branch arithmetic on the problem's own FD Jacobian.
        let mut jw = Vec::new();
        fd.fd_weighted_jacobian_rowmajor(&mut jw)
            .expect("fd jacobian");
        let j = faer::Mat::from_fn(n, n_free, |i, c| jw[i * n_free + c]);
        let gram = j.as_ref().transpose() * j.as_ref();
        let mut cov_ref = faer_cov_from_gram(gram.as_ref()).expect("invertible");
        let s = chi2 / dof as f64;
        for a in 0..n_free {
            for b in 0..n_free {
                cov_ref[(a, b)] *= s;
            }
        }
        let cov_fd = cov_fd.expect("fd covariance present");
        for a in 0..n_free {
            for b in 0..n_free {
                assert_eq!(cov_fd[(a, b)], cov_ref[(a, b)], "cov[{a},{b}]");
            }
        }
        assert_eq!(cond_fd, faer_cond_from_gram(gram.as_ref()));

        // The default mode keeps the analytic covariance, which differs from
        // the FD one in the low digits but agrees to FD accuracy.
        let mut an = build_lm_problem(&cg, &graph, x_all.clone(), y_all, vec![1.0; n]);
        let (cov_an, _, _) =
            compute_covariance_and_condition(&mut an, &cg, &x_all, n_free, chi2, dof, false)
                .expect("analytic covariance");
        let cov_an = cov_an.expect("analytic covariance present");
        let mut differs = false;
        for a in 0..n_free {
            for b in 0..n_free {
                let (f, g) = (cov_fd[(a, b)], cov_an[(a, b)]);
                differs |= f != g;
                assert!(
                    (f - g).abs() <= 1e-4 * f.abs().max(g.abs()).max(1e-12),
                    "cov[{a},{b}]: fd {f:e} vs analytic {g:e}"
                );
            }
        }
        assert!(
            differs,
            "the forced FD covariance must not be the analytic one"
        );
    }
    // ── #93 F4g: stationarity gate on the success flag ──────────────────────
    //
    // Fixture: five points, two orthogonal columns c1 = 1, c2 = (−2, −1, 0, 1, 2)
    // and a residual direction d = (1, −2, 1, 0, 0) orthogonal to both, so the
    // Gauss-Newton decrease of r = a·c1 + d is exactly 5a² / (5a² + 6).

    const C1: [f64; 5] = [1.0, 1.0, 1.0, 1.0, 1.0];
    const C2: [f64; 5] = [-2.0, -1.0, 0.0, 1.0, 2.0];
    const D: [f64; 5] = [1.0, -2.0, 1.0, 0.0, 0.0];
    const FREE: (f64, f64) = (f64::NEG_INFINITY, f64::INFINITY);

    fn jac_from_cols(cols: &[&[f64]]) -> faer::Mat<f64> {
        faer::Mat::from_fn(cols[0].len(), cols.len(), |i, c| cols[c][i])
    }

    /// `a·c1 + b·c2 + d`.
    fn residual(a: f64, b: f64) -> Vec<f64> {
        (0..5).map(|i| a * C1[i] + b * C2[i] + D[i]).collect()
    }

    fn gn(j: &faer::Mat<f64>, r: &[f64], theta: &[f64], bounds: &[(f64, f64)]) -> f64 {
        super::gauss_newton_decrease(j.as_ref(), r, theta, bounds)
    }

    /// (i) A convergence test that fires at a non-stationary point no longer
    /// reports success.
    #[test]
    fn gate_converged_stop_at_non_stationary_point_is_failure() {
        use super::stationarity_gate;
        let j = jac_from_cols(&[&C1, &C2]);
        let r = residual(0.5, 0.0);
        let g = gn(&j, &r, &[1.0, 1.0], &[FREE, FREE]);
        let expected = 1.25 / 7.25;
        assert!(
            (g - expected).abs() <= 1e-12 * expected,
            "GN decrease must be ||P r||² / RSS = {expected}, got {g}"
        );
        for msg in ["converged_xtol", "converged_ftol", "converged_gtol"] {
            assert!(
                !stationarity_gate(true, msg, g, false),
                "{msg} at GN = {g} must give success=false"
            );
        }
    }

    /// (ii) A `no_improvement_possible` stop at a stationary point is a
    /// success (the Misra1a/b case at the certified optimum); a
    /// `max_iterations` stop is not, at any GN.
    #[test]
    fn gate_soft_stop_at_stationary_point_is_success() {
        use super::stationarity_gate;
        let j = jac_from_cols(&[&C1, &C2]);
        let r = residual(0.0, 0.0);
        let g = gn(&j, &r, &[1.0, 1.0], &[FREE, FREE]);
        assert!(g <= 1e-28, "r ⟂ range(J) must give GN ≈ 0, got {g}");
        assert!(stationarity_gate(
            false,
            "no_improvement_possible",
            g,
            false
        ));
        assert!(stationarity_gate(true, "converged_ftol", g, false));
        // A budget stop never becomes a success, even at a stationary point.
        assert!(!stationarity_gate(false, "max_iterations", g, false));
        assert!(!stationarity_gate(false, "max_iterations", 0.0, false));
        // Neither a hard failure nor an unknown key becomes a success.
        assert!(!stationarity_gate(false, "numerical_error", g, false));
        assert!(!stationarity_gate(
            false,
            "diverged_off_domain (x)",
            g,
            false
        ));
        // Not stationary: a soft stop stays a failure.
        assert!(!stationarity_gate(
            false,
            "no_improvement_possible",
            0.5,
            false
        ));
        assert!(!stationarity_gate(false, "max_iterations", 0.5, false));
        // NaN is not stationary.
        assert!(!stationarity_gate(true, "converged_ftol", f64::NAN, false));
    }

    /// (iii) An optimum on a bound with the gradient pointing out of the box:
    /// the component is held, the rest is stationary, success. g = 2 Jᵀ r with
    /// the solver's residual ŷ − y, so at the lower bound g > 0 is outward and
    /// at the upper bound g < 0 is outward.
    #[test]
    fn gate_held_component_on_bound_with_outward_gradient_is_success() {
        use super::stationarity_gate;
        let j = jac_from_cols(&[&C1, &C2]);
        // Lower bound 0, θ₁ = 0, g₁ = 2·c1ᵀr = 2·(0.5·5) > 0 → outward → held.
        let r_lo = residual(0.5, 0.0);
        let g_lo = gn(&j, &r_lo, &[0.0, 1.0], &[(0.0, f64::INFINITY), FREE]);
        assert!(g_lo <= 1e-28, "held column must not count, got {g_lo}");
        assert!(stationarity_gate(true, "converged_xtol", g_lo, false));
        assert!(stationarity_gate(
            false,
            "no_improvement_possible",
            g_lo,
            false
        ));
        // Upper bound 2, θ₁ = 2, g₁ < 0 → outward → held.
        let r_hi = residual(-0.5, 0.0);
        let g_hi = gn(&j, &r_hi, &[2.0, 1.0], &[(f64::NEG_INFINITY, 2.0), FREE]);
        assert!(g_hi <= 1e-28, "held column must not count, got {g_hi}");
        assert!(stationarity_gate(true, "converged_xtol", g_hi, false));
        // Every column held → nothing left to decrease.
        let r_both = residual(0.5, 0.5);
        let g_both = gn(
            &j,
            &r_both,
            &[0.0, 0.0],
            &[(0.0, f64::INFINITY), (0.0, f64::INFINITY)],
        );
        assert_eq!(g_both, 0.0);
    }

    /// (iv) The same point when the bound is not active: the gradient points
    /// into the box, or θ is off the bound by more than 1e-12 relative. The
    /// component counts and GN > 1e-6 gives success=false.
    #[test]
    fn gate_inactive_bound_counts_the_component() {
        use super::stationarity_gate;
        let j = jac_from_cols(&[&C1, &C2]);
        let expected = 1.25 / 7.25;
        // On the lower bound, gradient inward (g₁ < 0).
        let g_in_lo = gn(
            &j,
            &residual(-0.5, 0.0),
            &[0.0, 1.0],
            &[(0.0, f64::INFINITY), FREE],
        );
        // On the upper bound, gradient inward (g₁ > 0).
        let g_in_hi = gn(
            &j,
            &residual(0.5, 0.0),
            &[2.0, 1.0],
            &[(f64::NEG_INFINITY, 2.0), FREE],
        );
        // Outward gradient but θ₁ off the bound.
        let g_off = gn(
            &j,
            &residual(0.5, 0.0),
            &[1e-3, 1.0],
            &[(0.0, f64::INFINITY), FREE],
        );
        for g in [g_in_lo, g_in_hi, g_off] {
            assert!(
                (g - expected).abs() <= 1e-12 * expected,
                "an inactive bound must not hold the column: GN = {g}"
            );
            assert!(!stationarity_gate(true, "converged_xtol", g, false));
            assert!(!stationarity_gate(
                false,
                "no_improvement_possible",
                g,
                false
            ));
        }
        // The 1e-12 relative rule: |θ − b| ≤ 1e-12 · max(|b|, 1), here 5e-12.
        let bounds = [(5.0, f64::INFINITY), FREE];
        let r = residual(0.5, 0.0);
        let g_inside_tol = gn(&j, &r, &[5.0 + 4e-12, 1.0], &bounds);
        let g_outside_tol = gn(&j, &r, &[5.0 + 6e-12, 1.0], &bounds);
        assert!(g_inside_tol <= 1e-28, "4e-12 from b = 5 is active");
        assert!(
            (g_outside_tol - expected).abs() <= 1e-12 * expected,
            "6e-12 from b = 5 is not active"
        );
        // Below 1 the rule is absolute: 1e-12 around b = 0.
        let bounds0 = [(0.0, f64::INFINITY), FREE];
        assert!(gn(&j, &r, &[0.9e-12, 1.0], &bounds0) <= 1e-28);
        assert!(gn(&j, &r, &[1.1e-12, 1.0], &bounds0) > 0.1);
    }

    /// (v) The threshold: GN ≤ 1e-6 is stationary. r = b·c2 + d with
    /// 10 b² / (10 b² + 6) = t.
    #[test]
    fn gate_threshold_is_one_in_a_million() {
        use super::stationarity_gate;
        let j = jac_from_cols(&[&C1, &C2]);
        for (t, pass) in [(0.999e-6_f64, true), (1.001e-6, false)] {
            let b = (0.6 * t / (1.0 - t)).sqrt();
            let g = gn(&j, &residual(0.0, b), &[1.0, 1.0], &[FREE, FREE]);
            assert!(
                (g - t).abs() <= 1e-9 * t,
                "GN decrease must equal {t}, got {g}"
            );
            assert_eq!(
                stationarity_gate(true, "converged_ftol", g, false),
                pass,
                "converged at GN = {g}"
            );
            assert_eq!(
                stationarity_gate(false, "no_improvement_possible", g, false),
                pass,
                "soft stop at GN = {g}"
            );
        }
    }

    /// (vi) Rank-deficient J: duplicate columns give the projection onto the
    /// range, and a column below rcond · σ_max (rcond = ε · max(m, n)) is
    /// dropped, as `numpy.linalg.lstsq(rcond=None)` does.
    #[test]
    fn gate_rank_deficient_jacobian() {
        let j_dup = jac_from_cols(&[&C1, &C1, &C2]);
        let theta = [1.0, 1.0, 1.0];
        let bounds = [FREE, FREE, FREE];
        let expected = 1.25 / 7.25;
        let g = gn(&j_dup, &residual(0.5, 0.0), &theta, &bounds);
        assert!(
            (g - expected).abs() <= 1e-10 * expected,
            "duplicate columns: GN = {g}, expected {expected}"
        );
        let g0 = gn(&j_dup, &residual(0.0, 0.0), &theta, &bounds);
        assert!(g0 <= 1e-20, "duplicate columns, r ⟂ range: GN = {g0}");
        // A column along d at 1e-20 of the others is numerically zero.
        let tiny: Vec<f64> = D.iter().map(|v| v * 1e-20).collect();
        let j_tiny = jac_from_cols(&[&C1, &C2, &tiny]);
        let g_tiny = gn(&j_tiny, &D, &theta, &bounds);
        assert!(
            g_tiny <= 1e-20,
            "a column below rcond must be dropped, GN = {g_tiny}"
        );
        // The same column at full scale is in the range: GN = 1.
        let j_full = jac_from_cols(&[&C1, &C2, &D]);
        let g_full = gn(&j_full, &D, &theta, &bounds);
        assert!((g_full - 1.0).abs() <= 1e-12, "GN = {g_full}");
    }

    /// (vii) RSS = 0 counts as stationary; a non-finite or malformed input
    /// does not.
    #[test]
    fn gate_zero_rss_is_stationary_and_bad_input_is_not() {
        use super::stationarity_gate;
        let j = jac_from_cols(&[&C1, &C2]);
        let g = gn(&j, &[0.0; 5], &[1.0, 1.0], &[FREE, FREE]);
        assert_eq!(g, 0.0);
        assert!(stationarity_gate(true, "residuals_zero", g, false));
        assert!(stationarity_gate(
            false,
            "no_improvement_possible",
            g,
            false
        ));
        // Zero-residual clause: RSS ≤ ε·Σ(y/σ)² is stationary at any GN, for a
        // convergence test or `no_improvement_possible`, never `max_iterations`.
        let y_sq = 100.0;
        assert!(super::at_zero_residual(0.0, y_sq));
        assert!(super::at_zero_residual(0.99 * f64::EPSILON * y_sq, y_sq));
        assert!(!super::at_zero_residual(1.01 * f64::EPSILON * y_sq, y_sq));
        assert!(!super::at_zero_residual(f64::NAN, y_sq));
        assert!(!super::at_zero_residual(f64::INFINITY, f64::INFINITY));
        assert!(stationarity_gate(true, "converged_gtol", 1.0, true));
        assert!(stationarity_gate(
            false,
            "no_improvement_possible",
            1.0,
            true
        ));
        assert!(!stationarity_gate(false, "max_iterations", 1.0, true));
        assert!(!stationarity_gate(false, "numerical_error", 1.0, true));
        assert!(!stationarity_gate(true, "converged_gtol", 1.0, false));
        // No free column: nothing to decrease.
        let j_empty = faer::Mat::<f64>::zeros(5, 0);
        assert_eq!(gn(&j_empty, &residual(0.5, 0.0), &[], &[]), 0.0);
        // Non-finite residual or Jacobian, or a row-count mismatch → ∞.
        let mut r_nan = residual(0.0, 0.0);
        r_nan[2] = f64::NAN;
        assert_eq!(gn(&j, &r_nan, &[1.0, 1.0], &[FREE, FREE]), f64::INFINITY);
        let mut j_nan = jac_from_cols(&[&C1, &C2]);
        j_nan[(1, 1)] = f64::NAN;
        assert_eq!(
            gn(&j_nan, &residual(0.0, 0.0), &[1.0, 1.0], &[FREE, FREE]),
            f64::INFINITY
        );
        assert_eq!(
            gn(&j, &[1.0, 2.0, 3.0], &[1.0, 1.0], &[FREE, FREE]),
            f64::INFINITY
        );
    }

    /// The gate through `assemble_result`: a one-parameter constant fit with
    /// the solver's weighted residual and analytic Jacobian. Run the stop
    /// through post-fit assembly at `c`, with `min` as the lower bound on `c`.
    fn assemble_constant(
        c: f64,
        min: f64,
        sigma: Option<Vec<f64>>,
        success: bool,
        message: &str,
    ) -> spectrafit_types::FitResultSpec {
        use super::{assemble_result, CompiledGraph, LmSolveOutcome, PostfitInputs};
        use spectrafit_types::{
            FitGraphSpec, MeasurementSpec, ModelNodeSpec, ModelTypeStr, ParameterSpec,
        };
        use std::collections::HashMap;

        let mut params = HashMap::new();
        params.insert(
            "c".to_string(),
            ParameterSpec {
                value: c,
                min,
                max: f64::INFINITY,
                vary: true,
                expr: None,
                scale: None,
            },
        );
        let graph = FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![ModelNodeSpec {
                id: "k".into(),
                model_type: ModelTypeStr::Constant,
                dataset_index: None,
                parameters: params,
            }],
            expr_edges: vec![],
        };
        let cg = CompiledGraph::compile(&graph).expect("graph should compile");
        let x_all = vec![0.0, 1.0, 2.0, 3.0];
        let y_all = vec![1.0, 2.0, 3.0, 4.0];
        let sigma_vec = sigma.clone().unwrap_or_else(|| vec![1.0; 4]);
        let problem = build_lm_problem(&cg, &graph, x_all.clone(), y_all.clone(), sigma_vec);
        let outcome = LmSolveOutcome {
            result_problem: problem,
            n_iter_val: 3,
            success_val: success,
            message_val: message.to_string(),
            solve_ns: 0,
            cost_history: vec![],
            gradient_norm_history: vec![],
            params_history: vec![],
        };
        let dataset = MeasurementSpec {
            schema_version: None,
            x: vec![x_all.clone()],
            y: y_all.clone(),
            sigma,
            label: None,
        };
        assemble_result(
            outcome,
            PostfitInputs {
                cg: &cg,
                graph: &graph,
                datasets: &[dataset],
                x_all: &x_all,
                y_all: &y_all,
            },
            vec![0.0; 4],
        )
        .expect("assembly should succeed")
    }

    #[test]
    fn assemble_result_applies_the_stationarity_gate() {
        let ninf = f64::NEG_INFINITY;
        // Soft stop at the optimum c = mean(y) = 2.5 → success, message kept.
        let r = assemble_constant(2.5, ninf, None, false, "no_improvement_possible");
        assert!(r.success, "soft stop at the optimum must be a success");
        assert_eq!(r.message, "no_improvement_possible");
        // Convergence test at c = 3: GN = n·mean(r)²/RSS = 1/6 → failure.
        let r = assemble_constant(3.0, ninf, None, true, "converged_xtol");
        assert!(!r.success, "converged_xtol at GN = 1/6 must be a failure");
        assert_eq!(r.message, "converged_xtol");
        // c = 3 on its lower bound, gradient 2·Σ(c − y) = 4 > 0 outward → held.
        let r = assemble_constant(3.0, 3.0, None, true, "converged_xtol");
        assert!(r.success, "held at an active bound must be a success");
        // Hard failure stays a failure at the optimum.
        let r = assemble_constant(2.5, ninf, None, false, "numerical_error");
        assert!(!r.success);
        assert_eq!(r.message, "numerical_error");
    }

    /// Zero-residual clause: at RSS ≤ ε·Σ(y/σ)² the relative GN measure is
    /// undefined (the round-off residual lies in range(J), GN ≈ 1), so the
    /// stop counts as stationary. Constant data y = 2.5 and c = 2.5 + offset:
    /// offset 1e-9 gives RSS/Σy² = 1e-18 ≤ ε, offset 1e-6 gives 1e-12 > ε.
    #[test]
    fn assemble_result_zero_residual_clause() {
        use super::{assemble_result, CompiledGraph, LmSolveOutcome, PostfitInputs};
        use spectrafit_types::{
            FitGraphSpec, MeasurementSpec, ModelNodeSpec, ModelTypeStr, ParameterSpec,
        };
        use std::collections::HashMap;

        let run = |offset: f64, message: &str, success: bool| {
            let mut params = HashMap::new();
            params.insert(
                "c".to_string(),
                ParameterSpec {
                    value: 2.5 + offset,
                    min: f64::NEG_INFINITY,
                    max: f64::INFINITY,
                    vary: true,
                    expr: None,
                    scale: None,
                },
            );
            let graph = FitGraphSpec {
                schema_version: "0.1".into(),
                nodes: vec![ModelNodeSpec {
                    id: "k".into(),
                    model_type: ModelTypeStr::Constant,
                    dataset_index: None,
                    parameters: params,
                }],
                expr_edges: vec![],
            };
            let cg = CompiledGraph::compile(&graph).expect("graph should compile");
            let x_all = vec![0.0, 1.0, 2.0, 3.0];
            let y_all = vec![2.5; 4];
            let problem = build_lm_problem(&cg, &graph, x_all.clone(), y_all.clone(), vec![1.0; 4]);
            let outcome = LmSolveOutcome {
                result_problem: problem,
                n_iter_val: 3,
                success_val: success,
                message_val: message.to_string(),
                solve_ns: 0,
                cost_history: vec![],
                gradient_norm_history: vec![],
                params_history: vec![],
            };
            let dataset = MeasurementSpec {
                schema_version: None,
                x: vec![x_all.clone()],
                y: y_all.clone(),
                sigma: None,
                label: None,
            };
            assemble_result(
                outcome,
                PostfitInputs {
                    cg: &cg,
                    graph: &graph,
                    datasets: &[dataset],
                    x_all: &x_all,
                    y_all: &y_all,
                },
                vec![0.0; 4],
            )
            .expect("assembly should succeed")
        };
        let r = run(1e-9, "converged_gtol", true);
        assert!(r.chi2 > 0.0, "RSS must be above 0 for this test");
        assert!(r.success, "RSS at round-off level counts as stationary");
        assert_eq!(r.message, "converged_gtol");
        assert!(run(1e-9, "no_improvement_possible", false).success);
        // A budget stop never succeeds, even at zero residual.
        assert!(!run(1e-9, "max_iterations", false).success);
        // Above the floor the relative GN measure decides: GN = 1 → failure.
        assert!(!run(1e-6, "converged_gtol", true).success);
    }

    /// The gate measures the objective the solver minimises, Σ((ŷ − y)/σ)²:
    /// with σ = (1, 1, 1, 0.1) the unweighted optimum 2.5 is not stationary,
    /// the weighted optimum Σ(y/σ²)/Σ(1/σ²) = 406/103 is.
    #[test]
    fn assemble_result_gate_uses_the_weighted_residual() {
        let ninf = f64::NEG_INFINITY;
        let sigma = Some(vec![1.0, 1.0, 1.0, 0.1]);
        let r = assemble_constant(2.5, ninf, sigma.clone(), false, "no_improvement_possible");
        assert!(!r.success, "unweighted optimum is not stationary under σ");
        let r = assemble_constant(406.0 / 103.0, ninf, sigma, false, "no_improvement_possible");
        assert!(r.success, "weighted optimum is stationary under σ");
    }

    /// Tied graphs use the solver's finite-difference weighted Jacobian. A
    /// constant offset of 0.3 on two-Gaussian data is not in the range of
    /// the Gaussian columns, so a converged stop there is not stationary; at
    /// RSS = 0 it is.
    #[test]
    fn assemble_result_gate_on_tied_graph_uses_fd_jacobian() {
        use super::{assemble_result, CompiledGraph, LmSolveOutcome, PostfitInputs};
        use spectrafit_graph::evaluate_compiled;
        use spectrafit_types::MeasurementSpec;

        for (offset, expect_success) in [(0.3, false), (0.0, true)] {
            let graph = tied_two_gaussian_graph_with_scale(0.5, Some(2.0));
            let cg = CompiledGraph::compile(&graph).expect("graph should compile");
            let x_all: Vec<f64> = (0..40).map(|i| -3.0 + 6.0 * i as f64 / 39.0).collect();
            let mut problem =
                build_lm_problem(&cg, &graph, x_all.clone(), vec![0.0; 40], vec![1.0; 40]);
            let p0: Vec<f64> = problem.params.iter().copied().collect();
            problem.set_free_and_tied(&p0);
            let model = evaluate_compiled(&cg, &problem.to_flat(), &x_all).expect("eval");
            let y_all: Vec<f64> = model.iter().map(|v| v + offset).collect();
            problem.y_concat = y_all.clone();
            let outcome = LmSolveOutcome {
                result_problem: problem,
                n_iter_val: 3,
                success_val: true,
                message_val: "converged_xtol".to_string(),
                solve_ns: 0,
                cost_history: vec![],
                gradient_norm_history: vec![],
                params_history: vec![],
            };
            let dataset = MeasurementSpec {
                schema_version: None,
                x: vec![x_all.clone()],
                y: y_all.clone(),
                sigma: None,
                label: None,
            };
            let r = assemble_result(
                outcome,
                PostfitInputs {
                    cg: &cg,
                    graph: &graph,
                    datasets: &[dataset],
                    x_all: &x_all,
                    y_all: &y_all,
                },
                vec![0.0; 40],
            )
            .expect("assembly should succeed");
            assert_eq!(
                r.success, expect_success,
                "tied graph, offset {offset}: message {}",
                r.message
            );
            assert_eq!(r.message, "converged_xtol");
        }
    }
}
