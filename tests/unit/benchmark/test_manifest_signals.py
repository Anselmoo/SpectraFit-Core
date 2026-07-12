"""ManifestSignals contract extension pins (Cycle 7.6).

Cycle 7.6 added `manifest: ManifestSignals | None` to `BenchReport` so the
web GateBadge can render the four gate numbers (geomean speedup, max |Δr²|,
spectrafit win-rate, pinned baseline ratio) without the "CLI-only" footer
that used to send users to `spc-bench show-baseline`.

These tests pin:

* `compute_manifest_signals` returns a `ManifestSignals` whose fields equal
  the legacy `_headline` dict values — single source of truth, no drift.
* `pinned` is `None` when no `perf_baseline.json` exists; populated as a
  `PinnedBaseline` when one is on disk.
* `BenchReport` round-trips through JSON with `manifest` preserved.
* An old payload (schema_version="1.1", no `manifest` field) validates as
  1.2 with `manifest=None` — Pydantic's default makes the bump purely
  additive (no `@register_migration` entry needed; matches the policy
  documented in `migrate.py:_upgrade_1_0_to_1_1` and CLAUDE.md).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oracles.bench_contract import (
    BenchReport,
    CategoryMeta,
    ManifestSignals,
    PinnedBaseline,
    SolverMeta,
    SuiteCase,
    SuiteMetric,
)
from oracles.reports import (
    _headline,
    compute_manifest_signals,
    write_perf_baseline,
)


def _tiny_report() -> BenchReport:
    """A minimal 2-case report whose `_headline` math is deterministic."""
    return BenchReport(
        solvers=[
            SolverMeta(id="spectrafit", label="spectrafit", color="#fff", soft="#eee"),
            SolverMeta(id="lmfit", label="lmfit", color="#fff", soft="#eee"),
        ],
        categories=[CategoryMeta(id="easy", label="Easy", n=2, hue="#fff")],
        analyzed=[],
        suite=[
            SuiteCase(
                id="EZ-001",
                name="case 1",
                category="easy",
                difficulty=0.1,
                m={
                    "spectrafit": SuiteMetric(
                        speedup=12.0,
                        r2=0.9998,
                        red_chi2=1.0,
                        med_ms=0.5,
                        param_err=0.0,
                        success=True,
                    ),
                    "lmfit": SuiteMetric(
                        speedup=1.0,
                        r2=0.9999,
                        red_chi2=1.0,
                        med_ms=6.0,
                        param_err=0.0,
                        success=True,
                    ),
                },
                winner="spectrafit",
                regression=False,
            ),
            SuiteCase(
                id="EZ-002",
                name="case 2",
                category="easy",
                difficulty=0.1,
                m={
                    "spectrafit": SuiteMetric(
                        speedup=18.0,
                        r2=0.9991,
                        red_chi2=1.0,
                        med_ms=0.3,
                        param_err=0.0,
                        success=True,
                    ),
                    "lmfit": SuiteMetric(
                        speedup=1.0,
                        r2=0.9992,
                        red_chi2=1.0,
                        med_ms=5.0,
                        param_err=0.0,
                        success=True,
                    ),
                },
                winner="spectrafit",
                regression=False,
            ),
        ],
    )


def test_signals_match_legacy_headline_for_same_report(
    monkeypatch, tmp_path: Path
) -> None:
    """ManifestSignals values equal the corresponding `_headline` dict keys.

    Single source of truth: both call `_compute_headline_numbers`, so any
    accidental drift surfaces here.
    """
    monkeypatch.chdir(tmp_path)
    report = _tiny_report()
    signals = compute_manifest_signals(report)
    legacy = _headline(report)
    assert signals.geomean_speedup_vs_baseline == legacy["geomean_speedup_vs_baseline"]
    assert signals.max_abs_delta_r2 == legacy["max_abs_delta_r2"]
    assert signals.spectrafit_win_rate == legacy["spectrafit_win_rate"]
    assert signals.regressions == legacy["regressions"]


def test_pinned_is_none_when_no_baseline_file(monkeypatch, tmp_path: Path) -> None:
    """No pin on disk → `signals.pinned is None`."""
    monkeypatch.chdir(tmp_path)
    signals = compute_manifest_signals(_tiny_report())
    assert signals.pinned is None


def test_pinned_is_populated_when_baseline_file_exists(
    monkeypatch, tmp_path: Path
) -> None:
    """A pinned baseline on disk → `signals.pinned` is a typed PinnedBaseline."""
    monkeypatch.chdir(tmp_path)
    # Use `write_perf_baseline` directly so the on-disk shape is the
    # canonical one (matches the CLI `spc-bench pin-baseline` path).
    write_perf_baseline(
        {
            "run_id": "2026-06-08_run_018",
            "schema_version": "1.2",
            "category": "benchmark",
            "baseline_solver_id": "lmfit",
            "geomean_speedup_vs_baseline": 12.36,
            "n_cases": 139,
        }
    )
    signals = compute_manifest_signals(_tiny_report())
    assert isinstance(signals.pinned, PinnedBaseline)
    assert signals.pinned.run_id == "2026-06-08_run_018"
    assert signals.pinned.geomean_speedup_vs_baseline == 12.36
    assert signals.pinned.n_cases == 139


def test_bench_report_roundtrips_with_manifest(monkeypatch, tmp_path: Path) -> None:
    """BenchReport → JSON → BenchReport preserves the manifest field."""
    monkeypatch.chdir(tmp_path)
    report = _tiny_report().model_copy(
        update={"manifest": compute_manifest_signals(_tiny_report())}
    )
    raw = report.model_dump_json(by_alias=True)
    again = BenchReport.model_validate_json(raw)
    assert again.manifest is not None
    assert again.manifest.geomean_speedup_vs_baseline == pytest.approx(
        report.manifest.geomean_speedup_vs_baseline  # type: ignore[union-attr]
    )
    assert again.manifest.regressions == 0


def test_old_1_1_payload_validates_as_1_2_with_manifest_none() -> None:
    """An old 1.1 payload (no `manifest` field) validates against the 1.2 schema.

    Additive-minor invariant: Pydantic's `None` default for `manifest`
    means old payloads on disk validate against the bumped schema without
    going through `@register_migration`. Matches the policy from CLAUDE.md
    (`SCHEMA_VERSION policy` ADR, 2026-06-06).
    """
    old_payload = {
        "schemaVersion": "1.1",
        "solvers": [],
        "categories": [],
        "analyzed": [],
        "suite": [],
        "baselineSolverId": "lmfit",
        # NO `manifest` key — pre-bump payloads never had it.
    }
    parsed = BenchReport.model_validate(old_payload)
    assert parsed.manifest is None
    # Round-trip dumps it back as `null` (or omitted in JSON, depending on alias
    # config); either way the validate→dump→validate cycle is stable.
    again = BenchReport.model_validate(
        json.loads(parsed.model_dump_json(by_alias=True))
    )
    assert again.manifest is None


def test_synth_build_report_populates_manifest() -> None:
    """`synth.build_report()` ships a populated `manifest` (FastAPI smoke needs it).

    The synthetic fixture is the contract-validation path used by the web
    `npm run contract` step; if it ever shipped `manifest=None`, the
    generated openapi.gen.ts would type the field as always-null and the
    GateBadge bindings would be unable to render real numbers in real runs.
    """
    from oracles.synth import build_report

    report = build_report()
    assert report.manifest is not None
    assert isinstance(report.manifest, ManifestSignals)
    assert report.manifest.geomean_speedup_vs_baseline > 0
