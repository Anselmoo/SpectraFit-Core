"""Reps-ladder stability study — variance-vs-N data for the paper's uncertainty section.

``spc-bench stability <dir>`` aggregates a *ladder* of benchmark runs executed at
increasing ``--reps`` budgets (``reps-1/`` … ``reps-100/``, each holding one
contract-valid ``results.json``) into per-backend convergence data: how the
suite-level headline numbers (geomean speedup, median speedup, median per-case
runtime) move as the timing-repetition budget grows, and at which budget the
measurement stops moving.

This module is a **CI artifact schema**, NOT the frozen wire contract — the
:class:`StabilityStudy` model deliberately lives here and not in
``oracles.bench_contract`` so the web/OpenAPI surface stays untouched. The consumer
is the ``benchmark:deep:merge`` GitLab job (``.gitlab/55-deep-bench.yml``) and,
downstream, the manuscript's measurement-uncertainty section.

Conventions (per CLAUDE.md): pydantic-first models, ``match``/``case`` dispatch,
no per-call maps.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from statistics import median

from pydantic import BaseModel, ConfigDict, Field

from oracles.bench_contract import BenchReport

#: Relative tolerance for the "measurement converged" verdict: the smallest reps
#: budget where EVERY backend's geomean speedup sits within this band of its
#: reference-budget (highest-reps, normally N=100) value.
CONVERGENCE_RTOL: float = 0.02

_REPS_DIR_RE = re.compile(r"^reps-(\d+)$")


class LadderRunFile(BaseModel):
    """One discovered ``reps-N/results.json`` entry in a ladder directory."""

    model_config = ConfigDict(extra="forbid")

    reps: int = Field(gt=0)
    results_path: Path


class LadderLayout(BaseModel):
    """Validated discovery result for a reps-ladder directory.

    ``runs`` requires at least one entry: pointing the stability command at a
    directory with no ``reps-N`` subdirectories is a caller error and surfaces
    as a pydantic ``ValidationError`` at this chokepoint rather than as an
    empty study downstream.
    """

    model_config = ConfigDict(extra="forbid")

    root: Path
    runs: list[LadderRunFile] = Field(min_length=1)


class BackendHeadline(BaseModel):
    """Suite-level headline numbers for one backend in one run."""

    model_config = ConfigDict(extra="forbid")

    geomean_speedup: float
    median_speedup: float
    median_ms: float


class StabilityPoint(BaseModel):
    """One backend's headline numbers at one reps budget.

    The ``rel_dev_*`` fields are the relative half-width vs the reference
    (highest-reps) run: ``abs(v_N - v_ref) / v_ref``.
    """

    model_config = ConfigDict(extra="forbid")

    reps: int
    geomean_speedup: float
    median_speedup: float
    median_ms: float
    rel_dev_geomean: float
    rel_dev_median_speedup: float
    rel_dev_median_ms: float


class BackendStability(BaseModel):
    """Convergence trajectory (ascending reps) for one backend."""

    model_config = ConfigDict(extra="forbid")

    solver_id: str
    points: list[StabilityPoint]


class StabilityStudy(BaseModel):
    """The full reps-ladder study — serialized to ``stability.json`` by the CLI."""

    model_config = ConfigDict(extra="forbid")

    reference_reps: int
    reps_ladder: list[int]
    tolerance: float = CONVERGENCE_RTOL
    converged_at_reps: int | None
    backends: list[BackendStability] = Field(min_length=1)


def discover_ladder(root: Path) -> LadderLayout:
    """Discover ``reps-N`` subdirectories under *root*, sorted by ascending reps.

    Args:
        root: Directory expected to contain ``reps-N/results.json`` subtrees.

    Returns:
        A validated :class:`LadderLayout`.

    Raises:
        pydantic.ValidationError: If *root* contains no ``reps-N`` subdirectories
            (including the *root does not exist* case).
    """
    entries: list[LadderRunFile] = []
    if root.is_dir():
        for child in sorted(root.iterdir()):
            if child.is_dir() and (m := _REPS_DIR_RE.match(child.name)):
                entries.append(
                    LadderRunFile(
                        reps=int(m.group(1)), results_path=child / "results.json"
                    )
                )
    entries.sort(key=lambda e: e.reps)
    return LadderLayout(root=root, runs=entries)


def backend_headline(report: BenchReport, solver_id: str) -> BackendHeadline | None:
    """Extract one backend's suite-level headline numbers from a report.

    Aggregates over every suite case where the backend reported (a backend may
    legitimately be absent from some cases — e.g. jax skips ``optfn``).

    Args:
        report: A contract-valid benchmark report.
        solver_id: The backend to summarize.

    Returns:
        The headline triple, or ``None`` when the backend reported on no case.
    """
    speedups: list[float] = []
    med_ms: list[float] = []
    for case in report.suite:
        metric = case.m.get(solver_id)
        if metric is None:
            continue
        if metric.speedup > 0.0:
            speedups.append(metric.speedup)
        med_ms.append(metric.med_ms)
    if not speedups or not med_ms:
        return None
    geomean = math.exp(math.fsum(math.log(s) for s in speedups) / len(speedups))
    return BackendHeadline(
        geomean_speedup=geomean,
        median_speedup=median(speedups),
        median_ms=median(med_ms),
    )


def _rel_dev(value: float, ref: float) -> float:
    """Relative half-width ``abs(value - ref) / ref`` (0.0 when ref is 0)."""
    return abs(value - ref) / ref if ref != 0.0 else 0.0


def _converged_at(
    backends: list[BackendStability], ladder: list[int], tolerance: float
) -> int | None:
    """Smallest reps budget where every backend's geomean is within tolerance.

    A budget qualifies only when *every* backend has a point there AND that
    point's ``rel_dev_geomean`` is at or below *tolerance*. The reference budget
    always qualifies (its deviation is 0 by construction), so the result is
    ``None`` only for a degenerate empty ladder.
    """
    points_by_backend = {b.solver_id: {p.reps: p for p in b.points} for b in backends}
    for reps in ladder:
        ok = all(
            (point := points_by_backend[sid].get(reps)) is not None
            and point.rel_dev_geomean <= tolerance
            for sid in points_by_backend
        )
        if ok:
            return reps
    return None


def build_stability_study(
    root: Path, *, tolerance: float = CONVERGENCE_RTOL
) -> StabilityStudy:
    """Aggregate a reps-ladder directory into a :class:`StabilityStudy`.

    The reference run is the highest-reps rung of the ladder (N=100 in the CI
    matrix); every other rung is compared against it.

    Args:
        root: Directory containing ``reps-N/results.json`` subtrees.
        tolerance: Relative band for the converged-at-N verdict.

    Returns:
        The aggregated study (ready for ``model_dump_json``).

    Raises:
        pydantic.ValidationError: If *root* has no ``reps-N`` subdirectories or
            no backend reported any case (empty ``backends``).
    """
    layout = discover_ladder(root)
    runs: list[tuple[int, BenchReport]] = [
        (
            rf.reps,
            BenchReport.model_validate_json(
                rf.results_path.read_text(encoding="utf-8")
            ),
        )
        for rf in layout.runs
    ]
    ladder = [reps for reps, _ in runs]
    ref_reps, ref_report = runs[-1]
    backends: list[BackendStability] = []
    for solver in ref_report.solvers:
        ref_h = backend_headline(ref_report, solver.id)
        if ref_h is None:
            continue
        points: list[StabilityPoint] = []
        for reps, report in runs:
            h = backend_headline(report, solver.id)
            if h is None:
                continue
            points.append(
                StabilityPoint(
                    reps=reps,
                    geomean_speedup=h.geomean_speedup,
                    median_speedup=h.median_speedup,
                    median_ms=h.median_ms,
                    rel_dev_geomean=_rel_dev(h.geomean_speedup, ref_h.geomean_speedup),
                    rel_dev_median_speedup=_rel_dev(
                        h.median_speedup, ref_h.median_speedup
                    ),
                    rel_dev_median_ms=_rel_dev(h.median_ms, ref_h.median_ms),
                )
            )
        backends.append(BackendStability(solver_id=solver.id, points=points))
    return StabilityStudy(
        reference_reps=ref_reps,
        reps_ladder=ladder,
        tolerance=tolerance,
        converged_at_reps=_converged_at(backends, ladder, tolerance),
        backends=backends,
    )


def render_markdown(study: StabilityStudy) -> str:
    """Render the study as a human-readable Markdown table + one-line verdict.

    Rows are reps budgets, columns are backends; each cell shows the geomean
    speedup with its signed Δ% vs the reference (highest-reps) value.
    """
    ids = [b.solver_id for b in study.backends]
    by_backend = {b.solver_id: {p.reps: p for p in b.points} for b in study.backends}
    ref_geomean = {sid: by_backend[sid].get(study.reference_reps) for sid in ids}

    lines = [
        "# Reps-ladder stability study",
        "",
        f"Cells: geomean speedup vs baseline (signed Δ% vs the N="
        f"{study.reference_reps} reference). Ladder: "
        f"{', '.join(str(r) for r in study.reps_ladder)}.",
        "",
        "| reps | " + " | ".join(ids) + " |",
        "|---:|" + "---:|" * len(ids),
    ]
    for reps in study.reps_ladder:
        cells: list[str] = []
        for sid in ids:
            point = by_backend[sid].get(reps)
            ref = ref_geomean[sid]
            if point is None or ref is None:
                cells.append("—")
                continue
            signed = (
                (point.geomean_speedup - ref.geomean_speedup) / ref.geomean_speedup
                if ref.geomean_speedup != 0.0
                else 0.0
            )
            cells.append(f"{point.geomean_speedup:.2f}× ({signed:+.1%})")
        lines.append(f"| {reps} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append(verdict_line(study))
    lines.append("")
    lines.append(
        f"The N={study.reference_reps} run is the canonical publication run "
        "(promoted to `canonical/` by the merge job)."
    )
    return "\n".join(lines) + "\n"


def verdict_line(study: StabilityStudy) -> str:
    """One-line convergence verdict for the Markdown report and the CLI echo."""
    match study.converged_at_reps:
        case None:
            return (
                f"Verdict: NO reps budget brought every backend within "
                f"{study.tolerance:.0%} of its N={study.reference_reps} geomean — "
                "the ladder is degenerate; inspect the per-backend points."
            )
        case int() as n if n == study.reference_reps:
            return (
                f"Verdict: measurement converged only at the reference budget "
                f"N={n} (no cheaper rung kept every backend within "
                f"{study.tolerance:.0%}); consider extending the ladder."
            )
        case int() as n:
            return (
                f"Verdict: measurement converged at N={n} — every backend's "
                f"geomean speedup is within {study.tolerance:.0%} of its "
                f"N={study.reference_reps} value from that budget on the ladder."
            )
    # Unreachable: the match above is exhaustive over `int | None`.
    raise AssertionError("unreachable")
