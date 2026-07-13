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
from typing import cast
import shutil
from collections.abc import Sequence
from datetime import date
from pathlib import Path

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
    run_dir = base / f"{date.today().isoformat()}_run_{max(nums, default=0) + 1:03d}"
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
        for _solver_id, metric in (metrics_map or {}).items():
            r2 = getattr(metric, "r2", None)
            if r2 is None and hasattr(metric, "get"):
                r2 = metric.get("r2")
            if r2 is not None:
                r2s.append(float(r2))
        # Need ≥2 backends to talk about inter-backend agreement.
        agrees = (
            len(r2s) >= 2 and (max(r2s) - min(r2s)) <= interbackend_tol and min(r2s) >= r2_floor
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
        "fail"
        if (max_dr2 > _GATE_DEFAULT_MAX_DR2 or nonfinite_dr2_ids)
        else "pass"
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


def _headline(report: BenchReport) -> dict[str, float | int | str | list[str] | None]:
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
    payload_obj, payload_suppressed = _sanitize_tracked(report.model_dump(by_alias=True))
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
            "date": date.today().isoformat(),
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
        (run_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        # Index update stays INSIDE the try (after both writes) so a failed run never
        # leaks a half-written entry into index.json.
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
    """Prepend *manifest* to ``index.json`` (newest first; dedupe by run_id)."""
    index_path = root / "index.json"
    runs = []
    if index_path.exists():
        try:
            runs = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            runs = []
    runs = [r for r in runs if r.get("run_id") != manifest["run_id"]]
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
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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
