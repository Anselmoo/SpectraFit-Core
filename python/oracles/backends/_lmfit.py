"""lmfit oracle — independent cross-verification of the spectrafit fit.

Builds composite ``lmfit.Model`` directly from the shared model registry's numpy
formula (whose named params lmfit introspects), so both backends fit identical
data with the same peak-height convention. lmfit exposes no per-iteration trace,
so the convergence history is a labelled reconstructed proxy.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np

from oracles.backends._base import (
    Backend,
    BackendOutcome,
    r2_score,
    reconstruct_history,
)
from oracles.cases import BenchCase
from oracles.models import get_model

# Finite bounds for the long-tail shape parameters lmfit's LM search can otherwise
# drive into the model function's overflow/NaN region (e.g. pearson7 ``m → 0⁺`` makes
# ``2^{1/m}`` overflow → NaN → lmfit aborts). The truth-side generators in
# ``cases.py`` draw from much narrower ranges; these envelopes are ~10× wider so the
# oracle stays independent (lmfit can still disagree with spectrafit) but cannot reach
# a numerically degenerate corner. Keyed by lmfit param suffix (``p{i}_<suffix>``).
_SHAPE_BOUNDS: dict[str, tuple[float, float]] = {
    "m": (1.05, 50.0),  # pearson7 — m > 1 keeps the Lorentzian-Gaussian interp finite
    "m_l": (1.05, 50.0),  # split_pearson7 left exponent
    "m_r": (1.05, 50.0),  # split_pearson7 right exponent
    "beta": (0.1, 50.0),  # moffat tail weight
    "nu": (0.5, 200.0),  # students_t degrees of freedom
    "q": (-100.0, 100.0),  # fano / breit_wigner asymmetry
    "k": (-50.0, 50.0),  # asym_ir logistic sharpness
}


class LmfitBackend(Backend):
    """Fit a case with lmfit (composite Models from the registry formula)."""

    name = "lmfit"

    def __init__(self) -> None:
        import lmfit  # noqa: F401  (import-time availability check)

    def build(self, case: BenchCase) -> Any:
        """Build (composite model, params, x, y) from the case components."""
        import lmfit

        de = case.solver_hint == "global"
        lo, hi = float(case.x.min()), float(case.x.max())
        amax = float(np.max(np.abs(case.y))) * 5.0 + 1.0
        smax = hi - lo

        # Fixed param names per lmfit prefix: "p0_center" for {"p0": ["center"]}.
        fixed_by_node: dict[str, list[str]] = case.spec.fixed_params

        composite = None
        params = None
        for i, comp in enumerate(case.comp_guess):
            pm = get_model(comp.model)
            m = lmfit.Model(pm.evaluate, prefix=f"p{i}_")
            composite = m if composite is None else composite + m
            cp = comp.to_params()
            # Fall back to PeakModel.extra_defaults for any param absent from the
            # case-spec guess (e.g. ``fraction`` on pseudo_voigt when only
            # amplitude/center/sigma are supplied). Explicit case-spec values always
            # win; extra_defaults are the last resort so lmfit never sees an
            # uninitialised parameter.
            pars = m.make_params(
                **{
                    n: float(cp[n]) if n in cp else float(pm.extra_defaults[n])
                    for n in pm.param_names
                }
            )
            names = pm.param_names
            fixed_names = fixed_by_node.get(f"p{i}", [])
            # differential_evolution (global) needs finite bounds on every varying
            # param; spectrafit derives these internally, so both search a comparable box.
            if de:
                if "amplitude" in names:
                    pars[f"p{i}_amplitude"].set(min=0.0, max=amax)
                if "center" in names:
                    pars[f"p{i}_center"].set(min=lo, max=hi)
                if "sigma" in names:
                    pars[f"p{i}_sigma"].set(min=1e-3, max=smax)
            else:
                for w in ("sigma", "gamma"):
                    if w in names:
                        pars[f"p{i}_{w}"].set(min=1e-6)
                for w, (lo_b, hi_b) in _SHAPE_BOUNDS.items():
                    if w in names:
                        pars[f"p{i}_{w}"].set(min=lo_b, max=hi_b)
            if "fraction" in names:
                pars[f"p{i}_fraction"].set(min=0.0, max=1.0)
            # Apply fixed parameters (vary=False).
            for pname in fixed_names:
                lmfit_key = f"p{i}_{pname}"
                if lmfit_key in pars:
                    pars[lmfit_key].set(vary=False)
            params = pars if params is None else params.update(pars) or params

        # Apply expr_edges as lmfit parameter expressions.
        # expr_edge: {"target_node": "p1", "target_param": "sigma",
        #             "expression": "p0.sigma"}
        # lmfit uses "p0_sigma" format (underscore prefix), so we translate dots.
        if params is not None:
            for edge in case.spec.expr_edges:
                lmfit_target = f"{edge['target_node']}_{edge['target_param']}"
                # Translate dotted node references to lmfit underscore prefixes.
                # "p0.sigma" → "p0_sigma"; "p0.center + 1.5" → "p0_center + 1.5"
                lmfit_expr = edge["expression"]
                lmfit_expr = re.sub(
                    r"\b(p\d+)\.(\w+)\b", r"\1_\2", lmfit_expr
                )
                if lmfit_target in params:
                    params[lmfit_target].set(expr=lmfit_expr)

        return composite, params, case.x, case.y

    def run(self, model: Any, case: BenchCase) -> Any:
        """Run the timed lmfit solve (DE for the multimodal optfn cases)."""
        composite, params, x, y = model
        match case.solver_hint:
            case "global":
                # Seed DE so the multimodal optfn results/timings are reproducible.
                return composite.fit(
                    y,
                    params,
                    x=x,
                    method="differential_evolution",
                    fit_kws={"seed": 0},
                )
            case _:
                return composite.fit(y, params, x=x)

    def extract(self, raw: Any, case: BenchCase) -> BackendOutcome:
        """Map an lmfit ModelResult to a normalized outcome."""
        result = raw
        best_fit = np.asarray(result.best_fit, dtype=float)
        params: dict[str, float] = {}
        stderr: dict[str, float | None] = {}
        for i, comp in enumerate(case.comp_true):
            for p in get_model(comp.model).param_names:
                par = result.params[f"p{i}_{p}"]
                params[f"p{i}.{p}"] = float(par.value)
                stderr[f"p{i}.{p}"] = (
                    float(par.stderr) if par.stderr is not None else None
                )
        chi2 = float(np.sum((case.y - best_fit) ** 2))
        # Prefer the iteration count; fall back to function-eval count (nfev).
        n_iter = int(getattr(result, "nit", None) or getattr(result, "nfev", 0) or 0)
        nvarys = int(getattr(result, "nvarys", len(case.comp_true)))
        dof = max(len(case.y) - nvarys, 1)
        init_fit = np.asarray(result.init_fit, dtype=float)
        cost0 = 0.5 * float(np.sum((case.y - init_fit) ** 2))
        cost, grad = reconstruct_history(cost0, 0.5 * chi2, max(2, min(n_iter, 40)))
        return BackendOutcome(
            backend=self.name,
            success=bool(result.success),
            r2=r2_score(case.y, best_fit),
            chi2=chi2,
            reduced_chi2=float(getattr(result, "redchi", chi2 / dof)),
            aic=float(getattr(result, "aic", 0.0)),
            bic=float(getattr(result, "bic", 0.0)),
            n_iter=n_iter,
            params=params,
            param_stderr=stderr,
            best_fit=best_fit,
            cost_history=cost,
            gradient_norm_history=grad,
            history_source="reconstructed",
            fit_dof=dof,
        )
