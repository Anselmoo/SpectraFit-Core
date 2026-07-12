"""G5 residual — ``reports._sanitize`` must disclose what it suppressed.

TDD: red-first. ``oracles.reports._sanitize`` coerces non-finite floats to 0.0
for presentation. The 2026-06-23 tribunal ruled the *silent* half of that
FAILS framing-integrity: a consumer cannot tell a measured 0.0 from a
suppressed NaN. The contract-safe fix (every model is ``extra="forbid"``, so
runner.py-style ``*_suppressed`` sibling keys would be rejected on round-trip)
follows the ``nonfinite_dr2_case_ids`` list-field precedent:

- ``_sanitize_tracked`` returns ``(sanitized, suppressed_paths)`` where each
  path is a JSONPath-ish locator (``$.suite[3].m.jax.r2``).
- ``write_run`` surfaces the results-payload paths in the additive contract
  field ``ManifestSignals.sanitized_value_paths`` and the manifest artifact's
  own paths under the ``sanitized_value_paths`` manifest key.
- A list survives ``_sanitize`` (only floats are coerced), so the disclosure
  cannot erase itself.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from oracles.bench_contract import (
    BenchReport,
    CategoryMeta,
    ManifestSignals,
    SolverMeta,
    SuiteCase,
    SuiteMetric,
)
from oracles.reports import _sanitize, _sanitize_tracked, write_run


# ---------------------------------------------------------------------------
# _sanitize_tracked — path collection contract
# ---------------------------------------------------------------------------


def test_tracked_records_path_for_nested_nonfinite() -> None:
    """Non-finite floats are coerced to 0.0 AND their paths are recorded."""
    data = {"a": {"b": float("inf")}, "xs": [1.0, float("nan"), 3.0]}
    out, paths = _sanitize_tracked(data)
    assert out == {"a": {"b": 0.0}, "xs": [1.0, 0.0, 3.0]}
    assert paths == ["$.a.b", "$.xs[1]"]


def test_tracked_finite_payload_records_nothing() -> None:
    """A fully-finite payload yields an empty path list and unchanged values."""
    data = {"x": 1.5, "n": 3, "s": "ok", "flag": True, "xs": [0.0, 2.0]}
    out, paths = _sanitize_tracked(data)
    assert out == data
    assert paths == []


def test_tracked_bool_passthrough() -> None:
    """bool is a float subclass — must pass through untouched, never coerced."""
    out, paths = _sanitize_tracked({"flag": True, "off": False})
    assert out == {"flag": True, "off": False}
    assert paths == []


def test_tracked_scalar_nonfinite_at_root() -> None:
    """A bare non-finite scalar is coerced and reported at the root path."""
    out, paths = _sanitize_tracked(float("-inf"))
    assert out == 0.0
    assert paths == ["$"]


def test_sanitize_wrapper_behavior_unchanged() -> None:
    """The legacy ``_sanitize`` wrapper keeps its exact 0.0-coercion semantics
    (no sibling keys, no path leakage into the payload)."""
    data = {"bad": float("nan"), "good": 1.0}
    out = _sanitize(data)
    assert out == {"bad": 0.0, "good": 1.0}
    assert not any(k.endswith("_suppressed") for k in out)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# write_run — the disclosure rides the contract + manifest artifacts
# ---------------------------------------------------------------------------


def _metric(*, r2: float, speedup: float = 5.0) -> SuiteMetric:
    # model_construct bypasses finite validation so a NaN r² can be injected —
    # mirrors a degenerate backend outcome escaping per-field guards upstream.
    return SuiteMetric.model_construct(
        speedup=speedup, r2=r2, red_chi2=1.0, med_ms=2.0, param_err=0.05, success=True
    )


def _report_with_nan_r2() -> BenchReport:
    case = SuiteCase.model_construct(
        id="G5-001",
        name="G5-001",
        category="easy",
        difficulty=0.1,
        m={
            "spectrafit": _metric(r2=float("nan")),
            "lmfit": _metric(r2=0.99, speedup=1.0),
        },
        winner="spectrafit",
        regression=False,
        winner_reason=None,
    )
    manifest = ManifestSignals(
        geomean_speedup_vs_baseline=5.0,
        max_abs_delta_r2=0.0,
        spectrafit_win_rate=1.0,
        regressions=0,
        nonfinite_dr2_case_ids=["G5-001"],
        gate_state="fail",
    )
    return BenchReport.model_construct(
        schema_version="1.7",
        solvers=[
            SolverMeta(id="spectrafit", label="SpectraFit", color="#f00", soft="#fee"),
            SolverMeta(id="lmfit", label="lmfit", color="#00f", soft="#eef"),
        ],
        categories=[CategoryMeta(id="easy", label="Easy", n=1, hue="#ccc")],
        analyzed=[],
        suite=[case],
        baseline_solver_id="lmfit",
        manifest=manifest,
        trust_block=None,
        panels=[],
        inference=None,
        git_commit=None,
        git_branch=None,
        run_timestamp_unix=None,
    )


def test_write_run_discloses_suppressed_paths(tmp_path: Path) -> None:
    """results.json carries its own suppression paths in manifest.sanitizedValuePaths."""
    run_dir = write_run(_report_with_nan_r2(), root=tmp_path)
    payload = json.loads((run_dir / "results.json").read_text())

    disclosed = payload["manifest"]["sanitizedValuePaths"]
    assert disclosed == ["$.suite[0].m.spectrafit.r2"], (
        "the NaN r² coerced to 0.0 must be disclosed by path"
    )
    # The coercion itself still happened (presentation stays JSON-valid).
    assert payload["suite"][0]["m"]["spectrafit"]["r2"] == 0.0


def test_write_run_results_json_round_trips_canonically(tmp_path: Path) -> None:
    """The disclosed payload must re-validate and re-emit byte-canonically
    (extra=forbid accepts the field; parse→emit does not drift)."""
    run_dir = write_run(_report_with_nan_r2(), root=tmp_path)
    raw = json.loads((run_dir / "results.json").read_text())
    model = BenchReport.model_validate(raw)
    assert model.manifest is not None
    assert model.manifest.sanitized_value_paths == ["$.suite[0].m.spectrafit.r2"]
    re_emitted = json.loads(model.model_dump_json(by_alias=True))
    assert json.dumps(re_emitted, sort_keys=True) == json.dumps(raw, sort_keys=True)


def test_write_run_manifest_artifact_discloses_its_own_paths(tmp_path: Path) -> None:
    """manifest.json carries its own (possibly empty) sanitized_value_paths key —
    presence is the contract; silence is what the tribunal ruled out."""
    run_dir = write_run(_report_with_nan_r2(), root=tmp_path)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert "sanitized_value_paths" in manifest
    # The headline math finite-filters |Δr²| (nonfinite_dr2_case_ids precedent),
    # so this minimal report's manifest artifact itself has nothing suppressed.
    assert manifest["sanitized_value_paths"] == []


def test_manifest_signals_field_defaults_empty() -> None:
    """Additive-field policy: old payloads (no key) validate with [] — no bump,
    no migrator, matching the nonfinite_dr2_case_ids / harmonic-mean precedent."""
    signals = ManifestSignals(
        geomean_speedup_vs_baseline=1.0,
        max_abs_delta_r2=0.0,
        spectrafit_win_rate=0.5,
        regressions=0,
    )
    assert signals.sanitized_value_paths == []
    assert not math.isnan(signals.geomean_speedup_vs_baseline)
