"""Per-backend profile assembly for a featured benchmark case (G27 split).

Extracted from ``oracles.engine``: the ``_build_profile`` cluster and its
metric/timing/scaling helpers. It depends only on the frozen contract types,
the backend/case value types, and the shared primitives in ``_engine_base`` —
never back on ``engine`` — so the package layers cleanly (engine core →
this module → base). ``engine`` re-imports the names its orchestration and the
test-suite reference.
"""

from __future__ import annotations

import math
import time

import numpy as np

from oracles import metrics
from oracles.backends import Backend, BackendOutcome
from oracles.cases import BenchCase, curve, materialize
from oracles.models import get_model
from oracles.bench_contract import (
    BackendProfile,
    Peak,
    PeakACS,
    Point2D,
    SolverFit,
    SpreadPt,
    StabilityEntry,
    Summary,
    TimingDist,
    Warmup,
    WarmupPt,
)
from oracles._engine_base import (
    _HAS_SPECTRAFIT,
    ProfileContext,
    _LOG,
    _RUNS_SCHED,
    _WARMUP_SCHED,
    _finite,
    _safe_fit,
)


def _peakacs(params: dict[str, float], case: BenchCase) -> list[PeakACS]:
    """One PeakACS (a/c/s) per graph component, **indexed by component position**.

    Kept GRAPH-INDEXED (one entry per ``comp_true`` component, not a peak-only filtered
    list) so consumers that look up by the dotted ``p{i}`` index — notably the web
    ExportView "Recovered parameters" table, which reads ``truth[pi]``/``fit[pi]`` for
    the ``pi`` parsed from a ``p{i}.<field>`` name — stay aligned. Components that lack a
    field (backgrounds/fano/decays have no ``sigma``; constant/linear/decay have no
    ``amplitude``) get a ``0.0`` sentinel for the missing field; that sentinel is never
    surfaced because the UI only reads a/c/s for param names that actually exist. This
    avoids the ``KeyError: p{i}.sigma`` on mixed peak+background cases while preserving
    index alignment (and keeps ``truth``/``peaks``/``fit.params`` in one index space).
    """
    return [
        PeakACS(
            a=float(params.get(f"p{i}.amplitude", 0.0)),
            c=float(params.get(f"p{i}.center", 0.0)),
            s=float(params.get(f"p{i}.sigma", 0.0)),
        )
        for i in range(len(case.comp_true))
    ]


def _cold_ms(backend: Backend, case: BenchCase) -> float:
    """Time a single cold solve (pre-warm-up) — JAX's compile cost shows here."""
    model = backend.build(case)
    t0 = time.perf_counter()
    try:
        backend.run(model, case)
    except Exception:  # noqa: BLE001
        return float("nan")
    return (time.perf_counter() - t0) * 1000.0


def _scaling(backend: Backend, case: BenchCase, ngrid: list[int]) -> list[Point2D]:
    """Median runtime of the featured model fit at increasing point counts.

    A failed grid fit carries forward the last finite time rather than emitting a
    NaN (which would corrupt the crossover and the JSON).
    """
    pts: list[Point2D] = []
    last = 1.0
    for n in ngrid:
        spec = case.spec.model_copy(update={"n_points": n, "id": f"{case.id}__n{n}"})
        big = materialize(spec)
        o = _safe_fit(backend, big, n_reps=2)
        y = float(np.median(o.timing_ms)) if o else float("nan")
        y = y if math.isfinite(y) else last
        last = y
        pts.append(Point2D(x=n, y=y))
    return pts


def _crossover(a: list[Point2D], b: list[Point2D]) -> float:
    """First N where series *b* overtakes *a* (linear interp), else last N.

    Intervals with a non-finite endpoint are skipped defensively.
    """
    for i in range(1, len(a)):
        da0, da1 = a[i - 1].y - b[i - 1].y, a[i].y - b[i].y
        if not (math.isfinite(da0) and math.isfinite(da1)):
            continue
        if da0 <= 0 < da1 or da0 >= 0 > da1:
            x0, x1 = a[i - 1].x, a[i].x
            t = abs(da0) / (abs(da0) + abs(da1) + 1e-30)
            return float(x0 + (x1 - x0) * t)
    return float(a[-1].x)


def _monte_carlo(
    backend: Backend, case: BenchCase, n_mc: int
) -> tuple[list[float], list[dict], list[dict], dict[str, list[float]]]:
    """Refit the featured case over fresh noise realizations; collect distributions."""
    red, ests, ses = [], [], []
    series: dict[str, list[float]] = {
        "r2": [],
        "rmse": [],
        "red_chi2": [],
        "iters": [],
        "perr": [],
    }
    base = curve(case.x, case.comp_true)
    for k in range(n_mc):
        rng = np.random.default_rng(1000 + k)
        y = base + rng.normal(0.0, case.spec.noise, case.x.size)
        spec = case.spec.model_copy(update={"id": f"{case.id}__mc{k}"})
        mc_case = case.model_copy(update={"spec": spec, "y": y})
        o = _safe_fit(backend, mc_case, n_reps=1)
        if o is None:
            continue
        red.append(o.reduced_chi2)
        ests.append(o.params)
        ses.append(o.param_stderr)
        series["r2"].append(o.r2)
        series["rmse"].append(float(np.sqrt(np.mean((y - o.best_fit) ** 2))))
        series["red_chi2"].append(o.reduced_chi2)
        series["iters"].append(float(o.n_iter))
        series["perr"].append(float(np.nan_to_num(o.param_error(mc_case), nan=0.0)))
    return red, ests, ses, series


def _theta_distance_to_truth(o: BackendOutcome, case: BenchCase) -> list[float] | None:
    """Scale-normalized per-iteration distance of θ to the synthetic ground truth.

    dₖ = ‖(θₖ − θ_true)/s‖₂ with sᵢ = max(|θ_true,ᵢ|, 1.0) — the REAL
    convergence-to-truth metric (DECISIONS.md 2026-06-13), distinct from the χ²
    descent. Returns ``None`` when no parameter trajectory was recorded (non-LM /
    non-spectrafit backend) or the case truth does not cover every free parameter
    (non-synthetic) — never a fabricated series.
    """
    order = o.params_param_order
    if not o.params_history or not order:
        return None
    truth = case.true_params
    if any(name not in truth for name in order):
        return None
    theta_true = np.array([truth[name] for name in order], dtype=float)
    scale = np.maximum(np.abs(theta_true), 1.0)
    out: list[float] = []
    for theta in o.params_history:
        if len(theta) != len(order):
            return None  # mismatched trajectory width — do not fabricate a value
        d = float(np.linalg.norm((np.asarray(theta, dtype=float) - theta_true) / scale))
        out.append(d)
    return out


def _build_profile(
    backend: Backend,
    o: BackendOutcome,
    case: BenchCase,
    cold_ms: float,
    ctx: ProfileContext,
    decim: list[int],
    raw_sink=None,
    audit: bool = False,
) -> BackendProfile:
    """Assemble one backend's full per-case profile (the single grouping)."""
    resid = case.y - o.best_fit
    ch = o.cost_history or [o.chi2 / 2]
    tdist = metrics.timing_dist(o.timing_ms)
    red, ests, ses, series = _monte_carlo(backend, case, ctx.n_mc)
    if raw_sink is not None:
        entry: dict = {
            "timing": [float(t) for t in o.timing_ms],
            "r2": list(series["r2"]),
        }
        if audit:
            y = np.asarray(case.y, dtype=float)
            fit = np.asarray(o.best_fit, dtype=float)
            entry["audit"] = {
                "y": [float(v) for v in y],
                "fit": [float(v) for v in fit],
                "sigma": float(case.spec.noise),
                "dof": (
                    o.fit_dof
                    if o.fit_dof is not None
                    else max(int(y.size) - len(o.params), 1)
                ),
                "stored_r2": float(o.r2),
                "stored_chi2_red": float(o.reduced_chi2),
                "stored_rmse": float(np.sqrt(np.mean((y - fit) ** 2))),
                "mc_ests": [dict(e) for e in ests],
                "mc_ses": [
                    {k: (None if v is None else float(v)) for k, v in s.items()}
                    for s in ses
                ],
                "true_params": {k: float(v) for k, v in case.true_params.items()},
                "kappa": (
                    None
                    if o.jacobian_condition_number is None
                    else float(o.jacobian_condition_number)
                ),
            }
        raw_sink[(case.id, backend.name)] = entry
    resid_scaled = [
        v
        for v in (np.abs(resid) / max(case.spec.noise, 1e-9)).tolist()
        if math.isfinite(v)
    ]

    def _spread(key: str) -> list[SpreadPt]:
        return metrics.spread_vs_runs(series[key] or [0.0], _RUNS_SCHED)

    # κ(J) — condition number of the Jacobian at convergence (Wire W2c).
    # Carried through BackendOutcome; backends that don't expose a Jacobian
    # leave it None (scipy-ls backends populate it from raw.jac).
    kappa = o.jacobian_condition_number

    return BackendProfile(
        fit=SolverFit(
            params=_peakacs(o.params, case),
            curve=[_finite(float(o.best_fit[i])) for i in decim],
            resid=[_finite(float(resid[i])) for i in decim],
        ),
        conv=ch,
        grad=o.gradient_norm_history or [0.0] * len(ch),
        # Provenance gate (EF-PY-11): conv_eff is derived from `ch`, which is a
        # proxy when history_source != "real". Only emit a measured efficiency
        # series for the subject's real cost history; None otherwise so a
        # consumer can't read a reconstructed-derived series as measured.
        conv_eff=(
            [(ch[0] - ch[i]) / (i + 1) for i in range(len(ch))]
            if o.history_source == "real"
            else None
        ),
        history_source=o.history_source,
        theta_distance=_theta_distance_to_truth(o, case),
        timing=tdist,
        accuracy=metrics.accuracy_dist(red or [o.reduced_chi2]),
        summary=_summary(o, case, tdist, ctx.baseline, ctx.min_aic, ctx.min_bic),
        param_err=_per_param_err(o, case),
        ecdf_resid=metrics.ecdf(resid_scaled),
        ecdf_time=metrics.ecdf(o.timing_ms),
        warmup=_warmup(cold_ms, tdist.median),
        scaling=_scaling(backend, case, ctx.ngrid),
        uncertainty=metrics.pulls_from_mc(ests, ses, case.true_params),
        param_spread=_spread("perr"),
        stability=StabilityEntry(
            r2=_spread("r2"),
            rmse=_spread("rmse"),
            red_chi2=_spread("red_chi2"),
            iters=_spread("iters"),
        ),
        jacobian_condition_number=kappa,
    )


def _per_param_err(o: BackendOutcome, case: BenchCase) -> list[float]:
    """Per-parameter relative error (%) in the order of ``true_params``."""
    out = []
    for key, true in case.true_params.items():
        if abs(true) < 1e-8 or key not in o.params:
            out.append(0.0)
        else:
            out.append(abs(o.params[key] - true) / abs(true) * 100.0)
    return out


def _warmup(cold_ms: float, hot_ms: float) -> Warmup:
    """Cold/hot amortization curve (cold falls back to hot when unavailable)."""
    cold = cold_ms if math.isfinite(cold_ms) else hot_ms
    return Warmup(
        curve=metrics.amortization_curve(cold, hot_ms, list(range(1, 101))),
        pts=[
            WarmupPt(n=k, per_run=(cold + hot_ms * (k - 1)) / k) for k in _WARMUP_SCHED
        ],
        hot_throughput=1000.0 / hot_ms if hot_ms > 0 else 0.0,
        cold_ms=cold,
        hot_ms=hot_ms,
    )


def _summary(
    o: BackendOutcome,
    case: BenchCase,
    timing: TimingDist,
    baseline: float,
    min_aic: float,
    min_bic: float,
) -> Summary:
    """Build the headline KPI block; ΔAIC/ΔBIC are vs the best solver in the run."""
    rmse = float(np.sqrt(np.mean((case.y - o.best_fit) ** 2)))
    mae = float(np.mean(np.abs(case.y - o.best_fit)))
    med = timing.median
    return Summary(
        r2=o.r2,
        chi2=o.chi2,
        red_chi2=o.reduced_chi2,
        rmse=rmse,
        mae=mae,
        n_iter=o.n_iter,
        med_ms=med,
        iqr_ms=timing.iqr,
        cv=timing.cv,
        speedup=baseline / med if med > 0 else 1.0,
        success=o.success,
        aic=o.aic,
        bic=o.bic,
        d_aic=o.aic - min_aic,
        d_bic=o.bic - min_bic,
    )


def _peak_contributions(case: BenchCase, o: BackendOutcome | None) -> list[Peak]:
    """Per-peak curves from the featured solver's fitted params (Gaussian sum)."""
    if o is None:
        return []
    out = []
    for i, comp in enumerate(case.comp_true):
        pm = get_model(comp.model)
        p = {n: o.params[f"p{i}.{n}"] for n in pm.param_names}
        out.append(Peak(label=f"g{i + 1}", y=pm.one(case.x, p).tolist()))
    return out


def _correlation(case: BenchCase) -> list[list[float]]:
    """Correlation matrix from the spectrafit covariance at the featured solution.

    Returns ``[]`` when spectrafit_core is unavailable (covariance is optional). The
    runtime fit is still guarded, but the dependency is now visible at module load
    rather than hidden inside a broad ``except`` that would also swallow a circular import.
    """
    if not _HAS_SPECTRAFIT:
        return []
    from spectrafit_core import fit

    from oracles.backends._spectrafit import SpectraFitBackend

    try:
        graph, data, options = SpectraFitBackend().build(case)
        result = fit(graph, data, options)
        return metrics.cov_to_corr(result.covariance)
    except Exception as exc:  # noqa: BLE001 - covariance is optional; don't sink the run
        _LOG.warning("correlation matrix unavailable: %s", exc)
        return []
