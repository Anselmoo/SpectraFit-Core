"""TDD: harmonic-mean speedup field in ManifestSignals (Track A Wave 4).

Eeckhout (2024) — "R.I.P. Geomean Speedup" — recommends reporting the
harmonic mean alongside the geometric mean: the harmonic mean is the correct
aggregate for equal-time comparisons and is always ≤ the geomean for
positively-skewed speedup distributions.

These tests pin:

* ``_harmonic_mean`` returns the closed-form value (N / Σ(1/xᵢ)) and
  ``None`` for an empty input.
* ``compute_manifest_signals`` populates
  ``ManifestSignals.harmonic_mean_speedup_vs_baseline`` and the value is
  ≤ the geometric mean (AM-HM inequality).
* The field round-trips through JSON / Pydantic.
* Old payloads (no ``harmonicMeanSpeedupVsBaseline`` key) validate with
  ``harmonic_mean_speedup_vs_baseline = None`` (additive-minor policy).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from oracles.bench_contract import (
    BenchReport,
    CategoryMeta,
    ManifestSignals,
    SuiteCase,
    SuiteMetric,
)
from oracles.reports import (
    _harmonic_mean,
    _headline,
    compute_manifest_signals,
)
from oracles.contract import SolverMeta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tiny_report(speedups: dict[str, float] | None = None) -> BenchReport:
    """Minimal 2-case report with known per-case speedup values.

    Default speedups: spectrafit → [12.0, 18.0], lmfit → [1.0, 1.0].
    Harmonic mean of [12, 18] = 2 / (1/12 + 1/18) = 2 / (5/36) = 72/5 = 14.4.
    Geomean of [12, 18] = sqrt(12 × 18) = sqrt(216) ≈ 14.697…
    """
    sf_speeds = speedups if speedups is not None else {"EZ-001": 12.0, "EZ-002": 18.0}
    cases = []
    for cid, spd in sf_speeds.items():
        cases.append(
            SuiteCase(
                id=cid,
                name=cid,
                category="easy",
                difficulty=0.1,
                m={
                    "spectrafit": SuiteMetric(
                        speedup=spd,
                        r2=0.9998,
                        red_chi2=1.0,
                        med_ms=1.0,
                        param_err=0.0,
                        success=True,
                    ),
                    "lmfit": SuiteMetric(
                        speedup=1.0,
                        r2=0.9998,
                        red_chi2=1.0,
                        med_ms=spd,
                        param_err=0.0,
                        success=True,
                    ),
                },
                winner="spectrafit",
                regression=False,
            )
        )
    return BenchReport(
        solvers=[
            SolverMeta(id="spectrafit", label="spectrafit", color="#fff", soft="#eee"),
            SolverMeta(id="lmfit", label="lmfit", color="#fff", soft="#eee"),
        ],
        categories=[CategoryMeta(id="easy", label="Easy", n=len(cases), hue="#fff")],
        analyzed=[],
        suite=cases,
    )


# ---------------------------------------------------------------------------
# Unit tests for _harmonic_mean helper
# ---------------------------------------------------------------------------


def test_harmonic_mean_closed_form_two_values() -> None:
    """Harmonic mean of [12, 18] = 2/(1/12+1/18) = 14.4 exactly."""
    result = _harmonic_mean([12.0, 18.0])
    assert result == pytest.approx(14.4)


def test_harmonic_mean_closed_form_four_values() -> None:
    """Harmonic mean of [1, 2, 4, 4] = 4/(1+0.5+0.25+0.25) = 4/2.0 = 2.0."""
    result = _harmonic_mean([1.0, 2.0, 4.0, 4.0])
    assert result == pytest.approx(2.0)


def test_harmonic_mean_single_value_returns_itself() -> None:
    """Harmonic mean of [x] = x."""
    assert _harmonic_mean([7.5]) == pytest.approx(7.5)


def test_harmonic_mean_empty_returns_none() -> None:
    """Empty input → None (not 0 or NaN; distinguishes 'no data')."""
    assert _harmonic_mean([]) is None


def test_harmonic_mean_equal_values() -> None:
    """Harmonic mean of k equal values = that value."""
    assert _harmonic_mean([5.0, 5.0, 5.0]) == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# ManifestSignals population
# ---------------------------------------------------------------------------


def test_compute_manifest_signals_populates_harmonic_mean(
    monkeypatch, tmp_path: Path
) -> None:
    """compute_manifest_signals populates harmonic_mean_speedup_vs_baseline."""
    monkeypatch.chdir(tmp_path)
    report = _tiny_report({"EZ-001": 12.0, "EZ-002": 18.0})
    signals = compute_manifest_signals(report)

    assert signals.harmonic_mean_speedup_vs_baseline is not None
    # 2 / (1/12 + 1/18) = 14.4
    assert signals.harmonic_mean_speedup_vs_baseline == pytest.approx(14.4)


def test_harmonic_mean_leq_geomean(monkeypatch, tmp_path: Path) -> None:
    """Harmonic ≤ geomean for positively-skewed speedup data (AM-HM inequality)."""
    monkeypatch.chdir(tmp_path)
    speedups = {"A": 2.0, "B": 8.0, "C": 32.0}
    report = _tiny_report(speedups)
    signals = compute_manifest_signals(report)

    assert signals.harmonic_mean_speedup_vs_baseline is not None
    # geomean of [2, 8, 32] = (2×8×32)^(1/3) = 512^(1/3) = 8.0
    assert signals.geomean_speedup_vs_baseline == pytest.approx(8.0)
    # harmonic of [2, 8, 32] = 3/(0.5+0.125+0.03125) = 3/0.65625 ≈ 4.571
    assert (
        signals.harmonic_mean_speedup_vs_baseline <= signals.geomean_speedup_vs_baseline
    )


def test_headline_dict_includes_harmonic_mean(monkeypatch, tmp_path: Path) -> None:
    """_headline dict carries 'harmonic_mean_speedup_vs_baseline' key."""
    monkeypatch.chdir(tmp_path)
    report = _tiny_report({"C1": 12.0, "C2": 18.0})
    h = _headline(report)
    assert "harmonic_mean_speedup_vs_baseline" in h
    assert h["harmonic_mean_speedup_vs_baseline"] == pytest.approx(14.4)


# ---------------------------------------------------------------------------
# JSON round-trip and additive-minor backward compatibility
# ---------------------------------------------------------------------------


def test_manifest_signals_roundtrip_preserves_harmonic_mean(
    monkeypatch, tmp_path: Path
) -> None:
    """ManifestSignals → JSON → ManifestSignals preserves harmonic_mean field."""
    monkeypatch.chdir(tmp_path)
    report = _tiny_report({"EZ-001": 12.0, "EZ-002": 18.0})
    signals = compute_manifest_signals(report)
    raw = signals.model_dump_json(by_alias=True)
    again = ManifestSignals.model_validate_json(raw)
    assert again.harmonic_mean_speedup_vs_baseline == pytest.approx(14.4)


def test_old_payload_without_harmonic_field_validates_with_none() -> None:
    """An old payload lacking harmonicMeanSpeedupVsBaseline validates as None.

    Additive-minor invariant: Pydantic fills None for absent optional fields.
    Matches the policy from CLAUDE.md SCHEMA_VERSION policy.
    """
    old_payload = {
        "geomeanSpeedupVsBaseline": 12.0,
        "maxAbsDeltaR2": 1e-4,
        "spectrafitWinRate": 0.85,
        "regressions": 0,
        # NO harmonicMeanSpeedupVsBaseline key — pre-field payloads never had it.
    }
    signals = ManifestSignals.model_validate(old_payload)
    assert signals.harmonic_mean_speedup_vs_baseline is None
    # Stable round-trip
    again = ManifestSignals.model_validate_json(signals.model_dump_json(by_alias=True))
    assert again.harmonic_mean_speedup_vs_baseline is None


def test_bench_report_manifest_harmonic_roundtrip(monkeypatch, tmp_path: Path) -> None:
    """BenchReport round-trips with harmonic_mean in the manifest."""
    monkeypatch.chdir(tmp_path)
    report = _tiny_report({"EZ-001": 12.0, "EZ-002": 18.0})
    report = report.model_copy(update={"manifest": compute_manifest_signals(report)})
    raw = report.model_dump_json(by_alias=True)
    again = BenchReport.model_validate_json(raw)
    assert again.manifest is not None
    assert again.manifest.harmonic_mean_speedup_vs_baseline == pytest.approx(14.4)


# ---------------------------------------------------------------------------
# Edge: empty speedup list (no subject solver in any case)
# ---------------------------------------------------------------------------


def test_harmonic_mean_is_none_when_no_speedup_data(
    monkeypatch, tmp_path: Path
) -> None:
    """When no subject case has speedup data, harmonic_mean is None."""
    monkeypatch.chdir(tmp_path)
    # Report with NO spectrafit entries → speedups list stays empty
    from oracles.bench_contract import SuiteCase, SuiteMetric

    empty_report = BenchReport(
        solvers=[
            SolverMeta(id="lmfit", label="lmfit", color="#fff", soft="#eee"),
        ],
        categories=[CategoryMeta(id="easy", label="Easy", n=1, hue="#fff")],
        analyzed=[],
        suite=[
            SuiteCase(
                id="E1",
                name="e1",
                category="easy",
                difficulty=0.1,
                m={
                    "lmfit": SuiteMetric(
                        speedup=1.0,
                        r2=0.999,
                        red_chi2=1.0,
                        med_ms=5.0,
                        param_err=0.0,
                        success=True,
                    )
                },
                winner="lmfit",
                regression=False,
            )
        ],
    )
    signals = compute_manifest_signals(empty_report)
    assert signals.harmonic_mean_speedup_vs_baseline is None


def test_harmonic_above_geomean_is_rejected() -> None:
    """Invariant V (V3): the validator enforces HM ≤ GM (AM ≥ GM ≥ HM).

    A payload where the harmonic mean exceeds the geometric mean is
    mathematically impossible for positive speedups and must refuse to construct
    — promotes the previously documentation-only property to an enforced
    contract invariant.
    """
    with pytest.raises(ValueError):
        ManifestSignals(
            geomean_speedup_vs_baseline=2.0,
            max_abs_delta_r2=1e-6,
            spectrafit_win_rate=0.5,
            regressions=0,
            harmonic_mean_speedup_vs_baseline=3.0,  # > geomean → impossible
        )


def test_harmonic_equal_to_geomean_is_allowed() -> None:
    # Equality holds when all per-case speedups are equal (degenerate but valid).
    ManifestSignals(
        geomean_speedup_vs_baseline=2.0,
        max_abs_delta_r2=1e-6,
        spectrafit_win_rate=0.5,
        regressions=0,
        harmonic_mean_speedup_vs_baseline=2.0,
    )
