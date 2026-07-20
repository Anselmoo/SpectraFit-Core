"""scipy.optimize.least_squares oracle — three solver-meta entries.

Adds `scipy-ls-lm` (MINPACK clone of lmfit's default `Model.fit`), `scipy-ls-trf`
(Trust-Region Reflective — a pure-NumPy independent voice), and `scipy-ls-dogbox`
(trust-region dogleg) to the bench roster. Together they cover the three
LM-family strategies scipy ships, so a regression that hits one of them
surfaces alongside the lmfit/jax oracles instead of going unnoticed.

Why all three? Per the 2026-06-06 scipy-ls memory note:

* `lm` is registered for *sanity* — it is the same MINPACK kernel lmfit
  reaches by default, so its results should track lmfit's tightly on
  LM-family cases. A divergence between `lm` and `lmfit` would point at
  parametrisation, not the solver.
* `trf` is the independent voice — pure-NumPy trust-region with reflective
  bounds; it disagrees with MINPACK honestly when the model is ill-scaled.
* `dogbox` is trust-region dogleg, the third LM-family strategy scipy
  documents, so the comparison is exhaustive across the family.

Bounds policy mirrors `_lmfit.py`'s `_SHAPE_BOUNDS` (the long-tail shape
parameters that lmfit's MINPACK search can otherwise drive into the model
function's overflow/NaN region). For `trf` and `dogbox` the bounds are
passed natively to `least_squares`; for `lm` (which cannot accept bounds)
they are enforced as a soft-barrier residual that grows quadratically
outside the envelope.

History is `"reconstructed"` because `least_squares(method="lm")` has no
callback parameter; `trf`/`dogbox` gained one in scipy 1.16+ but wiring it
through is a future evolutionary slot.

Structure (Plan C2 refactor 4/4): the orchestrator (`build` → `run` →
`extract`) delegates to typed phase helpers that each own one concern —
parameter-box assembly, the timed solve, Jacobian conditioning + stderr
extraction, and flat-vector → contract-keyed param unpacking. The helpers
share information via small Pydantic records (`_ParamBox`, `_FitContext`)
so a language server can check every consumer.
"""

from __future__ import annotations

import math
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict

from oracles.backends._base import (
    Backend,
    BackendOutcome,
    r2_score,
    reconstruct_history,
)
from oracles.cases import BenchCase
from oracles.models import get_model

# Mirror lmfit's `_SHAPE_BOUNDS` — the long-tail shape envelopes patched after
# the CX-033 NaN cascade. Kept in sync deliberately so the two oracles see the
# same parameter box (else a "disagreement" between scipy-ls and lmfit would
# just reflect a bounds-table drift, not a solver difference).
_SHAPE_BOUNDS: dict[str, tuple[float, float]] = {
    "m": (1.05, 50.0),
    "m_l": (1.05, 50.0),
    "m_r": (1.05, 50.0),
    "beta": (0.1, 50.0),
    "nu": (0.5, 200.0),
    "q": (-100.0, 100.0),
    "k": (-50.0, 50.0),
}

_Method = Literal["lm", "trf", "dogbox"]

# κ(J) cap — anything beyond this is reported as ``1e16`` to keep downstream
# aggregations (geomean, ratios, plots) from contaminating with ``inf``.
_KAPPA_CAP = 1e16

# Soft-barrier weight for the ``lm`` path (the MINPACK kernel cannot accept
# bounds). 10× a unit residual so a 10 % excursion past a bound contributes the
# same magnitude as a 10 % residual error — see `_make_lm_residual` docstring.
_LM_BARRIER_WEIGHT = 10.0


# --------------------------------------------------------------------------- #
# Internal typed records — Pydantic-first so a language server can check every
# consumer + ``extra="forbid"`` keeps the structural contract explicit.
# --------------------------------------------------------------------------- #
class _ParamBox(BaseModel):
    """Flat parameter box for one case — free/fixed split.

    ``names`` contains ALL parameter flat-names (``p{i}_{pname}`` order) so
    downstream reporting can reconstruct the full param dict.  The optimizer
    sees only the FREE slice (``free_names``, ``free_x0``, ``free_lo``,
    ``free_hi``); fixed parameters are held at ``fixed_vals`` and never enter
    ``theta``.

    Produced by :func:`_build_initial_guess`; consumed by :func:`_solve`
    (free bounds + x0) and :func:`_extract_params` (all names + fixed vals).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    # Full parameter inventory (all = free ∪ fixed, in component order).
    names: list[str]
    x0: np.ndarray  # full x0 (all params, clipped)
    lo: np.ndarray  # full lo (all params)
    hi: np.ndarray  # full hi (all params)
    init_fit: np.ndarray

    # Free-param slice — what the optimizer actually receives.
    free_names: list[str]
    free_x0: np.ndarray
    free_lo: np.ndarray
    free_hi: np.ndarray
    free_indices: list[int]  # positions in the full vector

    # Fixed-param slice — held constant throughout the solve.
    fixed_names: list[str]
    fixed_vals: np.ndarray
    fixed_indices: list[int]  # positions in the full vector


class _FitContext(BaseModel):
    """Bundle passed from ``build`` through ``run`` to ``extract``.

    ``run`` only needs ``(x0, lo, hi)``; ``extract`` needs the names + the
    initial-fit curve (to reconstruct the cost-history seed). Kept as one model
    so the ``Backend.build`` return type is a single object instead of a tuple
    of five disparate arrays.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    box: _ParamBox


# --------------------------------------------------------------------------- #
# Phase 1 — initial guess assembly (parameter box + clamped x0 + init fit curve)
# --------------------------------------------------------------------------- #
def _bounds_for(
    case: BenchCase,
) -> tuple[
    list[str],  # all param flat-names (full order)
    np.ndarray,  # full x0
    np.ndarray,  # full lo
    np.ndarray,  # full hi
    list[int],  # free_indices  (positions of free params in full vector)
    list[int],  # fixed_indices (positions of fixed params in full vector)
    np.ndarray,  # fixed_vals    (pinned values for fixed params)
]:
    """Flatten the case's component parameters into a free/fixed split.

    The same parameter envelope as the lmfit backend: per-peak amplitude in
    `[0, +inf)`, center in `[x_min, x_max]`, sigma/gamma in `(0, +inf)`,
    fraction in `[0, 1]`, plus `_SHAPE_BOUNDS` for the long-tail shape params.

    Fixed params (``case.fixed_params``) are separated out entirely — they do
    NOT enter the free vector that the optimizer sees.  Their pinned values are
    stored separately and re-inserted by :func:`_rebuild_theta` inside each
    residual call.
    """
    lo_x, hi_x = float(case.x.min()), float(case.x.max())
    names: list[str] = []
    x0_list: list[float] = []
    lo_list: list[float] = []
    hi_list: list[float] = []
    # Build a flat set of fixed param flat-names: "p{i}_{pname}"
    fixed_flat: set[str] = {
        f"p{i}_{pname}"
        for node_id, pnames in case.spec.fixed_params.items()
        # node_id is "p0", "p1", … — extract the integer index
        if (i := int(node_id[1:])) >= 0
        for pname in pnames
    }
    for i, comp in enumerate(case.comp_guess):
        pm = get_model(comp.model)
        cp = comp.to_params()
        for pname in pm.param_names:
            flat_name = f"p{i}_{pname}"
            val = float(cp[pname])
            names.append(flat_name)
            x0_list.append(val)
            if flat_name in fixed_flat:
                # Fixed params get placeholder bounds — they won't enter theta,
                # but we keep them in the full arrays for consistency.
                lo_list.append(val)
                hi_list.append(val)
            else:
                match pname:
                    case "amplitude":
                        lo_list.append(0.0)
                        hi_list.append(math.inf)
                    case "center":
                        lo_list.append(lo_x)
                        hi_list.append(hi_x)
                    case "sigma" | "gamma":
                        lo_list.append(1e-6)
                        hi_list.append(math.inf)
                    case "fraction":
                        lo_list.append(0.0)
                        hi_list.append(1.0)
                    case _ if pname in _SHAPE_BOUNDS:
                        a, b = _SHAPE_BOUNDS[pname]
                        lo_list.append(a)
                        hi_list.append(b)
                    case _:
                        lo_list.append(-math.inf)
                        hi_list.append(math.inf)

    x0 = np.asarray(x0_list)
    lo = np.asarray(lo_list)
    hi = np.asarray(hi_list)

    # Build free/fixed index lists.
    free_indices: list[int] = []
    fixed_indices: list[int] = []
    for idx, flat_name in enumerate(names):
        if flat_name in fixed_flat:
            fixed_indices.append(idx)
        else:
            free_indices.append(idx)

    fixed_vals = x0[fixed_indices] if fixed_indices else np.empty(0, dtype=float)

    return names, x0, lo, hi, free_indices, fixed_indices, fixed_vals


def _rebuild_theta(
    free_theta: np.ndarray,
    fixed_vals: np.ndarray,
    free_indices: list[int],
    fixed_indices: list[int],
    n_total: int,
) -> np.ndarray:
    """Reconstruct the full parameter vector from free + fixed slices.

    Free values are placed at ``free_indices``; fixed values are placed at
    ``fixed_indices``.  Together they fill all ``n_total`` positions.

    This is the core of the no-thrash guarantee: the optimizer works on
    ``free_theta`` only; fixed params are constants reconstructed here, never
    passed through ``theta``.
    """
    full = np.empty(n_total, dtype=float)
    if free_indices:
        full[free_indices] = free_theta
    if fixed_indices:
        full[fixed_indices] = fixed_vals
    return full


def _predict(theta: np.ndarray, case: BenchCase) -> np.ndarray:
    """Forward model: sum of component evaluations at the flat parameter vector."""
    y_pred = np.zeros_like(case.x, dtype=float)
    j = 0
    for comp in case.comp_guess:
        pm = get_model(comp.model)
        n = len(pm.param_names)
        kwargs = dict(zip(pm.param_names, theta[j : j + n]))
        y_pred = y_pred + pm.evaluate(case.x, **kwargs)
        j += n
    return y_pred


def _build_initial_guess(case: BenchCase) -> _ParamBox:
    """Assemble the parameter box, clamping x0 into bounds + caching init fit.

    Clamping is load-bearing: initial guesses that already escape the envelope
    (e.g. an out-of-range sigma) would make `lm`'s soft barrier residual
    dominate from iteration 0, masking the real objective. trf/dogbox would
    just reject the start, which we want to avoid for fair comparison.

    The free/fixed split produced here is the structural no-thrash guarantee:
    ``free_x0`` is the ONLY vector the optimizer ever sees.  Fixed params are
    held constant in ``fixed_vals`` and never enter ``theta``.
    """
    names, x0, lo, hi, free_indices, fixed_indices, fixed_vals = _bounds_for(case)
    # Clip free params into their bounds (fixed params have lo==hi==val; clipping
    # is a no-op for them, but we clip the full vector for uniformity).
    x0 = np.clip(x0, lo, hi)
    init_fit = _predict(x0, case)

    # Build free-param slices.
    free_names = [names[i] for i in free_indices]
    free_x0 = x0[free_indices] if free_indices else np.empty(0, dtype=float)
    free_lo = lo[free_indices] if free_indices else np.empty(0, dtype=float)
    free_hi = hi[free_indices] if free_indices else np.empty(0, dtype=float)
    fixed_names = [names[i] for i in fixed_indices]
    # Re-read fixed_vals from the clipped x0 (in case clipping moved them).
    fixed_vals_clipped = (
        x0[fixed_indices] if fixed_indices else np.empty(0, dtype=float)
    )

    return _ParamBox(
        names=names,
        x0=x0,
        lo=lo,
        hi=hi,
        init_fit=init_fit,
        free_names=free_names,
        free_x0=free_x0,
        free_lo=free_lo,
        free_hi=free_hi,
        free_indices=free_indices,
        fixed_names=fixed_names,
        fixed_vals=fixed_vals_clipped,
        fixed_indices=fixed_indices,
    )


# --------------------------------------------------------------------------- #
# Phase 2 — solve dispatch (method-aware least_squares invocation)
# --------------------------------------------------------------------------- #
def _make_lm_residual(
    case: BenchCase,
    box: "_ParamBox",
) -> Any:
    """Build the ``lm``-path soft-barrier residual.

    ``theta`` is the FREE parameter vector only.  The residual function
    reconstructs the full parameter vector via :func:`_rebuild_theta` before
    calling :func:`_predict`.

    MINPACK can't accept bounds; the envelope for free params is enforced as a
    soft-barrier residual that grows quadratically outside the box. Weight
    (`_LM_BARRIER_WEIGHT`) chosen so a 10 % excursion past a bound contributes
    the same magnitude as a 10 % residual error. Fixed params never appear in
    ``theta`` so no barrier terms are needed for them.
    """
    y = case.y
    n_total = len(box.names)
    free_indices = box.free_indices
    fixed_indices = box.fixed_indices
    fixed_vals = box.fixed_vals
    free_lo = box.free_lo
    free_hi = box.free_hi

    def residual(free_theta: np.ndarray) -> np.ndarray:
        full = _rebuild_theta(
            free_theta, fixed_vals, free_indices, fixed_indices, n_total
        )
        pred = _predict(full, case)
        main = pred - y
        # Soft barrier only on the FREE params.
        under = np.maximum(free_lo - free_theta, 0.0)
        over = np.maximum(free_theta - free_hi, 0.0)
        barrier = np.concatenate([under, over])
        return np.concatenate([main, _LM_BARRIER_WEIGHT * barrier])

    return residual


def _make_bounded_residual(
    case: BenchCase,
    box: "_ParamBox",
) -> Any:
    """Build the ``trf``/``dogbox`` residual (bounds are native to least_squares).

    ``theta`` is the FREE parameter vector only; the residual reconstructs the
    full vector before calling :func:`_predict`.
    """
    y = case.y
    n_total = len(box.names)
    free_indices = box.free_indices
    fixed_indices = box.fixed_indices
    fixed_vals = box.fixed_vals

    def residual(free_theta: np.ndarray) -> np.ndarray:
        full = _rebuild_theta(
            free_theta, fixed_vals, free_indices, fixed_indices, n_total
        )
        return _predict(full, case) - y

    return residual


class _PinnedResult:
    """Synthetic OptimizeResult-like object for the all-fixed case.

    When all params are fixed there is nothing to optimise; skip
    ``least_squares`` entirely and return a result that carries the pinned
    values as ``x``, zero residuals, and ``success=True``.
    """

    def __init__(self, x: np.ndarray, n_data: int) -> None:
        self.x: np.ndarray = x
        self.fun: np.ndarray = np.zeros(n_data, dtype=float)
        self.jac: np.ndarray | None = None
        self.cost: float = 0.0
        self.nfev: int = 0
        self.success: bool = True
        self.status: int = 1


def _solve(method: _Method, box: _ParamBox, case: BenchCase) -> Any:
    """Dispatch to ``least_squares`` with the method-appropriate bounds policy.

    Only the FREE parameter slice (``box.free_x0``, ``box.free_lo``,
    ``box.free_hi``) is passed to the optimizer.  Fixed params are held
    constant inside the residual via :func:`_rebuild_theta`.

    Degenerate guard: if the free vector is empty (all params are fixed),
    skip ``least_squares`` entirely and return a :class:`_PinnedResult` that
    carries the pinned values.  This prevents calling scipy with an empty
    theta (which raises) and is the only correct behaviour.

    Returns the raw ``OptimizeResult`` (or a ``_PinnedResult``). ``method``
    dispatch is a ``match`` on the literal — unknown methods raise
    ``ValueError`` so the registry can't silently use an unsupported solver.
    """
    from scipy.optimize import least_squares

    # All-fixed degenerate guard.
    if not box.free_indices:
        return _PinnedResult(x=box.fixed_vals.copy(), n_data=len(case.y))

    match method:
        case "lm":
            residual = _make_lm_residual(case, box)
            return least_squares(residual, box.free_x0, method="lm")
        case "trf" | "dogbox":
            residual = _make_bounded_residual(case, box)
            return least_squares(
                residual,
                box.free_x0,
                method=method,
                bounds=(box.free_lo, box.free_hi),
            )
        case _:  # pragma: no cover - Literal types pin this at the type level
            raise ValueError(f"_solve: unsupported method {method!r}")


# --------------------------------------------------------------------------- #
# Phase 3 — Jacobian-conditioning + SVD-pseudoinverse stderr extraction
# --------------------------------------------------------------------------- #
def _kappa_of(jac: np.ndarray | None) -> float | None:
    """Condition number κ(J), capped at ``_KAPPA_CAP``; ``None`` if undefined.

    Structural property of the case (Wire W2c): κ ≥ 1e6 → ill-conditioned.
    The cap protects downstream aggregations from ``inf`` contamination.
    """
    if jac is None or jac.size == 0:
        return None
    try:
        kappa_raw = float(np.linalg.cond(jac))
    except (ValueError, np.linalg.LinAlgError):
        return None
    if not math.isfinite(kappa_raw):
        return None
    return min(kappa_raw, _KAPPA_CAP)


def _stderr_from_jac(
    jac: np.ndarray | None,
    names: list[str],
    cost: float,
) -> dict[str, float | None]:
    """Curve_fit-style stderr via SVD pseudo-inverse of the Jacobian.

    `cov = inv(JᵀJ) · 2·cost/(m−n)` via SVD pseudo-inverse handles rank
    deficiency the way `scipy.optimize.curve_fit` does. When the Jacobian is
    missing, under-determined, or numerically degenerate, all stderrs collapse
    to ``None`` — better than reporting a bogus number.
    """
    blank = {f"{n.split('_', 1)[0]}.{n.split('_', 1)[1]}": None for n in names}
    if jac is None or jac.size == 0:
        return blank
    m, n_par = jac.shape
    if m <= n_par:
        return blank
    try:
        _u, sv, vh = np.linalg.svd(jac, full_matrices=False)
        threshold = np.finfo(float).eps * max(jac.shape) * sv[0] if sv.size else 0.0
        sv_inv = np.where(sv > threshold, 1.0 / np.where(sv > 0, sv, 1.0), 0.0)
        cov = (vh.T * sv_inv**2) @ vh
        s_sq = 2.0 * float(cost) / max(m - n_par, 1)
        var = np.diag(cov) * s_sq
    except (np.linalg.LinAlgError, ValueError):
        return blank
    out: dict[str, float | None] = {}
    for flat_name, v in zip(names, var):
        i_str, p_str = flat_name.split("_", 1)
        out[f"{i_str}.{p_str}"] = (
            float(math.sqrt(v)) if v > 0 and math.isfinite(v) else None
        )
    return out


def _extract_uncertainty(
    raw: Any, box: _ParamBox
) -> tuple[float | None, dict[str, float | None]]:
    """Return (κ(J), stderr map) from the raw ``OptimizeResult``.

    The Jacobian returned by ``least_squares`` has shape
    ``(n_data, n_free)`` — one column per FREE parameter.  κ(J) is computed
    over this free-param Jacobian.  Stderr entries exist only for free params;
    fixed params get ``None`` because their variance is zero by construction
    (but reporting them as ``None`` is honest — "not estimated").
    """
    jac = (
        np.asarray(raw.jac, dtype=float)
        if hasattr(raw, "jac") and raw.jac is not None
        else None
    )
    kappa = _kappa_of(jac)
    # stderr is computed over the FREE param subset only.
    stderr_free = _stderr_from_jac(jac, box.free_names, float(raw.cost))
    # Merge free stderrs with None entries for fixed params, in full name order.
    stderr: dict[str, float | None] = {}
    for flat_name in box.names:
        i_str, p_str = flat_name.split("_", 1)
        key = f"{i_str}.{p_str}"
        stderr[key] = stderr_free.get(key, None)
    return kappa, stderr


# --------------------------------------------------------------------------- #
# Phase 4 — flat-vector → contract-keyed params + success upgrade policy
# --------------------------------------------------------------------------- #
def _extract_params(raw: Any, box: _ParamBox) -> dict[str, float]:
    """Map the optimiser result + pinned fixed values → contract-keyed params.

    ``raw.x`` carries only the FREE parameter values (length ``n_free``).
    This function reconstructs the full parameter vector by inserting the
    free result at ``box.free_indices`` and the pinned ``box.fixed_vals`` at
    ``box.fixed_indices``, then converts to the ``p{i}.<name>`` dot notation
    that the contract expects.

    Mirrors lmfit's mapping; ``box.names`` carries the ``p{i}_{name}`` flat
    order produced by :func:`_bounds_for`.
    """
    n_total = len(box.names)
    full = _rebuild_theta(
        np.asarray(raw.x, dtype=float),
        box.fixed_vals,
        box.free_indices,
        box.fixed_indices,
        n_total,
    )
    params: dict[str, float] = {}
    for flat_name, val in zip(box.names, full):
        i_str, p_str = flat_name.split("_", 1)
        params[f"{i_str}.{p_str}"] = float(val)
    return params


def _upgrade_success(raw: Any, r2_quality: float) -> bool:
    """r²-quality upgrade for soft failures (status ≥ 0, r² ≥ 0.9).

    Mirrors the post-fit policy in ``apply_postfit_guards``
    (`crates/spectrafit-solver/src/postfit.rs`, Cycle 5.5 DECISIONS.md entry
    "r²-quality upgrade promotes soft-failure terminations").
    ``scipy.optimize.least_squares`` reports `success = False` for
    `status == 0` (max_nfev reached); for trf/dogbox `status == 0` is
    genuinely budget-exhausted, and for `lm` the soft-barrier residual
    inflates ``nfev`` faster than the underlying MINPACK driver was budgeted
    for. A fit that reached r² ≥ 0.9 is materially converged regardless of
    which budget tripped. ``status < 0`` (improper input, numerical error)
    is NEVER upgraded — that's a real broken state.
    """
    scipy_success = bool(raw.success)
    if not scipy_success and r2_quality >= 0.9 and int(getattr(raw, "status", 1)) >= 0:
        return True
    return scipy_success


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
class ScipyLeastSquaresBackend(Backend):
    """Fit a case via `scipy.optimize.least_squares` (one instance per method)."""

    def __init__(self, method: _Method) -> None:
        import scipy.optimize  # noqa: F401  (import-time availability check)

        self._method: _Method = method
        self.name = f"scipy-ls-{method}"

    def is_supported(self, case: BenchCase) -> bool:
        """Exclude tied-param cases: scipy least_squares cannot express expr_edges."""
        return not case.spec.expr_edges

    def build(self, case: BenchCase) -> Any:
        """Pack the parameter box + initial residuals for the chosen method."""
        return _FitContext(box=_build_initial_guess(case))

    def run(self, model: Any, case: BenchCase) -> Any:
        """Invoke `least_squares` with the method-appropriate bounds policy."""
        ctx: _FitContext = model
        return _solve(self._method, ctx.box, case)

    def extract(self, raw: Any, case: BenchCase) -> BackendOutcome:
        """Map `OptimizeResult` to the normalised `BackendOutcome`.

        AIC/BIC use the Gaussian-error formula `−2 log L = n · log(χ²/n)`
        (the `n·(ln(2π)+1)` constant is dropped so cross-backend ΔAIC/ΔBIC
        are comparable — the parity test in
        ``tests/parity/test_backend_metrics_parity.py`` locks this down).

        The AIC/BIC penalty uses the TOTAL parameter count (free + fixed) for
        consistency with the pre-FX behaviour on non-FX cases; the degrees of
        freedom for reduced-χ² likewise uses ``n_total_params``.
        """
        box = _build_initial_guess(case)
        n_data = len(case.y)
        n_params = len(box.names)  # total (free + fixed) — for AIC/BIC/dof
        # `raw.fun` for the `lm` path is `[main_residuals; soft_barrier]`;
        # trim to data residuals so χ² + r² are honest. The residual functions
        # (`_make_lm_residual` / `_make_bounded_residual`) return `pred − y`, so
        # the model prediction is `y + residuals` — NOT `y − residuals`. The
        # latter reflects the fit across the data (`2y − pred`), which made the
        # reconstructed `best_fit` a mirror image and, via the engine's central
        # `resid = case.y − best_fit`, flipped the stored residual sign relative
        # to spectrafit/lmfit/jax (they emit obs − fit). Adding restores both the
        # true curve and the canonical obs − fit residual convention; χ² is
        # unaffected (it squares the residual).
        residuals = np.asarray(raw.fun[:n_data], dtype=float)
        best_fit = case.y + residuals
        params = _extract_params(raw, box)
        kappa, stderr = _extract_uncertainty(raw, box)
        chi2 = float(np.sum(residuals**2))
        dof = max(n_data - n_params, 1)
        red_chi2 = chi2 / dof
        neg2_log_l = n_data * math.log(chi2 / n_data) if chi2 > 0 else 0.0
        aic = neg2_log_l + 2.0 * n_params
        bic = neg2_log_l + math.log(n_data) * n_params
        n_iter = int(getattr(raw, "nfev", 0) or 0)
        cost0 = 0.5 * float(np.sum((case.y - box.init_fit) ** 2))
        cost_hist, grad = reconstruct_history(
            cost0, 0.5 * chi2, max(2, min(n_iter, 40))
        )
        r2_quality = r2_score(case.y, best_fit)
        return BackendOutcome(
            backend=self.name,
            success=_upgrade_success(raw, r2_quality),
            r2=r2_quality,
            chi2=chi2,
            reduced_chi2=red_chi2,
            aic=aic,
            bic=bic,
            n_iter=n_iter,
            params=params,
            param_stderr=stderr,
            best_fit=best_fit,
            cost_history=cost_hist,
            gradient_norm_history=grad,
            history_source="reconstructed",
            jacobian_condition_number=kappa,
            fit_dof=dof,
        )
