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
    jacobian_compiled_indexed_weighted_into, residuals_compiled_indexed_into, CompiledGraph,
};
use spectrafit_levenberg_marquardt::TrustRegionProblem;
use spectrafit_types::{fd_step, CoreError, FdScheme, JacobianMode};

// ---------------------------------------------------------------------------
// LmProblem
// ---------------------------------------------------------------------------

/// All state needed by the LM solver.
///
/// The `'a` lifetime covers the `CompiledGraph` reference and dataset slice.
pub struct LmProblem<'a> {
    /// Pre-compiled graph (immutable during solve).
    pub compiled: &'a CompiledGraph,
    // NOTE: a `datasets: &'a [MeasurementSpec]` field was removed when the
    // crate's modules became private. It was assigned at construction and never
    // read — `x_concat` / `y_concat` below supersede it — but was invisible as
    // dead code while `pub mod lm_problem;` made the field publicly reachable.
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
    /// `FitOptionsSpec.jacobian`: whether the caller forced the graph-level
    /// finite-difference Jacobian. Read only by [`fd_jacobian_forced`]
    /// (the one place the option is consulted).
    ///
    /// [`fd_jacobian_forced`]: LmProblem::fd_jacobian_forced
    pub jacobian_mode: JacobianMode,
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
    ///
    /// The faer LM family (`lm` / `trf` / `geodesic` / `auto`) projects every
    /// trial point onto the box from [`bounds`](TrustRegionProblem::bounds)
    /// before calling `set_params` (projected LM step, Kanzow, Yamashita,
    /// Fukushima 2004; #93), so on that path the point arrives inside the box
    /// and the reflection here is the identity (up to an ulp of the
    /// `θ'_i · s_i` round trip for `s_i ≠ 1`). Reflection stays in effect for
    /// `lm-legacy`, `dogleg` and `newton-cg`.
    fn apply_free_params(&mut self, params: &[f64]) {
        Self::project_free_params(
            &self.free_to_node_param,
            &self.scales,
            &self.bounds,
            params,
            self.params.as_mut_slice(),
            &mut self.node_param_bufs,
        );
    }

    /// Reflect the optimiser's scaled working values `params` into the box,
    /// writing the scaled result into `scaled` and the physical value into
    /// `bufs`. The arithmetic behind [`apply_free_params`] (which targets the
    /// problem's own state) and the finite-difference Jacobian (which targets
    /// scratch copies), so both see identical parameter values.
    ///
    /// [`apply_free_params`]: LmProblem::apply_free_params
    fn project_free_params(
        free_to_node_param: &[(usize, usize)],
        scales: &[f64],
        bounds: &[(f64, f64)],
        params: &[f64],
        scaled: &mut [f64],
        bufs: &mut [Vec<f64>],
    ) {
        for (i, &(node_idx, param_pos)) in free_to_node_param.iter().enumerate() {
            let s = scales[i];
            let (lo, hi) = bounds[i];
            // Optimiser variable θ'_i → physical θ_i = θ'_i · s_i.
            let physical = params[i] * s;
            let p_bounded = if lo.is_finite() || hi.is_finite() {
                reflect_into_bounds(physical, lo, hi)
            } else {
                physical
            };
            // `bufs` is physical; `scaled` is the scaled working variable.
            scaled[i] = p_bounded / s;
            bufs[node_idx][param_pos] = p_bounded;
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
        let mut bufs = std::mem::take(&mut self.node_param_bufs);
        self.write_tied_into(self.params.as_slice(), &mut bufs);
        self.node_param_bufs = bufs;
    }

    /// Evaluate the tied targets for the scaled free values `scaled` and write
    /// them into `bufs`. Shared by [`apply_tied`] and the finite-difference
    /// Jacobian. On a bad expression `bufs` is left unchanged.
    ///
    /// [`apply_tied`]: LmProblem::apply_tied
    fn write_tied_into(&self, scaled: &[f64], bufs: &mut [Vec<f64>]) {
        if self.compiled.tied_plan.is_empty() {
            return;
        }
        // Flat map = all params (fixed defaults) overlaid with current free values.
        // `scaled` is in scaled units; tied expressions are written against
        // physical parameter values, so multiply back by the per-param scale
        // (a no-op when `s_i = 1.0`).
        let mut flat = self.all_params.clone();
        for (i, key) in self.free_keys.iter().enumerate() {
            flat.insert(key.clone(), scaled[i] * self.scales[i]);
        }
        // Dependency-ordered evaluation; on a bad expression leave bufs unchanged.
        if self.compiled.tied_plan.apply(&mut flat).is_err() {
            return;
        }
        for (ti, tp) in self.compiled.tied_plan.order.iter().enumerate() {
            if let Some(&v) = flat.get(&tp.target) {
                let (node_idx, param_pos) = self.tied_to_node_param[ti];
                bufs[node_idx][param_pos] = v;
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

    /// Whether the caller forced the finite-difference Jacobian
    /// (`FitOptionsSpec.jacobian = "finite_difference"`, #93).
    ///
    /// This is the one place the option is read. Every Jacobian consumer of
    /// the LM family goes through it: [`uses_fd_jacobian`] (the faer
    /// trust-region front end behind `lm`/`trf`/`geodesic`/`dogleg`/`newton-cg`,
    /// and the post-fit covariance) and the `lm-legacy` front end.
    ///
    /// [`uses_fd_jacobian`]: LmProblem::uses_fd_jacobian
    #[inline]
    pub fn fd_jacobian_forced(&self) -> bool {
        match self.jacobian_mode {
            JacobianMode::Analytic => false,
            JacobianMode::FiniteDifference => true,
        }
    }

    /// Whether the weighted Jacobian is the graph-level forward difference
    /// ([`fd_weighted_jacobian_rowmajor`]) rather than the per-kernel executor
    /// Jacobian: when forced by the option, or when the graph has tied
    /// parameters (whose chain-rule terms the executor Jacobian omits).
    ///
    /// [`fd_weighted_jacobian_rowmajor`]: LmProblem::fd_weighted_jacobian_rowmajor
    #[inline]
    pub fn uses_fd_jacobian(&self) -> bool {
        self.fd_jacobian_forced() || self.has_tied()
    }

    /// Evaluate the weighted residual vector `r = (ŷ − y)/σ` at the node
    /// buffers `bufs` into `out` without touching the public call counters
    /// (used internally by the finite-difference Jacobian).
    fn eval_weighted_residuals_into(
        &self,
        bufs: &[Vec<f64>],
        out: &mut [f64],
    ) -> Result<(), CoreError> {
        residuals_compiled_indexed_into(
            self.compiled,
            bufs,
            &self.x_concat,
            &self.y_concat,
            &self.sigma,
            out,
        )
    }

    /// Forward finite-difference weighted Jacobian into a row-major buffer
    /// `out[i*n_free + k] = ∂r_i/∂θ'_k` with respect to the optimiser's scaled
    /// working variable `θ'_k`, step `h_k = 1e-7 · max(|θ'_k|, 1e-7)`.
    ///
    /// Used when [`uses_fd_jacobian`] is true: for tied graphs, perturbing `θ_k`
    /// and re-applying the tied plan captures the chain-rule contribution
    /// `Σ_t (∂r/∂t)(∂t/∂θ_k)` that the analytic executor Jacobian (free columns
    /// only) omits; when forced by `FitOptionsSpec.jacobian`, it replaces every
    /// kernel's Jacobian with one full residual evaluation per free parameter.
    ///
    /// Method: the forward-difference formula, Nocedal & Wright, *Numerical
    /// Optimization*, 2nd ed., §8.1, eq. (8.1). MINPACK `fdjac2` (Moré, Garbow &
    /// Hillstrom, ANL-80-74, 1980), behind `lmdif` and lmfit's `leastsq`, uses
    /// the same forward difference with a different step, `sqrt(epsfcn)·|x|`.
    ///
    /// The perturbations are applied to scratch copies of the parameter
    /// buffers, so the problem's own state is never moved (the previous
    /// mutate-and-restore version could shift a working parameter by one ulp
    /// on the `θ' · s / s` round trip when `Parameter.scale ≠ 1`).
    ///
    /// # Errors
    /// Returns [`CoreError`] when weighted-residual evaluation
    /// (`residuals_compiled_indexed_into`, called once per perturbation) fails
    /// — e.g. a coordinate-layout/output-buffer shape mismatch, or an
    /// out-of-bounds dataset scope on a graph with `dataset_index`-scoped nodes.
    ///
    /// [`uses_fd_jacobian`]: LmProblem::uses_fd_jacobian
    pub fn fd_weighted_jacobian_rowmajor(&self, out: &mut Vec<f64>) -> Result<(), CoreError> {
        let m = self.y_concat.len();
        let nf = self.free_keys.len();
        out.clear();
        out.resize(m * nf, 0.0);

        let base: Vec<f64> = self.params.iter().copied().collect();
        let mut r0 = vec![0.0_f64; m];
        self.eval_weighted_residuals_into(&self.node_param_bufs, &mut r0)?;
        let mut rp = vec![0.0_f64; m];
        let mut bufs = self.node_param_bufs.clone();
        let mut scaled = base.clone();
        let mut pert = base.clone();

        for k in 0..nf {
            let s = self.scales[k];
            // Step `√ε · max(|θ'_k|, 1)` in the optimiser's scaled variable
            // θ' = θ / s, so the typical magnitude of the physical parameter is
            // its `Parameter.scale` (Dennis and Schnabel 1996, §5.4; see
            // `spectrafit_types::numdiff`). The floor keeps the step from
            // collapsing at θ = 0 (#92: the old `1e-7 · max(|θ|, 1e-7)` gave
            // `h = 1e-14` there and a column error of order 1e-2).
            let mut h = fd_step(base[k], 1.0, FdScheme::Forward);
            // Step toward the interior near an active bound: a forward step that
            // would overshoot the upper bound is reflected back by the bounds
            // projection, which folds the difference and corrupts the column's
            // sign/magnitude. Flip to a backward step there. `base` and `h` are
            // in scaled units; bounds are physical, so compare the physical
            // perturbed value `(base[k] + h) · s` (a no-op when s = 1).
            let (lo, hi) = self.bounds[k];
            if hi.is_finite() && (base[k] + h) * s > hi {
                if lo.is_finite() && (base[k] - h) * s < lo {
                    // The interval is narrower than the step: both directions
                    // leave it, and reflection would park the value back on the
                    // bound. Step into the side with more room, by that room.
                    let up = hi / s - base[k];
                    let down = base[k] - lo / s;
                    h = if up >= down { up } else { -down };
                } else {
                    h = -h;
                }
            }
            pert[k] = base[k] + h;
            Self::project_free_params(
                &self.free_to_node_param,
                &self.scales,
                &self.bounds,
                &pert,
                &mut scaled,
                &mut bufs,
            );
            self.write_tied_into(&scaled, &mut bufs);
            self.eval_weighted_residuals_into(&bufs, &mut rp)?;
            // Divide by the step actually taken, `θ'_pert − θ'_base`, not by `h`:
            // this is the representable step (Dennis and Schnabel, A5.4.1) and
            // also absorbs the rounding of the scale round trip in
            // `project_free_params`. A parameter that cannot move (`lo == hi`)
            // gets a zero column instead of 0/0.
            let step = scaled[k] - base[k];
            for i in 0..m {
                out[i * nf + k] = if step == 0.0 {
                    0.0
                } else {
                    (rp[i] - r0[i]) / step
                };
            }
            pert[k] = base[k];
        }
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
    /// `[lo, hi]`.  For extreme overshoots (double-bounce) we fall back to
    /// parking at the violated bound. This path serves `lm-legacy` only; the
    /// faer LM family projects trial points onto the box in its driver instead
    /// (see [`apply_free_params`](LmProblem::apply_free_params)).
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
    ///
    /// Honours a forced finite-difference Jacobian
    /// ([`fd_jacobian_forced`](LmProblem::fd_jacobian_forced)). In the default
    /// mode this `lm-legacy` front end keeps its previous behaviour, which uses
    /// the executor Jacobian on tied graphs too (unchanged here).
    fn jacobian(&self) -> Option<DMatrix<f64>> {
        *self.jacobian_count.borrow_mut() += 1;
        let _t0 = Instant::now();
        let mut jacobian_buf = self.jacobian_buf.borrow_mut();
        if self.fd_jacobian_forced() {
            // The FD Jacobian already differentiates the scaled working
            // variable, so it is not column-scaled again.
            self.fd_weighted_jacobian_rowmajor(&mut jacobian_buf).ok()?;
            let jac =
                DMatrix::from_row_slice(self.y_concat.len(), self.free_keys.len(), &jacobian_buf);
            *self.jacobian_time_ns.borrow_mut() += _t0.elapsed().as_nanos();
            return Some(jac);
        }
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
    /// free param re-applies the tied plan. The same forward difference replaces
    /// every kernel's Jacobian when the caller forces it
    /// (`FitOptionsSpec.jacobian = "finite_difference"`). The analytic path is
    /// unchanged for the default untied case. The switch is
    /// [`uses_fd_jacobian`](LmProblem::uses_fd_jacobian).
    fn jacobian_into(&mut self, mut jac: MatMut<'_, f64>) -> Result<(), CoreError> {
        *self.jacobian_count.borrow_mut() += 1;
        let t0 = Instant::now();
        // Point count = residual count (one y per point), NOT the strided coord
        // length: x_concat is n_points * n_dims for an n-D fit.
        let n_points = self.y_concat.len();
        let n_free = self.free_keys.len();

        if self.uses_fd_jacobian() {
            let mut buf = self.jacobian_buf.borrow_mut();
            self.fd_weighted_jacobian_rowmajor(&mut buf)?;
            for i in 0..n_points {
                let base = i * n_free;
                for j in 0..n_free {
                    jac[(i, j)] = buf[base + j];
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
            // ∂r/∂θ'_j = s_j · ∂r/∂θ_j. No-op when every s_j = 1.0. (The FD
            // branch above already differentiates the scaled variable, so
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

    /// Box bounds in the optimiser's working units: the physical bounds
    /// divided by the per-parameter scale, `(lo / s_i, hi / s_i)` (`s_i > 0` is
    /// guaranteed where the scales are built in `dispatch`). `None` when no free
    /// parameter has a finite bound, matching [`trust_scaling`](Self::trust_scaling).
    fn bounds(&self) -> Option<Vec<(f64, f64)>> {
        let any_finite = self
            .bounds
            .iter()
            .any(|&(lo, hi)| lo.is_finite() || hi.is_finite());
        if !any_finite {
            return None;
        }
        Some(
            self.bounds
                .iter()
                .zip(self.scales.iter())
                .map(|(&(lo, hi), &s)| (lo / s, hi / s))
                .collect(),
        )
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
    use spectrafit_types::{FitGraphSpec, ModelNodeSpec, ModelTypeStr, ParameterSpec};

    // ── helpers ──────────────────────────────────────────────────────────────
    //
    // Mirror `dispatch::tests`' helper style (`make_param`/`gaussian`) plus a
    // `build_test_problem` that replicates the index-buffer construction
    // `dispatch::prepare_lm_pre_solve` / `build_node_param_buffers` perform for
    // a real fit, so `LmProblem` methods can be unit-tested directly without
    // going through the public `fit()` entry point.

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

    /// Analytical Gaussian: A · exp(−(x−c)² / (2σ²))
    fn gaussian(x: f64, amplitude: f64, center: f64, sigma: f64) -> f64 {
        amplitude * (-(x - center).powi(2) / (2.0 * sigma * sigma)).exp()
    }

    /// Build a fully-wired `LmProblem` from a compiled graph and a flat
    /// `"node.param" -> value` map. `bounds`/`scales` are given in `free_keys`
    /// order (`cg.free_keys`); `x_concat`/`y_concat` are the caller's
    /// pre-concatenated point data.
    fn build_test_problem<'a>(
        cg: &'a CompiledGraph,
        all_params: &HashMap<String, f64>,
        bounds: Vec<(f64, f64)>,
        scales: Vec<f64>,
        x_concat: Vec<f64>,
        y_concat: Vec<f64>,
    ) -> LmProblem<'a> {
        let free_keys = cg.free_keys.clone();

        let node_param_bufs: Vec<Vec<f64>> = (0..cg.nodes.len())
            .map(|i| cg.node_params(i, all_params).unwrap())
            .collect();

        // Invert `node_free_cols`: free-key index (col) -> (node_idx, local_idx).
        let mut free_to_node_param = vec![(0usize, 0usize); cg.free_keys.len()];
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
                let (nid, pname) = tp.target.split_once('.').unwrap();
                let ni = cg.nodes.iter().position(|n| n.id == nid).unwrap();
                let pos = cg.nodes[ni]
                    .param_names
                    .iter()
                    .position(|p| p == pname)
                    .unwrap();
                (ni, pos)
            })
            .collect();

        let init_params: Vec<f64> = free_keys
            .iter()
            .zip(scales.iter())
            .map(|(k, &s)| all_params[k] / s)
            .collect();

        let n_free = free_keys.len();
        let y_len = y_concat.len();

        LmProblem {
            compiled: cg,
            free_keys,
            bounds,
            all_params: all_params.clone(),
            node_param_bufs,
            free_to_node_param,
            tied_to_node_param,
            x_concat,
            y_concat,
            params: DVector::from_vec(init_params),
            scales,
            sigma: vec![1.0; y_len],
            jacobian_mode: JacobianMode::Analytic,
            residual_buf: RefCell::new(vec![0.0; y_len]),
            jacobian_buf: RefCell::new(vec![0.0; y_len * n_free]),
            residual_count: RefCell::new(0),
            jacobian_count: RefCell::new(0),
            residual_time_ns: RefCell::new(0),
            jacobian_time_ns: RefCell::new(0),
        }
    }

    /// Single-Gaussian-node graph with `amplitude`/`center` free and `sigma`
    /// fixed, and no `expr_edges` (untied) — the base graph shared by several
    /// tests below.
    fn single_gaussian_graph(amplitude_vary: bool, center_vary: bool) -> FitGraphSpec {
        let mut params: HashMap<String, ParameterSpec> = HashMap::new();
        params.insert("amplitude".into(), make_param(5.0, amplitude_vary));
        params.insert("center".into(), make_param(0.0, center_vary));
        params.insert("sigma".into(), make_param(1.0, false));

        FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![ModelNodeSpec {
                id: "g1".into(),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: None,
                parameters: params,
            }],
            expr_edges: vec![],
        }
    }

    fn single_gaussian_all_params() -> HashMap<String, f64> {
        let mut all_params: HashMap<String, f64> = HashMap::new();
        all_params.insert("g1.amplitude".into(), 5.0);
        all_params.insert("g1.center".into(), 0.0);
        all_params.insert("g1.sigma".into(), 1.0);
        all_params
    }

    // ── apply_tied: expression-evaluation-failure branch (line ~179) ─────────

    #[test]
    fn apply_tied_leaves_node_bufs_unchanged_when_expr_eval_errors() {
        // `center` is tied to `amplitude / sigma`; `sigma` is fixed at 0.0, so
        // `TiedPlan::apply` fails with `DivisionByZero` on every call. This
        // exercises the "on a bad expression leave bufs unchanged" early
        // return in `apply_tied`: the tied target's `node_param_bufs` slot
        // must NOT be overwritten (with a stale/garbage value) when the plan
        // errors, while the ordinary free-parameter update still lands.
        let mut params: HashMap<String, ParameterSpec> = HashMap::new();
        params.insert("amplitude".into(), make_param(2.0, true));
        params.insert("center".into(), make_param(99.0, false));
        params.insert("sigma".into(), make_param(0.0, false));

        let graph = FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![ModelNodeSpec {
                id: "g1".into(),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: None,
                parameters: params,
            }],
            expr_edges: vec![spectrafit_types::ExprEdge {
                target_node: "g1".into(),
                target_param: "center".into(),
                expression: "g1.amplitude / g1.sigma".into(),
            }],
        };
        let cg = CompiledGraph::compile(&graph).expect("graph should compile");
        assert!(!cg.tied_plan.is_empty(), "center should be a tied target");

        let mut all_params: HashMap<String, f64> = HashMap::new();
        all_params.insert("g1.amplitude".into(), 2.0);
        all_params.insert("g1.center".into(), 99.0);
        all_params.insert("g1.sigma".into(), 0.0);

        let mut problem = build_test_problem(
            &cg,
            &all_params,
            vec![(f64::NEG_INFINITY, f64::INFINITY)],
            vec![1.0],
            vec![0.0, 1.0],
            vec![0.0, 0.0],
        );

        let (tied_node_idx, tied_param_pos) = problem.tied_to_node_param[0];
        assert_eq!(problem.node_param_bufs[tied_node_idx][tied_param_pos], 99.0);

        // Drives `apply_free_params` (amplitude -> 3.0) then `apply_tied`,
        // whose `TiedPlan::apply` errors (division by zero) and must return
        // before touching `node_param_bufs` for the tied target.
        problem.set_free_and_tied(&[3.0]);

        match problem.free_to_node_param.first() {
            Some(&(ni, pp)) => assert_eq!(
                problem.node_param_bufs[ni][pp], 3.0,
                "the free amplitude slot should still be updated normally"
            ),
            other => panic!("expected exactly one free-param mapping, got {other:?}"),
        }
        assert_eq!(
            problem.node_param_bufs[tied_node_idx][tied_param_pos], 99.0,
            "tied target slot must be left untouched when tied_plan.apply() errors"
        );
    }

    // ── fd_weighted_jacobian_rowmajor: upper-bound step-flip (line ~250) ─────

    #[test]
    fn fd_jacobian_flips_step_direction_at_upper_bound() {
        // `amplitude` sits exactly at its upper bound; the default forward FD
        // step would push it past the bound, so `fd_weighted_jacobian_rowmajor`
        // must flip to a backward step instead of reflecting garbage.
        let graph = single_gaussian_graph(true, false);
        let all_params = single_gaussian_all_params();

        let x = vec![-1.0, 0.0, 1.0];
        let y: Vec<f64> = x.iter().map(|&xi| gaussian(xi, 5.0, 0.0, 1.0)).collect();

        let cg = CompiledGraph::compile(&graph).expect("graph should compile");
        let problem = build_test_problem(
            &cg,
            &all_params,
            vec![(0.0, 5.0)], // amplitude pinned exactly at its upper bound
            vec![1.0],
            x,
            y,
        );

        let mut out = Vec::new();
        problem
            .fd_weighted_jacobian_rowmajor(&mut out)
            .expect("finite-difference Jacobian should succeed at a boundary point");

        assert_eq!(out.len(), problem.y_concat.len());
        assert!(out.iter().all(|v| v.is_finite()));
        // The backward difference must reproduce the analytic amplitude column
        // ∂r/∂A = exp(−x²/2) (σ_w = 1), not a reflected/folded one.
        let reference: Vec<f64> = problem
            .x_concat
            .iter()
            .map(|&xi| gaussian(xi, 1.0, 0.0, 1.0))
            .collect();
        let err = column_rel_err(&out, 1, 0, &reference);
        assert!(
            err <= TIED_FD_RTOL,
            "upper-bound column rel err = {err:.3e}"
        );
        // The base point must be restored exactly after the perturb/backward-diff.
        assert_eq!(problem.params[0], 5.0);
    }

    // ── fd_weighted_jacobian_rowmajor: step at θ = 0 (#92) ───────────────────
    //
    // The tied path differentiates the weighted residual by forward differences.
    // With the old step `1e-7 · max(|θ|, 1e-7)` a free parameter at (or within
    // 1e-7 of) zero got `h = 1e-14`, and the column was dominated by rounding in
    // the residuals: an error of order 1e-2 relative. The cases below are the
    // ones the EELS fits hit — a centre at 0 and an amplitude held on its lower
    // bound of 0 — checked against the analytic chain-rule column.

    /// Column error threshold, `‖fd − ref‖∞ / ‖ref‖∞`, for the tied-path
    /// forward-difference Jacobian against the analytic chain-rule column.
    /// A forward difference with a non-collapsing step is accurate to about
    /// `√ε ≈ 1.5e-8` relative on this problem; `h = 1e-14` gives about 1e-2.
    const TIED_FD_RTOL: f64 = 1e-6;

    /// `‖fd − ref‖∞ / ‖ref‖∞` over one Jacobian column (row-major `fd`, `nf`
    /// columns). `reference` must not be identically zero.
    fn column_rel_err(fd: &[f64], nf: usize, k: usize, reference: &[f64]) -> f64 {
        let mut diff = 0.0_f64;
        let mut norm = 0.0_f64;
        for (i, &r) in reference.iter().enumerate() {
            // `f64::max` drops a NaN operand, so carry it explicitly.
            let e = (fd[i * nf + k] - r).abs();
            diff = if e.is_nan() || diff.is_nan() {
                f64::NAN
            } else {
                diff.max(e)
            };
            norm = norm.max(r.abs());
        }
        assert!(norm > 0.0, "reference column {k} is identically zero");
        diff / norm
    }

    /// Two unit-width Gaussians with `g2.center = g1.center + 1` (an
    /// expression tie, so the FD path is taken). Free: `g1.amplitude`,
    /// `g1.center`, `g2.amplitude`; both sigmas fixed at 1.
    fn tied_two_gaussian_graph(a1: f64, c1: f64, a2: f64) -> FitGraphSpec {
        let mut p1: HashMap<String, ParameterSpec> = HashMap::new();
        p1.insert("amplitude".into(), make_param(a1, true));
        p1.insert("center".into(), make_param(c1, true));
        p1.insert("sigma".into(), make_param(1.0, false));
        let mut p2: HashMap<String, ParameterSpec> = HashMap::new();
        p2.insert("amplitude".into(), make_param(a2, true));
        p2.insert("center".into(), make_param(c1 + 1.0, false));
        p2.insert("sigma".into(), make_param(1.0, false));
        FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![
                ModelNodeSpec {
                    id: "g1".into(),
                    model_type: ModelTypeStr::Gaussian,
                    dataset_index: None,
                    parameters: p1,
                },
                ModelNodeSpec {
                    id: "g2".into(),
                    model_type: ModelTypeStr::Gaussian,
                    dataset_index: None,
                    parameters: p2,
                },
            ],
            expr_edges: vec![spectrafit_types::ExprEdge {
                target_node: "g2".into(),
                target_param: "center".into(),
                expression: "g1.center + 1".into(),
            }],
        }
    }

    /// Worst column error of the tied FD Jacobian at `(a1, c1, a2)` with
    /// `g2.amplitude` in the physical interval `g2_amplitude_bounds` and the
    /// given per-free-key scales (`scale_of(key)`), one entry per free key:
    /// `(key, error)`.
    fn tied_fd_column_errors(
        a1: f64,
        c1: f64,
        a2: f64,
        g2_amplitude_bounds: (f64, f64),
        scale_of: impl Fn(&str) -> f64,
    ) -> Vec<(String, f64)> {
        let graph = tied_two_gaussian_graph(a1, c1, a2);
        let cg = CompiledGraph::compile(&graph).expect("graph should compile");
        assert!(!cg.tied_plan.is_empty(), "g2.center must be a tied target");

        let mut all_params: HashMap<String, f64> = HashMap::new();
        all_params.insert("g1.amplitude".into(), a1);
        all_params.insert("g1.center".into(), c1);
        all_params.insert("g1.sigma".into(), 1.0);
        all_params.insert("g2.amplitude".into(), a2);
        all_params.insert("g2.center".into(), c1 + 1.0);
        all_params.insert("g2.sigma".into(), 1.0);

        // Non-zero residuals: the data come from a different parameter set, so
        // rounding in r is of the size of the data, as in a real fit.
        let x: Vec<f64> = (0..91).map(|i| -4.0 + 0.1 * f64::from(i)).collect();
        let y: Vec<f64> = x
            .iter()
            .map(|&xi| gaussian(xi, 5.0, 0.3, 1.0) + gaussian(xi, 2.0, 1.3, 1.0))
            .collect();

        let bounds: Vec<(f64, f64)> = cg
            .free_keys
            .iter()
            .map(|k| match k.as_str() {
                "g2.amplitude" => g2_amplitude_bounds,
                _ => (f64::NEG_INFINITY, f64::INFINITY),
            })
            .collect();
        let scales: Vec<f64> = cg.free_keys.iter().map(|k| scale_of(k)).collect();
        let mut problem =
            build_test_problem(&cg, &all_params, bounds, scales.clone(), x.clone(), y);
        let base: Vec<f64> = problem.params.iter().copied().collect();
        problem.set_free_and_tied(&base);

        let nf = cg.free_keys.len();
        let mut fd = Vec::new();
        problem
            .fd_weighted_jacobian_rowmajor(&mut fd)
            .expect("finite-difference Jacobian should succeed");

        // Analytic chain-rule columns of r = ŷ − y (σ = 1), in the optimiser's
        // scaled variable θ' = θ / s, i.e. multiplied by s.
        let c2 = c1 + 1.0;
        let g1 = |xi: f64| (-(xi - c1).powi(2) / 2.0).exp();
        let g2 = |xi: f64| (-(xi - c2).powi(2) / 2.0).exp();
        cg.free_keys
            .iter()
            .enumerate()
            .map(|(k, key)| {
                let s = scales[k];
                let reference: Vec<f64> = x
                    .iter()
                    .map(|&xi| {
                        s * match key.as_str() {
                            "g1.amplitude" => g1(xi),
                            "g1.center" => a1 * (xi - c1) * g1(xi) + a2 * (xi - c2) * g2(xi),
                            "g2.amplitude" => g2(xi),
                            other => panic!("unexpected free key {other}"),
                        }
                    })
                    .collect();
                (key.clone(), column_rel_err(&fd, nf, k, &reference))
            })
            .collect()
    }

    #[test]
    fn fd_tied_jacobian_column_accurate_at_zero_parameters() {
        // #92: g1.center at exactly 0 (and within 1e-12 of it), g2.amplitude
        // held exactly on its lower bound 0.
        let mut failures = Vec::new();
        for c1 in [0.0, 1e-12, -1e-12] {
            for (key, err) in tied_fd_column_errors(5.0, c1, 0.0, (0.0, f64::INFINITY), |_| 1.0) {
                eprintln!("#92 tied FD c1 = {c1:e}: {key} column rel err = {err:.3e}");
                if err.is_nan() || err > TIED_FD_RTOL {
                    failures.push(format!("c1 = {c1:e}, {key}: {err:.3e}"));
                }
            }
        }
        assert!(
            failures.is_empty(),
            "tied FD Jacobian column error above {TIED_FD_RTOL:e}: {failures:?}"
        );
    }

    #[test]
    fn fd_tied_jacobian_floor_follows_parameter_scale() {
        // The step floor is applied in the optimiser's scaled units, so a
        // `Parameter.scale` of 10 on g2.amplitude sets its typical magnitude:
        // the physical step at 0 is 10 · √ε. The column (in scaled units, 10× the
        // physical one) must still match the analytic reference.
        let scale_of = |k: &str| if k == "g2.amplitude" { 10.0 } else { 1.0 };
        let errs = tied_fd_column_errors(5.0, 0.0, 0.0, (0.0, f64::INFINITY), scale_of);
        for (key, err) in &errs {
            eprintln!("#92 tied FD, scale 10 on g2.amplitude: {key} column rel err = {err:.3e}");
        }
        assert!(
            errs.iter().all(|(_, e)| *e <= TIED_FD_RTOL),
            "tied FD Jacobian column error above {TIED_FD_RTOL:e}: {errs:?}"
        );
    }

    #[test]
    fn fd_tied_jacobian_bound_interval_narrower_than_step() {
        // With a non-collapsing step a bound interval can be narrower than the
        // step itself: g2.amplitude at 0 in [0, 1e-7] with scale 10 has a
        // physical forward step of 10 · √ε ≈ 1.5e-7. The forward step overshoots
        // the upper bound, and the flipped backward step overshoots the lower
        // one; `reflect_into_bounds` then parks the value back at 0, so neither
        // direction perturbs the parameter. The step must stay inside the
        // interval, and the column must still match the analytic reference.
        let scale_of = |k: &str| if k == "g2.amplitude" { 10.0 } else { 1.0 };
        let errs = tied_fd_column_errors(5.0, 0.0, 0.0, (0.0, 1e-7), scale_of);
        for (key, err) in &errs {
            eprintln!("#92 tied FD, g2.amplitude in [0, 1e-7]: {key} column rel err = {err:.3e}");
        }
        assert!(
            errs.iter().all(|(_, e)| *e <= TIED_FD_RTOL),
            "tied FD Jacobian column error above {TIED_FD_RTOL:e}: {errs:?}"
        );
    }

    #[test]
    fn fd_jacobian_zero_column_when_bounds_pin_a_free_parameter() {
        // A free parameter with `lo == hi` cannot move in either direction: the
        // step is 0, and the column must be 0 rather than 0/0 = NaN.
        let graph = single_gaussian_graph(true, false);
        let all_params = single_gaussian_all_params();
        let x = vec![-1.0, 0.0, 1.0];
        let y: Vec<f64> = x.iter().map(|&xi| gaussian(xi, 4.0, 0.0, 1.0)).collect();
        let cg = CompiledGraph::compile(&graph).expect("graph should compile");
        let problem = build_test_problem(&cg, &all_params, vec![(5.0, 5.0)], vec![1.0], x, y);

        let mut out = Vec::new();
        problem
            .fd_weighted_jacobian_rowmajor(&mut out)
            .expect("finite-difference Jacobian should succeed");
        assert_eq!(out, vec![0.0; 3]);
        assert_eq!(problem.params[0], 5.0);
    }

    // ── LeastSquaresProblem::jacobian: n_free == 0 branch (lines ~338-339) ───

    #[test]
    fn jacobian_returns_zero_width_matrix_when_all_params_fixed() {
        let graph = single_gaussian_graph(false, false);
        let all_params = single_gaussian_all_params();

        let cg = CompiledGraph::compile(&graph).expect("graph should compile");
        assert!(cg.free_keys.is_empty(), "every param is fixed");

        let x = vec![0.0, 1.0, 2.0];
        let y = vec![0.0, 0.0, 0.0];
        let problem = build_test_problem(&cg, &all_params, vec![], vec![], x, y);

        let jac = problem
            .jacobian()
            .expect("jacobian() should succeed even with zero free params");
        assert_eq!(jac.nrows(), 3);
        assert_eq!(jac.ncols(), 0);
    }

    // ── TrustRegionProblem::residuals_into / jacobian_into (lines ~379, 388,
    //    430) — a real `fit()` call never exercises the resize branch because
    //    it always pre-sizes `residual_buf` to `y_concat.len()` up front, and
    //    never calls these `MatMut`-based trait methods at all (the faer LM
    //    driver is the only caller, and this graph has no tied params so it
    //    also covers the analytic, non-FD `jacobian_into` branch). ─────────

    #[test]
    fn trust_region_residuals_into_resizes_buf_and_jacobian_into_is_analytic() {
        let graph = single_gaussian_graph(true, true);
        let all_params = single_gaussian_all_params();

        let x = vec![-1.0, 0.0, 1.0, 2.0];
        let y: Vec<f64> = x.iter().map(|&xi| gaussian(xi, 5.0, 0.0, 1.0)).collect();

        let cg = CompiledGraph::compile(&graph).expect("graph should compile");
        let mut problem = build_test_problem(
            &cg,
            &all_params,
            vec![(f64::NEG_INFINITY, f64::INFINITY); 2],
            vec![1.0; 2],
            x,
            y,
        );
        assert!(!problem.has_tied());

        // Force the scratch buffer to the wrong length so `residuals_into`
        // must resize it before writing.
        *problem.residual_buf.borrow_mut() = Vec::new();

        let m = problem.y_concat.len();
        let mut r = faer::Mat::<f64>::zeros(m, 1);
        problem
            .residuals_into(r.as_mut())
            .expect("residuals_into should succeed after resizing its scratch buffer");
        assert_eq!(problem.residual_buf.borrow().len(), m);

        let nf = problem.free_keys.len();
        let mut jac = faer::Mat::<f64>::zeros(m, nf);
        problem
            .jacobian_into(jac.as_mut())
            .expect("jacobian_into should take the analytic (non-tied) branch");
        for i in 0..m {
            for j in 0..nf {
                assert!(jac[(i, j)].is_finite());
            }
        }
    }

    // ── trust_scaling: zero-gradient branch measuring both bound distances
    //    (lines ~477-487) ──────────────────────────────────────────────────

    #[test]
    fn trust_scaling_handles_zero_gradient_component_with_mixed_bounds() {
        // `amplitude` has only a finite lower bound; `center` has only a
        // finite upper bound. With grad == 0.0 for both, `trust_scaling` takes
        // the "flat gradient" branch that measures distance to BOTH bounds
        // (`du`/`dl`) instead of picking one side by gradient sign — exercising
        // every finite/infinite combination of that branch in one test.
        let graph = single_gaussian_graph(true, true);
        let cg = CompiledGraph::compile(&graph).expect("graph should compile");
        assert_eq!(
            cg.free_keys,
            vec!["g1.amplitude".to_string(), "g1.center".to_string()]
        );

        let all_params = single_gaussian_all_params();
        let x = vec![0.0, 1.0];
        let y = vec![0.0, 0.0];
        let problem = build_test_problem(
            &cg,
            &all_params,
            vec![(0.0, f64::INFINITY), (f64::NEG_INFINITY, 10.0)],
            vec![1.0, 1.0],
            x,
            y,
        );

        let grad = vec![0.0, 0.0];
        let v = problem
            .trust_scaling(&grad)
            .expect("some bound is finite, so trust_scaling must return Some");
        assert_eq!(v.len(), 2);
        for &vi in &v {
            assert!((1e-9..=1.0).contains(&vi));
        }
    }

    #[test]
    fn bounds_are_reported_in_scaled_working_units() {
        let graph = single_gaussian_graph(true, true);
        let cg = CompiledGraph::compile(&graph).expect("graph should compile");
        let all_params = single_gaussian_all_params();
        let problem = build_test_problem(
            &cg,
            &all_params,
            vec![(0.0, 8.0), (f64::NEG_INFINITY, 10.0)],
            vec![2.0, 0.5],
            vec![0.0, 1.0],
            vec![0.0, 0.0],
        );
        let b = TrustRegionProblem::bounds(&problem).expect("finite bounds present");
        assert_eq!(b, vec![(0.0, 4.0), (f64::NEG_INFINITY, 20.0)]);
    }

    #[test]
    fn bounds_are_none_when_every_bound_is_infinite() {
        let graph = single_gaussian_graph(true, true);
        let cg = CompiledGraph::compile(&graph).expect("graph should compile");
        let all_params = single_gaussian_all_params();
        let problem = build_test_problem(
            &cg,
            &all_params,
            vec![(f64::NEG_INFINITY, f64::INFINITY); 2],
            vec![1.0, 1.0],
            vec![0.0, 1.0],
            vec![0.0, 0.0],
        );
        assert!(TrustRegionProblem::bounds(&problem).is_none());
    }

    /// 64-bit FNV-1a over f64 bit patterns, length-prefixed per vector.
    fn fnv1a_vecs(vs: &[Vec<f64>]) -> u64 {
        let mut h: u64 = 0xcbf2_9ce4_8422_2325;
        let mut eat = |w: u64| {
            for b in w.to_le_bytes() {
                h ^= u64::from(b);
                h = h.wrapping_mul(0x0000_0100_0000_01b3);
            }
        };
        for v in vs {
            eat(v.len() as u64);
            for x in v {
                eat(x.to_bits());
            }
        }
        h
    }

    /// Golden trajectory of the faer LM driver on a real `LmProblem` with
    /// `Parameter.scale != 1` and finite bounds that never become active
    /// (#93, active-set step test (c)). Recorded before the active-set
    /// projected step existed: with no component at a bound the step must be
    /// inert, so the accepted trajectory, final parameters, cost and counters
    /// stay bit-identical for LM, TRF and geodesic.
    #[test]
    fn lm_family_trajectory_with_inactive_scaled_bounds_is_bit_identical() {
        use spectrafit_levenberg_marquardt::{minimize, StrategyConfig};
        faer::set_global_parallelism(faer::Par::Seq);

        let graph = single_gaussian_graph(true, true);
        let cg = CompiledGraph::compile(&graph).expect("graph should compile");
        let all_params = single_gaussian_all_params();
        let x: Vec<f64> = (0..41).map(|i| -4.0 + 0.2 * f64::from(i)).collect();
        let y: Vec<f64> = x
            .iter()
            .enumerate()
            .map(|(i, &xi)| gaussian(xi, 3.0, 0.4, 1.0) + 0.01 * ((i % 5) as f64 - 2.0))
            .collect();
        let bounds = vec![(-50.0, 60.0), (-20.0, f64::INFINITY)];

        let configs: [(&str, StrategyConfig); 3] = [
            ("lm", StrategyConfig::default()),
            (
                "trf",
                StrategyConfig {
                    bound_scaling: true,
                    ..StrategyConfig::default()
                },
            ),
            (
                "geodesic",
                StrategyConfig {
                    geodesic: true,
                    ..StrategyConfig::default()
                },
            ),
        ];
        // (name, params_history hash, final params bits, cost bits,
        //  termination, n_iter, n_residual_evals, n_jacobian_evals)
        type Golden = (
            &'static str,
            u64,
            [u64; 2],
            u64,
            &'static str,
            usize,
            usize,
            usize,
        );
        #[rustfmt::skip]
        const GOLDEN: &[Golden] = &[
            ("lm", 0xe231f9408978a064, [0x3ff8000045845942, 0x3fe999a06501d4ee], 0x3f713404e69d15b0, "Ftol", 5, 6, 5),
            ("trf", 0x8cab06c93e216962, [0x3ff80000458458e9, 0x3fe999a06501d534], 0x3f713404e69d15be, "Ftol", 5, 6, 5),
            ("geodesic", 0x78d898d263dfc4bb, [0x3ff8000045845af1, 0x3fe999a06501299e], 0x3f713404e69d15b6, "Ftol", 4, 9, 4),
        ];

        let mut actual = Vec::new();
        let mut mismatches = Vec::new();
        for (name, config) in configs {
            let mut problem = build_test_problem(
                &cg,
                &all_params,
                bounds.clone(),
                vec![2.0, 0.5],
                x.clone(),
                y.clone(),
            );
            let report = minimize(&mut problem, &config);
            let wb = TrustRegionProblem::bounds(&problem).expect("finite bounds");
            for theta in &report.params_history {
                for (i, &t) in theta.iter().enumerate() {
                    for b in [wb[i].0, wb[i].1] {
                        if b.is_finite() {
                            assert!(
                                (t - b).abs() > 1e-3 * b.abs().max(1.0),
                                "{name}: theta[{i}] = {t} comes near bound {b}"
                            );
                        }
                    }
                }
            }
            let fin = TrustRegionProblem::params(&problem);
            let term = format!("{:?}", report.termination);
            let rendered = format!(
                "            (\"{name}\", 0x{:016x}, [0x{:016x}, 0x{:016x}], 0x{:016x}, \"{term}\", {}, {}, {}),",
                fnv1a_vecs(&report.params_history),
                fin[0].to_bits(),
                fin[1].to_bits(),
                report.cost.to_bits(),
                report.n_iter,
                report.n_residual_evals,
                report.n_jacobian_evals
            );
            let line = (
                fnv1a_vecs(&report.params_history),
                [fin[0].to_bits(), fin[1].to_bits()],
                report.cost.to_bits(),
                term.clone(),
                report.n_iter,
                report.n_residual_evals,
                report.n_jacobian_evals,
            );
            match GOLDEN.iter().find(|g| g.0 == name) {
                Some(g) if (g.1, g.2, g.3, g.4.to_string(), g.5, g.6, g.7) == line => {}
                Some(g) => mismatches.push(format!("expected {g:?}\n  actual {rendered}")),
                None => mismatches.push(format!("missing  {rendered}")),
            }
            actual.push(rendered);
        }
        assert!(
            mismatches.is_empty(),
            "{} golden mismatches:\n{}\n\nfull actual table:\n{}",
            mismatches.len(),
            mismatches.join("\n"),
            actual.join("\n")
        );
    }

    /// Clamp-AS (#93): a real `LmProblem` Gaussian started inside the box with
    /// its unconstrained optimum (amplitude 3, center 0.4) outside it. Trial
    /// points that cross the bound are projected onto the box (Kanzow,
    /// Yamashita, Fukushima 2004, projected LM step), so the iterate lands
    /// exactly on the bound, the active-set 1e-12 entry rule holds it, and the
    /// run ends as a success at a stationary point: the bounded component is
    /// on its bound with an outward gradient, and the Gauss-Newton decrease
    /// over the free component is at most 1e-6 · RSS. Under reflection the
    /// one-sided cases parked 5e-9 to 5e-8 off the bound.
    #[test]
    fn clamp_lands_interior_start_gaussian_endpoint_on_the_bound_and_stationary() {
        use faer::Mat;
        use spectrafit_levenberg_marquardt::{minimize, StrategyConfig};
        faer::set_global_parallelism(faer::Par::Seq);

        let graph = single_gaussian_graph(true, true);
        let cg = CompiledGraph::compile(&graph).expect("graph should compile");
        // Interior start for every box below: amplitude 1 (< 2), center 0 (< 0.1).
        let mut all_params = single_gaussian_all_params();
        all_params.insert("g1.amplitude".into(), 1.0);
        let x: Vec<f64> = (0..41).map(|i| -4.0 + 0.2 * f64::from(i)).collect();
        let y: Vec<f64> = x.iter().map(|&xi| gaussian(xi, 3.0, 0.4, 1.0)).collect();
        let free_box = (f64::NEG_INFINITY, f64::INFINITY);
        // (label, bounds, index of the bounded parameter, its active upper bound)
        type Setting = (&'static str, Vec<(f64, f64)>, usize, f64);
        let settings: [Setting; 3] = [
            (
                "amplitude <= 2",
                vec![(f64::NEG_INFINITY, 2.0), free_box],
                0,
                2.0,
            ),
            ("amplitude in [0, 2]", vec![(0.0, 2.0), free_box], 0, 2.0),
            (
                "center <= 0.1",
                vec![free_box, (f64::NEG_INFINITY, 0.1)],
                1,
                0.1,
            ),
        ];
        let configs: [(&str, StrategyConfig); 3] = [
            ("lm", StrategyConfig::default()),
            (
                "trf",
                StrategyConfig {
                    bound_scaling: true,
                    ..StrategyConfig::default()
                },
            ),
            (
                "geodesic",
                StrategyConfig {
                    geodesic: true,
                    ..StrategyConfig::default()
                },
            ),
        ];
        // Every case is checked before failing, so a red run names all of them.
        let mut failures: Vec<String> = Vec::new();
        for (label, bounds, k, b) in &settings {
            for (cname, config) in &configs {
                let tag = format!("{label} / {cname}");
                let mut problem = build_test_problem(
                    &cg,
                    &all_params,
                    bounds.clone(),
                    vec![1.0, 1.0],
                    x.clone(),
                    y.clone(),
                );
                let start = TrustRegionProblem::params(&problem);
                assert!(start[*k] < *b, "{tag}: start {start:?} not interior");
                let report = minimize(&mut problem, config);
                if !report.termination.was_successful() {
                    failures.push(format!("{tag}: {:?}", report.termination));
                }
                let theta = TrustRegionProblem::params(&problem);
                if theta[*k] != *b {
                    failures.push(format!("{tag}: endpoint {theta:?} not on the bound {b}"));
                }

                let m = TrustRegionProblem::n_residuals(&problem);
                let mut r = Mat::<f64>::zeros(m, 1);
                let mut jac = Mat::<f64>::zeros(m, 2);
                problem.residuals_into(r.as_mut()).expect("residuals");
                problem.jacobian_into(jac.as_mut()).expect("jacobian");
                let g = jac.transpose() * r.as_ref();
                // Upper bound active: the descent direction −g must point out.
                if g[(*k, 0)] >= 0.0 {
                    failures.push(format!("{tag}: gradient {} not outward", g[(*k, 0)]));
                }
                let f = 1 - *k;
                let col_sq: f64 = (0..m).map(|i| jac[(i, f)] * jac[(i, f)]).sum();
                let gn_decrease = 0.5 * g[(f, 0)] * g[(f, 0)] / col_sq;
                let rss: f64 = (0..m).map(|i| r[(i, 0)] * r[(i, 0)]).sum();
                if gn_decrease > 1e-6 * rss {
                    failures.push(format!(
                        "{tag}: GN decrease {gn_decrease} over the free component vs RSS {rss}"
                    ));
                }
            }
        }
        assert!(failures.is_empty(), "{}", failures.join("\n"));
    }

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
    fn reflect_extreme_undershoot_parks_at_lower_bound() {
        // Symmetric counterpart of `reflect_extreme_overshoot_parks_at_bound`:
        // p=-3.0, lo=0.0, hi=1.0 → reflected=2*0.0-(-3.0)=3.0 > hi → park at lo=0.0.
        assert_eq!(reflect_into_bounds(-3.0, 0.0, 1.0), 0.0);
    }

    #[test]
    fn reflect_infinite_bounds_unchanged() {
        let p = -999.0;
        assert_eq!(reflect_into_bounds(p, f64::NEG_INFINITY, f64::INFINITY), p);
    }
}
