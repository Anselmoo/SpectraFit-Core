//! spectrafit-core — PyO3 cdylib bindings (Phase 6)
// PyO3 0.22: `#[pyfunction]` generates `From<PyErr> for PyErr` conversions that
// clippy flags as useless. This is a known false-positive in the pyo3+clippy interaction.
#![allow(clippy::useless_conversion)]
#![warn(missing_docs)]
//!
//! Exposes Python-callable functions:
//!   - `fit(graph_json, data_json, options_json) -> str`
//!   - `fit_arrays(graph_json, x, y, sigma, dataset_sizes, n_dims, options_json) -> str`
//!   - `evaluate(graph_json, params_json, data_json) -> str`
//!   - `evaluate_components(graph_json, params_json, data_json) -> str`
//!
//! `fit` accepts JSON-encoded data (backwards-compatible, MCP-friendly).
//! `fit_arrays` accepts raw numpy buffers and eliminates JSON serialisation
//! of measurement data — the dominant bottleneck for large datasets.
//! `fit_arrays_numpy` extends `fit_arrays`: returns `(compact_json, best_fit_ndarray)`
//! so the large per-point arrays bypass JSON entirely, cutting 2–3 ms per call.
//! Graph/options remain JSON for reproducibility and language-neutrality.
//! `CoreError` maps to `PyValueError` so Python callers receive a descriptive
//! `ValueError`.

use std::collections::HashMap;

use numpy::{PyArray1, PyReadonlyArray1};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use spectrafit_types::{
    CoreError, FitGraphSpec, FitOptionsSpec, MeasurementInput, MeasurementSpec, ModelTypeStr,
};

// ---------------------------------------------------------------------------
// Internal helper: CoreError → PyValueError
// ---------------------------------------------------------------------------

fn core_err(e: CoreError) -> PyErr {
    PyValueError::new_err(e.to_string())
}

fn json_err(e: serde_json::Error) -> PyErr {
    PyValueError::new_err(format!("JSON parse error: {e}"))
}

// ---------------------------------------------------------------------------
// Internal helper: panic boundary
//
// A Rust panic crossing the PyO3 boundary surfaces in Python as
// `pyo3_runtime.PanicException`, a `BaseException` subclass that slips past
// `except Exception`. `guard` runs the entrypoint body inside `catch_unwind`
// and maps any caught panic to a clean `PyValueError`, so a degenerate input
// (e.g. a kernel arity precondition violated — see the `Model` trait `# Panics`
// contract in spectrafit-models) always reaches the caller as a catchable
// `Exception` rather than an uncatchable `PanicException`.
// ---------------------------------------------------------------------------

fn guard<T>(f: impl FnOnce() -> PyResult<T> + std::panic::UnwindSafe) -> PyResult<T> {
    match std::panic::catch_unwind(f) {
        Ok(result) => result,
        Err(payload) => {
            let msg = payload
                .downcast_ref::<&str>()
                .map(|s| (*s).to_string())
                .or_else(|| payload.downcast_ref::<String>().cloned())
                .unwrap_or_else(|| "unknown panic".to_string());
            Err(PyValueError::new_err(format!(
                "internal error (Rust panic): {msg}"
            )))
        }
    }
}

// ---------------------------------------------------------------------------
// Internal helper: flatten MeasurementSpec.x into a Vec<f64>
//
// Python sends x as "points × dims" where each inner list is one point's
// coordinates: x[i] = [x_value_for_point_i].  We extract x[i][0] for each i.
// ---------------------------------------------------------------------------

/// Flatten a validated 1-D MeasurementSpec's x into a `Vec<f64>` (point's first
/// coordinate). The caller (`collect_eval_x`) has already rejected empty rows, so
/// `first()` is guaranteed present — no silent `unwrap_or(0.0)` fabrication.
fn flatten_x(spec: &MeasurementSpec) -> Vec<f64> {
    spec.x.iter().map(|row| row[0]).collect()
}

/// Collect the 1-D x grid for `evaluate`/`evaluate_components`. Both wrap the
/// graph's 1-D, single-dataset evaluator, so reject multi-dataset / n-D inputs
/// explicitly rather than silently using only the first dataset's first dimension
/// (which produced wrong curves with no error for `Multi`/2-D input). Empty
/// coordinate rows are rejected too — previously they were silently fabricated as
/// `x = 0.0`, returning a wrong curve with no error.
fn collect_eval_x(input: MeasurementInput) -> PyResult<Vec<f64>> {
    let datasets = input.into_vec();
    if datasets.len() > 1 {
        return Err(PyValueError::new_err(format!(
            "evaluate() supports a single dataset only (got {}); use fit() for multi-dataset graphs",
            datasets.len()
        )));
    }
    match datasets.first() {
        Some(spec) if spec.x.iter().any(|row| row.len() > 1) => Err(PyValueError::new_err(
            "evaluate() is 1-D only; got n-D coordinates — use fit_arrays with n_dims for n-D models",
        )),
        Some(spec) if spec.x.iter().any(Vec::is_empty) => Err(PyValueError::new_err(
            "evaluate() received an x point with no coordinates (empty row); \
             every point must carry at least one coordinate",
        )),
        Some(spec) => Ok(flatten_x(spec)),
        None => Ok(Vec::new()),
    }
}

// ---------------------------------------------------------------------------
// Internal helper: transpose Python "points × dims" x format to Rust solver's
// "dims × points" format.
//
// Python schema:  x[i][d]  — i-th data point, d-th dimension
// Rust solver:    x[d][i]  — d-th dimension, i-th value along that dimension
//
// Example: [[0.0],[1.0],[2.0]] (3 pts × 1 dim) → [[0.0,1.0,2.0]] (1 dim × 3 pts)
// ---------------------------------------------------------------------------

fn transpose_x_for_solver(spec: MeasurementSpec) -> PyResult<MeasurementSpec> {
    if spec.x.is_empty() {
        return Ok(spec);
    }

    let n_points = spec.x.len();
    let n_dims = spec.x[0].len();
    if n_dims == 0 {
        return Err(PyValueError::new_err(
            "fit() received an x point with no coordinates (empty row); \
             every point must carry at least one coordinate",
        ));
    }
    // Reject ragged input rather than silently padding short rows with 0.0,
    // which produced a wrong fit with no error.
    if let Some(bad) = spec.x.iter().position(|row| row.len() != n_dims) {
        return Err(PyValueError::new_err(format!(
            "fit() received ragged x: point 0 has {n_dims} coordinate(s) but point \
             {bad} has {}; all points must share the same dimensionality",
            spec.x[bad].len()
        )));
    }

    let mut transposed: Vec<Vec<f64>> = vec![Vec::with_capacity(n_points); n_dims];
    for row in &spec.x {
        for (d, col) in transposed.iter_mut().enumerate() {
            col.push(row[d]);
        }
    }

    Ok(MeasurementSpec {
        x: transposed,
        ..spec
    })
}

// ---------------------------------------------------------------------------
// #[pyfunction] fit
// ---------------------------------------------------------------------------

/// Run a full Levenberg-Marquardt fit and return the result as JSON.
///
/// Arguments (all JSON strings):
/// - `graph_json`   — serialised `FitGraphSpec`
/// - `data_json`    — serialised `MeasurementInput` (single or array)
/// - `options_json` — serialised `FitOptionsSpec`
///
/// Returns a JSON string matching the `FitResult` Python schema.
#[pyfunction]
fn fit(graph_json: &str, data_json: &str, options_json: &str) -> PyResult<String> {
    guard(|| {
        // 1. Deserialise inputs
        let graph: FitGraphSpec = serde_json::from_str(graph_json).map_err(json_err)?;
        let input: MeasurementInput = serde_json::from_str(data_json).map_err(json_err)?;
        let options: FitOptionsSpec = serde_json::from_str(options_json).map_err(json_err)?;

        let datasets: Vec<MeasurementSpec> = input
            .into_vec()
            .into_iter()
            .map(transpose_x_for_solver)
            .collect::<PyResult<_>>()?;

        // 2. Run solver
        let result = spectrafit_solver::fit(&graph, datasets, &options).map_err(core_err)?;

        // 3. Serialise result to JSON
        serde_json::to_string(&result).map_err(json_err)
    })
}

// ---------------------------------------------------------------------------
// #[pyfunction] evaluate
// ---------------------------------------------------------------------------

/// Evaluate the model sum at every x-point and return a JSON array.
///
/// Arguments (all JSON strings):
/// - `graph_json`  — serialised `FitGraphSpec`
/// - `params_json` — flat dict `{"node.param": value, ...}`
/// - `data_json`   — serialised `MeasurementInput`
///
/// Returns a JSON array `[f64, ...]`.
#[pyfunction]
fn evaluate(graph_json: &str, params_json: &str, data_json: &str) -> PyResult<String> {
    guard(|| {
        // 1. Deserialise
        let graph: FitGraphSpec = serde_json::from_str(graph_json).map_err(json_err)?;
        let params: HashMap<String, f64> = serde_json::from_str(params_json).map_err(json_err)?;
        let input: MeasurementInput = serde_json::from_str(data_json).map_err(json_err)?;

        // 2. Collect x values (single-dataset, 1-D only — rejects Multi/n-D explicitly)
        let x: Vec<f64> = collect_eval_x(input)?;

        // 3. Evaluate
        let values = spectrafit_graph::evaluate(&graph, &params, &x).map_err(core_err)?;

        // 4. Serialise
        serde_json::to_string(&values).map_err(json_err)
    })
}

// ---------------------------------------------------------------------------
// #[pyfunction] evaluate_components
// ---------------------------------------------------------------------------

/// Evaluate each node independently and return a JSON object.
///
/// Arguments (all JSON strings):
/// - `graph_json`  — serialised `FitGraphSpec`
/// - `params_json` — flat dict `{"node.param": value, ...}`
/// - `data_json`   — serialised `MeasurementInput`
///
/// Returns a JSON object `{"node_id": [f64, ...], ...}`.
#[pyfunction]
fn evaluate_components(graph_json: &str, params_json: &str, data_json: &str) -> PyResult<String> {
    guard(|| {
        // 1. Deserialise
        let graph: FitGraphSpec = serde_json::from_str(graph_json).map_err(json_err)?;
        let params: HashMap<String, f64> = serde_json::from_str(params_json).map_err(json_err)?;
        let input: MeasurementInput = serde_json::from_str(data_json).map_err(json_err)?;

        // 2. Collect x values (single-dataset, 1-D only — rejects Multi/n-D explicitly)
        let x: Vec<f64> = collect_eval_x(input)?;

        // 3. Evaluate components
        let components =
            spectrafit_graph::evaluate_components(&graph, &params, &x).map_err(core_err)?;

        // 4. Serialise
        serde_json::to_string(&components).map_err(json_err)
    })
}

// ---------------------------------------------------------------------------
// #[pyfunction] fit_arrays
// ---------------------------------------------------------------------------

/// Run a Levenberg-Marquardt fit using raw numpy arrays for measurement data.
///
/// This eliminates JSON serialisation of x/y/sigma, which is the dominant
/// bottleneck for large datasets (scales as O(n)).
///
/// Arguments:
/// - `graph_json`     — serialised `FitGraphSpec` (JSON string)
/// - `x`              — flat 1-D numpy array of x-values in point-major layout
///                      (stride `n_dims`): point `i` of a dataset occupies the
///                      slice `x[i*n_dims .. (i+1)*n_dims]`, concatenated across
///                      datasets (shape `(n_total * n_dims,)`)
/// - `y`              — flat 1-D numpy array of observed values (shape `(n_total,)`)
/// - `sigma`          — optional 1-D numpy array of per-point σ (shape `(n_total,)`)
/// - `dataset_sizes`  — Python list of `int` giving the number of points per
///                      dataset; must sum to `len(y)`.  Pass `[len(y)]` for a
///                      single dataset.
/// - `n_dims`         — number of x-dimensions per point (1 or 2).  The flat `x`
///                      buffer is strided by this and reshaped to dims × points.
/// - `options_json`   — serialised `FitOptionsSpec` (JSON string)
///
/// Returns a JSON string matching the `FitResult` Python schema.
#[pyfunction]
#[pyo3(signature = (graph_json, x, y, sigma, dataset_sizes, n_dims, options_json))]
fn fit_arrays(
    graph_json: &str,
    x: PyReadonlyArray1<f64>,
    y: PyReadonlyArray1<f64>,
    sigma: Option<PyReadonlyArray1<f64>>,
    dataset_sizes: Vec<usize>,
    n_dims: usize,
    options_json: &str,
) -> PyResult<String> {
    // 1. Deserialise graph and options from JSON.
    let graph: FitGraphSpec = serde_json::from_str(graph_json).map_err(json_err)?;
    let options: FitOptionsSpec = serde_json::from_str(options_json).map_err(json_err)?;

    // 2. Validate sizes and slice the flat buffers.
    let x_slice = x
        .as_slice()
        .map_err(|e| PyValueError::new_err(format!("x array not contiguous: {e}")))?;
    let y_slice = y
        .as_slice()
        .map_err(|e| PyValueError::new_err(format!("y array not contiguous: {e}")))?;
    let sigma_vec: Option<Vec<f64>> = sigma
        .map(|s| {
            s.as_slice()
                .map(|sl| sl.to_vec())
                .map_err(|e| PyValueError::new_err(format!("sigma array not contiguous: {e}")))
        })
        .transpose()?;

    let datasets = split_array_datasets(
        x_slice,
        y_slice,
        sigma_vec.as_deref(),
        &dataset_sizes,
        n_dims,
    )?;

    // 3. Run solver and return JSON result.
    let result = spectrafit_solver::fit(&graph, datasets, &options).map_err(core_err)?;
    serde_json::to_string(&result).map_err(json_err)
}

// ---------------------------------------------------------------------------
// Internal helper: split flat point-major arrays into per-dataset specs.
//
// `x_slice` is point-major with stride `n_dims`: point `i` of the concatenated
// stream occupies `x_slice[i*n_dims .. (i+1)*n_dims]`.  Each per-dataset spec is
// reshaped to the solver's dims × points layout (matching `transpose_x_for_solver`
// on the JSON path).  `n_dims` of 1 reproduces the original 1-D behaviour.
// ---------------------------------------------------------------------------

fn split_array_datasets(
    x_slice: &[f64],
    y_slice: &[f64],
    sigma_slice: Option<&[f64]>,
    dataset_sizes: &[usize],
    n_dims: usize,
) -> PyResult<Vec<MeasurementSpec>> {
    if n_dims == 0 {
        return Err(PyValueError::new_err("n_dims must be >= 1"));
    }

    let n_total: usize = dataset_sizes.iter().sum();
    if n_total != y_slice.len() {
        return Err(PyValueError::new_err(format!(
            "dataset_sizes sum ({}) != len(y) ({})",
            n_total,
            y_slice.len()
        )));
    }
    // Checked multiply: an adversarial dataset_sizes could overflow usize and make
    // the length check pass spuriously, then panic on slice indexing below.
    let x_expected = n_total.checked_mul(n_dims).ok_or_else(|| {
        PyValueError::new_err("n_total * n_dims overflows usize (dataset_sizes too large)")
    })?;
    if x_expected != x_slice.len() {
        return Err(PyValueError::new_err(format!(
            "n_total * n_dims ({n_total} * {n_dims} = {x_expected}) != len(x) ({})",
            x_slice.len()
        )));
    }

    let mut datasets: Vec<MeasurementSpec> = Vec::with_capacity(dataset_sizes.len());
    let mut point_offset = 0usize;
    for &size in dataset_sizes {
        let x_base = point_offset * n_dims;
        // Reshape point-major (points × dims) into dims × points rows. The size
        // checks above guarantee these ranges are in-bounds, but use `get(..)` so
        // any future invariant drift surfaces as a clean ValueError, not a panic.
        let mut x_dims: Vec<Vec<f64>> = vec![Vec::with_capacity(size); n_dims];
        for i in 0..size {
            let pt = x_slice
                .get(x_base + i * n_dims..x_base + (i + 1) * n_dims)
                .ok_or_else(|| PyValueError::new_err("x slice out of bounds while reshaping"))?;
            for (d, col) in x_dims.iter_mut().enumerate() {
                col.push(pt[d]);
            }
        }
        let y_chunk = y_slice
            .get(point_offset..point_offset + size)
            .ok_or_else(|| PyValueError::new_err("y slice out of bounds while splitting datasets"))?
            .to_vec();
        let sigma_chunk = match sigma_slice {
            Some(s) => Some(
                s.get(point_offset..point_offset + size)
                    .ok_or_else(|| {
                        PyValueError::new_err("sigma slice out of bounds while splitting datasets")
                    })?
                    .to_vec(),
            ),
            None => None,
        };
        datasets.push(MeasurementSpec {
            schema_version: None,
            x: x_dims,
            y: y_chunk,
            sigma: sigma_chunk,
            label: None,
        });
        point_offset += size;
    }
    Ok(datasets)
}

// ---------------------------------------------------------------------------
// #[pyfunction] fit_arrays_numpy
// ---------------------------------------------------------------------------

/// Like `fit_arrays`, but bypasses JSON serialisation of per-point arrays.
///
/// Returns `(compact_result_json, best_fit_array)` where:
/// - `compact_result_json` contains parameters + scalar fit metrics only
///   (best_fit / residuals / init_fit / components are stripped out).
/// - `best_fit_array` is a 1-D float64 NumPy array of fitted values.
///
/// This eliminates the dominant per-call overhead (~2 ms) when the caller
/// only needs the fitted curve as a NumPy array, not as a JSON list.
// Allowed: PyO3 binding contract — 8 args mirror the Python boundary the
// caller already constructs; squashing into a struct would force the Python
// side to build an intermediate object on every call (defeats the
// "eliminates ~2 ms per-call overhead" goal stated above).
#[allow(clippy::too_many_arguments)]
#[pyfunction]
#[pyo3(signature = (graph_json, x, y, sigma, dataset_sizes, n_dims, options_json))]
fn fit_arrays_numpy<'py>(
    py: Python<'py>,
    graph_json: &str,
    x: PyReadonlyArray1<f64>,
    y: PyReadonlyArray1<f64>,
    sigma: Option<PyReadonlyArray1<f64>>,
    dataset_sizes: Vec<usize>,
    n_dims: usize,
    options_json: &str,
) -> PyResult<(String, Bound<'py, PyArray1<f64>>)> {
    let graph: FitGraphSpec = serde_json::from_str(graph_json).map_err(json_err)?;
    let options: FitOptionsSpec = serde_json::from_str(options_json).map_err(json_err)?;

    let x_slice = x
        .as_slice()
        .map_err(|e| PyValueError::new_err(format!("x array not contiguous: {e}")))?;
    let y_slice = y
        .as_slice()
        .map_err(|e| PyValueError::new_err(format!("y array not contiguous: {e}")))?;
    let sigma_vec: Option<Vec<f64>> = sigma
        .map(|s| {
            s.as_slice()
                .map(|sl| sl.to_vec())
                .map_err(|e| PyValueError::new_err(format!("sigma array not contiguous: {e}")))
        })
        .transpose()?;

    let datasets = split_array_datasets(
        x_slice,
        y_slice,
        sigma_vec.as_deref(),
        &dataset_sizes,
        n_dims,
    )?;

    let mut result = spectrafit_solver::fit(&graph, datasets, &options).map_err(core_err)?;

    // Extract best_fit before stripping the large arrays from the result.
    let best_fit = std::mem::take(&mut result.best_fit);
    result.residuals.clear();
    result.init_fit.clear();
    result.components.clear();
    result.dataset_slices = None;

    let compact_json = serde_json::to_string(&result).map_err(json_err)?;
    let best_fit_array = PyArray1::from_vec_bound(py, best_fit);
    Ok((compact_json, best_fit_array))
}

// ---------------------------------------------------------------------------
// #[pyfunction] model_type_wire_strings
// ---------------------------------------------------------------------------

/// Return the canonical wire-format string of every supported model type, in
/// `ModelTypeStr` declaration order.
///
/// This exposes the single Rust source of truth — the
/// `model_manifest!`-generated [`ModelTypeStr::ALL`] — to Python so the
/// `ModelType` ↔ Rust parity test can pin the hand-written Python enum against
/// the ACTUAL Rust variant set rather than a second hand-maintained list.
/// Adding a model to the manifest auto-updates this enumeration, so the Python
/// enum can drift from Rust only by failing that test (never silently).
#[pyfunction]
fn model_type_wire_strings() -> Vec<String> {
    ModelTypeStr::ALL
        .iter()
        .map(|m| m.as_str().to_string())
        .collect()
}

// ---------------------------------------------------------------------------
// #[pymodule]
// ---------------------------------------------------------------------------

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Eagerly initialize the global rayon thread pool so the first `fit()` call
    // does not pay the ~360 ms cold-start penalty.  The Err branch fires only
    // if the pool was already initialized (safe to ignore).
    let _ = rayon::ThreadPoolBuilder::new().build_global();

    m.add_function(wrap_pyfunction!(fit, m)?)?;
    m.add_function(wrap_pyfunction!(fit_arrays, m)?)?;
    m.add_function(wrap_pyfunction!(fit_arrays_numpy, m)?)?;
    m.add_function(wrap_pyfunction!(evaluate, m)?)?;
    m.add_function(wrap_pyfunction!(evaluate_components, m)?)?;
    m.add_function(wrap_pyfunction!(model_type_wire_strings, m)?)?;
    Ok(())
}
