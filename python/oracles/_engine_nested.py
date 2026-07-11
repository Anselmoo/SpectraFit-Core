"""Nested-model adequacy V&V for a benchmark case (G27 split).

Extracted from ``oracles.engine``: the nested-order refit oracle
(``_run_nested_adequacy``) and its order-construction helpers. Depends only on
the contract types, the case value types, ``oracles.nested`` and the shared
``_safe_fit`` primitive — never back on ``engine``. ``engine`` re-imports
``_run_nested_adequacy`` (orchestration) and ``_order_bench_case`` (tests).
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable

import numpy as np

from oracles.backends import Backend
from oracles.cases import BenchCase, Component, GaussianSpec
from oracles.nested import nested_adequacy as _nested_adequacy
from oracles.bench_contract import (
    NestedAdequacy as ContractNestedAdequacy,
    SelectionStats as ContractSelectionStats,
)
from oracles._engine_base import _LOG, _safe_fit

# Node reference pattern in a tied-parameter expression (e.g. "p1.center").
_EXPR_NODE_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.[A-Za-z_][A-Za-z0-9_]*\b")


def _is_peak_component(comp: Component) -> bool:
    """Return True if *comp* is a peak-shaped component (not a background/edge/decay).

    Background models (constant, linear, quadratic, step, decay, NIST curves,
    dispersion, relaxation) are excluded so that ``_peak_components`` filters the
    graph to only the signal peaks — the count that drives nested-model order.
    """
    match comp.model:
        case (
            "gaussian"
            | "lorentzian"
            | "pseudo_voigt"
            | "voigt"
            | "fano"
            | "true_voigt"
            | "skewed_gaussian"
            | "exp_gaussian"
            | "doniach_sunjic"
            | "log_normal"
            | "pearson7"
            | "split_gaussian"
            | "moffat"
            | "students_t"
            | "split_pearson7"
            | "breit_wigner"
            | "asym_ir"
            | "harmonic_ir"
        ):
            return True
        case _:
            return False


def _build_fit_order(
    case: BenchCase,
    spectrafit_backend: Backend,
) -> tuple[int, Callable[[int], tuple[float, int]]]:
    """Build a ``fit_order(order) -> (rss, k)`` closure for the featured case.

    Parameters
    ----------
    case:
        The featured materialized case — its ``x``/``y`` are the fixed data.
    spectrafit_backend:
        The subject backend (spectrafit); all order fits use this backend.

    Returns:
    --------
    (true_order, fit_order)
        ``true_order`` is the generative peak count (m*);
        ``fit_order(order)`` fits the case at the requested order and returns
        ``(rss, k)`` where ``rss = Σresid²`` and ``k`` = fitted free-parameter count.
        A failed fit returns ``(rss_null, k)`` where ``rss_null`` is the null-model
        RSS (fit = mean(y)) — never a fabricated zero — with a loud-skip log.
    """
    # Separate peak components from background components.
    peak_comps: list[Component] = [c for c in case.comp_true if _is_peak_component(c)]
    bg_comps: list[Component] = [c for c in case.comp_true if not _is_peak_component(c)]
    true_order = len(peak_comps)

    # Null RSS: Σ(y − ȳ)² — used as a fallback when a fit fails so downstream
    # statistics are pessimistic (worse fit) rather than fabricated.
    y = case.y
    rss_null = float(np.sum((y - float(np.mean(y))) ** 2))

    def fit_order(order: int) -> tuple[float, int]:
        """Fit the case at *order* peaks; return (rss, k)."""
        match order - true_order:
            case diff if diff < 0:
                # Reduced: truncate to `order` peaks (drop the least-prominent ones).
                order_peaks = peak_comps[:order]
            case 0:
                # True: use the generative components as-is.
                order_peaks = list(peak_comps)
            case _:
                # Over: extend with one extra Gaussian seeded near the largest residual.
                # We first fit the true-order model to get residuals, then seed a new
                # peak at the residual maximum as a data-driven extra guess.
                order_peaks = list(peak_comps)
                # Seed a new Gaussian near the point with the largest |residual|.
                # Use the true-order fit result if available; fall back to y itself.
                try:
                    true_case = _order_bench_case(case, list(peak_comps), bg_comps)
                    true_o = _safe_fit(spectrafit_backend, true_case, n_reps=1)
                    residuals = y - (true_o.best_fit if true_o else np.zeros_like(y))
                except Exception:  # noqa: BLE001
                    residuals = y
                idx_max = int(np.argmax(np.abs(residuals)))
                x_seed = float(case.x[idx_max])
                amp_seed = float(np.abs(residuals[idx_max]))
                sigma_seed = float(np.median(np.abs(np.diff(case.x))) * 5.0)
                extra_peak = GaussianSpec(
                    amplitude=max(amp_seed, 0.01),
                    center=x_seed,
                    sigma=max(sigma_seed, 0.1),
                )
                order_peaks = list(peak_comps) + [extra_peak]

        comps = order_peaks + bg_comps
        order_case = _order_bench_case(case, order_peaks, bg_comps)
        # k = number of free parameters (one per param per component)
        k = sum(len(c.to_params()) for c in comps)

        o = _safe_fit(spectrafit_backend, order_case, n_reps=1)
        if o is None or not o.success:
            _LOG.warning(
                "nested fit failed for case %s at order %d — using null RSS",
                case.id,
                order,
            )
            return rss_null, k

        rss = float(np.sum((y - o.best_fit) ** 2))
        return rss, k

    return true_order, fit_order


def _order_bench_case(
    base: BenchCase,
    peak_comps: list[Component],
    bg_comps: list[Component],
) -> BenchCase:
    """Build a BenchCase with a different set of components but the same x/y data.

    The guess components mirror the truth components (slightly perturbed is fine
    for the nested-adequacy solve; the spectrafit LM is robust to a close start).
    Uses the base case's data (x, y) unchanged — only the model order differs.

    expr_edges are scoped to the nodes present at this order: any edge whose
    ``target_node`` or whose expression source nodes are absent from the
    reduced/expanded component set is silently dropped so the FitGraph
    validator never sees a dangling reference.
    """
    comps = peak_comps + bg_comps
    # Guess = truth components with a small uniform jitter so the solver has a
    # realistic start (same as materialize but without re-jittering via _jitter).
    rng = random.Random(len(comps) * 17 + len(base.x))
    guess = [
        c.model_copy(
            update={
                k: v * (1.0 + rng.uniform(-0.05, 0.05))
                for k, v in c.to_params().items()
            }
        )
        for c in comps
    ]
    # Build a synthetic spec id to avoid cache collisions (spectrafit hashes by id).
    spec_id = f"{base.id}__order{len(comps)}"

    # Scope expr_edges: drop any edge whose target_node or whose expression
    # source nodes are not present in the component set at this order.
    present_nodes: set[str] = {f"p{i}" for i in range(len(comps))}
    scoped_edges = [
        e
        for e in base.spec.expr_edges
        if e["target_node"] in present_nodes
        and all(src in present_nodes for src in _EXPR_NODE_RE.findall(e["expression"]))
    ]

    spec = base.spec.model_copy(
        update={"id": spec_id, "components": comps, "expr_edges": scoped_edges}
    )
    return BenchCase(
        spec=spec,
        x=base.x,
        y=base.y,
        comp_true=comps,
        comp_guess=guess,
    )


def _run_nested_adequacy(
    case: BenchCase,
    spectrafit_backend: Backend | None,
) -> ContractNestedAdequacy | None:
    """Compute nested-model adequacy V&V for *case* using the subject (spectrafit).

    Returns ``None`` when:
    - spectrafit is not available (no backend),
    - the case has fewer than 2 peak components (under-constrained LRT),
    - any order fit fails entirely.

    On success, maps ``oracles.nested.NestedAdequacy`` → ``ContractNestedAdequacy``.
    """
    if spectrafit_backend is None:
        _LOG.warning("nested_adequacy skipped: spectrafit backend not available")
        return None

    peak_count = sum(1 for c in case.comp_true if _is_peak_component(c))
    if peak_count < 2:
        _LOG.warning(
            "nested_adequacy skipped for case %s: only %d peak component(s)",
            case.id,
            peak_count,
        )
        return None

    try:
        true_order, fit_order_fn = _build_fit_order(case, spectrafit_backend)
        na = _nested_adequacy(true_order, fit_order_fn, n=len(case.x))
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("nested_adequacy failed for case %s: %r", case.id, exc)
        return None

    def _map_stats(s) -> ContractSelectionStats:
        return ContractSelectionStats(
            lrt_stat=s.lrt_stat,
            lrt_p=s.lrt_p,
            f_stat=s.f_stat,
            f_p=s.f_p,
            d_aic=s.d_aic,
            d_bic=s.d_bic,
        )

    return ContractNestedAdequacy(
        true_order=na.true_order,
        reduced_rejected=na.reduced_rejected,
        over_not_preferred_aic=na.over_not_preferred_aic,
        over_not_preferred_bic=na.over_not_preferred_bic,
        selected_order_aic=na.selected_order_aic,
        selected_order_bic=na.selected_order_bic,
        recovered_true_order_aic=na.recovered_true_order_aic,
        recovered_true_order_bic=na.recovered_true_order_bic,
        reduced_vs_true=_map_stats(na.reduced_vs_true),
        true_vs_over=_map_stats(na.true_vs_over),
    )
