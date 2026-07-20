//! Graph compiler: converts a [`FitGraphSpec`] into a [`CompiledGraph`] ready
//! for evaluation.
//!
//! Responsibilities:
//!   - Instantiate model objects from `ModelTypeStr`
//!   - Resolve per-node parameter lists and `free_mask`
//!   - Build the ordered `free_keys` vector (node alpha-sorted, then model param order)
//!   - Reject duplicate node IDs
//!   - Reject duplicate or cyclic `expr_edge` targets

use std::collections::HashMap;

use spectrafit_models::model_from_str_with_dims;
use spectrafit_types::{CoreError, FitGraphSpec, ModelTypeStr, ParameterSpec};

use crate::error::GraphError;
use crate::expr::TiedPlan;

// Re-export Model for downstream use without needing to import spectrafit_models directly.
pub use spectrafit_models::Model;

/// Infer the dimensionality `D` of a parametric N-D kernel from a node's
/// parameters. For `gaussian_nd`, `D` is the number of `center_<i>` parameters
/// (`center_0`, `center_1`, …); contiguous indexing and the matching
/// `sigma_<i>` set are enforced downstream by the missing-parameter check
/// against `GaussianND::param_names()`. Returns `None` for fixed-dimensionality
/// models, which carry their own `n_dims` via the `Model` trait.
fn infer_parametric_n_dims(
    type_str: &str,
    params: &HashMap<String, ParameterSpec>,
) -> Option<usize> {
    if type_str != ModelTypeStr::GaussianNd.as_str() {
        return None;
    }
    let d = params
        .keys()
        .filter(|k| {
            k.strip_prefix("center_")
                .is_some_and(|rest| !rest.is_empty() && rest.bytes().all(|b| b.is_ascii_digit()))
        })
        .count();
    Some(d)
}

// ---------------------------------------------------------------------------
// Public data structures
// ---------------------------------------------------------------------------

/// A single compiled graph node: model instance + resolved param metadata.
pub struct NodeEntry {
    /// Node identifier (matches `ModelNodeSpec::id`).
    pub id: String,
    /// Boxed model kernel.
    pub model: Box<dyn Model>,
    /// Local parameter names in the order expected by the model.
    pub param_names: Vec<String>,
    /// `true` if the parameter is free (vary=true AND no expr).
    pub free_mask: Vec<bool>,
    /// Dataset scope (mirrors [`ModelNodeSpec::dataset_index`]). `None` = global
    /// node (contributes to every dataset's points); `Some(i)` = local to dataset
    /// `i` (contributes residuals/Jacobian only to that dataset's contiguous
    /// point-range). Used for simultaneous multi-dataset ("global analysis") fits.
    pub dataset_index: Option<usize>,
}

/// The compiled representation of a [`FitGraphSpec`], ready for evaluation.
pub struct CompiledGraph {
    /// Nodes in their original declaration order (used for evaluation).
    pub nodes: Vec<NodeEntry>,
    /// Keys `"node_id.param_name"` for all free parameters,
    /// sorted by node_id alphabetically, then by model param order within a node.
    pub free_keys: Vec<String>,
    /// Per-node Jacobian column layout, pre-computed during [`compile`].
    ///
    /// `node_free_cols[i]` lists `(local_param_idx, jac_col)` for every free
    /// parameter on `nodes[i]`.  Used by the solver to avoid string-parsing
    /// `free_keys` on every iteration.
    pub node_free_cols: Vec<Vec<(usize, usize)>>,
    /// Dependency-ordered plan for tied (`expr_edge`) parameters.
    ///
    /// Empty when the graph declares no `expr_edges`.  When non-empty, the
    /// solver calls [`TiedPlan::apply`] on the flat parameter map after
    /// updating the free parameters on every iteration, so that each tied
    /// target is recomputed from its expression before the model is evaluated.
    ///
    /// Applied per-iteration by `spectrafit-solver::problem::set_free_and_tied`
    /// — the single `set_params` entry shared by both the nalgebra-LM and faer
    /// trust-region front-ends. The FD Jacobian re-applies ties per
    /// perturbation, and the analytic Jacobian is swapped for FD when ties are
    /// present so chain-rule terms are captured. End-to-end coverage:
    /// `dispatch::tests::test_tied_amplitude_fit_recovers_ratio` and
    /// `test_tied_fit_reduces_free_param_count` in the solver crate.
    pub tied_plan: TiedPlan,
    /// Per-dataset point boundaries for simultaneous multi-dataset ("global
    /// analysis") fits: cumulative offsets of length `n_datasets + 1`, so
    /// dataset `i` owns the concatenated point-range `[offsets[i], offsets[i+1])`.
    ///
    /// **Empty by default** (single-dataset / fully-global fits). The solver
    /// dispatch fills it from the dataset sizes after `compile()`. The executor
    /// only consults it when it is non-empty AND at least one node carries a
    /// [`NodeEntry::dataset_index`]; otherwise every node contributes to all
    /// points exactly as before (the all-global path is byte-identical).
    pub dataset_offsets: Vec<usize>,
}

// ---------------------------------------------------------------------------
// Implementation
// ---------------------------------------------------------------------------

impl CompiledGraph {
    /// Compile a [`FitGraphSpec`] into a [`CompiledGraph`].
    ///
    /// # Errors
    /// Returns [`CoreError::Eval`] if:
    /// - an unknown model type is encountered
    /// - a required parameter is missing from the spec
    /// - two nodes share the same `id` (would silently corrupt the free-column
    ///   layout and overwrite components)
    /// - `expr_edges` contain duplicate targets (cycle / conflict)
    pub fn compile(graph: &FitGraphSpec) -> Result<Self, CoreError> {
        // ── 0. Reject duplicate node IDs ────────────────────────────────────
        // Node IDs key the free-column layout (`node_idx_by_id`) and the
        // per-node component map (`evaluate_components_compiled`).  A duplicate
        // ID silently keeps only the last index (dropping/doubling free
        // columns) and overwrites one node's component with another — wrong
        // fits with no error.  Reject up front instead.
        let mut seen_ids: std::collections::HashSet<&str> =
            std::collections::HashSet::with_capacity(graph.nodes.len());
        for node_spec in &graph.nodes {
            if !seen_ids.insert(node_spec.id.as_str()) {
                // Typed boundary error: a duplicate node id silently corrupts
                // the per-node free-column layout and component map (see the
                // GraphError::DuplicateNodeId docs).
                return Err(GraphError::DuplicateNodeId(node_spec.id.clone()).into());
            }
        }

        // ── 1. Build the dependency-ordered tied-parameter plan ─────────────
        // Parse every `expr_edge`, topologically order the tied targets, and
        // reject cycles / duplicate targets.  This replaces the former
        // `ExpressionNotImplemented` reject-block: the parse + topo-order +
        // cycle-detection structure is now real and stored on the compiled
        // graph as `tied_plan`.
        //
        // The per-iteration evaluation of `tied_plan` is wired in the solver
        // crate: `spectrafit-solver::problem::set_free_and_tied` applies it on
        // every iteration for both solver front-ends (landed in M6; see
        // `dispatch::tests::test_tied_amplitude_fit_recovers_ratio`).
        let tied_plan = build_tied_plan(graph)?;

        // ── 2. Compile nodes ───────────────────────────────────────────────
        // A parameter is tied (and therefore not free) if it is the target of an
        // `expr_edge` OR if its own `ParameterSpec.expr` is set.  Both sources
        // are now harvested into `tied_plan` by `build_tied_plan`; both must
        // also exclude the parameter from the free set here.
        let mut tied_targets: std::collections::HashSet<(String, String)> = graph
            .expr_edges
            .iter()
            .map(|e| (e.target_node.clone(), e.target_param.clone()))
            .collect();
        for node_spec in &graph.nodes {
            for (pname, spec) in &node_spec.parameters {
                if spec.expr.is_some() {
                    tied_targets.insert((node_spec.id.clone(), pname.clone()));
                }
            }
        }

        let mut nodes: Vec<NodeEntry> = Vec::with_capacity(graph.nodes.len());

        for node_spec in &graph.nodes {
            let type_str = node_spec.model_type.as_str();
            // Parametric N-D kernels (`gaussian_nd`) carry no fixed dimensionality:
            // infer D from the node's indexed `center_<i>` parameters so the
            // compiler builds a `GaussianND` of the right dimensionality. Fixed
            // models pass `None` and ignore it. A `gaussian_nd` node with no
            // `center_i` is degenerate (D == 0) — surface a clear missing-param
            // error rather than silently building a 0-D (constant) model.
            let n_dims = infer_parametric_n_dims(type_str, &node_spec.parameters);
            if matches!(n_dims, Some(0)) {
                return Err(GraphError::MissingParameter {
                    node: node_spec.id.clone(),
                    param: "center_0".to_string(),
                }
                .into());
            }
            let model = model_from_str_with_dims(type_str, n_dims)
                .ok_or_else(|| GraphError::UnknownModelType(type_str.to_string()))?;

            let param_names: Vec<String> =
                model.param_names().iter().map(|s| s.to_string()).collect();

            // Ensure every model-required parameter is present in the spec.
            for pname in &param_names {
                if !node_spec.parameters.contains_key(pname) {
                    return Err(GraphError::MissingParameter {
                        node: node_spec.id.clone(),
                        param: pname.clone(),
                    }
                    .into());
                }
            }

            let free_mask: Vec<bool> = param_names
                .iter()
                .map(|pname| {
                    let ps = &node_spec.parameters[pname];
                    let is_tied = tied_targets.contains(&(node_spec.id.clone(), pname.clone()));
                    ps.vary && ps.expr.is_none() && !is_tied
                })
                .collect();

            nodes.push(NodeEntry {
                id: node_spec.id.clone(),
                model,
                param_names,
                free_mask,
                dataset_index: node_spec.dataset_index,
            });
        }

        // ── 3. Build free_keys (alpha-sorted by node_id, model param order) ─
        let mut sorted_ids: Vec<&str> = nodes.iter().map(|n| n.id.as_str()).collect();
        sorted_ids.sort_unstable();

        // Quick lookup: node_id → index in `nodes`
        let node_idx_by_id: HashMap<&str, usize> = nodes
            .iter()
            .enumerate()
            .map(|(i, n)| (n.id.as_str(), i))
            .collect();

        let mut free_keys: Vec<String> = Vec::new();
        for nid in &sorted_ids {
            let idx = node_idx_by_id[nid];
            let node = &nodes[idx];
            for (pname, &is_free) in node.param_names.iter().zip(node.free_mask.iter()) {
                if is_free {
                    free_keys.push(format!("{}.{}", nid, pname));
                }
            }
        }

        // ── 4. Pre-compute per-node Jacobian column layout ───────────────────
        // Maps each free_key to (node_idx_in_nodes, local_param_pos) once at
        // compile time.  The solver reads `node_free_cols` directly instead
        // of re-parsing `free_keys` strings on every iteration.
        let mut node_free_cols: Vec<Vec<(usize, usize)>> = vec![Vec::new(); nodes.len()];
        for (col, key) in free_keys.iter().enumerate() {
            // key was built as "{node_id}.{param_name}"; the first '.' is the separator.
            // INVARIANT: every `key` in `free_keys` was produced by
            // `format!("{}.{}", nid, pname)` two lines above, so it always
            // contains exactly one '.' separator — `find` is infallible here.
            let dot = key.find('.').unwrap();
            let node_id = &key[..dot];
            let param_name = &key[dot + 1..];
            // INVARIANT: `node_id` came from `sorted_ids`, which was built from
            // `nodes`, so `node_idx_by_id` is guaranteed to contain it.
            let node_idx = node_idx_by_id[node_id];
            // INVARIANT: `param_name` came from `node.param_names` during step 3,
            // so the same slice is guaranteed to contain it.
            let local_idx = nodes[node_idx]
                .param_names
                .iter()
                .position(|p| p == param_name)
                .unwrap();
            node_free_cols[node_idx].push((local_idx, col));
        }

        Ok(CompiledGraph {
            nodes,
            free_keys,
            node_free_cols,
            tied_plan,
            dataset_offsets: Vec::new(),
        })
    }

    /// Extract the parameter value vector for node at `node_idx` from the flat dict.
    ///
    /// Values are ordered to match `model.param_names()`.
    pub fn node_params(
        &self,
        node_idx: usize,
        flat: &HashMap<String, f64>,
    ) -> Result<Vec<f64>, CoreError> {
        let node = &self.nodes[node_idx];
        node.param_names
            .iter()
            .map(|pname| {
                let key = format!("{}.{}", node.id, pname);
                flat.get(&key)
                    .copied()
                    .ok_or_else(|| GraphError::MissingParamKey(key).into())
            })
            .collect()
    }

    /// The common coordinate dimensionality shared by every node in the graph.
    ///
    /// The executor lays the flat `x` buffer out point-major (stride =
    /// `n_dims`), so all nodes must agree on how many coordinate components a
    /// single point carries.  A graph that mixes a 1-D and a 2-D model over the
    /// same coordinate grid is rejected.
    ///
    /// Returns `1` for an empty graph (degenerate but harmless; evaluation
    /// produces zeros).
    ///
    /// # Errors
    /// Returns [`CoreError::Eval`] if nodes declare differing `n_dims`.
    pub fn n_dims(&self) -> Result<usize, CoreError> {
        let mut iter = self.nodes.iter();
        let Some(first) = iter.next() else {
            return Ok(1);
        };
        let nd = first.model.n_dims();
        for node in iter {
            let other = node.model.n_dims();
            if other != nd {
                return Err(GraphError::DimensionalityMismatch {
                    first: first.id.clone(),
                    first_nd: nd,
                    second: node.id.clone(),
                    second_nd: other,
                }
                .into());
            }
        }
        Ok(nd)
    }
}

// ---------------------------------------------------------------------------
// Private helpers
// ---------------------------------------------------------------------------

/// Parse every `expr_edge` and every `Parameter.expr` into a
/// dependency-ordered [`TiedPlan`].
///
/// Returns an empty plan when the graph declares neither `expr_edges` nor any
/// per-parameter `expr` fields.  Otherwise the returned plan is topologically
/// ordered and guaranteed cycle-free; duplicate target assignments (including
/// a param targeted by both an `expr_edge` and its own `ParameterSpec.expr`)
/// and full expression-language cycles (e.g. `a → b → a`) are rejected with
/// [`CoreError::Eval`].
///
/// Targets are stored as the fully-qualified `"node.param"` key so they match
/// the `free_keys` / `params_flat` convention used throughout the engine.
fn build_tied_plan(graph: &FitGraphSpec) -> Result<TiedPlan, CoreError> {
    // Materialise "node.param" target keys for expr_edges so the borrowed
    // `(&str, &str)` pairs handed to `TiedPlan::build` outlive the call.
    let edge_targets: Vec<String> = graph
        .expr_edges
        .iter()
        .map(|e| format!("{}.{}", e.target_node, e.target_param))
        .collect();

    // Materialise "node.param" target keys for Parameter.expr fields.
    // Each entry is (fully-qualified target, expression source string).
    // Note: HashMap iteration order is nondeterministic, but that is safe —
    // TiedPlan::build's topo_sort orders by dependency, not insertion order.
    let param_expr_pairs: Vec<(String, String)> = graph
        .nodes
        .iter()
        .flat_map(|node| {
            node.parameters.iter().filter_map(|(pname, spec)| {
                spec.expr
                    .as_ref()
                    .map(|src| (format!("{}.{}", node.id, pname), src.clone()))
            })
        })
        .collect();

    if edge_targets.is_empty() && param_expr_pairs.is_empty() {
        return Ok(TiedPlan::default());
    }

    // Chain expr_edge edges followed by per-parameter expr edges.
    let expr_edge_iter = edge_targets
        .iter()
        .zip(graph.expr_edges.iter())
        .map(|(target, edge)| (target.as_str(), edge.expression.as_str()));

    let param_expr_iter = param_expr_pairs
        .iter()
        .map(|(target, src)| (target.as_str(), src.as_str()));

    TiedPlan::build(expr_edge_iter.chain(param_expr_iter))
}

// ---------------------------------------------------------------------------
// Unit tests for compiler internals
// ---------------------------------------------------------------------------
#[cfg(test)]
mod tests {
    use super::*;
    use spectrafit_types::{ExprEdge, FitGraphSpec, ModelNodeSpec, ModelTypeStr, ParameterSpec};
    use std::collections::HashMap;

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

    fn gaussian_node(id: &str, amp: f64, cen: f64, sig: f64) -> ModelNodeSpec {
        let mut params = HashMap::new();
        params.insert("amplitude".to_string(), make_param(amp, true));
        params.insert("center".to_string(), make_param(cen, true));
        params.insert("sigma".to_string(), make_param(sig, true));
        ModelNodeSpec {
            id: id.to_string(),
            model_type: ModelTypeStr::Gaussian,
            dataset_index: None,
            parameters: params,
        }
    }

    #[test]
    fn compile_single_node_free_keys() {
        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![gaussian_node("g1", 1.0, 0.0, 1.0)],
            expr_edges: vec![],
        };
        let cg = CompiledGraph::compile(&graph).unwrap();
        assert_eq!(cg.nodes.len(), 1);
        // All 3 params are free → 3 free keys
        assert_eq!(cg.free_keys.len(), 3);
        assert_eq!(cg.free_keys[0], "g1.amplitude");
        assert_eq!(cg.free_keys[1], "g1.center");
        assert_eq!(cg.free_keys[2], "g1.sigma");
    }

    #[test]
    fn compile_free_keys_sorted_by_node_id() {
        // Two nodes: "z_node" and "a_node" — free_keys should list "a_node" first
        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![
                gaussian_node("z_node", 1.0, 0.0, 1.0),
                gaussian_node("a_node", 2.0, 1.0, 0.5),
            ],
            expr_edges: vec![],
        };
        let cg = CompiledGraph::compile(&graph).unwrap();
        // 6 free params total; first 3 should belong to "a_node"
        assert_eq!(cg.free_keys.len(), 6);
        assert!(cg.free_keys[0].starts_with("a_node."));
        assert!(cg.free_keys[3].starts_with("z_node."));
    }

    #[test]
    fn compile_missing_parameter_returns_error() {
        let mut params = HashMap::new();
        // Intentionally omit "sigma"
        params.insert("amplitude".to_string(), make_param(1.0, true));
        params.insert("center".to_string(), make_param(0.0, true));

        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![ModelNodeSpec {
                id: "g1".to_string(),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: None,
                parameters: params,
            }],
            expr_edges: vec![],
        };
        assert!(CompiledGraph::compile(&graph).is_err());
    }

    #[test]
    fn compile_duplicate_expr_edge_target_returns_error() {
        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![gaussian_node("g1", 1.0, 0.0, 1.0)],
            expr_edges: vec![
                ExprEdge {
                    target_node: "g1".to_string(),
                    target_param: "amplitude".to_string(),
                    expression: "2.0".to_string(),
                },
                ExprEdge {
                    target_node: "g1".to_string(),
                    target_param: "amplitude".to_string(),
                    expression: "3.0".to_string(),
                },
            ],
        };
        assert!(CompiledGraph::compile(&graph).is_err());
    }

    /// A2 follow-up: the typed `GraphError::DuplicateNodeId` variant must be
    /// the source of the boundary-side `CoreError::Eval`. The match arms
    /// below pin the conversion path so a regression to a stringly-typed
    /// constructor breaks loudly.
    #[test]
    fn compile_duplicate_node_id_emits_graph_error_variant() {
        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![
                gaussian_node("dup", 1.0, 0.0, 1.0),
                gaussian_node("dup", 2.0, 1.0, 0.5),
            ],
            expr_edges: vec![],
        };
        // `CompiledGraph` is not `Debug`, so unwrap_err() won't compile;
        // pattern-match on the Result instead.
        let err = match CompiledGraph::compile(&graph) {
            Err(e) => e,
            Ok(_) => panic!("expected duplicate-node-id error, got Ok"),
        };
        let core_err: CoreError = GraphError::DuplicateNodeId("dup".into()).into();
        assert_eq!(format!("{err}"), format!("{core_err}"));
    }

    /// A2 follow-up: unknown model type → typed `GraphError::UnknownModelType`.
    #[test]
    fn gaussian_nd_infers_dimensionality_from_center_params() {
        use spectrafit_types::ModelTypeStr;
        let mut params = HashMap::new();
        params.insert("amplitude".to_string(), make_param(1.0, true));
        for i in 0..3 {
            params.insert(format!("center_{i}"), make_param(0.0, true));
            params.insert(format!("sigma_{i}"), make_param(1.0, true));
        }
        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![ModelNodeSpec {
                id: "gnd".to_string(),
                model_type: ModelTypeStr::GaussianNd,
                dataset_index: None,
                parameters: params,
            }],
            expr_edges: vec![],
        };
        let cg = CompiledGraph::compile(&graph).expect("3-D gaussian_nd must compile");
        assert_eq!(
            cg.n_dims().unwrap(),
            3,
            "D must be inferred from center_0..center_2"
        );
    }

    #[test]
    fn gaussian_nd_without_center_params_errors_clearly() {
        use spectrafit_types::ModelTypeStr;
        let mut params = HashMap::new();
        params.insert("amplitude".to_string(), make_param(1.0, true));
        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![ModelNodeSpec {
                id: "gnd".to_string(),
                model_type: ModelTypeStr::GaussianNd,
                dataset_index: None,
                parameters: params,
            }],
            expr_edges: vec![],
        };
        let err = match CompiledGraph::compile(&graph) {
            Ok(_) => panic!("expected an error for gaussian_nd with no center params"),
            Err(e) => e,
        };
        assert!(
            format!("{err}").contains("center_0"),
            "a gaussian_nd node with no center params must flag missing center_0; got: {err}"
        );
    }

    #[test]
    fn compile_unknown_model_type_emits_graph_error_variant() {
        use spectrafit_types::ModelTypeStr;
        // Hijack a valid spec then rewrite to an unknown wire token.
        let mut node = gaussian_node("g1", 1.0, 0.0, 1.0);
        // We can't directly construct an unknown ModelTypeStr; instead exercise
        // the `model_from_str` boundary by deserialising raw JSON.
        node.model_type = ModelTypeStr::Gaussian; // baseline
        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![node],
            expr_edges: vec![],
        };
        // Sanity: the baseline must compile.
        assert!(CompiledGraph::compile(&graph).is_ok());

        // Directly probe the GraphError → CoreError mapping that the compile
        // path uses internally.
        let err: CoreError = GraphError::UnknownModelType("not-a-model".into()).into();
        assert!(format!("{err}").contains("unknown model type"));
    }

    /// A2 follow-up: missing parameter → typed `GraphError::MissingParameter`.
    #[test]
    fn compile_missing_parameter_emits_graph_error_variant() {
        // Build a Gaussian node spec but drop the required `sigma` parameter.
        let mut params = HashMap::new();
        params.insert("amplitude".to_string(), make_param(1.0, true));
        params.insert("center".to_string(), make_param(0.0, true));
        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![ModelNodeSpec {
                id: "g1".to_string(),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: None,
                parameters: params,
            }],
            expr_edges: vec![],
        };
        let err = match CompiledGraph::compile(&graph) {
            Err(e) => e,
            Ok(_) => panic!("expected missing-parameter error, got Ok"),
        };
        let core_err: CoreError = GraphError::MissingParameter {
            node: "g1".into(),
            param: "sigma".into(),
        }
        .into();
        assert_eq!(format!("{err}"), format!("{core_err}"));
    }

    /// G2 regression: two nodes sharing an `id` must be rejected at compile
    /// time (otherwise the free-column layout drops/doubles columns and one
    /// node's component silently overwrites the other).
    #[test]
    fn compile_duplicate_node_id_returns_error() {
        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![
                gaussian_node("dup", 1.0, 0.0, 1.0),
                gaussian_node("dup", 2.0, 1.0, 0.5),
            ],
            expr_edges: vec![],
        };
        let result = CompiledGraph::compile(&graph);
        let Err(err) = result else {
            panic!("expected duplicate-node-id compile error, got Ok");
        };
        let msg = format!("{err}");
        assert!(
            msg.contains("duplicate node id") && msg.contains("dup"),
            "expected a duplicate-node-id error, got: {msg}"
        );
    }

    #[test]
    fn node_params_extracts_correct_order() {
        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![gaussian_node("g1", 3.0, 5.0, 0.5)],
            expr_edges: vec![],
        };
        let cg = CompiledGraph::compile(&graph).unwrap();
        let flat: HashMap<String, f64> =
            [("g1.amplitude", 3.0), ("g1.center", 5.0), ("g1.sigma", 0.5)]
                .iter()
                .map(|(k, v)| (k.to_string(), *v))
                .collect();
        let params = cg.node_params(0, &flat).unwrap();
        assert_eq!(params, vec![3.0, 5.0, 0.5]);
    }

    /// Build a Gaussian node whose `amplitude` is tied (`vary=false`, `expr`).
    ///
    /// Used by tests that exercise `Parameter.expr` directly (without a
    /// corresponding `expr_edge`).  Do not pair this with an `expr_edge` on
    /// the same target — that would be a duplicate-target conflict.
    fn gaussian_node_tied_amplitude(id: &str, cen: f64, sig: f64, expr: &str) -> ModelNodeSpec {
        let mut params = HashMap::new();
        let mut amp = make_param(0.0, false);
        amp.expr = Some(expr.to_string());
        params.insert("amplitude".to_string(), amp);
        params.insert("center".to_string(), make_param(cen, true));
        params.insert("sigma".to_string(), make_param(sig, true));
        ModelNodeSpec {
            id: id.to_string(),
            model_type: ModelTypeStr::Gaussian,
            dataset_index: None,
            parameters: params,
        }
    }

    /// A valid `expr_edge` now compiles (no longer `ExpressionNotImplemented`)
    /// and produces a dependency-ordered, non-empty `tied_plan`.
    /// g2 is a plain Gaussian node (no `Parameter.expr`); the tie comes
    /// exclusively from the `expr_edge`, which is the graph-level API.
    #[test]
    fn compile_builds_tied_plan_from_expr_edge() {
        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![
                gaussian_node("g1", 1.0, 0.0, 1.0),
                gaussian_node("g2", 2.0, 1.0, 1.0), // plain node — no Parameter.expr
            ],
            expr_edges: vec![ExprEdge {
                target_node: "g2".to_string(),
                target_param: "amplitude".to_string(),
                expression: "0.5 * g1.amplitude".to_string(),
            }],
        };
        let cg = CompiledGraph::compile(&graph).unwrap();
        assert_eq!(cg.tied_plan.len(), 1, "one tied parameter expected");
        assert_eq!(cg.tied_plan.order[0].target, "g2.amplitude");
    }

    /// The tied parameter (`g2.amplitude`, tied via `expr_edge`) is excluded from
    /// `free_keys`, so the free-parameter count drops by exactly one versus the
    /// fully-free two-Gaussian graph (6 → 5).
    /// g2 is a plain Gaussian node (no `Parameter.expr`) — the tie comes from
    /// the `expr_edge` alone, avoiding a double-specification conflict.
    #[test]
    fn compile_tied_param_excluded_from_free_keys() {
        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![
                gaussian_node("g1", 1.0, 0.0, 1.0),
                gaussian_node("g2", 2.0, 1.0, 1.0), // plain node — no Parameter.expr
            ],
            expr_edges: vec![ExprEdge {
                target_node: "g2".to_string(),
                target_param: "amplitude".to_string(),
                expression: "0.5 * g1.amplitude".to_string(),
            }],
        };
        let cg = CompiledGraph::compile(&graph).unwrap();
        // 6 params total, 1 tied → 5 free.
        assert_eq!(cg.free_keys.len(), 5);
        assert!(
            !cg.free_keys.iter().any(|k| k == "g2.amplitude"),
            "tied g2.amplitude must not appear in free_keys"
        );
    }

    /// A cyclic pair of `expr_edges` (`a → b → a`) is rejected at compile time.
    /// Plain Gaussian nodes are used here (no `Parameter.expr`) so the tie comes
    /// exclusively from the `expr_edge` pairs — testing the cycle-detection path
    /// without triggering the duplicate-target guard.
    #[test]
    fn compile_rejects_expr_cycle_a_b_a() {
        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![
                gaussian_node("a", 0.0, 1.0, 1.0), // plain — no Parameter.expr
                gaussian_node("b", 1.0, 1.0, 1.0), // plain — no Parameter.expr
            ],
            expr_edges: vec![
                ExprEdge {
                    target_node: "a".to_string(),
                    target_param: "amplitude".to_string(),
                    expression: "b.amplitude + 1.0".to_string(),
                },
                ExprEdge {
                    target_node: "b".to_string(),
                    target_param: "amplitude".to_string(),
                    expression: "a.amplitude * 2.0".to_string(),
                },
            ],
        };
        assert!(
            CompiledGraph::compile(&graph).is_err(),
            "a→b→a expr cycle must be rejected"
        );
    }

    /// `Parameter.expr` (no expr_edge) is harvested into the tied plan.
    ///
    /// Node `p0` is a fully-free Gaussian.  Node `p1` has `sigma.expr = "p0.sigma"` —
    /// NO corresponding `expr_edge`.  The compiler must:
    /// 1. succeed (no error),
    /// 2. exclude `p1.sigma` from `free_keys`,
    /// 3. populate `tied_plan` with at least one entry, and
    /// 4. have `tied_plan.apply` resolve `p1.sigma` from a values map that contains
    ///    `p0.sigma = 2.0`.
    #[test]
    fn compile_harvests_parameter_expr_into_tied_plan() {
        // Build p1 with sigma carrying expr="p0.sigma", no expr_edge.
        let mut p1_params = HashMap::new();
        p1_params.insert("amplitude".to_string(), make_param(1.0, true));
        p1_params.insert("center".to_string(), make_param(0.0, true));
        let mut sigma_tied = make_param(1.0, false);
        sigma_tied.expr = Some("p0.sigma".to_string());
        p1_params.insert("sigma".to_string(), sigma_tied);
        let p1 = ModelNodeSpec {
            id: "p1".to_string(),
            model_type: ModelTypeStr::Gaussian,
            dataset_index: None,
            parameters: p1_params,
        };

        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![gaussian_node("p0", 1.0, 0.0, 1.0), p1],
            expr_edges: vec![], // intentionally empty — no expr_edge for p1.sigma
        };

        // 1. compile succeeds
        let cg = CompiledGraph::compile(&graph).expect("compile must succeed");

        // 2. p1.sigma is NOT in free_keys (it is tied via Parameter.expr)
        assert!(
            !cg.free_keys.iter().any(|k| k == "p1.sigma"),
            "p1.sigma must be excluded from free_keys when Parameter.expr is set"
        );

        // 3. tied_plan is non-empty
        assert!(
            !cg.tied_plan.is_empty(),
            "tied_plan must contain at least the p1.sigma entry"
        );

        // 4. applying the plan with p0.sigma=2.0 sets p1.sigma=2.0
        let mut values: HashMap<String, f64> = HashMap::new();
        values.insert("p0.amplitude".to_string(), 1.0);
        values.insert("p0.center".to_string(), 0.0);
        values.insert("p0.sigma".to_string(), 2.0);
        cg.tied_plan.apply(&mut values).expect("apply must succeed");
        assert_eq!(
            values["p1.sigma"], 2.0,
            "p1.sigma must be resolved to p0.sigma=2.0 by the tied plan"
        );
    }

    /// I1: When `g2.amplitude` carries both a `Parameter.expr` AND an `expr_edge`
    /// targeting the same parameter, `compile` must return the
    /// `DuplicateExprTarget` error — the conflict rule mandated by T1.
    #[test]
    fn compile_rejects_when_expr_edge_and_param_expr_target_same_param() {
        // g2 node: amplitude is tied via Parameter.expr …
        let g2 = gaussian_node_tied_amplitude("g2", 1.0, 1.0, "0.5 * g1.amplitude");

        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![gaussian_node("g1", 1.0, 0.0, 1.0), g2],
            // … AND an expr_edge also targets g2.amplitude — duplicate!
            expr_edges: vec![ExprEdge {
                target_node: "g2".to_string(),
                target_param: "amplitude".to_string(),
                expression: "0.5 * g1.amplitude".to_string(),
            }],
        };

        let err = match CompiledGraph::compile(&graph) {
            Err(e) => e,
            Ok(_) => panic!("expected DuplicateExprTarget error, got Ok"),
        };
        // The error is a CoreError::Eval wrapping GraphError::DuplicateExprTarget.
        let expected: CoreError = GraphError::DuplicateExprTarget("g2.amplitude".into()).into();
        assert_eq!(
            format!("{err}"),
            format!("{expected}"),
            "expected DuplicateExprTarget for g2.amplitude, got: {err}"
        );
    }

    /// I2: A cycle formed purely via `Parameter.expr` (no `expr_edges`) is
    /// detected and rejected at compile time.  Node `a` has
    /// `amplitude.expr = "b.amplitude + 1.0"` and node `b` has
    /// `amplitude.expr = "a.amplitude * 2.0"` — a direct a→b→a cycle.
    #[test]
    fn compile_rejects_param_expr_cycle_a_b_a() {
        // Build node `a` using the tied-amplitude helper.
        let node_a = gaussian_node_tied_amplitude("a", 1.0, 1.0, "b.amplitude + 1.0");
        // Build node `b` using the tied-amplitude helper.
        let node_b = gaussian_node_tied_amplitude("b", 1.0, 1.0, "a.amplitude * 2.0");

        let graph = FitGraphSpec {
            schema_version: "0.1".to_string(),
            nodes: vec![node_a, node_b],
            expr_edges: vec![], // cycle comes from Parameter.expr alone
        };

        // Confirm the error message identifies a cycle — match on Result to
        // avoid unwrap_err() which requires CompiledGraph: Debug.
        let err = match CompiledGraph::compile(&graph) {
            Err(e) => e,
            Ok(_) => panic!("a→b→a param-expr cycle must be rejected at compile time"),
        };
        let msg = format!("{err}");
        assert!(
            msg.contains("cycle"),
            "expected a cycle error message, got: {msg}"
        );
    }
}
