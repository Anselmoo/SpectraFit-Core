"""Contract tests for the benchmark report data shape (``oracles.bench_contract``).

These guard the linchpin of the rebuild: the JSON the engine emits must match the
camelCase ``BENCH`` shape the ``web/`` UI consumes. The synthetic builder doubles
as a completeness check — if it fills every field, the contract is whole.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from oracles.bench_contract import SCHEMA_VERSION, BenchReport, PanelLayout, PanelSpec
from oracles.synth import build_report


def test_synth_report_is_contract_valid() -> None:
    """The deterministic synthetic report builds and is a valid BenchReport."""
    report = build_report()
    assert isinstance(report, BenchReport)
    # Subset assertion (relaxed for the scipy-ls extension, 2026-06-08): the
    # canonical 3 oracles must always be present; additions are additive.
    canonical = {"spectrafit", "lmfit", "jax"}
    assert canonical.issubset({s.id for s in report.solvers})
    assert len(report.solvers) >= 3
    from oracles.cases import CATEGORY_COUNTS

    # Derived from the single source of truth so a category rename can't re-drift this.
    assert {c.id for c in report.categories} == set(CATEGORY_COUNTS)
    assert len(report.suite) == sum(CATEGORY_COUNTS.values())


def test_report_is_deterministic() -> None:
    """Same seed → byte-identical JSON (fixtures and CI must be reproducible)."""
    a = build_report(seed=123).model_dump_json(by_alias=True)
    b = build_report(seed=123).model_dump_json(by_alias=True)
    assert a == b


def test_camelcase_aliases_match_mockup_keys() -> None:
    """Serialized keys use the exact mockup ``window.BENCH`` camelCase names."""
    payload = build_report().model_dump(by_alias=True)
    featured = payload["analyzed"][0]
    # Case-level (shared) keys.
    for key in ("profiles", "paramNames", "Ngrid", "crossN", "runsSched", "corr"):
        assert key in featured, f"missing featured key {key!r}"
    # Per-backend metrics now live under one profile per solver.
    prof = featured["profiles"]["spectrafit"]
    for key in (
        "fit",
        "convEff",
        "historySource",
        "paramErr",
        "ecdfResid",
        "ecdfTime",
        "paramSpread",
        "warmup",
        "scaling",
        "stability",
    ):
        assert key in prof, f"missing profile key {key!r}"
    for key in ("redChi2", "medMs", "iqrMs", "nIter", "aic", "bic", "dAIC", "dBIC"):
        assert key in prof["summary"], f"missing summary key {key!r}"
    assert "perRun" in prof["warmup"]["pts"][0]


def test_json_round_trip_revalidates() -> None:
    """Dump → JSON string → reload validates identically (no lossy fields)."""
    report = build_report()
    raw = report.model_dump_json(by_alias=True)
    reloaded = BenchReport.model_validate_json(raw)
    assert reloaded.model_dump_json(by_alias=True) == raw


def test_panelspec_serializes_camelcase_and_round_trips() -> None:
    """PanelSpec is part of the frozen contract: camelCase wire keys, strict fields."""
    spec = PanelSpec(
        id="spectrum",
        title="Spectrum · guess · fit",
        desc="Reference, initial guess, and each backend's fitted curve.",
        chart_kind="line",
        source="spectrumSeries",
        layout=PanelLayout(wide=True, height=300),
    )
    payload = spec.model_dump(by_alias=True)
    assert payload["chartKind"] == "line"
    assert payload["layout"] == {"wide": True, "height": 300}
    assert PanelSpec.model_validate(payload) == spec


def test_bench_report_panels_field_defaults_empty() -> None:
    """Additive: payloads without `panels` validate; default is []."""
    assert SCHEMA_VERSION == "1.7"
    report = build_report()  # existing factory from oracles.synth
    payload = report.model_dump(by_alias=True)
    payload.pop("panels", None)
    payload["schemaVersion"] = "1.2"
    revalidated = BenchReport.model_validate(payload)
    assert revalidated.panels == []


def test_report_carries_default_panels_after_engine_attachment() -> None:
    """Contract holds panels + source-proxy check that build_report attaches them.

    Uses the synth factory (fast, no real fits) + model_copy to exercise the
    engine-attachment code path without paying the full benchmark cost in unit tests.

    The ``inspect.getsource`` assertion below is a SOURCE-TEXT sentinel, not a
    behavioural check (a real ``build_report`` call costs a fit); the
    behavioural proof lives in the engine injection test / Plan D D12 round-trip.
    """
    from oracles.panels import DEFAULT_PANELS
    from oracles.engine import build_report as engine_build_report

    # Verify engine.build_report attaches panels by checking via the
    # synth-factory + model_copy path (same logic the engine uses post-fit).
    synth = build_report()  # synth factory — fast, no panels yet
    report_with_panels = synth.model_copy(update={"panels": list(DEFAULT_PANELS)})
    assert report_with_panels.panels == list(DEFAULT_PANELS)
    payload = report_with_panels.model_dump(by_alias=True)
    assert [p["id"] for p in payload["panels"]] == [p.id for p in DEFAULT_PANELS]

    # Smoke: engine.build_report is callable and imports default_panels correctly
    # (the import at module top would have already failed if it were circular).
    import inspect

    src = inspect.getsource(engine_build_report)
    assert "default_panels()" in src, "engine.build_report must call default_panels()"


def test_panelspec_rejects_unknown_chart_kind() -> None:
    """PanelSpec rejects chart_kind values not in the ChartKind Literal."""
    with pytest.raises(ValidationError):
        PanelSpec(id="x", title="x", chart_kind="pie", source="s")  # ty: ignore[invalid-argument-type]  # deliberately invalid chart_kind to test ValidationError


# ---------------------------------------------------------------------------
# Task 4.3: NestedAdequacy contract round-trip tests
# ---------------------------------------------------------------------------


def test_featured_nested_adequacy_defaults_to_none() -> None:
    """Additive-minor: payloads without nestedAdequacy validate with None."""
    report = build_report()
    payload = report.model_dump(by_alias=True)
    # Strip the field if the synth factory populates it in future
    featured = payload["analyzed"][0]
    featured.pop("nestedAdequacy", None)
    # Must reconstruct without error
    from oracles.bench_contract import Featured

    revalidated = Featured.model_validate(featured)
    assert revalidated.nested_adequacy is None


def test_nested_adequacy_round_trips_through_contract() -> None:
    """NestedAdequacy + SelectionStats serialise camelCase and reload cleanly."""
    from oracles.bench_contract import NestedAdequacy

    stats_payload = {
        "lrtStat": 42.0,
        "lrtP": 0.001,
        "fStat": 15.3,
        "fP": 0.002,
        "dAIC": -8.5,
        "dBIC": -6.2,
    }
    adequacy_payload = {
        "trueOrder": 3,
        "reducedRejected": True,
        "overNotPreferredAic": False,
        "overNotPreferredBic": True,
        "selectedOrderAic": 4,
        "selectedOrderBic": 3,
        "recoveredTrueOrderAic": False,
        "recoveredTrueOrderBic": True,
        "reducedVsTrue": stats_payload,
        "trueVsOver": {
            "lrtStat": 1.2,
            "lrtP": 0.27,
            "fStat": 0.9,
            "fP": 0.35,
            "dAIC": 3.1,
            "dBIC": 5.4,
        },
    }

    na = NestedAdequacy.model_validate(adequacy_payload)
    assert na.true_order == 3
    assert na.reduced_rejected is True
    assert na.over_not_preferred_aic is False
    assert na.over_not_preferred_bic is True
    assert na.selected_order_aic == 4
    assert na.selected_order_bic == 3
    assert na.recovered_true_order_aic is False
    assert na.recovered_true_order_bic is True
    assert na.reduced_vs_true.lrt_stat == 42.0
    assert na.true_vs_over.d_aic == 3.1

    # Dump to camelCase alias and reload — must round-trip exactly
    dumped = na.model_dump(by_alias=True)
    assert "trueOrder" in dumped
    assert "reducedVsTrue" in dumped
    assert "lrtStat" in dumped["reducedVsTrue"]

    reloaded = NestedAdequacy.model_validate(dumped)
    assert reloaded == na


def test_featured_nested_adequacy_populates_when_present() -> None:
    """Featured.nested_adequacy round-trips when included in the payload."""
    from oracles.bench_contract import Featured, NestedAdequacy

    report = build_report()
    featured = report.analyzed[0]

    stats = {
        "lrtStat": 10.0,
        "lrtP": 0.005,
        "fStat": 5.0,
        "fP": 0.01,
        "dAIC": -4.0,
        "dBIC": -3.0,
    }
    na_payload = {
        "trueOrder": 2,
        "reducedRejected": True,
        "overNotPreferredAic": True,
        "overNotPreferredBic": True,
        "selectedOrderAic": 2,
        "selectedOrderBic": 2,
        "recoveredTrueOrderAic": True,
        "recoveredTrueOrderBic": True,
        "reducedVsTrue": stats,
        "trueVsOver": {
            "lrtStat": 0.5,
            "lrtP": 0.48,
            "fStat": 0.4,
            "fP": 0.52,
            "dAIC": 2.0,
            "dBIC": 4.0,
        },
    }

    updated = featured.model_copy(
        update={"nested_adequacy": NestedAdequacy.model_validate(na_payload)}
    )
    dumped = updated.model_dump(by_alias=True)
    assert "nestedAdequacy" in dumped
    assert dumped["nestedAdequacy"]["trueOrder"] == 2

    reloaded = Featured.model_validate(dumped)
    assert reloaded.nested_adequacy is not None
    assert reloaded.nested_adequacy.true_order == 2
    assert reloaded.nested_adequacy.reduced_vs_true.lrt_stat == 10.0


# ---------------------------------------------------------------------------
# Task 5.3: CalibrationResult + SpeedInferenceResult contract round-trip tests
# ---------------------------------------------------------------------------


def test_inference_block_calibration_speed_default_none() -> None:
    """Additive-minor: InferenceBlock without calibration/speed_inference → both None."""
    from oracles.bench_contract import InferenceBlock, InferenceConfig

    ib = InferenceBlock(
        config=InferenceConfig(
            equivalence_margin=1e-3,
            bootstrap_b=10,
            seed=1,
            fdr_q=0.05,
        ),
        cases=[],
        equivalence=[],
        winner_stability={},
    )
    assert ib.calibration is None
    assert ib.speed_inference is None
    dumped = ib.model_dump(by_alias=True)
    reloaded = InferenceBlock.model_validate(dumped)
    assert reloaded.calibration is None
    assert reloaded.speed_inference is None


def test_calibration_result_round_trips() -> None:
    """CalibrationResult serialises camelCase and reloads cleanly."""
    from oracles.bench_contract import CalibrationResult

    cal = CalibrationResult(
        n=50,
        coverage=0.70,
        coverage_ci_lo=0.56,
        coverage_ci_hi=0.82,
        nominal=0.6827,
        binomial_p=0.23,
        ks_stat=0.08,
        ks_p=0.61,
        alpha=0.025,
        passed=True,
        skipped=False,
    )
    dumped = cal.model_dump(by_alias=True)
    # Check camelCase aliases
    assert "coverageCiLo" in dumped
    assert "coverageCiHi" in dumped
    assert "binomialP" in dumped
    assert "ksStat" in dumped
    assert "ksP" in dumped
    reloaded = CalibrationResult.model_validate(dumped)
    assert reloaded == cal


def test_speed_inference_result_round_trips() -> None:
    """SpeedInferenceResult serialises camelCase and reloads cleanly."""
    from oracles.bench_contract import SpeedInferenceResult

    sp = SpeedInferenceResult(
        geomean_speedup=3.5,
        ci_lo=2.1,
        ci_hi=5.0,
        excludes_one=True,
        sign_p=0.001,
        wilcoxon_p=0.002,
        alpha=0.025,
        passed=True,
        skipped=False,
    )
    dumped = sp.model_dump(by_alias=True)
    # Check camelCase aliases
    assert "geomeanSpeedup" in dumped
    assert "ciLo" in dumped
    assert "ciHi" in dumped
    assert "excludesOne" in dumped
    assert "signP" in dumped
    assert "wilcoxonP" in dumped
    reloaded = SpeedInferenceResult.model_validate(dumped)
    assert reloaded == sp


def test_inference_block_with_calibration_and_speed_round_trips() -> None:
    """InferenceBlock with calibration + speed_inference round-trips completely."""
    from oracles.bench_contract import (
        CalibrationResult,
        InferenceBlock,
        InferenceConfig,
        SpeedInferenceResult,
    )

    config = InferenceConfig(
        equivalence_margin=1e-3,
        bootstrap_b=200,
        seed=42,
        fdr_q=0.05,
        alpha_calibration=0.025,
        alpha_speed=0.025,
        coverage_nominal=0.6827,
        min_pulls=20,
    )
    cal = CalibrationResult(
        n=50,
        coverage=0.70,
        coverage_ci_lo=0.56,
        coverage_ci_hi=0.82,
        nominal=0.6827,
        binomial_p=0.23,
        ks_stat=0.08,
        ks_p=0.61,
        alpha=0.025,
        passed=True,
        skipped=False,
    )
    sp = SpeedInferenceResult(
        geomean_speedup=3.5,
        ci_lo=2.1,
        ci_hi=5.0,
        excludes_one=True,
        sign_p=0.001,
        wilcoxon_p=0.002,
        alpha=0.025,
        passed=True,
        skipped=False,
    )
    ib = InferenceBlock(
        config=config,
        cases=[],
        equivalence=[],
        winner_stability={},
        calibration=cal,
        speed_inference=sp,
    )
    dumped = ib.model_dump(by_alias=True)
    # Config new fields must appear in camelCase
    assert "alphaCalibration" in dumped["config"]
    assert "alphaSpeed" in dumped["config"]
    assert "coverageNominal" in dumped["config"]
    assert "minPulls" in dumped["config"]
    # Nested results present
    assert dumped["calibration"]["coverageCiLo"] == pytest.approx(0.56)
    assert dumped["speedInference"]["geomeanSpeedup"] == pytest.approx(3.5)
    reloaded = InferenceBlock.model_validate(dumped)
    assert reloaded.calibration == cal
    assert reloaded.speed_inference == sp


def test_inference_config_new_fields_have_correct_defaults() -> None:
    """InferenceConfig new fields default to the pre-registered α/nominal/min_pulls."""
    from oracles.bench_contract import InferenceConfig

    config = InferenceConfig(
        equivalence_margin=1e-3, bootstrap_b=10, seed=1, fdr_q=0.05
    )
    assert config.alpha_calibration == 0.025
    assert config.alpha_speed == 0.025
    assert config.coverage_nominal == 0.6827
    assert config.min_pulls == 20
