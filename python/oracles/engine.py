"""Benchmark engine: run the catalog, assemble the frozen ``BenchReport``.

Two paths:

- :func:`run_suite` — one fit per case per supported backend → per-case metrics
  (the 139-row suite for the regression map / win-rate panels).
- :func:`run_featured` — a deep dive on the featured case: per-solver fits, real
  convergence traces, timing distributions, a Monte-Carlo over noise realizations
  (accuracy / parameter pulls / stability), a scaling sweep, cold/hot amortization,
  the covariance correlation matrix, and a 2-D example.

Everything is measured; per-backend failures are caught so one bad fit never sinks
the run.
"""

from __future__ import annotations

import math
import subprocess
import time
from collections.abc import Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict

from oracles.backends import Backend, BackendOutcome, get_backends
from oracles.cases import (
    CATEGORY_COUNTS,
    CATEGORY_HUE,
    CATEGORY_LABELS,
    SOLVER_META,
    BenchCase,
    Component,
    build_catalog,
    curve,
    featured_case,
)
from oracles.bench_contract import (
    BenchReport,
    CategoryMeta,
    ExprEdge,
    Featured,
    Peak,
    PeakACS,
    SuiteCase,
    SuiteMetric,
)
from oracles.panels import default_panels
from oracles.models import get_model
from oracles._engine_multidim import _global_fit, _multidim
from oracles._engine_nested import _run_nested_adequacy
from oracles._engine_nested import _order_bench_case  # noqa: F401  — re-exported for tests
from oracles._engine_profile import (
    _build_profile,
    _cold_ms,
    _correlation,
    _crossover,
    _peak_contributions,
)
from oracles._engine_profile import (  # noqa: F401  — re-exported for the test suite
    _monte_carlo,
    _summary,
)
from oracles._engine_base import (
    ProfileContext,
    _NGRID,
    _RUNS_SCHED,
    _WARMUP_SCHED,
    _finite,
    _safe_fit,
)


_CATEGORY_META = [
    CategoryMeta(id=cid, label=CATEGORY_LABELS[cid], n=n, hue=CATEGORY_HUE[cid])
    for cid, n in CATEGORY_COUNTS.items()
]


# Explicit key → Rust source filename mapping for registry keys that diverge from the
# default {key}.rs pattern.  Keys not listed here fall back to f"{key}.rs".
# Maintained as a small dict rather than inferred from the filename so a future rename
# in the Rust tree is caught by the parametrized existence-guard test, not silently
# producing a missing-file path in the contract.
_MODEL_SOURCE_MAP: dict[str, str] = {
    # multi-shape files
    "constant": "polynomial.rs",
    "linear": "polynomial.rs",
    "quadratic": "polynomial.rs",
    "arctan_step": "step.rs",
    "tanh_step": "step.rs",
    "erfc_step": "step.rs",
    "double_exponential": "exponential.rs",
    # renamed files
    "true_voigt": "voigt_true.rs",
    "exp_gaussian": "emg.rs",
    "doniach_sunjic": "doniach.rs",
}


class FitTriple(BaseModel):
    """One backend's completed fit, ready for profiling (named, not positional)."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True, extra="forbid")

    name: str
    backend: Backend
    outcome: BackendOutcome


def _capture_git_provenance() -> tuple[str | None, str | None]:
    """Return (short_commit_hash, branch_name) from the repo at run time.

    Both values fall back to ``None`` on any subprocess failure (no git, detached
    HEAD, running outside a repo, etc.).  Never raises.
    """

    def _run(args: list[str]) -> str | None:
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:  # noqa: BLE001
            return None

    commit = _run(["git", "rev-parse", "--short", "HEAD"])
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    return commit, branch


def _red_chi2_weighted(
    y: object,
    fit: object,
    sigma: float,
    dof: int,
) -> tuple[float | None, str | None]:
    """Compute σ-weighted reduced-χ²: Σ((y−ŷ)/σ)² / dof.

    Returns ``(value, None)`` when σ > 0 and dof > 0;
    ``(None, reason)`` when undefined (σ == 0, dof ≤ 0, or non-finite result).
    The plain stored ``reduced_chi2`` stays UNWEIGHTED — this is the separate
    σ-weighted goodness-of-fit.
    """
    import numpy as _np

    if sigma <= 0.0:
        return None, "sigma=0 (noiseless)"
    if dof <= 0:
        return None, "dof<=0"
    y_arr = _np.asarray(y, dtype=float)
    fit_arr = _np.asarray(fit, dtype=float)
    chi2 = float(_np.sum(((y_arr - fit_arr) / sigma) ** 2))
    val = chi2 / dof
    if not math.isfinite(val):
        return None, "non-finite result"
    return val, None


def _build_winner_reason(
    winner_id: str,
    baseline_id: str,
    outcomes: dict[str, BackendOutcome | None],
) -> str | None:
    """Build a short human string contrasting winner vs baseline on key signals.

    Uses a declarative signal-extraction approach: each signal defines a
    label and an extractor callable; the function joins the available signals
    into a compact comparison string.

    Returns ``None`` when required data is absent (winner/baseline not in
    outcomes, both missing signals).
    """
    winner_o = outcomes.get(winner_id)
    base_o = outcomes.get(baseline_id)
    if winner_o is None or base_o is None:
        return None

    def _kappa(o: object) -> str | None:
        kappa = getattr(o, "jacobian_condition_number", None)
        if kappa is None or not math.isfinite(kappa):
            return None
        if kappa >= 1_000_000:
            return f"κ≈{kappa:.0e}"
        if kappa >= 1_000:
            return f"κ≈{kappa:.1e}"
        return f"κ≈{kappa:.0f}"

    def _niters(o: object) -> str | None:
        n = getattr(o, "n_iter", None)
        if n is None:
            return None
        return f"{n} iters"

    def _conv_eff(o: object) -> str | None:
        ch = getattr(o, "cost_history", None)
        hs = getattr(o, "history_source", None)
        n_iter = getattr(o, "n_iter", None)
        if not ch or len(ch) < 2 or hs != "real" or not n_iter or n_iter <= 0:
            return None
        # Use o.n_iter (same denominator as the stored convergence_efficiency field
        # in run_suite) so the eff= shown in winner_reason matches convergenceEfficiency.
        eff = (ch[0] - ch[-1]) / n_iter
        if not math.isfinite(eff):
            return None
        return f"eff={eff:.2e}"

    signal_fns = [_kappa, _niters, _conv_eff]

    def _describe(o: object, label: str) -> str:
        parts = [fn(o) for fn in signal_fns]
        parts_str = ", ".join(p for p in parts if p is not None)
        if not parts_str:
            return label
        return f"{label} {parts_str}"

    w_desc = _describe(winner_o, winner_id)
    b_desc = _describe(base_o, baseline_id)
    if w_desc == winner_id and b_desc == baseline_id:
        # Both descriptions are bare labels — no signal data available.
        return None
    return f"{w_desc}; {b_desc}"


# --------------------------------------------------------------------------- #
# Phase helpers (shared across pipelines, all module-private)
# --------------------------------------------------------------------------- #


def _phase_comp_acs(comps: list[Component]) -> list[PeakACS]:
    """Convert a component list (comp_true or comp_guess) to PeakACS records."""
    return [
        PeakACS(
            a=cp.get("amplitude", 0.0),
            c=cp.get("center", 0.0),
            s=cp.get("sigma", 0.0),
        )
        for cp in (c.to_params() for c in comps)
    ]


def _phase_suite_regression(
    backends: Sequence[Backend],
    outcomes: dict[str, BackendOutcome | None],
    case: BenchCase,
) -> bool:
    """Return True if any supported backend failed on *case*.

    Regression policy mirrors the accuracy gate's optfn exclusion
    (``reports.py:_headline``: ``case.category != "optfn"`` filter on |Δr²|).
    optfn cases are multimodal-landscape surrogates that the oracle
    backends are EXPECTED to mis-converge on (CLAUDE.md "Backend
    Comparison Fairness"). Counting an oracle's optfn failure as a
    regression turned every healthy run into a FAIL on the eyes-on-glass
    gate badge — defeating its purpose. The subject (spectrafit) is
    the SUT and IS expected to handle optfn via its global solver, so
    its failure on any category still flags as a regression.
    """
    for b in backends:
        if not b.is_supported(case):
            continue
        o = outcomes.get(b.name)
        if o is None or not o.success:
            if case.category == "optfn" and b.name != "spectrafit":
                continue
            return True
    return False


def _phase_fit_backends(
    backends: Sequence[Backend],
    case: BenchCase,
    n_reps: int,
) -> tuple[dict[str, float], list[FitTriple]]:
    """Cold-time and fit every supported backend once.

    Returns ``(cold, fits)`` where ``cold[name]`` is the pre-warm-up ms
    (NaN for unsupported backends) and ``fits`` is the ordered list of
    successful :class:`FitTriple` records.
    """
    cold: dict[str, float] = {}
    fits: list[FitTriple] = []
    for b in backends:
        cold[b.name] = _cold_ms(b, case) if b.is_supported(case) else float("nan")
        o = _safe_fit(b, case, n_reps)
        if o is not None:
            fits.append(FitTriple(name=b.name, backend=b, outcome=o))
    return cold, fits


def _phase_build_context(
    fits: list[FitTriple],
    baseline_solver_id: str,
    ngrid: list[int],
    n_mc: int,
) -> tuple[float, ProfileContext]:
    """Derive the baseline timing and build the shared :class:`ProfileContext`.

    Returns ``(baseline_ms, ctx)``; ``baseline_ms`` is 1.0 when the named
    solver did not produce a result.
    """
    by_name = {ft.name: ft.outcome for ft in fits}
    baseline = (
        float(np.median(by_name[baseline_solver_id].timing_ms))
        if baseline_solver_id in by_name
        else 1.0
    )
    ctx = ProfileContext(
        baseline=baseline,
        min_aic=min((ft.outcome.aic for ft in fits), default=0.0),
        min_bic=min((ft.outcome.bic for ft in fits), default=0.0),
        ngrid=ngrid,
        n_mc=n_mc,
    )
    return baseline, ctx


# --------------------------------------------------------------------------- #
# Suite
# --------------------------------------------------------------------------- #
def run_suite(
    catalog: Sequence[BenchCase],
    backends: Sequence[Backend],
    n_reps: int = 2,
    baseline_solver_id: str = "lmfit",
) -> list[SuiteCase]:
    """Fit every case with every supported backend → the 139-row suite.

    ``baseline_solver_id`` names the solver whose median runtime is the speedup
    denominator (× 1.0 by construction); was hardcoded ``"lmfit"`` and is now
    threaded through the contract so adding a fourth backend or retiring lmfit
    doesn't ripple across the codebase.
    """
    rows: list[SuiteCase] = []
    for case in catalog:
        outcomes = {b.name: _safe_fit(b, case, n_reps) for b in backends}
        base = outcomes.get(baseline_solver_id)
        base_ms = float(np.median(base.timing_ms)) if base else None
        sigma = float(case.spec.noise)
        metricmap: dict[str, SuiteMetric] = {}
        for name, o in outcomes.items():
            if o is None:
                continue
            med = float(np.median(o.timing_ms))
            # σ-weighted reduced-χ²: defined when σ > 0 (noiseless optfn cases get None).
            dof = max(int(np.asarray(case.y).size) - len(o.params), 1)
            w_chi2, undef_reason = _red_chi2_weighted(case.y, o.best_fit, sigma, dof)
            # convergence_efficiency: only from real cost histories.
            ch = o.cost_history or []
            if o.history_source == "real" and len(ch) >= 2 and o.n_iter > 0:
                ce_val: float = (ch[0] - ch[-1]) / o.n_iter
                ce: float | None = ce_val if math.isfinite(ce_val) else None
            else:
                ce = None
            # ill_conditioned: κ(J) ≥ 1e6 signals a rank-deficient Jacobian.
            kappa = o.jacobian_condition_number
            ill: bool | None = (kappa >= 1e6) if kappa is not None else None
            # Guard non-finite r2/reduced_chi2 at the producer: a model overflow
            # (ss_res=inf → r2=-inf) or chi2/dof with no finite guard (jax/scipy)
            # must NOT raise ValidationError from the contract and sink the run.
            # Treat as a failed fit: success=False + safe finite sentinels.
            r2_raw = o.r2
            chi2_raw = o.reduced_chi2
            _r2_ok = math.isfinite(r2_raw)
            _chi2_ok = math.isfinite(chi2_raw)
            _fit_success = o.success and _r2_ok and _chi2_ok
            metricmap[name] = SuiteMetric(
                speedup=(base_ms / med) if base_ms and med > 0 else 1.0,
                r2=_finite(r2_raw, -1.0),
                red_chi2=_finite(chi2_raw, 0.0),
                med_ms=med,
                param_err=float(np.nan_to_num(o.param_error(case), nan=0.0)),
                success=_fit_success,
                convergence_efficiency=ce,
                ill_conditioned=ill,
                red_chi2_weighted=w_chi2,
                metric_undefined_reason=undef_reason,
            )
        winner = max(
            metricmap, key=lambda s: metricmap[s].r2 * metricmap[s].speedup, default=""
        )
        regression = _phase_suite_regression(backends, outcomes, case)
        winner_reason = _build_winner_reason(winner, baseline_solver_id, outcomes)
        rows.append(
            SuiteCase(
                id=case.id,
                name=case.name,
                category=case.category,
                difficulty=case.difficulty,
                m=metricmap,
                winner=winner,
                regression=regression,
                winner_reason=winner_reason,
            )
        )
    return rows


# --------------------------------------------------------------------------- #
# Featured deep-dive
# --------------------------------------------------------------------------- #


_DECIM_CAP = 200  # max plotted points per analyzed case (keeps 100 cases a few MB)


def _decim_indices(n: int, cap: int = _DECIM_CAP) -> list[int]:
    """Strided, endpoint-preserving indices so a long curve plots at ≤ ``cap`` points.

    The same index set is applied to x/ref/guess and every backend's curve/resid so the
    decimated arrays stay point-aligned. Short curves (``n <= cap``) pass through.
    """
    if n <= cap:
        return list(range(n))
    step = (n - 1) / (cap - 1)
    idx = sorted({int(round(i * step)) for i in range(cap)})
    if idx and idx[-1] != n - 1:
        idx.append(n - 1)
    return idx


def run_featured(
    case: BenchCase,
    backends: Sequence[Backend],
    n_reps: int,
    n_mc: int,
    ngrid: list[int] | None = None,
    with_multidim: bool = False,
    baseline_solver_id: str = "lmfit",
    raw_sink=None,
    audit: bool = False,
) -> Featured:
    """Deep-dive one case into the full Featured contract block.

    Point arrays (x/ref/guess + each backend's curve/resid) are decimated to a shared
    index set so a report carrying many analyzed cases stays a few MB. The heavy 2-D
    ``multidim`` example is attached only when ``with_multidim`` (one case per report).
    """
    ngrid = ngrid if ngrid is not None else _NGRID
    decim = _decim_indices(len(case.x))
    cold, fits = _phase_fit_backends(backends, case, n_reps)
    baseline, ctx = _phase_build_context(fits, baseline_solver_id, ngrid, n_mc)

    profiles = {
        ft.name: _build_profile(
            ft.backend,
            ft.outcome,
            case,
            cold[ft.name],
            ctx,
            decim,
            raw_sink=raw_sink,
            audit=audit,
        )
        for ft in fits
    }

    scross = profiles["spectrafit"].scaling if "spectrafit" in profiles else []
    jcross = profiles["jax"].scaling if "jax" in profiles else scross
    cross_n = _finite(
        _crossover(scross, jcross) if scross and jcross else float(ngrid[-1]),
        float(ngrid[-1]),
    )
    by_name = {ft.name: ft.outcome for ft in fits}
    guess_curve = curve(case.x, case.comp_guess)
    xs, refs, gss = case.x.tolist(), case.y.tolist(), guess_curve.tolist()

    # Nested-model adequacy V&V: fit orders m*−1/m*/m*+1 on the subject and verify
    # that model-selection criteria (LRT/F/AIC/BIC) recover the known generative order.
    # Only computed for cases with a known order (synthetic, at least 2 peaks).
    sf_backend = next((b for b in backends if b.name == "spectrafit"), None)
    nested_adequacy_result = _run_nested_adequacy(case, sf_backend)

    # Code provenance: source file + formula from the oracle model registry.
    # Takes the model of the first component (the primary shape of the case).
    model_source_file: str | None = None
    model_formula: str | None = None
    components = getattr(case.spec, "components", [])
    if components:
        first_model_key = getattr(components[0], "model", None)
        if first_model_key is not None:
            try:
                peak_model = get_model(first_model_key)
                # Source file: explicit key→file map for divergent keys; default {key}.rs.
                _src_filename = _MODEL_SOURCE_MAP.get(
                    first_model_key, f"{first_model_key}.rs"
                )
                model_source_file = f"crates/spectrafit-models/src/{_src_filename}"
                # Formula from registry (empty string → None).
                model_formula = peak_model.formula_latex or None
            except KeyError:
                pass  # landscape / optfn cases without a registered peak model

    return Featured(
        id=case.id,
        name=case.name,
        category=case.category,
        x=[xs[i] for i in decim],
        ref=[refs[i] for i in decim],
        guess=[gss[i] for i in decim],
        truth=_phase_comp_acs(case.comp_true),
        guess_params=_phase_comp_acs(case.comp_guess),
        noise=case.spec.noise,
        baseline=baseline,
        profiles=profiles,
        peaks=[
            Peak(label=p.label, y=[p.y[i] for i in decim])
            for p in _peak_contributions(case, by_name.get("spectrafit"))
        ],
        param_names=list(case.true_params.keys()),
        corr=_correlation(case),
        n_grid=ngrid,
        schedule=_WARMUP_SCHED,
        runs_sched=_RUNS_SCHED,
        cross_n=cross_n,
        multidim=_multidim() if with_multidim else None,
        global_fit=_global_fit() if with_multidim else None,
        nested_adequacy=nested_adequacy_result,
        model_source_file=model_source_file,
        model_formula=model_formula,
        fixed_params=case.spec.fixed_params,
        expr_edges=[ExprEdge.model_validate(e) for e in case.spec.expr_edges],
    )


# --------------------------------------------------------------------------- #
# Top-level
# --------------------------------------------------------------------------- #
def _select_analyzed(
    catalog: Sequence[BenchCase], analyzed_ids: list[str] | None
) -> list[BenchCase]:
    """Choose the cases rendered in full detail (selectable/plottable in the UI).

    ``analyzed_ids`` overrides explicitly. Otherwise **every case is analyzed**:
    every category (``edge`` / ``easy`` / ``complex`` / ``scaling`` / ``lineshapes`` /
    ``reality`` / ``optfn``) becomes deep-divable in the selector.

    ``optfn`` cases fit a 2-Gaussian surrogate to a multimodal landscape
    (``recover=False``); the standard ``Featured`` panels still render usefully —
    the surrogate curve overlaid on e.g. ackley / rastrigin shows where local
    solvers got trapped vs where global solvers (DE) found the basin. Per-peak
    recovery metrics are meaningless for these, but the spectrum / residuals /
    convergence / accuracy panels tell the global-vs-local story directly.
    """
    by_id = {c.id: c for c in catalog}
    if analyzed_ids is not None:
        return [by_id[i] for i in analyzed_ids if i in by_id] or [
            featured_case(catalog)
        ]

    selected = list(catalog)
    return selected or [featured_case(catalog)]


def _phase_run_analyzed(
    selected: list[BenchCase],
    backends: Sequence[Backend],
    n_reps: int,
    n_mc: int,
    ngrid: list[int] | None,
    baseline_solver_id: str,
    raw_sink=None,
    audit: bool = False,
) -> list[Featured]:
    """Deep-dive each selected case; use lighter settings when there are many.

    A multi-case analyzed set gets fewer MC reps and a coarser scaling grid so
    the run stays tractable and the payload stays a few MB.
    """
    light = len(selected) > 1
    a_mc = max(4, n_mc // 4) if light else n_mc
    a_ngrid = [128, 512, 2048] if (light and ngrid is None) else ngrid
    return [
        run_featured(
            c,
            backends,
            n_reps=n_reps,
            n_mc=a_mc,
            ngrid=a_ngrid,
            with_multidim=(idx == 0),
            baseline_solver_id=baseline_solver_id,
            raw_sink=raw_sink,
            audit=audit,
        )
        for idx, c in enumerate(selected)
    ]


def build_report(
    n_reps: int = 5,
    n_mc: int = 20,
    seed: int = 20260603,
    catalog: Sequence[BenchCase] | None = None,
    backends: Sequence[Backend] | None = None,
    ngrid: list[int] | None = None,
    analyzed_ids: list[str] | None = None,
    baseline_solver_id: str = "lmfit",
    audit_sink: dict | None = None,
) -> BenchReport:
    """Run the benchmark and assemble the report payload.

    ``catalog`` / ``backends`` / ``ngrid`` are injectable for fast tests; they
    default to the full 139-case catalog, all available backends, and the full
    scaling grid. ``baseline_solver_id`` (was implicitly ``"lmfit"``) names the
    solver whose median timing defines speedup = 1.0 and is recorded on the
    returned ``BenchReport`` so consumers can label their charts without
    guessing slot positions.

    ``audit_sink``, when provided, receives the full per-(case, backend) arrays
    for exact wire recompute. The default ``None`` captures nothing (lean path).
    """
    # Capture git provenance + run timestamp at the very start of the run.
    git_commit, git_branch = _capture_git_provenance()
    run_timestamp_unix = int(time.time())

    catalog = list(catalog) if catalog is not None else build_catalog(seed)
    backends = list(backends) if backends is not None else get_backends()
    suite = run_suite(
        catalog,
        backends,
        n_reps=max(1, n_reps // 2),
        baseline_solver_id=baseline_solver_id,
    )
    # `analyzed`: cases rendered in full detail (selectable in the UI).
    # `analyzed_ids` overrides; default is every case. A tiny catalog with no
    # peak-fit cases falls back to the featured case.
    selected = _select_analyzed(catalog, analyzed_ids)
    audit = audit_sink is not None
    raw_sink: dict[tuple[str, str], dict] = audit_sink if audit_sink is not None else {}
    analyzed = _phase_run_analyzed(
        selected,
        backends,
        n_reps,
        n_mc,
        ngrid,
        baseline_solver_id,
        raw_sink=raw_sink,
        audit=audit,
    )
    report = BenchReport(
        solvers=SOLVER_META,
        categories=_CATEGORY_META,
        analyzed=analyzed,
        suite=suite,
        baseline_solver_id=baseline_solver_id,
        panels=default_panels(),
        git_commit=git_commit,
        git_branch=git_branch,
        run_timestamp_unix=run_timestamp_unix,
    )
    # Populate `manifest` so the web GateBadge can render the four gate numbers
    # (geomean / max |Δr²| / win-rate / pinned ratio) from the typed contract
    # instead of telling the user to run `spc-bench show-baseline`.
    # `compute_manifest_signals` shares math with `_headline` so the dict and
    # the contract field cannot drift.
    from oracles.reports import compute_manifest_signals

    report = report.model_copy(update={"manifest": compute_manifest_signals(report)})
    from oracles.inference_report import compute_inference

    report = report.model_copy(
        update={"inference": compute_inference(report, raw_sink)}
    )
    return report
