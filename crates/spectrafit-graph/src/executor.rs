//! Graph executor: evaluation and Jacobian computation against a
//! [`CompiledGraph`].
//!
//! All public functions are generic over a pre-compiled graph so the caller
//! can amortise compilation cost (e.g. in the solver loop).

use std::collections::HashMap;

use nalgebra::DMatrix;
use rayon::prelude::*;
use spectrafit_types::CoreError;

use crate::compiler::CompiledGraph;
use crate::error::GraphError;

// Rayon dispatch thresholds.
//
// Rayon's thread-pool has ~30–50 µs wake-up latency.  Parallel dispatch only
// pays off when:
//  (a) there are enough points that each thread gets a meaningful chunk, and
//  (b) total arithmetic work exceeds the dispatch overhead.
//
// Previous thresholds (192 pts/thread, 120k total work) were too aggressive:
// they triggered parallelism for single-peak 1-D fits with ~300 points where
// the overhead dominated.  The new values require a minimum of 512 points per
// thread and at least 1.5M arithmetic operations before going parallel, which
// reserves Rayon for genuinely large fits (n > ~2k on 4-thread machines).
const POINTS_PER_THREAD_CUTOFF: usize = 512;
const MIN_TOTAL_WORK_CUTOFF: usize = 1_500_000;

/// Decide whether a point-wise kernel should use rayon.
///
/// Returns `true` only when both conditions hold:
/// - `n_points >= 512 * n_threads` — each worker gets a large enough chunk
/// - `n_points * work_per_point >= 1_500_000` — dispatch overhead is amortised
#[inline]
fn should_parallel(n_points: usize, work_per_point: usize) -> bool {
    let n_threads = rayon::current_num_threads();
    if n_threads <= 1 {
        return false;
    }

    let point_cutoff = POINTS_PER_THREAD_CUTOFF.saturating_mul(n_threads);
    let work_cutoff = MIN_TOTAL_WORK_CUTOFF;
    let total_work = n_points.saturating_mul(work_per_point.max(1));

    n_points >= point_cutoff && total_work >= work_cutoff
}

// ---------------------------------------------------------------------------
// evaluate — sum of all node contributions
// ---------------------------------------------------------------------------

/// The flat coordinate buffer `x` is laid out **point-major**: dimension
/// `stride = cg.n_dims()` components per point, so point `i` occupies
/// `x[i*stride .. (i+1)*stride]`.  For the common 1-D case `stride == 1` and
/// each point is a single `f64`, identical to the historical behavior.
///
/// Validates that `x.len()` is an exact multiple of `stride` and returns the
/// number of points.
#[inline]
fn coord_layout(cg: &CompiledGraph, x_len: usize) -> Result<(usize, usize), CoreError> {
    let stride = cg.n_dims()?;
    debug_assert!(stride >= 1);
    if !x_len.is_multiple_of(stride) {
        return Err(GraphError::XBufferStrideMismatch {
            x_len,
            n_dims: stride,
        }
        .into());
    }
    Ok((stride, x_len / stride))
}

/// Evaluate the model sum at each x-point.
///
/// For each point, sums `model.eval(coord, &params)` across all nodes, where
/// `coord` is the `n_dims`-length coordinate slice for that point.  For 1-D
/// models `coord` is a single-element slice (`x[i..i+1]`); for n-D models it is
/// the full strided coordinate `x[i*d..(i+1)*d]`.
pub fn evaluate_compiled(
    cg: &CompiledGraph,
    flat: &HashMap<String, f64>,
    x: &[f64],
) -> Result<Vec<f64>, CoreError> {
    // Pre-extract param vectors for every node once, outside the x-loop.
    let node_params: Vec<Vec<f64>> = (0..cg.nodes.len())
        .map(|i| cg.node_params(i, flat))
        .collect::<Result<_, _>>()?;

    let (stride, n_points) = coord_layout(cg, x.len())?;

    // Simultaneous multi-dataset scoping (cold path): a node with `dataset_index`
    // contributes only to its dataset's points, so `best_fit` is the correctly
    // scoped sum. The all-global path below is untouched.
    if scoping_active(cg) {
        validate_dataset_scope(cg)?;
        let offsets = cg.dataset_offsets.as_slice();
        let values: Vec<f64> = x
            .chunks_exact(stride)
            .enumerate()
            .map(|(p, coord)| {
                let ds = dataset_of_point(offsets, p);
                let mut sum = 0.0_f64;
                for (node, params) in cg.nodes.iter().zip(node_params.iter()) {
                    if let Some(i) = node.dataset_index {
                        if i != ds {
                            continue;
                        }
                    }
                    sum += node.model.eval(coord, params);
                }
                sum
            })
            .collect();
        return Ok(values);
    }

    // Evaluate over x-points; each point is independent.
    // Auto-switch between sequential and rayon based on thread count and
    // estimated arithmetic work.
    let eval_point = |coord: &[f64]| -> f64 {
        let mut sum = 0.0_f64;
        for (node, params) in cg.nodes.iter().zip(node_params.iter()) {
            sum += node.model.eval(coord, params);
        }
        sum
    };

    let values: Vec<f64> = if should_parallel(n_points, cg.nodes.len().saturating_mul(stride)) {
        x.par_chunks_exact(stride).map(eval_point).collect()
    } else {
        x.chunks_exact(stride).map(eval_point).collect()
    };
    Ok(values)
}

// ---------------------------------------------------------------------------
// evaluate_components — per-node contributions
// ---------------------------------------------------------------------------

/// Evaluate each node independently.
///
/// Returns `{ node_id => Vec<f64> }` with one entry per node.
pub fn evaluate_components_compiled(
    cg: &CompiledGraph,
    flat: &HashMap<String, f64>,
    x: &[f64],
) -> Result<HashMap<String, Vec<f64>>, CoreError> {
    let mut result: HashMap<String, Vec<f64>> = HashMap::with_capacity(cg.nodes.len());

    let (stride, n_points) = coord_layout(cg, x.len())?;
    // Reject out-of-range `dataset_index` once, before the per-node loop indexes
    // `dataset_offsets[di + 1]`, so a mismatched spec/offsets errors cleanly.
    validate_dataset_scope(cg)?;

    for (i, node) in cg.nodes.iter().enumerate() {
        let params = cg.node_params(i, flat)?;

        let eval_pt = |coord: &[f64]| node.model.eval(coord, &params);

        let mut values: Vec<f64> = if should_parallel(n_points, stride) {
            x.par_chunks_exact(stride).map(eval_pt).collect()
        } else {
            x.chunks_exact(stride).map(eval_pt).collect()
        };

        // Dataset scoping: a local node's component curve is zero outside its
        // dataset's point-range (keeps per-dataset slices/components correct).
        if scoping_active(cg) {
            if let Some(di) = node.dataset_index {
                let offs = &cg.dataset_offsets;
                let (a, b) = (offs[di], offs[di + 1]);
                for (p, v) in values.iter_mut().enumerate() {
                    if p < a || p >= b {
                        *v = 0.0;
                    }
                }
            }
        }

        result.insert(node.id.clone(), values);
    }

    Ok(result)
}

// ---------------------------------------------------------------------------
// evaluate_compiled_indexed — hot path: bypasses HashMap lookup
// ---------------------------------------------------------------------------

/// Evaluate the model sum using pre-computed per-node parameter buffers.
///
/// This is the hot-path version of [`evaluate_compiled`] used by the solver.
/// The caller maintains `node_params[i]` (one `Vec<f64>` per node, in model
/// `param_names()` order) and updates only the free-param slots via
/// [`CompiledGraph::free_to_node_param`] on each iteration.
///
/// Eliminates all `HashMap` lookups from the inner loop.
pub fn evaluate_compiled_indexed(
    cg: &CompiledGraph,
    node_params: &[Vec<f64>],
    x: &[f64],
) -> Result<Vec<f64>, CoreError> {
    // Size the output by the number of points (x.len() / n_dims), not the raw
    // x length, so the n-D strided path allocates a correctly-shaped buffer.
    let (_stride, n_points) = coord_layout(cg, x.len())?;
    let mut values = vec![0.0_f64; n_points];
    evaluate_compiled_indexed_into(cg, node_params, x, &mut values)?;
    Ok(values)
}

/// Evaluate the model sum using pre-computed per-node parameter buffers into a
/// reusable output slice.
///
/// Callers that already own a scratch buffer can reuse it across iterations and
/// avoid an extra heap allocation for the predicted values.
pub fn evaluate_compiled_indexed_into(
    cg: &CompiledGraph,
    node_params: &[Vec<f64>],
    x: &[f64],
    out: &mut [f64],
) -> Result<(), CoreError> {
    let (stride, n_points) = coord_layout(cg, x.len())?;

    if out.len() != n_points {
        return Err(GraphError::OutputBufferLength {
            actual: out.len(),
            expected: n_points,
        }
        .into());
    }

    let eval_point = |coord: &[f64]| {
        let mut sum = 0.0_f64;
        for (node, params) in cg.nodes.iter().zip(node_params.iter()) {
            sum += node.model.eval(coord, params);
        }
        sum
    };

    if should_parallel(n_points, cg.nodes.len().saturating_mul(stride)) {
        out.par_iter_mut()
            .zip(x.par_chunks_exact(stride))
            .for_each(|(slot, coord)| *slot = eval_point(coord));
    } else {
        for (slot, coord) in out.iter_mut().zip(x.chunks_exact(stride)) {
            *slot = eval_point(coord);
        }
    }

    Ok(())
}

/// Compute weighted residuals directly into a reusable buffer.
///
/// This fuses prediction, subtraction, and sigma weighting so solver loops do
/// not materialize an intermediate prediction vector.
/// Whether simultaneous multi-dataset ("global analysis") scoping is active:
/// ≥2 datasets recorded on the compiled graph AND at least one node carrying a
/// [`crate::compiler::NodeEntry::dataset_index`]. When false, every node
/// contributes to all points — the historical, byte-identical behaviour.
#[inline]
fn scoping_active(cg: &CompiledGraph) -> bool {
    cg.dataset_offsets.len() > 2 && cg.nodes.iter().any(|n| n.dataset_index.is_some())
}

/// Validate that every node's `dataset_index` is in range for the recorded
/// `dataset_offsets`.
///
/// `dataset_offsets` has length `n_datasets + 1`, so dataset `i` is valid iff
/// `i < dataset_offsets.len() - 1` (i.e. `i + 1 < dataset_offsets.len()`).
/// Because the solver fills `dataset_offsets` *after* `compile()`, the node
/// spec and the offsets can disagree with no guard between them; indexing
/// `offsets[di + 1]` blindly would panic. Returns [`CoreError::Eval`] instead
/// so the scoped eval/Jacobian paths fail cleanly rather than aborting.
///
/// A no-op (always `Ok`) when scoping is inactive.
#[inline]
fn validate_dataset_scope(cg: &CompiledGraph) -> Result<(), CoreError> {
    if !scoping_active(cg) {
        return Ok(());
    }
    let n_datasets = cg.dataset_offsets.len() - 1;
    for node in &cg.nodes {
        if let Some(di) = node.dataset_index {
            if di >= n_datasets {
                return Err(GraphError::DatasetIndexOutOfRange {
                    node: node.id.clone(),
                    dataset_index: di,
                    n_datasets,
                }
                .into());
            }
        }
    }
    Ok(())
}

/// Dataset index owning concatenated point `p`, from cumulative `offsets`
/// (len = n_datasets + 1, ascending). `partition_point` is O(log n_datasets).
#[inline]
fn dataset_of_point(offsets: &[usize], p: usize) -> usize {
    offsets.partition_point(|&o| o <= p).saturating_sub(1)
}

/// Post-pass for the analytical Jacobian: zero the free-parameter columns of
/// every local (`dataset_index`-scoped) node for rows outside that node's
/// dataset point-range. The normal fill computes each node's Jacobian at all
/// rows; this restricts a local node's columns to its own dataset (a no-op when
/// scoping is inactive), keeping the hot fill loops untouched.
fn apply_jacobian_dataset_scope(
    cg: &CompiledGraph,
    n_points: usize,
    n_free: usize,
    data: &mut [f64],
) {
    if !scoping_active(cg) {
        return;
    }
    let offsets = &cg.dataset_offsets;
    for (node_idx, node) in cg.nodes.iter().enumerate() {
        let Some(di) = node.dataset_index else {
            continue;
        };
        let (a, b) = (offsets[di], offsets[di + 1]);
        for &(_local, col) in &cg.node_free_cols[node_idx] {
            for row in 0..n_points {
                if row < a || row >= b {
                    data[row * n_free + col] = 0.0;
                }
            }
        }
    }
}

/// Compute weighted residuals `r[i] = (ŷ[i] − y[i]) / σ[i]` into `out` using
/// pre-computed per-node parameter buffers. Honours per-node `dataset_index`
/// scoping for simultaneous multi-dataset fits (a no-op for single-dataset /
/// fully-global graphs).
pub fn residuals_compiled_indexed_into(
    cg: &CompiledGraph,
    node_params: &[Vec<f64>],
    x: &[f64],
    y: &[f64],
    sigma: &[f64],
    out: &mut [f64],
) -> Result<(), CoreError> {
    let (stride, n_points) = coord_layout(cg, x.len())?;

    if out.len() != n_points || y.len() != n_points || sigma.len() != n_points {
        return Err(GraphError::OutputBufferShape.into());
    }

    // Simultaneous multi-dataset scoping (cold path — only with ≥2 datasets AND
    // a local node): a node with `dataset_index = Some(i)` contributes only to
    // dataset i's points. Uses the scalar `eval` for any stride; the optimized
    // all-global paths below are left untouched.
    if scoping_active(cg) {
        validate_dataset_scope(cg)?;
        let offsets = cg.dataset_offsets.as_slice();
        for (p, (slot, (coord, (&obs, &s)))) in out
            .iter_mut()
            .zip(x.chunks_exact(stride).zip(y.iter().zip(sigma.iter())))
            .enumerate()
        {
            let ds = dataset_of_point(offsets, p);
            let mut sum = 0.0_f64;
            for (node, params) in cg.nodes.iter().zip(node_params.iter()) {
                if let Some(i) = node.dataset_index {
                    if i != ds {
                        continue;
                    }
                }
                sum += node.model.eval(coord, params);
            }
            *slot = (sum - obs) / s;
        }
        return Ok(());
    }

    // 1-D batched path (any number of nodes): batch-evaluate each node with
    // `eval_slice_into`, accumulate the node sum, then apply (out - obs) / sigma.
    // `stride == 1` implies every node is 1-D (stride = cg.n_dims()), so this
    // replaces the per-(point, node) virtual `eval` dispatch with one batched
    // call per node — hoisting each model's loop-invariant constants. The scalar
    // path below is kept only for n-D models (stride > 1).
    if stride == 1 && !cg.nodes.is_empty() {
        debug_assert_eq!(out.len(), x.len());
        // First node overwrites `out`; remaining nodes accumulate via scratch.
        cg.nodes[0].model.eval_slice_into(x, &node_params[0], out);
        if cg.nodes.len() > 1 {
            let mut scratch = vec![0.0_f64; n_points];
            for (node, params) in cg.nodes.iter().zip(node_params.iter()).skip(1) {
                node.model.eval_slice_into(x, params, &mut scratch);
                for (slot, &c) in out.iter_mut().zip(scratch.iter()) {
                    *slot += c;
                }
            }
        }
        for ((slot, &obs), &s) in out.iter_mut().zip(y.iter()).zip(sigma.iter()) {
            *slot = (*slot - obs) / s;
        }
        return Ok(());
    }

    let eval_point = |coord: &[f64]| {
        let mut sum = 0.0_f64;
        for (node, params) in cg.nodes.iter().zip(node_params.iter()) {
            sum += node.model.eval(coord, params);
        }
        sum
    };

    if should_parallel(n_points, cg.nodes.len().saturating_mul(stride)) {
        out.par_iter_mut()
            .zip(
                x.par_chunks_exact(stride)
                    .zip(y.par_iter().zip(sigma.par_iter())),
            )
            .for_each(|(slot, (coord, (&obs, &s)))| *slot = (eval_point(coord) - obs) / s);
    } else {
        for (slot, (coord, (&obs, &s))) in out
            .iter_mut()
            .zip(x.chunks_exact(stride).zip(y.iter().zip(sigma.iter())))
        {
            *slot = (eval_point(coord) - obs) / s;
        }
    }

    Ok(())
}

// ---------------------------------------------------------------------------
// jacobian — full analytical Jacobian [n_points × n_free_params]
// ---------------------------------------------------------------------------

/// Compute the analytical Jacobian matrix using a pre-built flat param map.
///
/// Layout: row `i` = x-point `i`; column `j` = free parameter `j`
/// (ordered as in `cg.free_keys`).
///
/// Only parameters with `free_mask == true` contribute a column.
/// Fixed and expression-bound parameters are excluded.
///
/// Uses `cg.node_free_cols` (pre-computed at compile time) to avoid
/// string-parsing `free_keys` on every call.
pub fn jacobian_compiled(
    cg: &CompiledGraph,
    flat: &HashMap<String, f64>,
    x: &[f64],
) -> Result<DMatrix<f64>, CoreError> {
    // Pre-extract param vectors once.
    let node_params: Vec<Vec<f64>> = (0..cg.nodes.len())
        .map(|i| cg.node_params(i, flat))
        .collect::<Result<_, _>>()?;

    jacobian_compiled_indexed(cg, &node_params, x)
}

/// Compute the analytical Jacobian using pre-computed per-node param buffers.
///
/// Hot-path companion to [`jacobian_compiled`]: the caller maintains
/// `node_params[i]` and passes it directly, bypassing all `HashMap` lookups.
pub fn jacobian_compiled_indexed(
    cg: &CompiledGraph,
    node_params: &[Vec<f64>],
    x: &[f64],
) -> Result<DMatrix<f64>, CoreError> {
    let mut data = Vec::new();
    jacobian_compiled_indexed_into(cg, node_params, x, &mut data)?;
    let (_stride, n_points) = coord_layout(cg, x.len())?;
    let n_free = cg.free_keys.len();
    if n_free == 0 {
        Ok(DMatrix::zeros(n_points, 0))
    } else {
        Ok(DMatrix::from_row_slice(n_points, n_free, &data))
    }
}

/// Compute the analytical Jacobian using pre-computed per-node param buffers
/// and apply per-row sigma weights during materialization.
pub fn jacobian_compiled_indexed_weighted(
    cg: &CompiledGraph,
    node_params: &[Vec<f64>],
    x: &[f64],
    sigma: &[f64],
) -> Result<DMatrix<f64>, CoreError> {
    let mut data = Vec::new();
    jacobian_compiled_indexed_weighted_into(cg, node_params, x, sigma, &mut data)?;
    let (_stride, n_points) = coord_layout(cg, x.len())?;
    let n_free = cg.free_keys.len();
    if n_free == 0 {
        Ok(DMatrix::zeros(n_points, 0))
    } else {
        Ok(DMatrix::from_row_slice(n_points, n_free, &data))
    }
}

/// Compute the analytical Jacobian using a reusable row-major scratch buffer.
///
/// Callers with iterative solve loops can reuse ``data`` across iterations to
/// reduce repeated heap allocation churn.
pub fn jacobian_compiled_indexed_into(
    cg: &CompiledGraph,
    node_params: &[Vec<f64>],
    x: &[f64],
    data: &mut Vec<f64>,
) -> Result<(), CoreError> {
    let (stride, n_points) = coord_layout(cg, x.len())?;
    let n_free = cg.free_keys.len();

    // Reject out-of-range `dataset_index` before the scope post-pass indexes
    // `dataset_offsets[di + 1]`.
    validate_dataset_scope(cg)?;

    if n_free == 0 {
        data.clear();
        return Ok(());
    }

    // `cg.node_free_cols` was pre-computed during `CompiledGraph::compile()` —
    // no string-parsing or HashMap construction needed here.
    let required = n_points.saturating_mul(n_free);
    if data.len() != required {
        data.resize(required, 0.0);
    } else {
        data.fill(0.0);
    }

    // Maximum parameter count across all nodes — determines scratch buffer size.
    let max_params = cg
        .nodes
        .iter()
        .map(|n| n.param_names.len())
        .max()
        .unwrap_or(0);

    if should_parallel(n_points, cg.nodes.len().saturating_mul(n_free)) {
        // Parallel: each rayon worker thread gets its own scratch buffer (cloned
        // once per thread, not once per point).  Avoids heap allocations in the
        // inner loop while keeping the data-race-free par_chunks_mut layout.
        data.par_chunks_mut(n_free)
            .zip(x.par_chunks_exact(stride))
            .for_each_with(vec![0.0_f64; max_params], |scratch, (row_buf, coord)| {
                for (node_idx, node) in cg.nodes.iter().enumerate() {
                    let free_cols = &cg.node_free_cols[node_idx];
                    if free_cols.is_empty() {
                        continue;
                    }
                    let params = &node_params[node_idx];
                    node.model
                        .jacobian_into(coord, params, &mut scratch[..params.len()]);
                    for &(local_idx, col) in free_cols {
                        row_buf[col] = scratch[local_idx];
                    }
                }
            });
    } else {
        // Sequential: one scratch buffer reused for every (x-point, node) pair —
        // zero heap allocations inside the loop.
        let mut scratch = vec![0.0_f64; max_params];
        for (i, coord) in x.chunks_exact(stride).enumerate() {
            let row_buf = &mut data[i * n_free..(i + 1) * n_free];
            for (node_idx, node) in cg.nodes.iter().enumerate() {
                let free_cols = &cg.node_free_cols[node_idx];
                if free_cols.is_empty() {
                    continue;
                }
                let params = &node_params[node_idx];
                node.model
                    .jacobian_into(coord, params, &mut scratch[..params.len()]);
                for &(local_idx, col) in free_cols {
                    row_buf[col] = scratch[local_idx];
                }
            }
        }
    }

    apply_jacobian_dataset_scope(cg, n_points, n_free, data);
    Ok(())
}

/// Compute the weighted analytical Jacobian into a reusable row-major buffer.
///
/// Each generated row is divided by the corresponding sigma weight before
/// storing into `data`, avoiding a second pass over the dense matrix.
pub fn jacobian_compiled_indexed_weighted_into(
    cg: &CompiledGraph,
    node_params: &[Vec<f64>],
    x: &[f64],
    sigma: &[f64],
    data: &mut Vec<f64>,
) -> Result<(), CoreError> {
    let (stride, n_points) = coord_layout(cg, x.len())?;
    let n_free = cg.free_keys.len();

    if sigma.len() != n_points {
        return Err(GraphError::OutputBufferLength {
            actual: sigma.len(),
            expected: n_points,
        }
        .into());
    }

    // Reject out-of-range `dataset_index` before the scope post-pass indexes
    // `dataset_offsets[di + 1]`.
    validate_dataset_scope(cg)?;

    if n_free == 0 {
        data.clear();
        return Ok(());
    }

    let required = n_points.saturating_mul(n_free);
    if data.len() != required {
        data.resize(required, 0.0);
    } else {
        data.fill(0.0);
    }

    // Single-node, 1-D fast path: uses `jac_slice_into` to hoist model
    // invariants.  Only applicable when free_cols is an identity mapping so
    // we can write directly into `data` without a scatter step.  `jac_slice_into`
    // is a 1-D-only contract, so it is gated on stride == 1.
    if !scoping_active(cg)
        && stride == 1
        && cg.nodes.len() == 1
        && cg.nodes[0].model.n_dims() == 1
        && n_free == cg.nodes[0].param_names.len()
        && cg.node_free_cols[0]
            .iter()
            .enumerate()
            .all(|(i, &(local, col))| local == i && col == i)
    {
        let node = &cg.nodes[0];
        node.model.jac_slice_into(x, &node_params[0], data);
        // Apply sigma weighting in a second tight pass.
        for i in 0..n_points {
            let inv_s = 1.0 / sigma[i];
            for v in &mut data[i * n_free..(i + 1) * n_free] {
                *v *= inv_s;
            }
        }
        return Ok(());
    }

    // General 1-D batched path (multi-node, or single node with a non-identity
    // free-column map): batch each node's Jacobian with `jac_slice_into`, then
    // scatter its columns into the free-parameter layout with sigma weighting.
    // `stride == 1` implies every node is 1-D, so this replaces the per-(point,
    // node) virtual `jacobian_into` dispatch with one batched call per node.
    // The scalar path below is kept only for n-D models (stride > 1).
    // Under dataset scoping this batched path is skipped — fall through to the
    // scalar path so the post-pass can restrict local nodes to their dataset.
    if stride == 1 && !scoping_active(cg) {
        // Reused across nodes; sized to the widest node's [n_points × n_local].
        let mut node_scratch: Vec<f64> = Vec::new();
        for (node_idx, node) in cg.nodes.iter().enumerate() {
            let free_cols = &cg.node_free_cols[node_idx];
            if free_cols.is_empty() {
                continue;
            }
            let n_local = node.param_names.len();
            node_scratch.clear();
            node_scratch.resize(n_points * n_local, 0.0);
            node.model
                .jac_slice_into(x, &node_params[node_idx], &mut node_scratch);
            for i in 0..n_points {
                let inv_s = 1.0 / sigma[i];
                let base = i * n_local;
                let row = &mut data[i * n_free..(i + 1) * n_free];
                for &(local_idx, col) in free_cols {
                    row[col] = node_scratch[base + local_idx] * inv_s;
                }
            }
        }
        return Ok(());
    }

    let max_params = cg
        .nodes
        .iter()
        .map(|n| n.param_names.len())
        .max()
        .unwrap_or(0);

    if should_parallel(n_points, cg.nodes.len().saturating_mul(n_free)) {
        data.par_chunks_mut(n_free)
            .zip(x.par_chunks_exact(stride).zip(sigma.par_iter()))
            .for_each_with(
                vec![0.0_f64; max_params],
                |scratch, (row_buf, (coord, &s))| {
                    for (node_idx, node) in cg.nodes.iter().enumerate() {
                        let free_cols = &cg.node_free_cols[node_idx];
                        if free_cols.is_empty() {
                            continue;
                        }
                        let params = &node_params[node_idx];
                        node.model
                            .jacobian_into(coord, params, &mut scratch[..params.len()]);
                        for &(local_idx, col) in free_cols {
                            row_buf[col] = scratch[local_idx] / s;
                        }
                    }
                },
            );
    } else {
        let mut scratch = vec![0.0_f64; max_params];
        for (i, (coord, &s)) in x.chunks_exact(stride).zip(sigma.iter()).enumerate() {
            let row_buf = &mut data[i * n_free..(i + 1) * n_free];
            for (node_idx, node) in cg.nodes.iter().enumerate() {
                let free_cols = &cg.node_free_cols[node_idx];
                if free_cols.is_empty() {
                    continue;
                }
                let params = &node_params[node_idx];
                node.model
                    .jacobian_into(coord, params, &mut scratch[..params.len()]);
                for &(local_idx, col) in free_cols {
                    row_buf[col] = scratch[local_idx] / s;
                }
            }
        }
    }

    apply_jacobian_dataset_scope(cg, n_points, n_free, data);
    Ok(())
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------
#[cfg(test)]
mod tests {
    use super::*;
    use crate::compiler::CompiledGraph;
    use approx::assert_relative_eq;
    use spectrafit_types::{FitGraphSpec, ModelNodeSpec, ModelTypeStr, ParameterSpec};

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

    fn flat(pairs: &[(&str, f64)]) -> HashMap<String, f64> {
        pairs.iter().map(|(k, v)| (k.to_string(), *v)).collect()
    }

    fn single_gaussian() -> (FitGraphSpec, HashMap<String, f64>) {
        let mut params = HashMap::new();
        params.insert("amplitude".to_string(), make_param(2.0, true));
        params.insert("center".to_string(), make_param(1.0, true));
        params.insert("sigma".to_string(), make_param(0.5, true));
        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![ModelNodeSpec {
                id: "g".to_string(),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: None,
                parameters: params,
            }],
            expr_edges: vec![],
        };
        let pf = flat(&[("g.amplitude", 2.0), ("g.center", 1.0), ("g.sigma", 0.5)]);
        (graph, pf)
    }

    #[test]
    fn evaluate_single_gaussian_at_center() {
        let (graph, pf) = single_gaussian();
        let cg = CompiledGraph::compile(&graph).unwrap();
        let result = evaluate_compiled(&cg, &pf, &[1.0]).unwrap();
        // At x=center: amplitude * exp(0) = 2.0
        assert_relative_eq!(result[0], 2.0, epsilon = 1e-12);
    }

    #[test]
    fn evaluate_multi_point() {
        let (graph, pf) = single_gaussian();
        let cg = CompiledGraph::compile(&graph).unwrap();
        let x = vec![0.0, 1.0, 2.0];
        let result = evaluate_compiled(&cg, &pf, &x).unwrap();
        assert_eq!(result.len(), 3);
        // Each value should be positive
        for v in &result {
            assert!(*v >= 0.0);
        }
    }

    #[test]
    fn evaluate_components_returns_all_nodes() {
        let mut g_params = HashMap::new();
        g_params.insert("amplitude".to_string(), make_param(1.0, true));
        g_params.insert("center".to_string(), make_param(0.0, true));
        g_params.insert("sigma".to_string(), make_param(1.0, true));
        let mut c_params = HashMap::new();
        c_params.insert("c".to_string(), make_param(3.0, true));

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
                    id: "bg".to_string(),
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
            ("bg.c", 3.0),
        ]);
        let cg = CompiledGraph::compile(&graph).unwrap();
        let comps = evaluate_components_compiled(&cg, &pf, &[0.0]).unwrap();
        assert_eq!(comps.len(), 2);
        assert_relative_eq!(comps["peak"][0], 1.0, epsilon = 1e-12);
        assert_relative_eq!(comps["bg"][0], 3.0, epsilon = 1e-12);
    }

    #[test]
    fn jacobian_shape_single_gaussian() {
        let (graph, pf) = single_gaussian();
        let cg = CompiledGraph::compile(&graph).unwrap();
        let x = vec![0.0, 0.5, 1.0, 1.5, 2.0];
        let jac = jacobian_compiled(&cg, &pf, &x).unwrap();
        assert_eq!(jac.nrows(), 5);
        assert_eq!(jac.ncols(), 3); // amplitude, center, sigma
    }

    #[test]
    fn jacobian_matches_finite_difference() {
        let (graph, pf) = single_gaussian();
        let cg = CompiledGraph::compile(&graph).unwrap();
        let x = vec![0.8f64]; // off-center for non-trivial derivatives
        let h = 1e-6;
        let jac = jacobian_compiled(&cg, &pf, &x).unwrap();

        let keys = ["g.amplitude", "g.center", "g.sigma"];
        for (col, key) in keys.iter().enumerate() {
            let mut pf_plus = pf.clone();
            *pf_plus.get_mut(*key).unwrap() += h;
            let f_plus = evaluate_compiled(&cg, &pf_plus, &x).unwrap()[0];
            let f_base = evaluate_compiled(&cg, &pf, &x).unwrap()[0];
            let fd = (f_plus - f_base) / h;
            assert!(
                (jac[(0, col)] - fd).abs() < 1e-5,
                "col {} ({}) analytical vs FD mismatch: got {}, expected {}",
                col,
                key,
                jac[(0, col)],
                fd
            );
        }
    }

    #[test]
    fn jacobian_fixed_param_excluded() {
        // amplitude is fixed (vary=false) — only 2 free params (center, sigma)
        let mut params = HashMap::new();
        params.insert("amplitude".to_string(), make_param(2.0, false)); // fixed
        params.insert("center".to_string(), make_param(0.0, true));
        params.insert("sigma".to_string(), make_param(1.0, true));
        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![ModelNodeSpec {
                id: "g".to_string(),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: None,
                parameters: params,
            }],
            expr_edges: vec![],
        };
        let pf = flat(&[("g.amplitude", 2.0), ("g.center", 0.0), ("g.sigma", 1.0)]);
        let cg = CompiledGraph::compile(&graph).unwrap();
        let jac = jacobian_compiled(&cg, &pf, &[0.0]).unwrap();
        assert_eq!(jac.ncols(), 2, "only 2 free params (center, sigma)");
    }

    // ── M1: multi-node batched path == scalar reference ────────────────────

    /// Two Gaussians + a constant background, with one fixed parameter, over a
    /// multi-point grid with non-trivial sigma. Exercises the batched 1-D
    /// residual and Jacobian paths (multi-node accumulation + free-col scatter)
    /// and pins them against an independent per-point scalar reference.
    fn two_gauss_plus_const() -> (FitGraphSpec, HashMap<String, f64>) {
        let mut g1 = HashMap::new();
        g1.insert("amplitude".to_string(), make_param(2.0, true));
        g1.insert("center".to_string(), make_param(-1.0, true));
        g1.insert("sigma".to_string(), make_param(0.7, false)); // fixed → scatter gap
        let mut g2 = HashMap::new();
        g2.insert("amplitude".to_string(), make_param(1.3, true));
        g2.insert("center".to_string(), make_param(1.2, true));
        g2.insert("sigma".to_string(), make_param(0.5, true));
        let mut bg = HashMap::new();
        bg.insert("c".to_string(), make_param(0.4, true));
        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![
                ModelNodeSpec {
                    id: "a".to_string(),
                    model_type: ModelTypeStr::Gaussian,
                    dataset_index: None,
                    parameters: g1,
                },
                ModelNodeSpec {
                    id: "b".to_string(),
                    model_type: ModelTypeStr::Gaussian,
                    dataset_index: None,
                    parameters: g2,
                },
                ModelNodeSpec {
                    id: "k".to_string(),
                    model_type: ModelTypeStr::Constant,
                    dataset_index: None,
                    parameters: bg,
                },
            ],
            expr_edges: vec![],
        };
        let pf = flat(&[
            ("a.amplitude", 2.0),
            ("a.center", -1.0),
            ("a.sigma", 0.7),
            ("b.amplitude", 1.3),
            ("b.center", 1.2),
            ("b.sigma", 0.5),
            ("k.c", 0.4),
        ]);
        (graph, pf)
    }

    #[test]
    fn multi_node_residuals_and_jacobian_match_scalar_reference() {
        let (graph, pf) = two_gauss_plus_const();
        let cg = CompiledGraph::compile(&graph).unwrap();
        let n = 9usize;
        let x: Vec<f64> = (0..n)
            .map(|i| -2.0 + 4.0 * i as f64 / (n - 1) as f64)
            .collect();
        let y: Vec<f64> = x.iter().map(|xi| 0.3 * xi + 0.1).collect();
        let sigma: Vec<f64> = (0..n).map(|i| 0.5 + 0.1 * i as f64).collect();

        let node_params: Vec<Vec<f64>> = (0..cg.nodes.len())
            .map(|i| cg.node_params(i, &pf).unwrap())
            .collect();
        let n_free = cg.free_keys.len();

        // Batched (production) path.
        let mut res = vec![0.0; n];
        residuals_compiled_indexed_into(&cg, &node_params, &x, &y, &sigma, &mut res).unwrap();
        let mut jac = Vec::new();
        jacobian_compiled_indexed_weighted_into(&cg, &node_params, &x, &sigma, &mut jac).unwrap();

        // Independent scalar reference.
        let mut res_ref = vec![0.0; n];
        let mut jac_ref = vec![0.0; n * n_free];
        for i in 0..n {
            let mut sum = 0.0;
            for (ni, node) in cg.nodes.iter().enumerate() {
                sum += node.model.eval(&[x[i]], &node_params[ni]);
                let jn = node.model.jacobian(&[x[i]], &node_params[ni]);
                for &(local, col) in &cg.node_free_cols[ni] {
                    jac_ref[i * n_free + col] = jn[local] / sigma[i];
                }
            }
            res_ref[i] = (sum - y[i]) / sigma[i];
        }

        for i in 0..n {
            assert_relative_eq!(res[i], res_ref[i], epsilon = 1e-12);
        }
        for k in 0..n * n_free {
            assert_relative_eq!(jac[k], jac_ref[k], epsilon = 1e-12);
        }
        // 7 params total minus the fixed a.sigma → 6 free:
        // a.amplitude, a.center, b.amplitude, b.center, b.sigma, k.c
        assert_eq!(n_free, 6);
    }

    // ── 2-D executor striding (U2) ─────────────────────────────────────────

    /// Build a single-node Gaussian2D graph plus its flat param map.
    fn single_gaussian2d() -> (FitGraphSpec, HashMap<String, f64>) {
        let mut params = HashMap::new();
        params.insert("amplitude".to_string(), make_param(3.0, true));
        params.insert("center_x".to_string(), make_param(0.5, true));
        params.insert("center_y".to_string(), make_param(-1.0, true));
        params.insert("sigma_x".to_string(), make_param(1.0, true));
        params.insert("sigma_y".to_string(), make_param(1.5, true));
        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![ModelNodeSpec {
                id: "g2".to_string(),
                model_type: ModelTypeStr::Gaussian2D,
                dataset_index: None,
                parameters: params,
            }],
            expr_edges: vec![],
        };
        let pf = flat(&[
            ("g2.amplitude", 3.0),
            ("g2.center_x", 0.5),
            ("g2.center_y", -1.0),
            ("g2.sigma_x", 1.0),
            ("g2.sigma_y", 1.5),
        ]);
        (graph, pf)
    }

    /// Real (passing) test: the executor must stride a 2-column flat `x` so each
    /// point receives its full `[x, y]` coordinate.  A constant model ignores
    /// coordinates, so this asserts the *layout* contract (n_points = len/stride)
    /// holds for stride > 1 while the 1-D path stays identical.
    #[test]
    fn executor_strides_two_column_x_for_constant_model() {
        // Constant is a 1-D model (n_dims == 1); to exercise stride==2 layout we
        // pair it with a Gaussian2D node that fixes the graph dimensionality to 2.
        // Here we instead use a pure-2D graph and a constant offset is emulated by
        // a Gaussian2D with zero amplitude is overkill — use Gaussian2D directly
        // but assert the *point count*, which is the striding invariant.
        let (graph, pf) = single_gaussian2d();
        let cg = CompiledGraph::compile(&graph).unwrap();
        assert_eq!(cg.n_dims().unwrap(), 2);

        // Three points laid out point-major: [x0,y0, x1,y1, x2,y2].
        let x_flat = vec![0.5, -1.0, 10.0, 10.0, 0.5, -1.0];
        let vals = evaluate_compiled(&cg, &pf, &x_flat).unwrap();
        assert_eq!(vals.len(), 3, "len/stride = 6/2 = 3 points");

        // Point 0 and 2 are at the center → value == amplitude (3.0).
        assert_relative_eq!(vals[0], 3.0, epsilon = 1e-12);
        assert_relative_eq!(vals[2], 3.0, epsilon = 1e-12);
        // Point 1 is far from center → strongly attenuated, strictly < amplitude.
        assert!(
            vals[1] < 1e-6,
            "far-field point should be ~0, got {}",
            vals[1]
        );

        // Sanity: a non-multiple-of-stride buffer is rejected.
        assert!(evaluate_compiled(&cg, &pf, &[0.0, 0.0, 0.0]).is_err());
    }

    /// Real (passing) test: the 1-D path is unchanged — a constant model over a
    /// plain 1-column `x` still yields one value per element.
    #[test]
    fn executor_one_d_constant_path_unchanged() {
        let mut params = HashMap::new();
        params.insert("c".to_string(), make_param(7.0, true));
        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![ModelNodeSpec {
                id: "bg".to_string(),
                model_type: ModelTypeStr::Constant,
                dataset_index: None,
                parameters: params,
            }],
            expr_edges: vec![],
        };
        let pf = flat(&[("bg.c", 7.0)]);
        let cg = CompiledGraph::compile(&graph).unwrap();
        assert_eq!(cg.n_dims().unwrap(), 1);
        let vals = evaluate_compiled(&cg, &pf, &[0.0, 1.0, 2.0, 3.0]).unwrap();
        assert_eq!(vals.len(), 4);
        for v in &vals {
            assert_relative_eq!(*v, 7.0, epsilon = 1e-12);
        }
    }

    #[test]
    fn gaussian2d_grid_evaluation_is_peaked_at_center() {
        // The 2-D *evaluation* half of a round-trip: a Gaussian2D over a strided
        // 5x5 grid yields one value per point, all positive, peaking at the grid
        // node nearest the true center (0.5, -1.0). The full solver-side round
        // trip (perturb start → fit → recover params) lives in the solver crate
        // (`crates/spectrafit-solver/tests/gaussian2d.rs`), which — unlike this
        // graph crate — depends on the solver. 2-D fitting works end-to-end; the
        // strided-x plumbing (`point_major_x`, point-count residual/Jacobian
        // sizing) was already complete (U2 / R4).
        let (graph, pf_true) = single_gaussian2d();
        let cg = CompiledGraph::compile(&graph).unwrap();

        // Build a synthetic grid (5x5) flattened point-major: [xᵢ, yᵢ] per point.
        let mut x_flat = Vec::new();
        let mut coords = Vec::new();
        for i in 0..5 {
            for j in 0..5 {
                let xi = -2.0 + i as f64;
                let yj = -3.0 + j as f64;
                x_flat.push(xi);
                x_flat.push(yj);
                coords.push((xi, yj));
            }
        }
        let y = evaluate_compiled(&cg, &pf_true, &x_flat).unwrap();
        assert_eq!(y.len(), 25, "len/stride = 50/2 = 25 points");

        // Every value is positive and bounded by the amplitude (3.0).
        for &v in &y {
            assert!(v > 0.0 && v <= 3.0 + 1e-12, "value out of range: {v}");
        }

        // The peak grid value sits at the node nearest the true center (0.5,-1.0):
        // (cx≈0.0..1.0, cy=-1.0) → grid index (2,2) = coord (0.0, -1.0).
        let (peak_idx, &peak) = y
            .iter()
            .enumerate()
            .max_by(|a, b| a.1.partial_cmp(b.1).unwrap())
            .unwrap();
        assert!(peak > 0.0);
        let (px, py) = coords[peak_idx];
        assert!(
            (px - 0.0).abs() <= 1.0 && (py - (-1.0)).abs() <= 1e-12,
            "peak at ({px},{py}) not nearest true center (0.5,-1.0)"
        );
    }

    #[test]
    fn gaussian2d_jacobian_matches_finite_difference() {
        // Mirror of `jacobian_matches_finite_difference`, but over a strided
        // 2-D coordinate.  Verifies the executor passes the full [x, y] coord to
        // the analytical Jacobian and that it matches a forward difference.
        let (graph, pf) = single_gaussian2d();
        let cg = CompiledGraph::compile(&graph).unwrap();
        // Single off-center point [x, y].
        let x = vec![0.9f64, -0.2f64];
        let h = 1e-6;
        let jac = jacobian_compiled(&cg, &pf, &x).unwrap();
        assert_eq!(jac.nrows(), 1);
        assert_eq!(jac.ncols(), 5);

        let keys = [
            "g2.amplitude",
            "g2.center_x",
            "g2.center_y",
            "g2.sigma_x",
            "g2.sigma_y",
        ];
        for (col, key) in keys.iter().enumerate() {
            let mut pf_plus = pf.clone();
            *pf_plus.get_mut(*key).unwrap() += h;
            let f_plus = evaluate_compiled(&cg, &pf_plus, &x).unwrap()[0];
            let f_base = evaluate_compiled(&cg, &pf, &x).unwrap()[0];
            let fd = (f_plus - f_base) / h;
            assert!(
                (jac[(0, col)] - fd).abs() < 1e-5,
                "col {} ({}) analytical vs FD mismatch: got {}, expected {}",
                col,
                key,
                jac[(0, col)],
                fd
            );
        }
    }

    #[test]
    fn dataset_index_scopes_local_node_to_its_dataset() {
        // Two datasets of 3 points each, x concatenated (offsets [0, 3, 6]).
        // "gg" is global (dataset_index=None) → contributes to all 6 points.
        // "gl" is local to dataset 1 (dataset_index=Some(1)) → only points 3..6.
        let mk_node = |id: &str, ds: Option<usize>, c: f64| ModelNodeSpec {
            id: id.to_string(),
            model_type: ModelTypeStr::Gaussian,
            dataset_index: ds,
            parameters: {
                let mut p = HashMap::new();
                p.insert("amplitude".to_string(), make_param(1.0, true));
                p.insert("center".to_string(), make_param(c, true));
                p.insert("sigma".to_string(), make_param(0.5, true));
                p
            },
        };
        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![mk_node("gg", None, 0.0), mk_node("gl", Some(1), 5.0)],
            expr_edges: vec![],
        };
        let mut cg = CompiledGraph::compile(&graph).unwrap();
        cg.dataset_offsets = vec![0, 3, 6];

        let x = vec![-0.5, 0.0, 0.5, 4.5, 5.0, 5.5];
        let pf = flat(&[
            ("gg.amplitude", 1.0),
            ("gg.center", 0.0),
            ("gg.sigma", 0.5),
            ("gl.amplitude", 1.0),
            ("gl.center", 5.0),
            ("gl.sigma", 0.5),
        ]);

        // Components: the local node is zero on dataset 0, nonzero on dataset 1.
        let comps = evaluate_components_compiled(&cg, &pf, &x).unwrap();
        assert!(
            comps["gl"][0..3].iter().all(|&v| v == 0.0),
            "local node must contribute zero outside its dataset"
        );
        assert!(
            comps["gl"][3..6].iter().any(|&v| v.abs() > 1e-6),
            "local node must contribute inside its dataset"
        );
        assert!(comps["gg"][0..3].iter().any(|&v| v.abs() > 1e-6));

        // best_fit on a dataset-0 point excludes the local node (= gg only).
        let best = evaluate_compiled(&cg, &pf, &x).unwrap();
        assert!(
            (best[1] - comps["gg"][1]).abs() < 1e-12,
            "best_fit on dataset 0 must exclude the local node"
        );

        // Jacobian: the local node's free columns are zero on dataset-0 rows.
        let node_params: Vec<Vec<f64>> = (0..cg.nodes.len())
            .map(|i| cg.node_params(i, &pf).unwrap())
            .collect();
        let mut jdata = Vec::new();
        jacobian_compiled_indexed_into(&cg, &node_params, &x, &mut jdata).unwrap();
        let n_free = cg.free_keys.len();
        let gl_cols: Vec<usize> = cg
            .free_keys
            .iter()
            .enumerate()
            .filter(|(_, k)| k.starts_with("gl."))
            .map(|(i, _)| i)
            .collect();
        assert!(!gl_cols.is_empty());
        for row in 0..3 {
            for &col in &gl_cols {
                assert_eq!(
                    jdata[row * n_free + col],
                    0.0,
                    "local node Jacobian must be zero outside its dataset"
                );
            }
        }
    }

    /// G1 regression: a node whose `dataset_index` points beyond the recorded
    /// `dataset_offsets` must produce a `CoreError`, not an index panic, in the
    /// scoped eval/residual/Jacobian paths.
    #[test]
    fn out_of_range_dataset_index_errors_not_panics() {
        let mk_node = |id: &str, ds: Option<usize>, c: f64| ModelNodeSpec {
            id: id.to_string(),
            model_type: ModelTypeStr::Gaussian,
            dataset_index: ds,
            parameters: {
                let mut p = HashMap::new();
                p.insert("amplitude".to_string(), make_param(1.0, true));
                p.insert("center".to_string(), make_param(c, true));
                p.insert("sigma".to_string(), make_param(0.5, true));
                p
            },
        };
        // Two datasets recorded (offsets [0, 3, 6] → valid indices 0 and 1),
        // but "gl" references dataset 2 — beyond the offsets array.
        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![mk_node("gg", None, 0.0), mk_node("gl", Some(2), 5.0)],
            expr_edges: vec![],
        };
        let mut cg = CompiledGraph::compile(&graph).unwrap();
        cg.dataset_offsets = vec![0, 3, 6]; // 2 datasets → index 2 is out of range

        let x = vec![-0.5, 0.0, 0.5, 4.5, 5.0, 5.5];
        let y = vec![0.0; 6];
        let sigma = vec![1.0; 6];
        let pf = flat(&[
            ("gg.amplitude", 1.0),
            ("gg.center", 0.0),
            ("gg.sigma", 0.5),
            ("gl.amplitude", 1.0),
            ("gl.center", 5.0),
            ("gl.sigma", 0.5),
        ]);

        // best_fit (scoped sum) must error, not panic.
        let err = evaluate_compiled(&cg, &pf, &x).unwrap_err();
        assert!(
            format!("{err}").contains("dataset_index"),
            "expected a dataset_index range error, got: {err}"
        );

        // Components path must error too.
        assert!(evaluate_components_compiled(&cg, &pf, &x).is_err());

        // Residual path must error.
        let node_params: Vec<Vec<f64>> = (0..cg.nodes.len())
            .map(|i| cg.node_params(i, &pf).unwrap())
            .collect();
        let mut res = vec![0.0; 6];
        assert!(
            residuals_compiled_indexed_into(&cg, &node_params, &x, &y, &sigma, &mut res).is_err()
        );

        // Jacobian (unweighted and weighted) post-pass must error.
        let mut jdata = Vec::new();
        assert!(jacobian_compiled_indexed_into(&cg, &node_params, &x, &mut jdata).is_err());
        let mut jw = Vec::new();
        assert!(
            jacobian_compiled_indexed_weighted_into(&cg, &node_params, &x, &sigma, &mut jw)
                .is_err()
        );
    }

    /// A2 follow-up: an `x` buffer whose length is not a multiple of `n_dims`
    /// must surface the typed `GraphError::XBufferStrideMismatch` variant via
    /// the CoreError boundary conversion (a stale stringly-typed message would
    /// silently regress the typed-error contract).
    #[test]
    fn x_buffer_stride_mismatch_emits_graph_error_variant() {
        // Single Gaussian2D: n_dims = 2. Hand it an 7-long buffer (odd → not a
        // multiple of 2) so `coord_layout` rejects it.
        let mut params = HashMap::new();
        params.insert("amplitude".to_string(), make_param(1.0, true));
        params.insert("center_x".to_string(), make_param(0.0, true));
        params.insert("center_y".to_string(), make_param(0.0, true));
        params.insert("sigma_x".to_string(), make_param(1.0, true));
        params.insert("sigma_y".to_string(), make_param(1.0, true));
        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![ModelNodeSpec {
                id: "g".to_string(),
                model_type: ModelTypeStr::Gaussian2D,
                dataset_index: None,
                parameters: params,
            }],
            expr_edges: vec![],
        };
        let cg = CompiledGraph::compile(&graph).unwrap();
        let pf = flat(&[
            ("g.amplitude", 1.0),
            ("g.center_x", 0.0),
            ("g.center_y", 0.0),
            ("g.sigma_x", 1.0),
            ("g.sigma_y", 1.0),
        ]);

        let bad_x: Vec<f64> = vec![0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]; // length 7, n_dims = 2
        let err = evaluate_compiled(&cg, &pf, &bad_x).unwrap_err();
        let expected: CoreError = GraphError::XBufferStrideMismatch {
            x_len: 7,
            n_dims: 2,
        }
        .into();
        assert_eq!(format!("{err}"), format!("{expected}"));
    }
}
