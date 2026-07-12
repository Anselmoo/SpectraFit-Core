//! Global optimiser — Differential Evolution (DE) + LM refinement.
//!
//! DE is a stochastic population-based method that works without gradient
//! information.  It is well-suited for pathological cases (Ackley, Rastrigin,
//! multi-modal surfaces) where local LM converges to a wrong minimum.
//!
//! Algorithm (DE/rand/1/bin — the canonical variant):
//!   1. Initialise population of `pop_size` candidate vectors, uniformly
//!      sampled within the parameter bounds.
//!   2. For each generation:
//!      a. For each candidate `x_i`, select three distinct individuals `a`, `b`, `c`.
//!      b. Mutant:  `v = a + F * (b − c)` where `F` is the differential weight.
//!      c. Crossover: trial `u_j = v_j` if `rand() < CR`, else `u_j = x_j`.
//!      d. Selection: if `cost(u) < cost(x_i)`, replace `x_i` with `u`.
//!   3. After convergence (or `max_gen` reached), run LM from the best
//!      individual to refine the solution.
//!
//! Reference: Storn & Price (1997), Journal of Global Optimization.
//!
//! Usage: `FitOptions(solver="global")`.

use std::collections::HashMap;

use spectrafit_graph::{compiler::CompiledGraph, evaluate_compiled};
use spectrafit_types::{CoreError, FitGraphSpec, FitOptionsSpec, FitResultSpec, MeasurementSpec};

use crate::dispatch::fit as lm_fit;
use crate::dispatch::point_major_x;
use crate::error::SolverError;

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

/// Configuration for the Differential Evolution global optimiser.
#[derive(Debug, Clone)]
pub struct DeConfig {
    /// Population size (default: 15 × n_free, min 10).
    pub pop_size: usize,
    /// Maximum number of generations (default: 100).
    pub max_gen: usize,
    /// Differential weight `F` in `[0, 2]` (default: 0.8).
    pub f_weight: f64,
    /// Crossover probability `CR` in `[0, 1]` (default: 0.9).
    pub cr: f64,
    /// Cost improvement threshold for early stopping (default: 1e-7).
    pub tol: f64,
    /// Random seed (default: 42 for reproducibility).
    pub seed: u64,
}

impl Default for DeConfig {
    fn default() -> Self {
        DeConfig {
            pop_size: 0, // 0 → auto: 15 * n_free, min 10
            max_gen: 100,
            f_weight: 0.8,
            cr: 0.9,
            tol: 1e-7,
            seed: 42,
        }
    }
}

// ---------------------------------------------------------------------------
// Solver entry point
// ---------------------------------------------------------------------------

/// Run Differential Evolution followed by LM refinement.
///
/// # Arguments
/// * `graph`    — model DAG.
/// * `datasets` — one or more measurement datasets.
/// * `options`  — fit options (used for LM refinement step).
/// * `config`   — DE configuration.
pub fn solve_global(
    graph: &FitGraphSpec,
    datasets: Vec<MeasurementSpec>,
    options: &FitOptionsSpec,
    mut config: DeConfig,
) -> Result<FitResultSpec, CoreError> {
    // Override DE tolerance from options when explicitly set (non-zero).
    if options.tolerance > 0.0 {
        config.tol = options.tolerance;
    }
    // ── 1. Compile graph and extract bounds ─────────────────────────────────
    let cg = CompiledGraph::compile(graph)?;
    let free_keys = cg.free_keys.clone();
    let n_free = free_keys.len();

    if n_free == 0 {
        // No free parameters — delegate directly to LM.
        let lm_opts = FitOptionsSpec {
            solver: "lm".into(),
            ..options.clone()
        };
        return lm_fit(graph, datasets, &lm_opts);
    }

    // ── 2. Build combined x/y for cost evaluation ───────────────────────────
    // Built before the bounds loop so unbounded parameters can fall back to
    // *data-aware* ranges rather than a fixed ±10 window around the seed.
    // Point-major (stride = n_dims) so `evaluate_compiled` reads each point's full
    // coordinate; 1-D reduces to the old per-dataset `ds.x[0]` concatenation. Using
    // only `ds.x[0]` broke any n-D model (e.g. gaussian2d) under the global/DE path.
    let x_all: Vec<f64> = datasets.iter().flat_map(point_major_x).collect();
    let y_all: Vec<f64> = datasets
        .iter()
        .flat_map(|ds| ds.y.iter().copied())
        .collect();

    let (x_min, x_max) = x_all
        .iter()
        .copied()
        .filter(|v| v.is_finite())
        .fold((f64::INFINITY, f64::NEG_INFINITY), |(lo, hi), v| {
            (lo.min(v), hi.max(v))
        });
    let x_span = if x_max > x_min { x_max - x_min } else { 10.0 };
    let y_max_abs = y_all
        .iter()
        .copied()
        .filter(|v| v.is_finite())
        .fold(0.0_f64, |m, v| m.max(v.abs()));

    let mut bounds: Vec<(f64, f64)> = Vec::with_capacity(n_free);
    for key in &free_keys {
        let (node_id, param_name) = key
            .split_once('.')
            .ok_or_else(|| SolverError::Dispatch(format!("malformed free key: '{key}'")))?;
        let node = graph
            .nodes
            .iter()
            .find(|n| n.id == node_id)
            .ok_or_else(|| SolverError::Dispatch(format!("node '{node_id}' not found")))?;
        let pspec = node.parameters.get(param_name).ok_or_else(|| {
            SolverError::Dispatch(format!(
                "param '{param_name}' not found in node '{node_id}'"
            ))
        })?;
        // Data-aware fallback for unbounded parameters: a `center` that may
        // roam to ±1e3 produces a flat off-domain model, so DE must explore the
        // observed x-range instead of a fixed window around the seed value.
        let (fb_lo, fb_hi) =
            fallback_bounds(param_name, pspec.value, x_min, x_max, x_span, y_max_abs);
        let lo = if pspec.min.is_finite() {
            pspec.min
        } else {
            fb_lo
        };
        let hi = if pspec.max.is_finite() {
            pspec.max
        } else {
            fb_hi
        };
        bounds.push((lo, hi));
    }

    let cost_fn = |params: &[f64]| -> f64 {
        let flat: HashMap<String, f64> = build_flat(graph, &free_keys, params);
        match evaluate_compiled(&cg, &flat, &x_all) {
            // A length mismatch means the model and observations disagree on point
            // count (e.g. a bad x layout); treat as a diverged candidate rather than
            // letting `zip` silently truncate to a wrong-but-finite cost.
            Ok(pred) if pred.len() == y_all.len() => pred
                .iter()
                .zip(y_all.iter())
                .map(|(p, o)| (p - o).powi(2))
                .sum(),
            Ok(_) => f64::INFINITY,
            Err(_) => f64::INFINITY,
        }
    };

    // ── 3. Initialise population ─────────────────────────────────────────────
    let pop_size = if config.pop_size > 0 {
        config.pop_size
    } else {
        (15 * n_free).max(10)
    };

    let mut rng = Lcg64(config.seed);
    let mut population: Vec<Vec<f64>> = (0..pop_size)
        .map(|_| {
            bounds
                .iter()
                .map(|&(lo, hi)| lo + (hi - lo) * rng.next_f64())
                .collect()
        })
        .collect();
    let mut costs: Vec<f64> = population.iter().map(|p| cost_fn(p)).collect();

    // ── 4. DE main loop ──────────────────────────────────────────────────────
    let mut best_cost = costs.iter().cloned().fold(f64::INFINITY, f64::min);

    // Early-stop guards: never quit before exploring `min_gen` generations, and
    // require several consecutive stalls of *relative* improvement afterwards.
    // The previous absolute `|Δcost| < tol` test exited after ~1 generation on a
    // degenerate start where every candidate was equally (finitely) bad.
    // Explore at least `max_gen/10` generations (floor 20) before honouring an
    // early-stop. This both escapes the degenerate flat start and pushes past
    // the early plateaus that multimodal surrogates (rastrigin/griewank) exhibit
    // before reaching the good basin; a too-low floor stops at the first plateau.
    let min_gen = (config.max_gen / 10).max(20);
    let mut stall = 0usize;
    let mut gens_run = 0usize;

    for gen in 0..config.max_gen {
        gens_run = gen + 1;
        let prev_best = best_cost;

        for i in 0..pop_size {
            // Pick 3 distinct indices ≠ i
            let (a, b, c) = pick3(&mut rng, pop_size, i);

            // Mutant vector
            let mut trial: Vec<f64> = (0..n_free)
                .map(|j| population[a][j] + config.f_weight * (population[b][j] - population[c][j]))
                .collect();

            // Crossover
            let j_rand = (rng.next_f64() * n_free as f64) as usize;
            for j in 0..n_free {
                if j != j_rand && rng.next_f64() >= config.cr {
                    trial[j] = population[i][j];
                }
                // Clamp to bounds
                let (lo, hi) = bounds[j];
                trial[j] = trial[j].clamp(lo, hi);
            }

            // Selection
            let trial_cost = cost_fn(&trial);
            if trial_cost < costs[i] {
                costs[i] = trial_cost;
                population[i] = trial;
            }
        }

        best_cost = costs.iter().cloned().fold(f64::INFINITY, f64::min);
        let rel_improvement =
            (prev_best - best_cost).abs() / prev_best.abs().max(f64::MIN_POSITIVE);
        if rel_improvement < config.tol {
            stall += 1;
        } else {
            stall = 0;
        }
        if gen + 1 >= min_gen && stall >= 5 {
            break;
        }
    }

    // ── 5. Extract best individual ───────────────────────────────────────────
    // INVARIANT: the iterator was pre-filtered by `.filter(|(_, c)| c.is_finite())`, so
    // both `a` and `b` are guaranteed to be finite f64 values here, making `partial_cmp`
    // infallible (finite f64 values always have a defined ordering).
    let best_idx = costs
        .iter()
        .enumerate()
        .filter(|(_, c)| c.is_finite())
        .min_by(|(_, a), (_, b)| a.partial_cmp(b).expect("INVARIANT: both values are finite"))
        .map(|(i, _)| i)
        .ok_or_else(|| SolverError::GlobalFailure("all DE candidates diverged (NaN costs)".into()))?;

    let best_params = &population[best_idx];

    // ── 6. Seed LM from best DE solution ────────────────────────────────────
    let mut refined_graph = graph.clone();
    for node in &mut refined_graph.nodes {
        for (pname, pspec) in &mut node.parameters {
            let key = format!("{}.{}", node.id, pname);
            if let Some(pos) = free_keys.iter().position(|k| k == &key) {
                pspec.value = best_params[pos];
                // Constrain LM refinement to the same data-aware range DE
                // explored. Otherwise an originally-unbounded parameter can
                // diverge off-domain during refinement (e.g. a Gaussian centre
                // shooting to 1e216), undoing the global search. User-supplied
                // finite bounds are left untouched.
                let (lo, hi) = bounds[pos];
                if !pspec.min.is_finite() {
                    pspec.min = lo;
                }
                if !pspec.max.is_finite() {
                    pspec.max = hi;
                }
            }
        }
    }

    let lm_opts = FitOptionsSpec {
        solver: "lm".into(),
        ..options.clone()
    };
    // Refine from the DE best, then surface the DE search effort: `n_iter` on the
    // returned result counts only the post-DE LM refinement (often 0), so without
    // this the global search would appear to have done nothing. The DE-applied
    // data-aware bounds on `refined_graph` also mean the off-domain guard in
    // `assemble_result` never trips on this path.
    let mut result = lm_fit(&refined_graph, datasets, &lm_opts)?;
    result.n_de_generations = Some(gens_run as u64);
    Ok(result)
}

// ---------------------------------------------------------------------------
// Private helpers
// ---------------------------------------------------------------------------

/// Data-aware fallback bounds for a parameter whose user min/max is non-finite.
///
/// The DE population is seeded uniformly inside these bounds, so they must keep
/// candidates inside the region where the model is non-degenerate:
/// * `center`-like params are clamped to the observed x-range.
/// * `amplitude`/`height` params span `[min(0, seed), ~4·max|y|]`.
/// * width-like params (`sigma`/`gamma`/`width`) stay positive and bounded by
///   the data span.
/// * everything else gets a span-scaled window around the seed.
pub(crate) fn fallback_bounds(
    param: &str,
    value: f64,
    x_min: f64,
    x_max: f64,
    x_span: f64,
    y_max_abs: f64,
) -> (f64, f64) {
    let lname = param.to_ascii_lowercase();
    if lname.contains("center") || lname.contains("position") {
        if x_max > x_min {
            (x_min, x_max)
        } else {
            (value - x_span, value + x_span)
        }
    } else if lname.contains("amplitude") || lname.contains("height") {
        let cap = (4.0 * y_max_abs).max(value.abs() * 2.0).max(1.0);
        (0.0_f64.min(value), cap)
    } else if lname.contains("sigma") || lname.contains("gamma") || lname.contains("width") {
        (1e-6, x_span.max(value.abs() * 4.0).max(1e-3))
    } else {
        let pad = (2.0 * x_span).max(value.abs() * 2.0).max(10.0);
        (value - pad, value + pad)
    }
}

/// Build a flat `{key → value}` param map, injecting free param values.
fn build_flat(graph: &FitGraphSpec, free_keys: &[String], params: &[f64]) -> HashMap<String, f64> {
    let mut flat: HashMap<String, f64> = HashMap::new();
    for node in &graph.nodes {
        for (pname, pspec) in &node.parameters {
            flat.insert(format!("{}.{}", node.id, pname), pspec.value);
        }
    }
    for (i, key) in free_keys.iter().enumerate() {
        flat.insert(key.clone(), params[i]);
    }
    flat
}

/// Pick three distinct indices in `[0, n)`, all ≠ `exclude`.
fn pick3(rng: &mut Lcg64, n: usize, exclude: usize) -> (usize, usize, usize) {
    let mut indices: Vec<usize> = (0..n).filter(|&i| i != exclude).collect();
    // Partial Fisher-Yates shuffle to get 3 distinct values
    for i in 0..3.min(indices.len()) {
        let j = i + (rng.next_f64() * (indices.len() - i) as f64) as usize;
        indices.swap(i, j);
    }
    (
        indices[0 % indices.len()],
        indices[1 % indices.len()],
        indices[2 % indices.len()],
    )
}

// ---------------------------------------------------------------------------
// Minimal LCG RNG (no external dependency)
// ---------------------------------------------------------------------------

/// 64-bit linear congruential generator (Knuth multiplier).
struct Lcg64(u64);

impl Lcg64 {
    /// Advance and return a pseudo-random f64 in [0, 1).
    fn next_f64(&mut self) -> f64 {
        self.0 = self
            .0
            .wrapping_mul(6_364_136_223_846_793_005)
            .wrapping_add(1_442_695_040_888_963_407);
        // Use the upper 53 bits for mantissa precision
        (self.0 >> 11) as f64 / (1u64 << 53) as f64
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lcg64_range() {
        let mut rng = Lcg64(42);
        for _ in 0..1000 {
            let v = rng.next_f64();
            assert!((0.0..1.0).contains(&v), "LCG out of range: {v}");
        }
    }

    #[test]
    fn pick3_distinct() {
        let mut rng = Lcg64(1);
        for exclude in 0..10 {
            let (a, b, c) = pick3(&mut rng, 10, exclude);
            assert_ne!(a, exclude);
            assert_ne!(b, exclude);
            assert_ne!(c, exclude);
            assert!(a < 10 && b < 10 && c < 10);
        }
    }

    #[test]
    fn de_recovers_gaussian() {
        use spectrafit_types::{
            FitGraphSpec, MeasurementSpec, ModelNodeSpec, ModelTypeStr, ParameterSpec,
        };

        let (true_a, true_c, true_s) = (5.0_f64, 1.0_f64, 0.5_f64);
        let n = 60usize;
        let x: Vec<f64> = (0..n)
            .map(|i| -2.0 + 6.0 * i as f64 / (n - 1) as f64)
            .collect();
        let y: Vec<f64> = x
            .iter()
            .map(|&xi| true_a * (-(xi - true_c).powi(2) / (2.0 * true_s * true_s)).exp())
            .collect();

        let mut params = HashMap::new();
        params.insert(
            "amplitude".into(),
            ParameterSpec {
                value: 1.0,
                min: 0.0,
                max: 10.0,
                vary: true,
                expr: None,
                scale: None,
            },
        );
        params.insert(
            "center".into(),
            ParameterSpec {
                value: 0.0,
                min: -3.0,
                max: 3.0,
                vary: true,
                expr: None,
                scale: None,
            },
        );
        params.insert(
            "sigma".into(),
            ParameterSpec {
                value: 2.0,
                min: 0.01,
                max: 5.0,
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
        let dataset = MeasurementSpec {
            schema_version: None,
            x: vec![x],
            y,
            sigma: None,
            label: None,
        };
        let options = FitOptionsSpec {
            schema_version: None,
            solver: "global".into(),
            max_iterations: 200,
            tolerance: 1e-8,
            delta0: None,
            max_delta: None,
            eta: None,
        };

        let cfg = DeConfig {
            pop_size: 50,
            max_gen: 200,
            ..Default::default()
        };
        let result =
            solve_global(&graph, vec![dataset], &options, cfg).expect("DE should not error");

        let a = result.parameters["g1.amplitude"].value;
        let c = result.parameters["g1.center"].value;
        let s = result.parameters["g1.sigma"].value;
        // Tolerances are looser than LM because the global search seeds LM, which
        // then refines; the combined result should converge to <5% for clean data.
        assert!((a - true_a).abs() / true_a < 0.05, "amplitude: {a}");
        assert!((c - true_c).abs() < 0.05, "center: {c}");
        assert!((s - true_s).abs() / true_s < 0.05, "sigma: {s}");
        // The global path must surface its DE search effort: n_iter counts only
        // the post-DE LM refinement, so n_de_generations is how a caller sees
        // that DE actually ran.
        assert!(
            result.n_de_generations.unwrap_or(0) > 0,
            "global fit must report DE generations, got {:?}",
            result.n_de_generations
        );
    }

    #[test]
    fn fallback_bounds_center_uses_data_range() {
        // Unbounded center must fall back to the observed x-range, not seed±10.
        let (lo, hi) = fallback_bounds("center", 0.0, -5.0, 5.0, 10.0, 3.0);
        assert_eq!((lo, hi), (-5.0, 5.0));
    }

    #[test]
    fn de_starts_with_unbounded_centers() {
        // Regression: a two-Gaussian basis with *unbounded* centers (the case
        // the pathological benchmark uses) used to come out flat because DE
        // seeded centers in [seed-10, seed+10] and exited after ~1 generation.
        use spectrafit_types::{
            FitGraphSpec, MeasurementSpec, ModelNodeSpec, ModelTypeStr, ParameterSpec,
        };

        // Bimodal target: two well-separated Gaussians on x ∈ [-6, 6].
        let n = 120usize;
        let x: Vec<f64> = (0..n)
            .map(|i| -6.0 + 12.0 * i as f64 / (n - 1) as f64)
            .collect();
        let g = |xi: f64, a: f64, c: f64, s: f64| a * (-(xi - c).powi(2) / (2.0 * s * s)).exp();
        let y: Vec<f64> = x
            .iter()
            .map(|&xi| g(xi, 4.0, -2.5, 0.7) + g(xi, 3.0, 2.5, 0.7))
            .collect();

        let unbounded_center = |c0: f64| ParameterSpec {
            value: c0,
            min: f64::NEG_INFINITY,
            max: f64::INFINITY,
            vary: true,
            expr: None,
            scale: None,
        };
        let bounded = |v: f64, lo: f64, hi: f64| ParameterSpec {
            value: v,
            min: lo,
            max: hi,
            vary: true,
            expr: None,
            scale: None,
        };
        let make_node = |id: &str, c0: f64| {
            let mut params = HashMap::new();
            params.insert("amplitude".into(), bounded(1.0, 0.0, 20.0));
            params.insert("center".into(), unbounded_center(c0));
            params.insert("sigma".into(), bounded(1.0, 1e-3, 5.0));
            ModelNodeSpec {
                id: id.into(),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: None,
                parameters: params,
            }
        };

        let graph = FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![make_node("p1", -1.0), make_node("p2", 1.0)],
            expr_edges: vec![],
        };
        let dataset = MeasurementSpec {
            schema_version: None,
            x: vec![x],
            y: y.clone(),
            sigma: None,
            label: None,
        };
        let options = FitOptionsSpec {
            schema_version: None,
            solver: "global".into(),
            max_iterations: 300,
            tolerance: 1e-8,
            delta0: None,
            max_delta: None,
            eta: None,
        };

        let result = solve_global(&graph, vec![dataset], &options, DeConfig::default())
            .expect("DE should not error");

        // The fit must actually move off the seed and reduce residuals — a flat
        // off-domain result would leave a near-zero model and a huge SSR.
        let centers = [
            result.parameters["p1.center"].value,
            result.parameters["p2.center"].value,
        ];
        assert!(
            centers.iter().all(|c| (-6.0..=6.0).contains(c)),
            "centers escaped data domain: {centers:?}"
        );
        // SSR of a flat (all-zero) model is Σy². The fit must be far below that.
        let ssr_flat: f64 = y.iter().map(|v| v * v).sum();
        let ssr_fit: f64 = result
            .best_fit
            .iter()
            .zip(y.iter())
            .map(|(p, o)| (p - o).powi(2))
            .sum();
        // Regression guard: the previous bug left the model flat/off-domain so
        // SSR stayed ≈ Σy². The fix must make DE explore and substantially
        // reduce residuals (this asserts "DE starts and improves", not global
        // optimality — solver tuning is measured separately by the benchmark).
        assert!(
            ssr_fit < 0.5 * ssr_flat,
            "fit did not improve: ssr_fit={ssr_fit}, ssr_flat={ssr_flat}"
        );
    }
}
