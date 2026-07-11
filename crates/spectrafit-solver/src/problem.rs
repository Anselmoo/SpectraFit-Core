//! `LmProblem` — wraps the DAG graph + datasets into the
//! `levenberg_marquardt::LeastSquaresProblem` trait so the solver can drive it.
//!
//! ## Performance design
//!
//! Three classes of per-iteration overhead have been eliminated:
//!
//! 1. **Graph recompilation** — `CompiledGraph` is compiled once in `fit()` and
//!    stored as a reference; `residuals()` and `jacobian()` never call
//!    `CompiledGraph::compile()`.
//!
//! 2. **Concatenation allocations** — `x_concat` and `y_concat` are built at
//!    construction time.  `residuals()` and `jacobian()` use the cached slices
//!    directly.
//!
//! 3. **HashMap lookups in the hot path** — `node_param_bufs[i]` holds the
//!    current parameter values for `compiled.nodes[i]` as a plain `Vec<f64>`.
//!    `set_params` updates only the free-param slots using the pre-computed
//!    `free_to_node_param` index pairs — no `HashMap` operations per iteration.
//!    `evaluate_compiled_indexed` and `jacobian_compiled_indexed` consume
//!    `node_param_bufs` directly.

use std::cell::RefCell;
use std::collections::HashMap;
use std::time::Instant;

use faer::MatMut;
use levenberg_marquardt::LeastSquaresProblem;
use nalgebra::{storage::Owned, DMatrix, DVector, Dyn};
use spectrafit_graph::{
    compiler::CompiledGraph,
    executor::{jacobian_compiled_indexed_weighted_into, residuals_compiled_indexed_into},
};
use spectrafit_levenberg_marquardt::TrustRegionProblem;
use spectrafit_types::{CoreError, MeasurementSpec};

// ---------------------------------------------------------------------------
// LmProblem
// ---------------------------------------------------------------------------

/// All state needed by the LM solver.
///
/// The `'a` lifetime covers the `CompiledGraph` reference and dataset slice.
pub struct LmProblem<'a> {
    /// Pre-compiled graph (immutable during solve).
    pub compiled: &'a CompiledGraph,
    /// All measurement datasets.
    pub datasets: &'a [MeasurementSpec],
    /// `"node_id.param_name"` for every *free* parameter, canonical order.
    pub free_keys: Vec<String>,
    /// `(min, max)` bounds per free parameter.
    pub bounds: Vec<(f64, f64)>,
    /// All parameters (free + fixed), keyed by `"node_id.param_name"`.
    /// Used only in [`to_flat`] (post-solve), not touched in the hot path.
    pub all_params: HashMap<String, f64>,
    /// Per-node parameter buffers (one `Vec<f64>` per compiled node).
    ///
    /// Fixed params are filled at construction and never touched again.
    /// Free params are updated in-place by [`set_params`] via
    /// [`free_to_node_param`] — no `HashMap` involved.
    pub node_param_bufs: Vec<Vec<f64>>,
    /// Maps free-param index → `(node_idx_in_compiled, param_pos_in_node)`.
    ///
    /// Built once at construction from `compiled.node_free_cols` data.
    pub free_to_node_param: Vec<(usize, usize)>,
    /// Maps tied-target index (aligned with `compiled.tied_plan.order`) →
    /// `(node_idx, param_pos)` in `node_param_bufs`. Empty when the graph has no
    /// `expr_edges`. Used by [`apply_tied`](LmProblem::apply_tied) to write each
    /// recomputed tied value back into the node buffers each iteration.
    pub tied_to_node_param: Vec<(usize, usize)>,
    /// Cached concatenation of `x[0]` across all datasets (first dimension).
    pub x_concat: Vec<f64>,
    /// Cached concatenation of `y` across all datasets.
    pub y_concat: Vec<f64>,
    /// Current free-parameter vector **in the optimiser's working (scaled)
    /// units**, `θ'_i = θ_i / scales[i]` (updated by the LM solver each step).
    /// `node_param_bufs` always carries the *physical* values `θ_i`.
    pub params: DVector<f64>,
    /// Per-free-parameter `Parameter.scale` factors (`s_i`, defaulting to 1.0).
    ///
    /// The solver optimises the rescaled variable `θ'_i = θ_i / s_i`, so its view
    /// of every column of the Jacobian is `∂r/∂θ'_i = s_i · ∂r/∂θ_i` (chain rule).
    /// Equalising the column norms this way reshapes `JᵀJ` and hence improves the
    /// effective conditioning `κ(JᵀJ)`. With all `s_i = 1.0` every operation below
    /// is an exact arithmetic no-op (multiply/divide by 1.0), so a fit without any
    /// `scale` set is byte-for-byte identical to the un-scaled path (parity oracle).
    pub scales: Vec<f64>,
    /// Per-point σ weights: `r[i] = (ŷ[i] − y[i]) / σ[i]`.
    pub sigma: Vec<f64>,
    /// Reusable row buffer for weighted residual construction.
    pub residual_buf: RefCell<Vec<f64>>,
    /// Reusable row-major scratch buffer for analytical Jacobian construction.
    pub jacobian_buf: RefCell<Vec<f64>>,
    /// Counts calls to `residuals()` (incremented each call).
    pub residual_count: RefCell<u64>,
    /// Counts calls to `jacobian()` (incremented each call).
    pub jacobian_count: RefCell<u64>,
    /// Cumulative nanoseconds spent inside `residuals()` (profiling only).
    pub residual_time_ns: RefCell<u128>,
    /// Cumulative nanoseconds spent inside `jacobian()` (profiling only).
    pub jacobian_time_ns: RefCell<u128>,
}

impl<'a> LmProblem<'a> {
    // -----------------------------------------------------------------------
    // Post-solve helper
    // -----------------------------------------------------------------------

    /// Build a complete `{ "node_id.param_name" → value }` map from the
    /// current `node_param_bufs` (with bounds clamping already applied via
    /// `set_params`).
    ///
    /// Called **once** after the solve completes — not on the hot path.
    pub fn to_flat(&self) -> HashMap<String, f64> {
        let mut flat = self.all_params.clone();
        for (i, &(node_idx, param_pos)) in self.free_to_node_param.iter().enumerate() {
            let key = &self.free_keys[i];
            flat.insert(key.clone(), self.node_param_bufs[node_idx][param_pos]);
        }
        // Tied targets were recomputed into `node_param_bufs` by `apply_tied`;
        // surface their converged values (not the initial placeholders).
        for (ti, tp) in self.compiled.tied_plan.order.iter().enumerate() {
            let (node_idx, param_pos) = self.tied_to_node_param[ti];
            flat.insert(tp.target.clone(), self.node_param_bufs[node_idx][param_pos]);
        }
        flat
    }

    /// Install a proposed free-parameter vector with reflective bounds
    /// projection, writing directly into `node_param_bufs` and `self.params`.
    ///
    /// The incoming `params` are the optimiser's **scaled** working variables
    /// `θ'_i`; the physical value is `θ_i = θ'_i · s_i`. Bounds are expressed in
    /// physical units, so reflection is applied to `θ_i` and `node_param_bufs`
    /// receives the physical value. `self.params` stores the scaled value so the
    /// optimiser sees a consistent rescaled coordinate system. With `s_i = 1.0`
    /// this reduces exactly to the prior physical-space update.
    ///
    /// Shared by both solver front-ends ([`LeastSquaresProblem::set_params`] for
    /// the legacy `levenberg-marquardt` crate and
    /// [`TrustRegionProblem::set_params`] for the faer-native core) so the
    /// bounds/parameterisation semantics are identical on both paths.
    fn apply_free_params(&mut self, params: &[f64]) {
        for (i, &(node_idx, param_pos)) in self.free_to_node_param.iter().enumerate() {
            let s = self.scales[i];
            let (lo, hi) = self.bounds[i];
            // Optimiser variable θ'_i → physical θ_i = θ'_i · s_i.
            let physical = params[i] * s;
            let p_bounded = if lo.is_finite() || hi.is_finite() {
                reflect_into_bounds(physical, lo, hi)
            } else {
                physical
            };
            // node_param_bufs is physical; self.params is the scaled working var.
            self.params[i] = p_bounded / s;
            self.node_param_bufs[node_idx][param_pos] = p_bounded;
        }
    }

    /// Recompute expression-tied parameters from the current free values and
    /// write them back into `node_param_bufs`. No-op when the graph has no
    /// `expr_edges`. Called after every free-parameter update so the model sees
    /// the tied targets at their evaluated values.
    fn apply_tied(&mut self) {
        if self.compiled.tied_plan.is_empty() {
            return;
        }
        // Flat map = all params (fixed defaults) overlaid with current free values.
        // `self.params` is in scaled units; tied expressions are written against
        // physical parameter values, so multiply back by the per-param scale
        // (a no-op when `s_i = 1.0`).
        let mut flat = self.all_params.clone();
        for (i, key) in self.free_keys.iter().enumerate() {
            flat.insert(key.clone(), self.params[i] * self.scales[i]);
        }
        // Dependency-ordered evaluation; on a bad expression leave bufs unchanged.
        if self.compiled.tied_plan.apply(&mut flat).is_err() {
            return;
        }
        for (ti, tp) in self.compiled.tied_plan.order.iter().enumerate() {
            if let Some(&v) = flat.get(&tp.target) {
                let (node_idx, param_pos) = self.tied_to_node_param[ti];
                self.node_param_bufs[node_idx][param_pos] = v;
            }
        }
    }

    /// Install free params (with reflection) and then recompute tied targets.
    /// The single entry point both solver front-ends use to update parameters.
    pub fn set_free_and_tied(&mut self, params: &[f64]) {
        self.apply_free_params(params);
        self.apply_tied();
    }

    /// Whether the graph has expression-tied parameters.
    #[inline]
    pub fn has_tied(&self) -> bool {
        !self.compiled.tied_plan.is_empty()
    }

    /// Evaluate the weighted residual vector `r = (ŷ − y)/σ` into `out` without
    /// touching the public call counters (used internally by the finite-
    /// difference Jacobian).
    fn eval_weighted_residuals_into(&self, out: &mut [f64]) -> Result<(), CoreError> {
        residuals_compiled_indexed_into(
            self.compiled,
            &self.node_param_bufs,
            &self.x_concat,
            &self.y_concat,
            &self.sigma,
            out,
        )
    }

    /// Forward finite-difference weighted Jacobian into a row-major buffer
    /// `out[i*n_free + k] = ∂r_i/∂θ_k`. Used only when the graph has tied
    /// parameters: perturbing `θ_k` and re-applying the tied plan captures the
    /// chain-rule contribution `Σ_t (∂r/∂t)(∂t/∂θ_k)` automatically, which the
    /// analytic executor Jacobian (free columns only) omits. Restores the base
    /// parameters before returning.
    pub fn fd_weighted_jacobian_rowmajor(&mut self, out: &mut Vec<f64>) -> Result<(), CoreError> {
        let m = self.y_concat.len();
        let nf = self.free_keys.len();
        out.clear();
        out.resize(m * nf, 0.0);

        let base: Vec<f64> = self.params.iter().copied().collect();
        let mut r0 = vec![0.0_f64; m];
        self.eval_weighted_residuals_into(&mut r0)?;
        let mut rp = vec![0.0_f64; m];

        for k in 0..nf {
            let s = self.scales[k];
            let mut h = 1e-7_f64 * base[k].abs().max(1e-7);
            // Step toward the interior near an active bound: a forward step that
            // would overshoot the upper bound is reflected back by
            // `set_free_and_tied`, which folds the difference and corrupts the
            // column's sign/magnitude. Flip to a backward step there. `base` and
            // `h` are in scaled units; bounds are physical, so compare the
            // physical perturbed value `(base[k] + h) · s` (a no-op when s = 1).
            let (lo, hi) = self.bounds[k];
            if hi.is_finite() && (base[k] + h) * s > hi {
                h = -h;
            } else if lo.is_finite() && (base[k] + h) * s < lo {
                // (only reachable for h < 0 inputs; symmetric guard)
                h = -h;
            }
            let mut pert = base.clone();
            pert[k] += h;
            self.set_free_and_tied(&pert);
            self.eval_weighted_residuals_into(&mut rp)?;
            for i in 0..m {
                out[i * nf + k] = (rp[i] - r0[i]) / h;
            }
        }
        // Restore the base point (re-applies tied targets too).
        self.set_free_and_tied(&base);
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// LeastSquaresProblem implementation
// ---------------------------------------------------------------------------

impl LeastSquaresProblem<f64, Dyn, Dyn> for LmProblem<'_> {
    type ResidualStorage = Owned<f64, Dyn>;
    type JacobianStorage = Owned<f64, Dyn, Dyn>;
    type ParameterStorage = Owned<f64, Dyn>;

    /// Update free-parameter values with reflective bounds projection, writing
    /// directly into `node_param_bufs`.  O(n_free) Vec writes — no HashMap.
    ///
    /// When a proposed step overshoots a bound the value is reflected back into
    /// `[lo, hi]` rather than clamped.  Reflection avoids the oscillation that
    /// clamp-after-iterate causes when the optimum is near a boundary: the solver
    /// continues moving smoothly across the reflected region instead of stalling
    /// against the hard wall.  For extreme overshoots (double-bounce) we fall
    /// back to parking at the violated bound.
    fn set_params(&mut self, params: &DVector<f64>) {
        self.set_free_and_tied(params.as_slice());
    }

    fn params(&self) -> DVector<f64> {
        self.params.clone()
    }

    /// Weighted residual: `r[i] = (ŷ[i] − y[i]) / σ[i]`.
    fn residuals(&self) -> Option<DVector<f64>> {
        *self.residual_count.borrow_mut() += 1;
        let _t0 = Instant::now();
        let mut residual_buf = self.residual_buf.borrow_mut();
        if residual_buf.len() != self.y_concat.len() {
            residual_buf.resize(self.y_concat.len(), 0.0);
        }
        residuals_compiled_indexed_into(
            self.compiled,
            &self.node_param_bufs,
            &self.x_concat,
            &self.y_concat,
            &self.sigma,
            &mut residual_buf[..],
        )
        .ok()?;

        let capacity = residual_buf.capacity().max(residual_buf.len());
        let residuals = std::mem::replace(&mut *residual_buf, Vec::with_capacity(capacity));
        *self.residual_time_ns.borrow_mut() += _t0.elapsed().as_nanos();
        Some(DVector::from_vec(residuals))
    }

    /// Weighted Jacobian: `J[i, j] = (∂ŷ[i]/∂θ[j]) / σ[i]`.
    fn jacobian(&self) -> Option<DMatrix<f64>> {
        *self.jacobian_count.borrow_mut() += 1;
        let _t0 = Instant::now();
        let mut jacobian_buf = self.jacobian_buf.borrow_mut();
        jacobian_compiled_indexed_weighted_into(
            self.compiled,
            &self.node_param_bufs,
            &self.x_concat,
            &self.sigma,
            &mut jacobian_buf,
        )
        .ok()?;

        // Point count = residual count (one y per point), NOT the strided coord
        // length: x_concat is n_points * n_dims for an n-D fit.
        let n_points = self.y_concat.len();
        let n_free = self.compiled.free_keys.len();
        if n_free == 0 {
            *self.jacobian_time_ns.borrow_mut() += _t0.elapsed().as_nanos();
            return Some(DMatrix::zeros(n_points, 0));
        }

        // Chain rule for the scaled working variable θ'_j = θ_j / s_j:
        // ∂r/∂θ'_j = s_j · ∂r/∂θ_j. No-op when every s_j = 1.0.
        scale_columns_rowmajor(&mut jacobian_buf, n_points, n_free, &self.scales);

        let jac = DMatrix::from_row_slice(n_points, n_free, &jacobian_buf);
        *self.jacobian_time_ns.borrow_mut() += _t0.elapsed().as_nanos();
        Some(jac)
    }
}

// ---------------------------------------------------------------------------
// TrustRegionProblem implementation (faer-native core)
// ---------------------------------------------------------------------------

impl TrustRegionProblem for LmProblem<'_> {
    fn n_residuals(&self) -> usize {
        self.y_concat.len()
    }

    fn n_params(&self) -> usize {
        self.free_keys.len()
    }

    fn params(&self) -> Vec<f64> {
        self.params.iter().copied().collect()
    }

    fn set_params(&mut self, p: &[f64]) {
        self.set_free_and_tied(p);
    }

    /// Weighted residual `r[i] = (ŷ[i] − y[i]) / σ[i]` written into `r`.
    fn residuals_into(&mut self, mut r: MatMut<'_, f64>) -> Result<(), CoreError> {
        *self.residual_count.borrow_mut() += 1;
        let t0 = Instant::now();
        let mut buf = self.residual_buf.borrow_mut();
        if buf.len() != self.y_concat.len() {
            buf.resize(self.y_concat.len(), 0.0);
        }
        residuals_compiled_indexed_into(
            self.compiled,
            &self.node_param_bufs,
            &self.x_concat,
            &self.y_concat,
            &self.sigma,
            &mut buf[..],
        )?;
        for (i, &v) in buf.iter().enumerate() {
            r[(i, 0)] = v;
        }
        *self.residual_time_ns.borrow_mut() += t0.elapsed().as_nanos();
        Ok(())
    }

    /// Weighted Jacobian `J[i, j] = (∂ŷ[i]/∂θ[j]) / σ[i]` written into `jac`.
    ///
    /// With expression-tied parameters the analytic executor Jacobian (free
    /// columns only) omits the chain-rule terms, so a forward finite-difference
    /// is used instead — it captures `Σ_t (∂r/∂t)(∂t/∂θ_k)` because perturbing a
    /// free param re-applies the tied plan. The analytic path is unchanged for
    /// the common untied case.
    fn jacobian_into(&mut self, mut jac: MatMut<'_, f64>) -> Result<(), CoreError> {
        *self.jacobian_count.borrow_mut() += 1;
        let t0 = Instant::now();
        // Point count = residual count (one y per point), NOT the strided coord
        // length: x_concat is n_points * n_dims for an n-D fit.
        let n_points = self.y_concat.len();
        let n_free = self.free_keys.len();

        if self.has_tied() {
            // FD needs `&mut self`, so it cannot hold the `jacobian_buf` borrow —
            // use a local buffer.
            let mut local = Vec::new();
            self.fd_weighted_jacobian_rowmajor(&mut local)?;
            for i in 0..n_points {
                let base = i * n_free;
                for j in 0..n_free {
                    jac[(i, j)] = local[base + j];
                }
            }
        } else {
            let mut buf = self.jacobian_buf.borrow_mut();
            jacobian_compiled_indexed_weighted_into(
                self.compiled,
                &self.node_param_bufs,
                &self.x_concat,
                &self.sigma,
                &mut buf,
            )?;
            // Chain rule for the scaled working variable θ'_j = θ_j / s_j:
            // ∂r/∂θ'_j = s_j · ∂r/∂θ_j. No-op when every s_j = 1.0. (The tied
            // branch above already differentiates the scaled variable via FD, so
            // it must not be re-scaled here.)
            scale_columns_rowmajor(&mut buf, n_points, n_free, &self.scales);
            // Row-major `buf[i*n_free + j]` → faer column-major `jac[(i, j)]`.
            for i in 0..n_points {
                let base = i * n_free;
                for j in 0..n_free {
                    jac[(i, j)] = buf[base + j];
                }
            }
        }
        *self.jacobian_time_ns.borrow_mut() += t0.elapsed().as_nanos();
        Ok(())
    }

    /// Coleman–Li scaling `v_i ∈ (0,1]` = fraction of the box still available in
    /// the descent direction `−g_i`. `None` when no parameter is bounded.
    fn trust_scaling(&self, grad: &[f64]) -> Option<Vec<f64>> {
        let any_finite = self
            .bounds
            .iter()
            .any(|&(lo, hi)| lo.is_finite() || hi.is_finite());
        if !any_finite {
            return None;
        }
        let v = (0..self.free_keys.len())
            .map(|i| {
                let (lo, hi) = self.bounds[i];
                let x = self.params[i];
                let g = grad.get(i).copied().unwrap_or(0.0);
                // Distance to the bound the descent direction (−g) points toward.
                let dist = if g < 0.0 {
                    if hi.is_finite() {
                        hi - x
                    } else {
                        f64::INFINITY
                    }
                } else if g > 0.0 {
                    if lo.is_finite() {
                        x - lo
                    } else {
                        f64::INFINITY
                    }
                } else {
                    let du = if hi.is_finite() {
                        hi - x
                    } else {
                        f64::INFINITY
                    };
                    let dl = if lo.is_finite() {
                        x - lo
                    } else {
                        f64::INFINITY
                    };
                    du.min(dl)
                };
                // Scale-free: fraction of the box remaining in that direction.
                let range = if lo.is_finite() && hi.is_finite() {
                    hi - lo
                } else {
                    f64::INFINITY
                };
                if range.is_finite() && range > 0.0 {
                    (dist / range).clamp(1e-9, 1.0)
                } else {
                    1.0
                }
            })
            .collect();
        Some(v)
    }
}

// ---------------------------------------------------------------------------
// Reflective bounds helper
// ---------------------------------------------------------------------------

/// Project `p` back into `[lo, hi]` using reflection.
///
/// If `p` overshoots `hi` by `δ`, return `hi − δ` (mirror from the upper wall).
/// If `p` undershoots `lo` by `δ`, return `lo + δ` (mirror from the lower wall).
/// For extreme overshoots (reflected value still outside bounds), fall back to
/// parking at the violated bound.  Infinite bounds are treated as unconstrained.
#[inline]
fn reflect_into_bounds(p: f64, lo: f64, hi: f64) -> f64 {
    if p < lo {
        let reflected = 2.0 * lo - p;
        if hi.is_finite() && reflected > hi {
            lo
        } else {
            reflected.min(if hi.is_finite() { hi } else { f64::MAX })
        }
    } else if p > hi {
        let reflected = 2.0 * hi - p;
        if lo.is_finite() && reflected < lo {
            hi
        } else {
            reflected.max(if lo.is_finite() { lo } else { f64::MIN })
        }
    } else {
        p
    }
}

/// Multiply each column `j` of a row-major `m × n` matrix in-place by `scales[j]`.
///
/// Used to apply the `Parameter.scale` chain-rule factor to a freshly built
/// Jacobian: the solver optimises `θ'_j = θ_j / s_j`, so its column is
/// `∂r/∂θ'_j = s_j · ∂r/∂θ_j`. Columns whose scale is exactly `1.0` are skipped,
/// so the all-default (unscaled) case leaves `buf` byte-for-byte unchanged.
#[inline]
fn scale_columns_rowmajor(buf: &mut [f64], n_rows: usize, n_cols: usize, scales: &[f64]) {
    debug_assert_eq!(scales.len(), n_cols, "one scale factor per column");
    // Fast path: nothing to do when no column is rescaled (preserves parity).
    if scales.iter().all(|&s| s == 1.0) {
        return;
    }
    for row in 0..n_rows {
        let base = row * n_cols;
        for (col, &s) in scales.iter().enumerate() {
            if s != 1.0 {
                buf[base + col] *= s;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reflect_within_bounds_unchanged() {
        assert_eq!(reflect_into_bounds(0.5, 0.0, 1.0), 0.5);
    }

    #[test]
    fn reflect_overshoot_upper() {
        // p=1.2, hi=1.0 → reflected = 2*1.0 - 1.2 = 0.8
        assert!((reflect_into_bounds(1.2, 0.0, 1.0) - 0.8).abs() < 1e-12);
    }

    #[test]
    fn reflect_overshoot_lower() {
        // p=-0.3, lo=0.0 → reflected = 2*0.0 - (-0.3) = 0.3
        assert!((reflect_into_bounds(-0.3, 0.0, 1.0) - 0.3).abs() < 1e-12);
    }

    #[test]
    fn reflect_extreme_overshoot_parks_at_bound() {
        // p=3.0, lo=0.0, hi=1.0 → reflected=2*1.0-3.0=-1.0 < lo → park at hi=1.0
        assert_eq!(reflect_into_bounds(3.0, 0.0, 1.0), 1.0);
    }

    #[test]
    fn reflect_infinite_bounds_unchanged() {
        let p = -999.0;
        assert_eq!(reflect_into_bounds(p, f64::NEG_INFINITY, f64::INFINITY), p);
    }
}
