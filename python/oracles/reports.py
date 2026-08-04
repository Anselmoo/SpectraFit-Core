"""Report output layout: one run-centric tree + a manifest + a top-level index.

Replaces the old 7-scheme ``.spectrafit_reports`` mess with a single convention::

    .spectrafit_reports/
      index.json                                  # all runs, newest first
      <category>/<YYYY-MM-DD>_run_NNN/
        results.json                              # the BENCH contract payload
        manifest.json                             # run metadata + headline stats

``results.json`` is served at runtime by the FastAPI app (``oracles.api``) and
fetched by the ``web/`` UI — there is no inlined HTML artifact. ``manifest.json`` is
the single source of truth for a run's headline stats; there is no duplicated "latest"
copy. ``index.json`` lets tools discover runs without walking the tree.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import statistics
from collections.abc import Sequence
from datetime import UTC, date
from pathlib import Path
from typing import cast

from oracles.bench_contract import (
    GATE_RANK,
    GATE_STATES,
    BenchReport,
    GateState,
    ManifestSignals,
    PinnedBaseline,
)

REPORTS_ROOT = Path(".spectrafit_reports")
_RUN_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_run_(\d{3,})$")


def _sanitize_tracked(obj: object, path: str = "$") -> tuple[object, list[str]]:
    """Recursively replace non-finite floats (NaN / ±Inf) with 0.0, tracking paths.

    A single degenerate metric (e.g. ``reduced_chi2`` with dof≤0, an Inf cost-history
    entry) must not sink an entire multi-minute run: ``json.dumps(allow_nan=False)``
    would raise mid-write and strand an empty run dir. Sanitizing the whole payload at
    this one chokepoint guarantees RFC-8259-valid JSON regardless of where upstream a
    float escaped per-field ``_finite`` wrapping.

    Returns ``(sanitized, suppressed_paths)`` where each path is a JSONPath-ish
    locator (``$.suite[3].m.jax.r2``) of a coerced value. The silent half of the
    coercion failed framing-integrity review (G5, 2026-06-23 tribunal): a consumer
    cannot tell a measured 0.0 from a suppressed NaN, so :func:`write_run` surfaces
    the paths via ``ManifestSignals.sanitized_value_paths`` — a list, which this
    sanitizer never touches, so the disclosure cannot erase itself. Sibling
    ``*_suppressed`` keys (the ``oracles.audit.runner._sanitize`` pattern) are NOT
    an option here: every contract model is ``extra="forbid"`` and would reject
    them on round-trip.
    """
    match obj:
        case bool():
            return obj, []
        case float():
            if math.isfinite(obj):
                return obj, []
            return 0.0, [path]
        case dict():
            out: dict[object, object] = {}
            paths: list[str] = []
            for k, v in obj.items():
                sv, sp = _sanitize_tracked(v, f"{path}.{k}")
                out[k] = sv
                paths.extend(sp)
            return out, paths
        case list():
            out_list: list[object] = []
            list_paths: list[str] = []
            for i, v in enumerate(obj):
                sv, sp = _sanitize_tracked(v, f"{path}[{i}]")
                out_list.append(sv)
                list_paths.extend(sp)
            return out_list, list_paths
        case _:
            return obj, []


def _sanitize(obj: object) -> object:
    """Recursively replace non-finite floats with 0.0 (path-tracking discarded).

    Thin wrapper over :func:`_sanitize_tracked` for callers that only need the
    sanitized value; :func:`write_run` uses the tracked variant to disclose what
    was suppressed.
    """
    return _sanitize_tracked(obj)[0]


def allocate_run_dir(category: str = "benchmark", root: Path = REPORTS_ROOT) -> Path:
    """Create and return ``<root>/<category>/<today>_run_NNN`` (NNN monotonic)."""
    base = root / category
    base.mkdir(parents=True, exist_ok=True)
    nums = [
        int(m.group(2))
        for d in base.iterdir()
        if d.is_dir() and (m := _RUN_RE.match(d.name))
    ]
    run_dir = base / f"{date.today().isoformat()}_run_{max(nums, default=0) + 1:03d}"  # noqa: DTZ011 - local run-numbering, tz-naive is fine
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


_GATE_DEFAULT_MIN_GEOMEAN: float = 1.0
_GATE_DEFAULT_MAX_DR2: float = 1e-3
_GATE_DEFAULT_MAX_REGRESSIONS: int = 0
_SATURATION_INTERBACKEND_TOL: float = 1e-3
# Saturation means "backends agree at a NEAR-PERFECT fit", not merely "agree".
# A mediocre-but-unanimous case (e.g. every backend at r²≈0.5) is NOT solved —
# reporting it as saturated overstates ("too easy / done"). The floor is a real
# fit-quality ceiling: only clusters at r² ≥ 0.99 (residuals near the noise
# floor) count. Below that, agreement just means the backends are equally wrong.
_SATURATION_R2_FLOOR: float = 0.99


def _saturated_categories(
    suite: list,
    interbackend_tol: float = _SATURATION_INTERBACKEND_TOL,
    r2_floor: float = _SATURATION_R2_FLOOR,
) -> list[str]:
    """Return categories saturated by inter-backend r² agreement.

    A category is saturated when every case in it shows ``max(r²) - min(r²) ≤
    interbackend_tol`` across all reporting backends, AND ``min(r²) ≥ r2_floor``
    so that only near-perfect, mutually-confirmed fits count — not cases where
    every backend is *equally mediocre*.

    Why both conditions: saturation is "backends agree at a near-perfect fit",
    i.e. the case is below differentiation noise *because it is solved*, not
    because everyone failed the same way. The agreement test (``interbackend_tol``)
    captures "indistinguishable"; the floor (``r2_floor`` ≥ 0.99) captures
    "indistinguishable *and good*". Empirically the easy/edge/lineshapes/etc.
    cases hit max-min ≤ 1e-10 across all 6 backends on the same noise draw at
    r² near 1.0 — exactly what "solved, below differentiation noise" means.
    Per memory: triage/benchmark-saturation-real-life-too-easy.md.

    Parameters
    ----------
    suite:
        List of :class:`oracles.bench_contract.SuiteCase` instances (or dicts with
        the same shape). Each has ``category: str`` and ``m: dict[solver_id, SuiteMetric]``
        where ``SuiteMetric`` has ``r2: float``.
    interbackend_tol:
        Maximum allowed ``max(r²) - min(r²)`` per case for "agreement". Default 1e-3.
    r2_floor:
        Minimum allowed ``min(r²)`` per case. Guards against vacuous saturation when
        every backend produced garbage *or merely mediocre* fits. Default 0.99 — a
        real fit-quality ceiling, so "agreement" must be agreement at a good fit.

    Returns:
    -------
    list[str]
        Sorted list of saturated category ids.
    """
    by_cat: dict[str, list[bool]] = {}
    for case in suite:
        case_cat = getattr(case, "category", None) or (
            case.get("category") if hasattr(case, "get") else None
        )
        if not case_cat:
            continue
        metrics_map = getattr(case, "m", None) or (
            case.get("m") if hasattr(case, "get") else {}
        )
        r2s: list[float] = []
        for metric in (metrics_map or {}).values():
            r2 = getattr(metric, "r2", None)
            if r2 is None and hasattr(metric, "get"):
                r2 = metric.get("r2")
            if r2 is not None:
                r2s.append(float(r2))
        # Need ≥2 backends to talk about inter-backend agreement.
        agrees = (
            len(r2s) >= 2
            and (max(r2s) - min(r2s)) <= interbackend_tol
            and min(r2s) >= r2_floor
        )
        by_cat.setdefault(case_cat, []).append(agrees)
    return sorted(c for c, flags in by_cat.items() if flags and all(flags))


def _worst_gate_state(levels: Sequence[GateState]) -> GateState:
    """Aggregate per-axis ``GateState`` values into the overall (worst) state.

    ``pass`` < ``warn`` < ``fail`` by rank (``GATE_RANK``). The overall state is
    the worst rank present. Shared by :func:`_compute_default_gate_state` (in
    this module) and :func:`oracles.cli._gate_evaluate` (the user-thresholds
    path) so the aggregation rule cannot drift between the two.
    """
    worst_rank = max(GATE_RANK[lvl] for lvl in levels)
    return GATE_STATES[worst_rank]


def _compute_default_gate_state(
    geomean: float,
    max_dr2: float,
    reg_ids: list[str],
    nonfinite_dr2_ids: list[str],
) -> GateState:
    """Compute the aggregate gate state using the default ``spc-bench gate`` thresholds.

    This is the single computation that populates ``manifest.json`` and
    ``ManifestSignals.gate_state`` so the web GateBadge can read one field
    rather than recomputing from regression flags. Thresholds match the defaults
    in ``oracles.cli.gate`` (``min_geomean=1.0``, ``max_dr2=1e-3``,
    ``max_regressions=0``).

    Returns a :data:`oracles.bench_contract.GateState` Literal value.
    """
    levels: list[GateState] = []
    # speed axis: higher-is-better → fail if geomean < min_geomean
    levels.append("fail" if geomean < _GATE_DEFAULT_MIN_GEOMEAN else "pass")
    # accuracy axis: lower-is-better → fail if max_dr2 > threshold OR any compared
    # case had a non-finite |Δr²| (a non-finite metric must never pass: `NaN >
    # threshold` is False, which would otherwise be a silent pass).
    levels.append(
        "fail" if (max_dr2 > _GATE_DEFAULT_MAX_DR2 or nonfinite_dr2_ids) else "pass"
    )
    # regressions axis: lower-is-better → fail if n_reg > max_regressions
    levels.append("fail" if len(reg_ids) > _GATE_DEFAULT_MAX_REGRESSIONS else "pass")
    return _worst_gate_state(levels)


def _harmonic_mean(values: list[float]) -> float | None:
    """Return the harmonic mean of *values* (N / Σ(1/xᵢ)), or None on empty input.

    Per Eeckhout (2024): the harmonic mean is the correct aggregate for
    equal-time comparisons and is always ≤ the geometric mean for positively-
    skewed speedup distributions. Returns None rather than a sentinel so callers
    can distinguish "no data" from a legitimate small value.
    """
    if not values:
        return None
    return len(values) / sum(1.0 / x for x in values)


def _compute_headline_numbers(
    report: BenchReport,
) -> tuple[float, float, float, list[str], float | None, list[str]]:
    """Shared math for `_headline` (manifest.json) and `compute_manifest_signals`.

    Returns ``(geomean, max_dr2, sf_win_rate, regression_case_ids, harmonic_mean,
    nonfinite_dr2_case_ids)``. Single chokepoint so the manifest dict and the
    contract field cannot disagree. ``nonfinite_dr2_case_ids`` carries the cases
    whose ``|Δr²|`` was non-finite so the accuracy gate fails on them instead of
    silently passing (``NaN > threshold`` is ``False``) — a list survives
    ``_sanitize`` (which only coerces floats), so the signal cannot be erased.
    """
    baseline_id = report.baseline_solver_id
    speedups, dr2 = [], []
    nonfinite_dr2_ids: list[str] = []
    sf_wins = 0
    for case in report.suite:
        sf = case.m.get("spectrafit")
        baseline = case.m.get(baseline_id)
        if sf and sf.speedup > 0:
            speedups.append(sf.speedup)
        # Accuracy parity is only meaningful on the deterministic LM-family cases;
        # `optfn` is multimodal global optimization where spectrafit's global solver
        # and lmfit's differential_evolution legitimately reach different optima.
        if sf and baseline and case.category != "optfn":
            delta = abs(sf.r2 - baseline.r2)
            if math.isfinite(delta):
                dr2.append(delta)
            else:
                # A non-finite delta is a defect, not a tiny number: record the
                # case so the accuracy gate fails on it. Do NOT let it into `dr2`
                # (it would corrupt the max) and do NOT drop it silently.
                nonfinite_dr2_ids.append(case.id)
        # Only count a win when spectrafit actually produced a metric for the case
        # (the engine never defaults `winner` to a backend that did not run).
        if case.winner == "spectrafit" and "spectrafit" in case.m:
            sf_wins += 1
    geomean = (
        math.exp(sum(map(math.log, speedups)) / len(speedups)) if speedups else 1.0
    )
    reg_ids = [c.id for c in report.suite if c.regression]
    max_dr2 = max(dr2, default=0.0)
    sf_win_rate = sf_wins / max(len(report.suite), 1)
    harmonic = _harmonic_mean(speedups)
    return geomean, max_dr2, sf_win_rate, reg_ids, harmonic, nonfinite_dr2_ids


def compute_manifest_signals(
    report: BenchReport, root: Path = REPORTS_ROOT
) -> ManifestSignals:
    """Derive the typed :class:`ManifestSignals` from a report + optional pin sidecar.

    Same math as :func:`_headline` (single shared helper, no duplication);
    additionally reads the ``perf_baseline.json`` sidecar via
    :func:`read_perf_baseline` and exposes it as a typed :class:`PinnedBaseline`
    (or ``None`` when no baseline is pinned). Called by ``engine.build_report``
    and ``synth.build_report`` to populate ``BenchReport.manifest`` so the web
    GateBadge can render the four gate numbers without a sidecar fetch.
    """
    geomean, max_dr2, sf_win_rate, reg_ids, harmonic, nonfinite_dr2_ids = (
        _compute_headline_numbers(report)
    )
    pin = read_perf_baseline(root)
    pinned: PinnedBaseline | None = None
    if pin is not None:
        try:
            pinned = PinnedBaseline(
                run_id=str(pin["run_id"]),
                recorded_at=str(pin["recorded_at"]),
                geomean_speedup_vs_baseline=float(pin["geomean_speedup_vs_baseline"]),
                n_cases=int(pin.get("n_cases", 0)),
            )
        except (KeyError, ValueError, TypeError):
            # Corrupt pin → treat as absent (mirrors `read_perf_baseline`'s
            # tolerance for malformed sidecars; the CLI gate already handles
            # this branch by skipping the self-vs-self check).
            pinned = None
    return ManifestSignals(
        geomean_speedup_vs_baseline=geomean,
        max_abs_delta_r2=max_dr2,
        spectrafit_win_rate=sf_win_rate,
        regressions=len(reg_ids),
        pinned=pinned,
        harmonic_mean_speedup_vs_baseline=harmonic,
        gate_state=_compute_default_gate_state(
            geomean, max_dr2, reg_ids, nonfinite_dr2_ids
        ),
        nonfinite_dr2_case_ids=nonfinite_dr2_ids,
        saturated_categories=_saturated_categories(report.suite),
    )


def _median(values: list[float]) -> float | None:
    """Median of *values*, or ``None`` for an empty sample.

    ``statistics.median`` has identical semantics (mean of the two middle values
    for an even-length sample) but raises on empty input. A backend that ran zero
    cases must yield ``None`` rather than sink the whole run.
    """
    return statistics.median(values) if values else None


def _backend_facts(report: BenchReport) -> dict[str, dict[str, float | int | None]]:
    """Per-backend medians across the whole suite, keyed by solver id.

    A deliberate field-for-field port of ``backendFacts()`` in
    ``web/src/series/backendFacts.ts``, so the docs table and the dashboard's
    "Measured medians across the suite" table cannot show different numbers for
    the same run. The dashboard computes this in the browser from the ~49 MB
    ``results.json``; the docs site has no such payload, so the manifest caches
    the same reduction rather than growing a second, divergent implementation.

    The mirroring is enforced by ``tests/parity/test_backend_facts_parity.py``
    and its TypeScript half ``web/src/series/__tests__/backendFacts.golden.test.ts``,
    which assert against one shared fixture
    (``tests/parity/fixtures/backend_facts_golden.json``) so either side drifting
    fails in its own language. An earlier version of this docstring claimed that
    enforcement existed before it did — if this reduction changes, the golden and
    BOTH implementations move together, or the dashboard and the docs performance
    page will publish different numbers for the same run id.

    Backends are discovered from the data (``suite[].m`` keys), never a hardcoded
    roster, and sorted alphabetically — order implies nothing.
    """
    ids: set[str] = set()
    for case in report.suite:
        ids.update(case.m.keys())

    facts: dict[str, dict[str, float | int | None]] = {}
    for solver_id in sorted(ids):
        ms: list[float] = []
        r2: list[float] = []
        speedup: list[float] = []
        cases_run = 0
        success_hits = 0
        success_total = 0
        for case in report.suite:
            metric = case.m.get(solver_id)
            if metric is None:
                continue
            cases_run += 1
            # Non-finite guard mirrors the TS `Number.isFinite` checks: a NaN
            # med_ms from a diverged fit must not poison the median.
            if math.isfinite(metric.med_ms):
                ms.append(metric.med_ms)
            if math.isfinite(metric.r2):
                r2.append(metric.r2)
            if math.isfinite(metric.speedup):
                speedup.append(metric.speedup)
            success_total += 1
            if metric.success:
                success_hits += 1
        facts[solver_id] = {
            "med_ms": _median(ms),
            "med_r2": _median(r2),
            "med_speedup": _median(speedup),
            "cases_run": cases_run,
            "success_rate": (success_hits / success_total) if success_total else None,
        }
    return facts


def _per_case_points(report: BenchReport) -> dict[str, list[dict[str, float]]]:
    """Per-case ``(ms, r2, speedup)`` records per backend, paired by case.

    For the docs site's Pareto (speed vs. accuracy) scatter and speedup-
    distribution charts, which need real per-case spread rather than a single
    median. Deliberately a SEPARATE function from :func:`_backend_facts`, not an
    added field on it: this is O(n_cases) per backend (~151 points here) rather
    than O(1), and — unlike ``_backend_facts``'s output — must never flow through
    :func:`write_run`'s ``_update_index`` call, which prepends the manifest dict
    into ``index.json`` on every run, forever; an O(n_cases) field riding along
    that path would bloat every historical index row, not just the current one.
    See ``write_run``'s own wiring: this field is added to the per-run
    ``manifest.json`` dict only, after the (lean) index write.

    Each record requires BOTH ``med_ms`` and ``r2`` to be finite for that case —
    unlike ``_backend_facts``'s medians, which filter each field independently
    (only the aggregate matters there, so an unequal-length ``ms``/``r2`` list is
    fine), a scatter genuinely needs matched pairs: filtering fields
    independently here could silently plot one case's finite ``ms`` against a
    different case's ``r2``.
    """
    points: dict[str, list[dict[str, float]]] = {}
    for case in report.suite:
        for solver_id, metric in case.m.items():
            if not (math.isfinite(metric.med_ms) and math.isfinite(metric.r2)):
                continue
            record: dict[str, float] = {"ms": metric.med_ms, "r2": metric.r2}
            if math.isfinite(metric.speedup):
                record["speedup"] = metric.speedup
            points.setdefault(solver_id, []).append(record)
    return points


def _headline(
    report: BenchReport,
) -> dict[
    str,
    float | int | str | list[str] | dict[str, dict[str, float | int | None]] | None,
]:
    """Compute headline stats (geomean speedup vs lmfit, accuracy parity, win rate)."""
    geomean, max_dr2, sf_win_rate, reg_ids, harmonic, nonfinite_dr2_ids = (
        _compute_headline_numbers(report)
    )
    return {
        "n_cases": len(report.suite),
        # Canonical key: `geomean_speedup_vs_baseline`. Legacy alias
        # `geomean_speedup_vs_lmfit` retained one deprecation cycle so old gates,
        # dashboards, and on-disk manifests keep parsing. The contract field
        # `baseline_solver_id` names which solver is actually the baseline.
        "geomean_speedup_vs_baseline": geomean,
        "geomean_speedup_vs_lmfit": geomean,  # DEPRECATED — drop after 1 release cycle
        "baseline_solver_id": report.baseline_solver_id,
        "max_abs_delta_r2": max_dr2,
        "spectrafit_win_rate": sf_win_rate,
        "regressions": len(reg_ids),
        "regression_case_ids": reg_ids,
        # Cases whose |Δr²| was non-finite — surfaced so the accuracy gate fails on
        # them. A list survives `_sanitize` (floats→0.0 would erase the signal).
        "nonfinite_dr2_case_ids": nonfinite_dr2_ids,
        # Harmonic mean complements geomean per Eeckhout (2024): always ≤ geomean
        # for positively-skewed speedup data; the correct aggregate for equal-time.
        "harmonic_mean_speedup_vs_baseline": harmonic,
        # Single source of truth for the web GateBadge (Wire W6). Computed using
        # the default `spc-bench gate` thresholds so the UI reads one field rather
        # than recomputing from regression flags.
        "gate_state": _compute_default_gate_state(
            geomean, max_dr2, reg_ids, nonfinite_dr2_ids
        ),
        # Categories where every supported backend hits r²≥0.999 on every case.
        # Differential below the noise floor; UI marks these explicitly. Mirrors
        # ManifestSignals.saturated_categories on the contract side.
        "saturated_categories": _saturated_categories(report.suite),
        # Per-backend medians so a consumer without results.json (the docs site)
        # can render the same comparison the dashboard does. Deliberately NOT
        # mirrored onto ManifestSignals / the contract: manifest.json is a plain
        # file artifact off the OpenAPI surface, so this stays additive and needs
        # no schema bump, no golden regen, and no migrator (same precedent as
        # nonfinite_dr2_case_ids). Nested one level, ~6 backends x 5 scalars —
        # note this rides into every index.json row too, so keep it small.
        "backend_facts": _backend_facts(report),
    }


def write_run(
    report: BenchReport, category: str = "benchmark", root: Path = REPORTS_ROOT
) -> Path:
    """Write ``results.json`` + ``manifest.json`` into a fresh run dir; update the index."""
    run_dir = allocate_run_dir(category, root)
    # Sanitize the whole payload AND the manifest: a single non-finite metric (NaN
    # reduced_chi2, an Inf headline geomean) must not raise mid-write and strand an
    # empty run dir. allow_nan=False stays as a backstop so anything that slipped
    # through still fails loudly rather than emitting RFC-invalid JSON tokens.
    payload_obj, payload_suppressed = _sanitize_tracked(
        report.model_dump(by_alias=True)
    )
    payload = cast(dict[str, object], payload_obj)
    # G5 disclosure: surface what the sanitizer coerced. Each artifact reports its
    # OWN suppressions — results.json via the contract field
    # `manifest.sanitizedValuePaths`, manifest.json via its `sanitized_value_paths`
    # key. Injected post-dump (the paths are only known after sanitizing); the
    # contract field's default [] makes the injected value round-trip-valid.
    manifest_block = payload.get("manifest")
    if isinstance(manifest_block, dict):
        cast(dict[str, object], manifest_block)["sanitizedValuePaths"] = (
            payload_suppressed
        )
    manifest_obj, manifest_suppressed = _sanitize_tracked(
        {
            "run_id": run_dir.name,
            "date": date.today().isoformat(),  # noqa: DTZ011 - manifest metadata, tz-naive is fine
            "category": category,
            "schema_version": report.schema_version,
            "backends": [s.id for s in report.solvers],
            "featured_ids": [f.id for f in report.analyzed],
            **_headline(report),
            "artifacts": ["results.json", "manifest.json"],
        }
    )
    manifest: dict[str, object] = cast(dict[str, object], manifest_obj)
    manifest["sanitized_value_paths"] = manifest_suppressed
    try:
        (run_dir / "results.json").write_text(
            json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        # `per_case_points` is per-run-manifest-only (see its docstring): built
        # AFTER the dict handed to `_update_index` below, on a COPY, so it never
        # rides into index.json's accumulated history.
        run_manifest = {**manifest, "per_case_points": _per_case_points(report)}
        (run_dir / "manifest.json").write_text(
            json.dumps(run_manifest, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        # Index update stays INSIDE the try (after both writes) so a failed run never
        # leaks a half-written entry into index.json. Uses the LEAN `manifest`,
        # not `run_manifest` — see `_per_case_points`'s docstring.
        _update_index(
            manifest,
            root,
        )
    except Exception:
        # Never leave a stranded run dir lacking its core artifacts behind for the
        # gate/index to trip over: drop it if either write did not land, then re-raise.
        if (
            not (run_dir / "results.json").exists()
            or not (run_dir / "manifest.json").exists()
        ):
            shutil.rmtree(run_dir, ignore_errors=True)
        raise
    return run_dir


def _update_index(manifest: dict, root: Path = REPORTS_ROOT) -> None:
    """Prepend *manifest* to ``index.json`` (newest first; dedupe by (run_id, category)).

    ``run_id`` is only unique WITHIN a category — :func:`allocate_run_dir` keeps a
    per-category ``NNN`` counter, so two different categories (e.g. ``benchmark``
    and ``spectrafit_solo``) can legitimately produce the same ``run_id`` on the
    same day. Deduping on ``run_id`` alone would let the second category's write
    silently evict the first category's index entry. Match on BOTH fields so an
    entry is only replaced when it is truly the same run.
    """
    index_path = root / "index.json"
    runs = []
    if index_path.exists():
        try:
            runs = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            runs = []
    runs = [
        r
        for r in runs
        if not (
            r.get("run_id") == manifest["run_id"]
            and r.get("category") == manifest["category"]
        )
    ]
    runs.insert(0, manifest)
    index_path.write_text(json.dumps(runs, indent=2) + "\n", encoding="utf-8")


def latest_results(
    category: str = "benchmark", root: Path = REPORTS_ROOT
) -> Path | None:
    """Return the newest run's ``results.json`` path, or ``None`` if none exist."""
    index_path = root / "index.json"
    if not index_path.exists():
        return None
    try:
        runs = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    for r in runs:
        if r.get("category") == category:
            p = root / category / r["run_id"] / "results.json"
            if p.exists():
                return p
    return None


def latest_run_dir(
    category: str = "benchmark", root: Path = REPORTS_ROOT
) -> Path | None:
    """Return the newest indexed run DIR for *category*, or ``None`` if none exist.

    Unlike :func:`latest_results`, this does NOT filter on a present ``results.json``:
    it names the most recent run the index claims, so the gate can distinguish "no run
    at all" from "newest run failed to write its artifacts" and refuse stale data.
    """
    index_path = root / "index.json"
    if not index_path.exists():
        return None
    try:
        runs = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    for r in runs:
        if r.get("category") == category:
            return root / category / r["run_id"]
    return None


# ---------------------------------------------------------------------------
# Self-vs-self perf baseline (Vista-trap fix: gate-against-our-past-self).
# A single pinned JSON sidecar at ``.spectrafit_reports/perf_baseline.json``
# captures the geomean speedup of a chosen run so the gate can answer
# "did *we* get slower?", not just "are we still faster than the oracle?".
# Pin is intentionally cross-category (one file) — `category` is recorded
# inside the payload so a pin from `benchmark` is not used to gate a future
# `quick` run. ``baseline_solver_id`` is also stored so a baseline pinned
# against lmfit cannot silently grade a later run that switched baselines.
# ---------------------------------------------------------------------------


_PERF_BASELINE_NAME = "perf_baseline.json"


def _utc_iso() -> str:
    """ISO-8601 UTC timestamp for the pin record (no microseconds)."""
    from datetime import datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat()


def read_perf_baseline(root: Path = REPORTS_ROOT) -> dict | None:
    """Return the pinned self-vs-self perf baseline, or ``None`` if no pin exists.

    A corrupt pin (non-JSON, truncated) is treated as absent rather than fatal —
    the gate falls back to the lmfit-relative geomean check, the user sees the
    "no pin" branch in ``show-baseline``, and a fresh ``pin-baseline`` overwrites.
    """
    p = root / _PERF_BASELINE_NAME
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_perf_baseline(manifest: dict, root: Path = REPORTS_ROOT) -> Path:
    """Pin *manifest*'s geomean speedup as the perf baseline; return the pin path.

    Overwrites any prior pin. Stores ``baseline_solver_id`` and ``category`` so the
    gate can refuse to compare across mismatched contexts (different baseline solver
    or report category).
    """
    geomean = float(
        manifest.get(
            "geomean_speedup_vs_baseline",
            manifest.get("geomean_speedup_vs_lmfit", 1.0),
        )
    )
    pinned = {
        "run_id": manifest["run_id"],
        "recorded_at": _utc_iso(),
        "schema_version": manifest.get("schema_version"),
        "category": manifest.get("category", "benchmark"),
        "baseline_solver_id": manifest.get("baseline_solver_id", "lmfit"),
        "geomean_speedup_vs_baseline": geomean,
        "n_cases": int(manifest.get("n_cases", 0)),
    }
    p = root / _PERF_BASELINE_NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(pinned, indent=2) + "\n", encoding="utf-8")
    return p


def clear_perf_baseline(root: Path = REPORTS_ROOT) -> bool:
    """Remove any pinned perf baseline; return ``True`` if a pin was removed."""
    p = root / _PERF_BASELINE_NAME
    if p.exists():
        p.unlink()
        return True
    return False
