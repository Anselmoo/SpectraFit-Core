"""spectrafit backend — the subject under test (the Rust kernel via spectrafit_core).

Times the solve via ``fit_fast`` (compact path) so per-point array serialization
never inflates the timing, and surfaces the real per-iteration convergence history
the faer drivers now record. Model dispatch goes through the shared registry
(:mod:`oracles.models`) — no per-backend model map.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from oracles.backends._base import Backend, BackendOutcome
from oracles.cases import BenchCase
from oracles.models import get_model

# κ(J) cap — mirrors _scipy_ls._KAPPA_CAP so both backends share the same axis.
# Anything beyond this is reported as 1e16 to keep downstream aggregations
# (geomean, ratios, plots) from being contaminated by inf.
_KAPPA_CAP = 1e16


def _jacobian_kappa(condition_number: float | None) -> float | None:
    """Convert Rust's κ(JᵀJ) to κ(J) for the benchmark axis.

    The Rust kernel records the *Gram* condition number κ(JᵀJ) = κ(J)².
    scipy's ``np.linalg.cond(jac)`` returns κ(J) directly, so to put both
    backends on the same axis we take the square root here.

    Returns ``None`` for ``None``, negative, non-finite, or imaginary inputs.
    The result is capped at ``_KAPPA_CAP`` (1e16) to protect downstream
    aggregations from ``inf`` contamination.
    """
    if condition_number is None:
        return None
    if not math.isfinite(condition_number) or condition_number < 0.0:
        return None
    kappa = math.sqrt(condition_number)
    return min(kappa, _KAPPA_CAP)


def _param(value: float, name: str) -> Any:
    """Build a spectrafit Parameter with name-appropriate bounds."""
    from spectrafit_core import Parameter

    match name:
        case "sigma" | "gamma":
            return Parameter(value=value, min=1e-6)
        case "fraction":
            return Parameter(value=value, min=0.0, max=1.0)
        case _:
            return Parameter(value=value)


class SpectraFitBackend(Backend):
    """Fit a case with the spectrafit Rust kernel."""

    name = "spectrafit"

    def build(self, case: BenchCase) -> Any:
        """Build (FitGraph, MeasurementData, FitOptions) from the case guess."""
        from spectrafit_core import (
            ExprEdge,
            FitGraph,
            FitOptions,
            MeasurementData,
            ModelNodeSpec,
            ModelType,
            Parameter,
        )

        # Fixed param names per node index: {"p0": ["center"]} → {0: ["center"]}
        fixed_by_node: dict[str, list[str]] = case.spec.fixed_params

        nodes = []
        for i, comp in enumerate(case.comp_guess):
            pm = get_model(comp.model)
            mt = getattr(ModelType, pm.spectrafit_type)
            cp = comp.to_params()
            fixed_names = fixed_by_node.get(f"p{i}", [])
            parameters: dict[str, Any] = {}
            for n in pm.param_names:
                val = float(cp[n])
                if n in fixed_names:
                    parameters[n] = Parameter(value=val, vary=False)
                else:
                    parameters[n] = _param(val, n)
            nodes.append(
                ModelNodeSpec(
                    id=f"p{i}",
                    model_type=mt,
                    parameters=parameters,
                )
            )

        # Materialise expr_edges from the case spec into typed ExprEdge objects.
        expr_edges = [
            ExprEdge(
                target_node=e["target_node"],
                target_param=e["target_param"],
                expression=e["expression"],
            )
            for e in case.spec.expr_edges
        ]

        graph = FitGraph(nodes=nodes, expr_edges=expr_edges)
        data = MeasurementData(x=case.x.tolist(), y=case.y.tolist())
        match case.solver_hint:
            case "global":
                max_iter = 500
            case _:
                max_iter = 2000
        options = FitOptions(solver=case.solver_hint, max_iterations=max_iter)
        return graph, data, options

    def run(self, model: Any, case: BenchCase) -> Any:
        """Run the timed solve via ``fit_fast`` (compact, returns best_fit array)."""
        from spectrafit_core import fit_fast

        graph, data, options = model
        return fit_fast(graph, data, options)

    def extract(self, raw: Any, case: BenchCase) -> BackendOutcome:
        """Map (FitResult, best_fit) to a normalized outcome."""
        result, best_fit = raw
        # result.dof = n_data − n_free_params (from Rust); clamp to ≥ 1.
        fit_dof = max(int(result.dof), 1)
        return BackendOutcome(
            backend=self.name,
            success=bool(result.success),
            r2=float(result.r_squared),
            chi2=float(result.chi2),
            reduced_chi2=float(result.reduced_chi2),
            aic=float(result.aic),
            bic=float(result.bic),
            n_iter=int(result.n_iter),
            params={k: v.value for k, v in result.parameters.items()},
            param_stderr={k: v.stderr for k, v in result.parameters.items()},
            best_fit=np.asarray(best_fit, dtype=float),
            cost_history=list(result.cost_history),
            gradient_norm_history=list(result.gradient_norm_history),
            history_source="real" if result.cost_history else "reconstructed",
            params_history=[list(theta) for theta in result.params_history],
            params_param_order=list(result.covariance_param_order or []),
            # Rust emits κ(JᵀJ) = κ(J)²; take √ to match scipy's κ(J) axis.
            jacobian_condition_number=_jacobian_kappa(result.condition_number),
            fit_dof=fit_dof,
        )
