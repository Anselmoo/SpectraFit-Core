"""Assemble the inference block from a fully-built report + a transient raw sink.

Reads the assembled :class:`BenchReport` (suite for category grouping + winner
scores) and a transient ``raw_sink`` populated during the analyzed phase
(``{(case_id, backend): {"timing": [...], "r2": [...]}}``), and returns an
:class:`InferenceBlock`. The raw arrays are bootstrapped then discarded — they
never enter the payload. Mirrors ``reports.compute_manifest_signals``: pure
function of the assembled report (+ sink), attached via ``model_copy``.
"""

from __future__ import annotations

import numpy as np

from oracles.bench_contract import (
    CI,
    BenchReport,
    CalibrationResult,
    CaseInference,
    EquivalenceResult,
    InferenceBlock,
    InferenceConfig,
    SpeedInferenceResult,
)
from oracles.inference import (
    CalibrationStat,
    SpeedStat,
    coverage_test,
    delta_r2_ci,
    geomean_speedup_test,
    speedup_ci,
    tost_paired,
    winner_stability,
)

DEFAULT_CONFIG = InferenceConfig(
    equivalence_margin=1e-3, bootstrap_b=2000, seed=20260612, fdr_q=0.05
)


def compute_inference(
    report: BenchReport,
    raw_sink: dict[tuple[str, str], dict[str, list[float]]],
    config: InferenceConfig | None = None,
) -> InferenceBlock:
    """Bootstrap CIs + TOST equivalence + winner stability from the raw sink."""
    cfg = config or DEFAULT_CONFIG
    baseline = report.baseline_solver_id

    # ---- per-case CIs (subject = best non-baseline by mean-r2 * speedup) ----
    case_ids = sorted({cid for (cid, _b) in raw_sink})
    cases: list[CaseInference] = []
    for cid in case_ids:
        pb = {b: raw_sink[(c, b)] for (c, b) in raw_sink if c == cid}
        base = pb.get(baseline)
        subjects = [b for b in pb if b != baseline and pb[b]["timing"] and pb[b]["r2"]]
        if base is None or not base["timing"] or not subjects:
            continue

        def _score(bn: str, base=base, pb=pb) -> float:
            d = pb[bn]
            sp = float(np.median(base["timing"]) / np.median(d["timing"]))
            return float(np.mean(d["r2"])) * sp

        subj = pb[max(subjects, key=_score)]
        sp_lo, sp_pt, sp_hi = speedup_ci(
            base["timing"], subj["timing"], b=cfg.bootstrap_b, alpha=0.05, seed=cfg.seed
        )
        dr_lo, dr_pt, dr_hi = delta_r2_ci(
            subj["r2"],
            base["r2"],
            b_resamples=cfg.bootstrap_b,
            alpha=0.05,
            seed=cfg.seed,
        )
        cases.append(
            CaseInference(
                case_id=cid,
                speedup_ci=CI(lo=sp_lo, point=sp_pt, hi=sp_hi),
                delta_r2_ci=CI(lo=dr_lo, point=dr_pt, hi=dr_hi),
            )
        )

    # ---- per-category equivalence (TOST): EVERY non-baseline backend vs baseline ----
    equivalence: list[EquivalenceResult] = []
    cats: dict[str, list] = {}
    for sc in report.suite:
        cats.setdefault(sc.category, []).append(sc)
    for cat, rows in cats.items():
        backends = {b for r in rows for b in r.m} - {baseline}
        worst_diff = 0.0
        all_equiv = True
        tested_any = False
        for bn in sorted(backends):
            # PAIRED per-case Δr² (subject − baseline) on cases where BOTH ran.
            # Paired is correct here: an unpaired test would inflate the SE with
            # case-to-case r² spread and wrongly reject equivalence (the
            # saturation claim is a per-case backend comparison, not a
            # comparison of category means).
            deltas = [
                r.m[bn].r2 - r.m[baseline].r2
                for r in rows
                if bn in r.m and baseline in r.m
            ]
            if len(deltas) < 2:
                continue
            tested_any = True
            v = tost_paired(deltas, margin=cfg.equivalence_margin, alpha=0.05)
            all_equiv = all_equiv and v.equivalent
            worst_diff = max(worst_diff, abs(v.diff))
        all_equiv = all_equiv and tested_any
        equivalence.append(
            EquivalenceResult(
                category=cat,
                equivalent=all_equiv,
                margin=cfg.equivalence_margin,
                diff=worst_diff,
            )
        )

    # ---- winner stability (suite-wide; score = r2 * speedup) ----
    scores: dict[str, list[float]] = {}
    for sc in report.suite:
        for bn, m in sc.m.items():
            scores.setdefault(bn, []).append(m.r2 * m.speedup)
    n = len(report.suite)
    scores = {k: v for k, v in scores.items() if len(v) == n}  # aligned vectors only
    stab = winner_stability(scores, b=cfg.bootstrap_b, seed=cfg.seed) if scores else {}

    # ---- calibration: aggregate subject pulls from all deep-dive analyzed cases ----
    # The subject is identified by history_source == "real" (only the subject records
    # a measured convergence history; oracle backends are "reconstructed"). This is
    # subject-blind — no backend id is hardcoded.
    pulls: list[float] = [
        p
        for f in report.analyzed
        for _sid, prof in f.profiles.items()
        if prof.history_source == "real"
        for p in prof.uncertainty.pulls
    ]
    cal_stat: CalibrationStat = coverage_test(
        pulls,
        nominal=cfg.coverage_nominal,
        alpha=cfg.alpha_calibration,
        min_pulls=cfg.min_pulls,
        equivalence_margin=cfg.calibration_margin,
    )
    # Engine→contract bridge: snake_case model_dump() keys are accepted by the
    # contract views because _Base sets populate_by_name=True (do not remove that).
    calibration = CalibrationResult.model_validate(cal_stat.model_dump())

    # ---- speed inference: bootstrap CI over per-case subject speedups ----
    # Reuse the point estimates already computed in `cases`; no backend id hardcoded.
    #
    # NOTE (W11 subject framing, I2): the per-case speedup here is the speedup of the
    # *best non-baseline backend* selected by composite score (r2 * speedup), NOT
    # strictly the history_source=="real" subject used by W10 calibration (lines above).
    # On the current roster spectrafit dominates every case, so the two selections are
    # identical in practice — but the selection criterion differs.  The W11 claim is
    # therefore "the best-performing non-baseline backend per case is significantly
    # faster than the baseline", not the more specific "the subject (history_source==real)
    # is faster".  The dashboard wording is aligned to this: see inferentialHeadline.tsx
    # speedBody and standing.tsx W11 disclosure text.
    speedups: list[float] = [c.speedup_ci.point for c in cases]
    spd_stat: SpeedStat = geomean_speedup_test(
        speedups,
        b=cfg.bootstrap_b,
        seed=cfg.seed,
        alpha=cfg.alpha_speed,
    )
    # Engine→contract bridge: snake_case model_dump() keys are accepted by the
    # contract views because _Base sets populate_by_name=True (do not remove that).
    speed_inference = SpeedInferenceResult.model_validate(spd_stat.model_dump())

    return InferenceBlock(
        config=cfg,
        cases=cases,
        equivalence=equivalence,
        winner_stability=stab,
        calibration=calibration,
        speed_inference=speed_inference,
    )
