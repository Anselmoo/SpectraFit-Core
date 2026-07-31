//! Manual implementation of [`SeparableNonlinearModel`] backed by a compiled
//! spectrafit graph.
//!
//! # Model layout
//!
//! For a graph with `M` model nodes, each node contributes **one column** to the
//! basis-function matrix Φ (n_data × M).  For separable nodes the column is
//! evaluated at `amplitude = 1.0` (amplitude is the linear coefficient for the
//! varpro solve).
//!
//! The global nonlinear parameter vector α is the concatenation of each node's
//! non-amplitude, free parameters in graph-node order, then model-param order.
//! Fixed params are injected as constants; `amplitude` is excluded (it is a
//! linear coefficient solved by varpro, not part of α).
//!
//! # Invariant nodes
//! `constant` and `linear` nodes have no nonlinear parameters; their Φ column
//! is evaluated once at construction time and never changes.

use nalgebra::{DVector, Dyn, OMatrix, OVector};
use spectrafit_graph::compiler::CompiledGraph;
use spectrafit_models::Model;
use spectrafit_types::{FitGraphSpec, MeasurementSpec, ParameterSpec};
use std::collections::HashMap;
use varpro::model::errors::ModelError;
use varpro::model::SeparableNonlinearModel;

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/// Per-node parameter bookkeeping.
#[derive(Debug)]
struct NodeSpec {
    /// Full resolved param values (`amplitude` = initial value, nonlinear = initial).
    /// Mutated in `set_params` for the nonlinear params.
    param_values: Vec<f64>,
    /// For each param slot: `Some(alpha_idx)` if it is a free nonlinear param,
    /// `None` if it is the amplitude (linear) or a fixed param.
    alpha_indices: Vec<Option<usize>>,
    /// Whether the column is invariant (no nonlinear params — constant/linear).
    is_invariant: bool,
}

// ---------------------------------------------------------------------------
// GraphSeparableModel
// ---------------------------------------------------------------------------

/// Implements varpro's `SeparableNonlinearModel` trait for an arbitrary
/// separable spectrafit graph.
pub struct GraphSeparableModel {
    /// Boxed model kernels (one per node, in graph order).
    models: Vec<Box<dyn Model>>,
    /// Per-node parameter bookkeeping.
    node_specs: Vec<NodeSpec>,
    /// Flat x values (single 1-D dataset).
    x: Vec<f64>,
    /// Number of data points.
    n_data: usize,
    /// Current nonlinear parameters α.
    params: OVector<f64, Dyn>,
    /// Cached basis matrix Φ (n_data × n_basis).  Recomputed in `set_params`.
    phi: OMatrix<f64, Dyn, Dyn>,
    /// Names of alpha keys, for mapping results back.
    pub alpha_keys: Vec<String>,
}

impl GraphSeparableModel {
    /// Build from a compiled graph, one dataset, and the full parameter map.
    ///
    /// `all_params` maps `"node_id.param_name"` → [`ParameterSpec`].
    pub fn new(
        graph: &FitGraphSpec,
        dataset: &MeasurementSpec,
        all_params: &HashMap<String, ParameterSpec>,
    ) -> Result<Self, ModelError> {
        let compiled =
            CompiledGraph::compile(graph).map_err(|_| ModelError::ParameterNotInModel {
                parameter: "graph compilation failed".into(),
            })?;

        let x: Vec<f64> = dataset.x.first().cloned().unwrap_or_default();
        let n_data = x.len();
        let n_basis = compiled.nodes.len();

        // ── 1. Assign alpha indices ────────────────────────────────────────
        let mut alpha_keys: Vec<String> = Vec::new();
        let mut node_specs: Vec<NodeSpec> = Vec::new();

        for node_entry in &compiled.nodes {
            let model_type_str = graph
                .nodes
                .iter()
                .find(|n| n.id == node_entry.id)
                .map(|n| n.model_type.as_str())
                .unwrap_or("constant");

            let is_invariant = crate::INVARIANT_MODEL_TYPES.contains(&model_type_str);

            let mut param_values: Vec<f64> = Vec::new();
            let mut alpha_indices: Vec<Option<usize>> = Vec::new();

            for (i, pname) in node_entry.param_names.iter().enumerate() {
                let key = format!("{}.{}", node_entry.id, pname);
                let spec = all_params.get(&key);
                let value = spec.map(|s| s.value).unwrap_or(0.0);
                param_values.push(value);

                // i == 0 is amplitude for separable models (linear coeff, not in α).
                // For invariant models all params are linear — skip all.
                let is_amplitude = i == 0 && !is_invariant;
                let is_fixed = spec.map(|s| !s.vary).unwrap_or(true);

                if !is_amplitude && !is_fixed {
                    let idx = alpha_keys.len();
                    alpha_keys.push(key);
                    alpha_indices.push(Some(idx));
                } else {
                    alpha_indices.push(None);
                }
            }

            node_specs.push(NodeSpec {
                param_values,
                alpha_indices,
                is_invariant,
            });
        }

        // ── 2. Build initial α ─────────────────────────────────────────────
        let init_alpha: Vec<f64> = alpha_keys
            .iter()
            .map(|k| all_params.get(k).map(|s| s.value).unwrap_or(0.0))
            .collect();
        let params = OVector::<f64, Dyn>::from_vec(init_alpha);

        // ── 3. Allocate Φ ──────────────────────────────────────────────────
        let phi = OMatrix::<f64, Dyn, Dyn>::zeros(n_data, n_basis);

        // Extract models from compiled (moves out of compiled.nodes)
        let models: Vec<Box<dyn Model>> = compiled.nodes.into_iter().map(|n| n.model).collect();

        let mut model_obj = Self {
            models,
            node_specs,
            x,
            n_data,
            params: params.clone(),
            phi,
            alpha_keys,
        };
        // Fill cache with initial params (errors bubble up)
        model_obj.set_params(params)?;
        Ok(model_obj)
    }

    /// Compute basis column `j` from current α.
    fn eval_column(&self, j: usize) -> DVector<f64> {
        let spec = &self.node_specs[j];
        let model = &self.models[j];

        let mut pv = spec.param_values.clone();
        // Inject current α
        for (i, ai) in spec.alpha_indices.iter().enumerate() {
            if let Some(idx) = ai {
                pv[i] = self.params[*idx];
            }
        }
        // Amplitude (index 0) acts as the linear coefficient; set to 1 so the
        // column is the normalised shape (varpro solves for the amplitude).
        if !spec.is_invariant && !pv.is_empty() {
            pv[0] = 1.0;
        }
        DVector::from_iterator(self.n_data, self.x.iter().map(|&xi| model.eval(&[xi], &pv)))
    }

    /// Compute ∂(column j)/∂α[alpha_idx].
    fn deriv_column(&self, j: usize, alpha_idx: usize) -> DVector<f64> {
        let spec = &self.node_specs[j];
        let model = &self.models[j];

        // Which local param position corresponds to alpha_idx?
        let param_pos = spec
            .alpha_indices
            .iter()
            .position(|ai| *ai == Some(alpha_idx));
        let Some(param_pos) = param_pos else {
            return DVector::zeros(self.n_data);
        };

        let mut pv = spec.param_values.clone();
        for (i, ai) in spec.alpha_indices.iter().enumerate() {
            if let Some(idx) = ai {
                pv[i] = self.params[*idx];
            }
        }
        if !spec.is_invariant && !pv.is_empty() {
            pv[0] = 1.0;
        }
        // model.jacobian returns one derivative per param in the order of param_names
        DVector::from_iterator(
            self.n_data,
            self.x.iter().map(|&xi| {
                let jac = model.jacobian(&[xi], &pv);
                jac[param_pos]
            }),
        )
    }
}

// ---------------------------------------------------------------------------
// Manual Debug impl (models are Box<dyn Model> which doesn't derive Debug)
// ---------------------------------------------------------------------------

impl std::fmt::Debug for GraphSeparableModel {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("GraphSeparableModel")
            .field("n_data", &self.n_data)
            .field("n_basis", &self.models.len())
            .field("n_alpha", &self.params.len())
            .finish()
    }
}

// ---------------------------------------------------------------------------
// SeparableNonlinearModel impl
// ---------------------------------------------------------------------------

impl SeparableNonlinearModel for GraphSeparableModel {
    type ScalarType = f64;
    type Error = ModelError;

    fn parameter_count(&self) -> usize {
        self.params.len()
    }

    fn base_function_count(&self) -> usize {
        self.models.len()
    }

    fn output_len(&self) -> usize {
        self.n_data
    }

    fn set_params(&mut self, parameters: OVector<f64, Dyn>) -> Result<(), Self::Error> {
        if parameters.len() != self.params.len() {
            return Err(ModelError::IncorrectParameterCount {
                expected: self.params.len(),
                actual: parameters.len(),
            });
        }
        self.params = parameters;
        for j in 0..self.models.len() {
            let col = self.eval_column(j);
            self.phi.set_column(j, &col);
        }
        Ok(())
    }

    fn params(&self) -> OVector<f64, Dyn> {
        self.params.clone()
    }

    fn eval(&self) -> Result<OMatrix<f64, Dyn, Dyn>, Self::Error> {
        Ok(self.phi.clone())
    }

    fn eval_partial_deriv(
        &self,
        derivative_index: usize,
    ) -> Result<OMatrix<f64, Dyn, Dyn>, Self::Error> {
        if derivative_index >= self.params.len() {
            return Err(ModelError::DerivativeIndexOutOfBounds {
                index: derivative_index,
            });
        }
        let n_basis = self.models.len();
        let mut dphi = OMatrix::<f64, Dyn, Dyn>::zeros(self.n_data, n_basis);
        for j in 0..n_basis {
            let col = self.deriv_column(j, derivative_index);
            dphi.set_column(j, &col);
        }
        Ok(dphi)
    }
}
