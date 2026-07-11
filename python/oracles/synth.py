"""Deterministic synthetic ``BenchReport`` builder.

A small, seeded, contract-valid report used to (a) prove the :mod:`contract` is
complete, (b) give the ``web/`` UI a fixture to build against before the real
engine (Phase 4) exists, and (c) drive the round-trip schema test. It mirrors
the essential structure of the ``BenchReport`` contract at reduced size.

NOT a benchmark: the numbers are plausible but synthetic. The real engine
(``oracles.engine``) emits the same shape from actual fits.
"""

from __future__ import annotations

import math
import random

import numpy as np
from pydantic import BaseModel, ConfigDict

from oracles import models
from oracles.cases import (
    CATEGORY_COUNTS,
    CATEGORY_HUE,
    CATEGORY_LABELS,
    PREFIX,
    SOLVER_META,
)
from oracles.bench_contract import (
    AccuracyDist,
    BackendProfile,
    BenchReport,
    CategoryMeta,
    Featured,
    MultiDim,
    NdPeak,
    Peak,
    PeakACS,
    Point2D,
    Projection,
    SolverFit,
    SpreadPt,
    StabilityEntry,
    Summary,
    SuiteCase,
    SuiteMetric,
    TimingDist,
    Uncertainty,
    Warmup,
    WarmupPt,
)
from oracles.metrics import pcts

_CATEGORIES = [
    CategoryMeta(id=cid, label=CATEGORY_LABELS[cid], n=n, hue=CATEGORY_HUE[cid])
    for cid, n in CATEGORY_COUNTS.items()
]
_SOLVER_IDS = [s.id for s in SOLVER_META]
_QS = (0.05, 0.25, 0.50, 0.75, 0.95)


def _g(xi: float, a: float, c: float, s: float) -> float:
    """Scalar wrapper over the canonical :func:`models.gaussian` for fixture data."""
    return float(models.gaussian(np.array([xi]), amplitude=a, center=c, sigma=s)[0])


# ---------------------------------------------------------------------------
# Phase helpers — pydantic-first wrappers for the four logical groups of
# fields that the `Featured` synthetic builder fills. Each helper preserves
# the original RNG draw order; reordering any call here will silently shift
# the deterministic JSON output and break the byte-identical regression
# guard in tests/unit/oracles/test_build_featured_phases.py.
# ---------------------------------------------------------------------------


class _FeaturedGrid(BaseModel):
    """Truth peaks + grid + ref/guess curves for the synthetic featured case."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    x: list[float]
    truth: list[PeakACS]
    ref: list[float]
    guess_p: list[PeakACS]
    guess: list[float]
    noise: float


class _FeaturedTimings(BaseModel):
    """Per-solver timing knobs + scaling/warmup schedules (no RNG draws)."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    perturb: dict[str, float]
    base_ms: dict[str, float]
    n_grid: list[int]
    schedule: list[int]
    runs_sched: list[int]
    param_names: list[str]
    n_params: int


class _FeaturedProfiles(BaseModel):
    """Per-solver :class:`BackendProfile` map + the raw fit-param peaks."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    profiles: dict[str, BackendProfile]
    fit_params: dict[str, list[PeakACS]]


class _FeaturedExtras(BaseModel):
    """Trailing fields: peak overlays, parameter correlation, 2-D map."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    peaks: list[Peak]
    corr: list[list[float]]
    multidim: MultiDim


class _SolverFitBlock(BaseModel):
    """Perturbed fit peaks + the curve/resid pair derived from them."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    pf: list[PeakACS]
    curve: list[float]
    resid: list[float]


class _SolverStatsBlock(BaseModel):
    """Sampled timing + accuracy distributions for one solver."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    raw_t: list[float]
    timing: TimingDist
    raw_a: list[float]
    a5: float
    a25: float
    amed: float
    a75: float
    med: float
    p75: float


def _build_featured_truth_and_grid(rng: random.Random, n: int) -> _FeaturedGrid:
    """Build the truth peaks, grid, noisy ref curve, and initial-guess curve.

    The single RNG draw block is the ``rng.gauss(0, noise)`` per grid point
    that perturbs the truth into the observed ``ref``.
    """
    x = [(-5.2 + 10.4 * i / (n - 1)) for i in range(n)]
    truth = [
        PeakACS(a=4.95, c=0.0, s=1.0),
        PeakACS(a=2.30, c=-2.5, s=0.6),
        PeakACS(a=1.65, c=2.4, s=0.8),
    ]
    noise = 0.085
    ref = [sum(_g(xi, p.a, p.c, p.s) for p in truth) + rng.gauss(0, noise) for xi in x]
    guess_p = [
        PeakACS(a=4.2, c=0.18, s=1.18),
        PeakACS(a=1.9, c=-2.2, s=0.75),
        PeakACS(a=1.3, c=2.7, s=1.0),
    ]
    guess = [sum(_g(xi, p.a, p.c, p.s) for p in guess_p) for xi in x]
    return _FeaturedGrid(
        x=x, truth=truth, ref=ref, guess_p=guess_p, guess=guess, noise=noise
    )


def _build_featured_per_solver_timings() -> _FeaturedTimings:
    """Per-solver noise + base timing constants. No RNG draws.

    The scipy-ls trio adds LM-class defaults similar to lmfit's 4.9 ms
    baseline (they share the same MINPACK kernel for ``lm`` and the same
    trust-region family for ``trf``/``dogbox``). Values are representative
    for the synthetic render smoke; real timings come from
    :func:`engine.run_suite`.
    """
    perturb = {
        "spectrafit": 0.004,
        "lmfit": 0.0045,
        "jax": 0.006,
        "scipy-ls-lm": 0.0048,
        "scipy-ls-trf": 0.0050,
        "scipy-ls-dogbox": 0.0052,
    }
    base_ms = {
        "spectrafit": 4.1,
        "lmfit": 4.9,
        "jax": 7.2,
        "scipy-ls-lm": 4.6,
        "scipy-ls-trf": 4.8,
        "scipy-ls-dogbox": 5.0,
    }
    # Aligned with the engine constants (_NGRID / _WARMUP_SCHED / _RUNS_SCHED).
    n_grid = [128, 256, 512, 1024, 2048, 4096]
    schedule = [1, 5, 10, 25, 50, 100]
    runs_sched = [1, 2, 5, 10, 25, 50]
    param_names: list[str] = [
        f"{lbl}.{p}"
        for lbl in ("g1", "g2", "g3")
        for p in ("amplitude", "center", "sigma")
    ]
    return _FeaturedTimings(
        perturb=perturb,
        base_ms=base_ms,
        n_grid=n_grid,
        schedule=schedule,
        runs_sched=runs_sched,
        param_names=param_names,
        n_params=len(param_names),
    )


def _stab_entry(idx: int, runs_sched: list[int]) -> StabilityEntry:
    """Synthetic stability spread per backend (indexed by solver position)."""
    return StabilityEntry(
        r2=[SpreadPt(n=k, mean=1.0, sd=0.5 / math.sqrt(k)) for k in runs_sched],
        rmse=[SpreadPt(n=k, mean=0.09, sd=0.02 / math.sqrt(k)) for k in runs_sched],
        red_chi2=[
            SpreadPt(n=k, mean=1.0, sd=0.3 / math.sqrt(k)) for k in runs_sched
        ],
        iters=[
            SpreadPt(n=k, mean=7.0 + idx, sd=1.0 / math.sqrt(k)) for k in runs_sched
        ],
    )


def _draw_solver_fit_block(
    rng: random.Random,
    *,
    sid: str,
    grid: _FeaturedGrid,
    timings: _FeaturedTimings,
    n: int,
) -> _SolverFitBlock:
    """Perturb the truth peaks for one solver and derive the curve + residuals.

    RNG draws: three ``rng.gauss`` per truth peak (amplitude, center, sigma).
    """
    perturb_sd = timings.perturb[sid]
    pf = [
        PeakACS(
            a=p.a * (1 + rng.gauss(0, perturb_sd)),
            c=p.c + rng.gauss(0, perturb_sd * 0.6),
            s=p.s * (1 + rng.gauss(0, perturb_sd)),
        )
        for p in grid.truth
    ]
    curve = [sum(_g(xi, p.a, p.c, p.s) for p in pf) for xi in grid.x]
    resid = [grid.ref[i] - curve[i] for i in range(n)]
    return _SolverFitBlock(pf=pf, curve=curve, resid=resid)


def _draw_solver_stats_block(
    rng: random.Random, *, sid: str, timings: _FeaturedTimings
) -> _SolverStatsBlock:
    """Sample timing + accuracy distributions for one solver.

    RNG draws: 60 timing samples then 60 accuracy samples, in that order.
    """
    ms = timings.base_ms[sid]
    raw_t = [max(0.1, rng.gauss(ms, ms * 0.08)) for _ in range(60)]
    p5, p25, med, p75, p95 = pcts(raw_t, _QS)
    mean = sum(raw_t) / len(raw_t)
    timing = TimingDist(
        raw=raw_t,
        median=med,
        mean=mean,
        p5=p5,
        p25=p25,
        p75=p75,
        p95=p95,
        iqr=p75 - p25,
        cv=100 * (sum((v - mean) ** 2 for v in raw_t) / len(raw_t)) ** 0.5 / mean,
    )
    raw_a = [max(1e-4, rng.gauss(0.0078, 0.0008)) for _ in range(60)]
    a5, a25, amed, a75, _ = pcts(raw_a, _QS)
    return _SolverStatsBlock(
        raw_t=raw_t,
        timing=timing,
        raw_a=raw_a,
        a5=a5,
        a25=a25,
        amed=amed,
        a75=a75,
        med=med,
        p75=p75,
    )


def _assemble_backend_profile(
    rng: random.Random,
    *,
    idx: int,
    sid: str,
    n: int,
    fit_block: _SolverFitBlock,
    stats: _SolverStatsBlock,
    timings: _FeaturedTimings,
) -> BackendProfile:
    """Stitch the fit + stats blocks into a complete :class:`BackendProfile`.

    RNG draws (after fit + stats already drew): 90 uncertainty pulls, then
    ``len(param_names)`` ``rng.gauss`` for ``param_err``, then
    ``len(n_grid)`` ``rng.gauss`` for ``scaling``.
    """
    ms = timings.base_ms[sid]
    amed, med, p75 = stats.amed, stats.med, stats.p75
    timing = stats.timing
    n_iter = 7 + idx
    summary = Summary(
        r2=0.9973 - 0.0003 * idx,
        chi2=amed * (n - 9),
        red_chi2=amed,
        rmse=0.09 + 0.01 * idx,
        mae=0.07,
        n_iter=n_iter,
        med_ms=med,
        iqr_ms=p75 - timing.p25,
        cv=timing.cv,
        speedup=timings.base_ms["lmfit"] / med,
        success=True,
        aic=-540.0 + 6 * idx,
        bic=-520.0 + 6 * idx,
        d_aic=6.0 * idx,
        d_bic=6.0 * idx,
    )

    c0 = amed * (n - 9) * 80
    conv = [
        amed * (n - 9) + (c0 - amed * (n - 9)) * math.exp(-0.7 * i)
        for i in range(n_iter)
    ]
    a, b = ms / 1500.0, ms * 0.6
    cold = ms * (6.0 if sid == "jax" else 1.4)
    pulls = [rng.gauss(0, 1.0 + 0.1 * idx) for _ in range(90)]

    return BackendProfile(
        fit=SolverFit(params=fit_block.pf, curve=fit_block.curve, resid=fit_block.resid),
        conv=conv,
        grad=[
            math.sqrt(max(c, 1e-9)) * math.exp(-0.6 * i) for i, c in enumerate(conv)
        ],
        # history_source is "reconstructed" here, so conv_eff stays None (EF-PY-11):
        # a proxy-derived efficiency must not be presented as a measured series.
        conv_eff=None,
        history_source="reconstructed",
        timing=timing,
        accuracy=AccuracyDist(
            raw=stats.raw_a, median=amed, p5=stats.a5, p25=stats.a25, p75=stats.a75
        ),
        summary=summary,
        param_err=[
            abs(rng.gauss(0, timings.perturb[sid])) * 100 for _ in timings.param_names
        ],
        ecdf_resid=[Point2D(x=k / 30 * 3, y=k / 30) for k in range(31)],
        ecdf_time=[
            Point2D(x=sorted(stats.raw_t)[min(k, len(stats.raw_t) - 1)], y=k / 60)
            for k in range(61)
        ],
        warmup=Warmup(
            curve=[
                Point2D(x=k, y=(cold + ms * (k - 1)) / k) for k in range(1, 101)
            ],
            pts=[
                WarmupPt(n=k, per_run=(cold + ms * (k - 1)) / k)
                for k in timings.schedule
            ],
            hot_throughput=1000.0 / ms,
            cold_ms=cold,
            hot_ms=ms,
        ),
        scaling=[
            Point2D(x=nn, y=a * nn + b + rng.gauss(0, 0.04 * b))
            for nn in timings.n_grid
        ],
        uncertainty=Uncertainty(
            pulls=pulls,
            coverage=sum(1 for v in pulls if abs(v) < 1) / len(pulls),
            sigma=[0.01 + 0.002 * j for j in range(timings.n_params)],
        ),
        param_spread=[
            SpreadPt(n=k, mean=0.0, sd=timings.perturb[sid] * 100 / math.sqrt(k))
            for k in timings.runs_sched
        ],
        stability=_stab_entry(idx, timings.runs_sched),
    )


def _build_featured_per_solver_profile(
    rng: random.Random,
    *,
    idx: int,
    sid: str,
    grid: _FeaturedGrid,
    timings: _FeaturedTimings,
    n: int,
) -> tuple[BackendProfile, list[PeakACS]]:
    """Build the per-solver :class:`BackendProfile` + perturbed fit peaks.

    The RNG draw order is **load-bearing** — three gaussians per truth peak
    for the perturbed fit params, then 60 timing samples, then 60 accuracy
    samples, then 90 uncertainty pulls, then one ``rng.gauss`` per param for
    ``param_err``, then one ``rng.gauss`` per grid point for ``scaling``.
    """
    fit_block = _draw_solver_fit_block(rng, sid=sid, grid=grid, timings=timings, n=n)
    stats = _draw_solver_stats_block(rng, sid=sid, timings=timings)
    profile = _assemble_backend_profile(
        rng, idx=idx, sid=sid, n=n, fit_block=fit_block, stats=stats, timings=timings
    )
    return profile, fit_block.pf


def _build_featured_per_solver_profiles(
    rng: random.Random,
    *,
    grid: _FeaturedGrid,
    timings: _FeaturedTimings,
    n: int,
) -> _FeaturedProfiles:
    """Iterate the canonical solver roster and assemble all profiles."""
    profiles: dict[str, BackendProfile] = {}
    fit_params: dict[str, list[PeakACS]] = {}
    for idx, sid in enumerate(_SOLVER_IDS):
        profile, pf = _build_featured_per_solver_profile(
            rng, idx=idx, sid=sid, grid=grid, timings=timings, n=n
        )
        fit_params[sid] = pf
        profiles[sid] = profile
    return _FeaturedProfiles(profiles=profiles, fit_params=fit_params)


def _build_featured_extras(
    rng: random.Random,
    *,
    grid: _FeaturedGrid,
    timings: _FeaturedTimings,
    fit_params: dict[str, list[PeakACS]],
) -> _FeaturedExtras:
    """Build peak overlays, the parameter correlation matrix, and the 2-D map.

    RNG order: ``corr`` (one draw per off-diagonal cell) → 2-D ``obs``
    (one draw per pixel) → ``projections`` (one draw per matrix cell).
    """
    sf = fit_params["spectrafit"]
    x = grid.x
    n_params = timings.n_params
    peaks = [
        Peak(label=f"g{k + 1}", y=[_g(xi, sf[k].a, sf[k].c, sf[k].s) for xi in x])
        for k in range(3)
    ]
    corr = [
        [1.0 if i == j else round(rng.gauss(0, 0.2), 3) for j in range(n_params)]
        for i in range(n_params)
    ]

    multidim = MultiDim(
        n_dims=3,
        shape=[12, 12, 12],
        n_points=12**3,
        r_squared=0.998,
        peaks=[NdPeak(amplitude=8.0, center=[10.0, 9.0, 5.0], sigma=[3.0, 4.0, 2.5])],
        projections=[
            Projection(
                labels=("E_in", "E_out"),
                matrix=[[rng.random() for _ in range(8)] for _ in range(8)],
            )
        ],
    )
    return _FeaturedExtras(peaks=peaks, corr=corr, multidim=multidim)


def build_featured(rng: random.Random, n: int = 48) -> Featured:
    """Build a tri-Gaussian featured case filling every contract field."""
    grid = _build_featured_truth_and_grid(rng, n)
    timings = _build_featured_per_solver_timings()
    bundle = _build_featured_per_solver_profiles(
        rng, grid=grid, timings=timings, n=n
    )
    extras = _build_featured_extras(
        rng, grid=grid, timings=timings, fit_params=bundle.fit_params
    )
    return Featured(
        id="RL-031",
        name="tri-gaussian · reality-like + 8.5% noise",
        category="reality",
        x=grid.x,
        ref=grid.ref,
        guess=grid.guess,
        truth=grid.truth,
        noise=grid.noise,
        baseline=timings.base_ms["lmfit"],
        profiles=bundle.profiles,
        peaks=extras.peaks,
        param_names=timings.param_names,
        corr=extras.corr,
        n_grid=timings.n_grid,
        schedule=timings.schedule,
        runs_sched=timings.runs_sched,
        cross_n=3100.0,
        multidim=extras.multidim,
    )


def build_suite(rng: random.Random) -> list[SuiteCase]:
    """Build a representative suite spanning the 5 categories (108 cases)."""
    out: list[SuiteCase] = []
    for cat in _CATEGORIES:
        for k in range(cat.n):
            m: dict[str, SuiteMetric] = {}
            for sid in _SOLVER_IDS:
                # Mirror real data: jax is unsupported on multimodal/global (optfn)
                # cases, so it is absent from `m` there. Keeping the fixture realistic
                # means the render smoke exercises the missing-backend code paths.
                if cat.id == "optfn" and sid == "jax":
                    continue
                m[sid] = SuiteMetric(
                    speedup=max(0.5, rng.gauss(1.3, 0.4)),
                    r2=min(1.0, max(0.0, rng.gauss(0.97, 0.05))),
                    red_chi2=max(1e-3, rng.gauss(0.02, 0.01)),
                    med_ms=max(0.2, rng.gauss(5, 1.5)),
                    param_err=abs(rng.gauss(0, 2)),
                    success=rng.random() > 0.03,
                )
            winner = max(m, key=lambda s: m[s].r2 * m[s].speedup)
            out.append(
                SuiteCase(
                    id=f"{PREFIX[cat.id]}-{k + 1:03d}",
                    name=f"{cat.label.lower()} case {k + 1}",
                    category=cat.id,
                    difficulty=round(rng.random(), 3),
                    m=m,
                    winner=winner,
                    regression=any(not v.success for v in m.values()),
                )
            )
    return out


def build_report(seed: int = 20260602) -> BenchReport:
    """Build a complete, deterministic, contract-valid :class:`BenchReport`."""
    from oracles.bench_contract import ManifestSignals

    rng = random.Random(seed)
    return BenchReport(
        solvers=SOLVER_META,
        categories=_CATEGORIES,
        analyzed=[build_featured(rng)],
        suite=build_suite(rng),
        # Deterministic plausible defaults for the GateBadge; the synthetic
        # fixture is used by the FastAPI smoke (no real fits), so the numbers
        # are pinned rather than derived from `_compute_headline_numbers` over
        # the random suite. Real runs go through `engine.build_report` which
        # calls `compute_manifest_signals(report)` for the live numbers.
        manifest=ManifestSignals(
            geomean_speedup_vs_baseline=12.0,
            max_abs_delta_r2=1.0e-4,
            spectrafit_win_rate=0.86,
            regressions=0,
            pinned=None,
        ),
    )
