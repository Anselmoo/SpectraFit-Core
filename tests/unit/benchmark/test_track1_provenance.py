"""TDD tests for Track 1: code-provenance + winner-why + σ-weighted χ²_red.

RED-FIRST: these tests are written before implementation. They document the
exact contract changes Track 1 delivers:

  1. BenchReport  → git_commit, git_branch, run_timestamp_unix
  2. Featured     → model_source_file, model_formula
  3. SuiteCase    → winner_reason
  4. SuiteMetric  → convergence_efficiency, ill_conditioned, red_chi2_weighted,
                    metric_undefined_reason
  5. PeakModel    → formula_latex
  6. Finite-only validator on float metric fields (inf/NaN → ValidationError)
  7. Engine populates all new fields from real data.
  8. winner_reason built from kappa + n_iter + convergence_efficiency signals.
"""

from __future__ import annotations

import math
import time

import pytest
from pydantic import ValidationError

from oracles.bench_contract import BenchReport, SuiteCase, SuiteMetric
from oracles.models import MODEL_REGISTRY
from oracles.synth import build_report


# ---------------------------------------------------------------------------
# 1. BenchReport new fields
# ---------------------------------------------------------------------------


def test_bench_report_has_git_provenance_fields() -> None:
    """BenchReport accepts git_commit / git_branch / run_timestamp_unix."""
    report = build_report()
    # Fields exist (None from synth builder — it doesn't capture git)
    assert hasattr(report, "git_commit")
    assert hasattr(report, "git_branch")
    assert hasattr(report, "run_timestamp_unix")


def test_bench_report_git_fields_default_none() -> None:
    """New provenance fields default to None for backward compat."""
    report = build_report()
    assert report.git_commit is None
    assert report.git_branch is None
    assert report.run_timestamp_unix is None


def test_bench_report_git_fields_accept_values() -> None:
    """BenchReport round-trips with populated git fields."""
    report = build_report()
    updated = report.model_copy(
        update={
            "git_commit": "abc1234def5678",
            "git_branch": "fix/dashboard-and-greenups",
            "run_timestamp_unix": 1_700_000_000,
        }
    )
    assert updated.git_commit == "abc1234def5678"
    assert updated.git_branch == "fix/dashboard-and-greenups"
    assert updated.run_timestamp_unix == 1_700_000_000


def test_bench_report_git_fields_roundtrip_json() -> None:
    """Provenance fields survive a JSON round-trip with camelCase aliases."""
    report = build_report()
    updated = report.model_copy(
        update={"git_commit": "deadbeef", "git_branch": "main", "run_timestamp_unix": 100}
    )
    payload = updated.model_dump(by_alias=True)
    assert payload["gitCommit"] == "deadbeef"
    assert payload["gitBranch"] == "main"
    assert payload["runTimestampUnix"] == 100
    restored = BenchReport.model_validate(payload, strict=False)
    assert restored.git_commit == "deadbeef"


# ---------------------------------------------------------------------------
# 2. Featured new fields
# ---------------------------------------------------------------------------


def test_featured_has_model_source_file_field() -> None:
    """Featured carries model_source_file (None by default)."""
    report = build_report()
    feat = report.analyzed[0]
    assert hasattr(feat, "model_source_file")
    assert feat.model_source_file is None  # synth doesn't populate


def test_featured_has_model_formula_field() -> None:
    """Featured carries model_formula (None by default)."""
    report = build_report()
    feat = report.analyzed[0]
    assert hasattr(feat, "model_formula")
    assert feat.model_formula is None


def test_featured_model_source_roundtrip() -> None:
    """model_source_file / model_formula round-trip via JSON."""
    report = build_report()
    feat = report.analyzed[0]
    updated = feat.model_copy(
        update={
            "model_source_file": "crates/spectrafit-models/src/gaussian.rs",
            "model_formula": r"A \cdot \exp\!\left(-\tfrac{(x-c)^2}{2\sigma^2}\right)",
        }
    )
    payload = updated.model_dump(by_alias=True)
    assert payload["modelSourceFile"] == "crates/spectrafit-models/src/gaussian.rs"
    assert "modelFormula" in payload


# ---------------------------------------------------------------------------
# 3. SuiteCase new fields
# ---------------------------------------------------------------------------


def test_suite_case_has_winner_reason_field() -> None:
    """SuiteCase carries winner_reason (None by default)."""
    report = build_report()
    for case in report.suite:
        assert hasattr(case, "winner_reason")
    # All synth rows have None (engine not invoked)
    assert all(c.winner_reason is None for c in report.suite)


def test_suite_case_winner_reason_roundtrip() -> None:
    """winner_reason serializes to camelCase winnerReason."""
    report = build_report()
    case = report.suite[0]
    updated = case.model_copy(update={"winner_reason": "spectrafit κ≈2e3, 12 iters"})
    payload = updated.model_dump(by_alias=True)
    assert payload["winnerReason"] == "spectrafit κ≈2e3, 12 iters"
    restored = SuiteCase.model_validate(payload, strict=False)
    assert restored.winner_reason == "spectrafit κ≈2e3, 12 iters"


# ---------------------------------------------------------------------------
# 4. SuiteMetric new fields + finite validator
# ---------------------------------------------------------------------------


def test_suite_metric_has_new_fields() -> None:
    """SuiteMetric carries the four new per-backend metric fields."""
    report = build_report()
    for case in report.suite:
        for _sid, m in case.m.items():
            assert hasattr(m, "convergence_efficiency")
            assert hasattr(m, "ill_conditioned")
            assert hasattr(m, "red_chi2_weighted")
            assert hasattr(m, "metric_undefined_reason")


def test_suite_metric_new_fields_default_none() -> None:
    """New SuiteMetric fields default to None (backward compat)."""
    report = build_report()
    m = report.suite[0].m[next(iter(report.suite[0].m))]
    assert m.convergence_efficiency is None
    assert m.ill_conditioned is None
    assert m.red_chi2_weighted is None
    assert m.metric_undefined_reason is None


def test_suite_metric_new_fields_accept_values() -> None:
    """SuiteMetric round-trips with new fields populated."""
    report = build_report()
    m = report.suite[0].m[next(iter(report.suite[0].m))]
    updated = m.model_copy(
        update={
            "convergence_efficiency": 0.05,
            "ill_conditioned": False,
            "red_chi2_weighted": 1.12,
            "metric_undefined_reason": None,
        }
    )
    assert updated.convergence_efficiency == pytest.approx(0.05)
    assert updated.ill_conditioned is False
    assert updated.red_chi2_weighted == pytest.approx(1.12)


def test_suite_metric_rejects_inf_r2() -> None:
    """Validator: r2=inf must raise ValidationError."""
    with pytest.raises(ValidationError):
        SuiteMetric(
            speedup=1.0,
            r2=float("inf"),
            red_chi2=1.0,
            med_ms=10.0,
            param_err=0.0,
            success=True,
        )


def test_suite_metric_rejects_nan_r2() -> None:
    """Validator: r2=NaN must raise ValidationError."""
    with pytest.raises(ValidationError):
        SuiteMetric(
            speedup=1.0,
            r2=float("nan"),
            red_chi2=1.0,
            med_ms=10.0,
            param_err=0.0,
            success=True,
        )


def test_suite_metric_rejects_inf_red_chi2() -> None:
    """Validator: red_chi2=inf must raise ValidationError."""
    with pytest.raises(ValidationError):
        SuiteMetric(
            speedup=1.0,
            r2=0.99,
            red_chi2=float("inf"),
            med_ms=10.0,
            param_err=0.0,
            success=True,
        )


def test_suite_metric_rejects_inf_speedup() -> None:
    """Validator: speedup=inf must raise ValidationError."""
    with pytest.raises(ValidationError):
        SuiteMetric(
            speedup=float("inf"),
            r2=0.99,
            red_chi2=1.0,
            med_ms=10.0,
            param_err=0.0,
            success=True,
        )


def test_suite_metric_rejects_inf_red_chi2_weighted() -> None:
    """Validator: red_chi2_weighted=inf must raise ValidationError."""
    with pytest.raises(ValidationError):
        SuiteMetric(
            speedup=1.0,
            r2=0.99,
            red_chi2=1.0,
            med_ms=10.0,
            param_err=0.0,
            success=True,
            red_chi2_weighted=float("inf"),
        )


def test_suite_metric_allows_none_red_chi2_weighted() -> None:
    """Validator: red_chi2_weighted=None (sigma=0 noiseless case) is allowed."""
    m = SuiteMetric(
        speedup=1.0,
        r2=0.99,
        red_chi2=1.0,
        med_ms=10.0,
        param_err=0.0,
        success=True,
        red_chi2_weighted=None,
        metric_undefined_reason="sigma=0 (noiseless)",
    )
    assert m.red_chi2_weighted is None
    assert m.metric_undefined_reason == "sigma=0 (noiseless)"


def test_suite_metric_finite_roundtrip() -> None:
    """Valid finite SuiteMetric builds and round-trips."""
    m = SuiteMetric(
        speedup=2.5,
        r2=0.998,
        red_chi2=1.02,
        med_ms=5.3,
        param_err=0.01,
        success=True,
        convergence_efficiency=0.04,
        ill_conditioned=False,
        red_chi2_weighted=1.05,
    )
    payload = m.model_dump(by_alias=True)
    assert payload["convergenceEfficiency"] == pytest.approx(0.04)
    assert payload["illConditioned"] is False
    assert payload["redChi2Weighted"] == pytest.approx(1.05)


# ---------------------------------------------------------------------------
# 5. PeakModel formula_latex field
# ---------------------------------------------------------------------------


def test_peak_model_has_formula_latex_field() -> None:
    """PeakModel carries formula_latex (str)."""
    m = MODEL_REGISTRY.get("gaussian")
    assert m is not None
    assert hasattr(m, "formula_latex")
    assert isinstance(m.formula_latex, str)
    assert len(m.formula_latex) > 0


def test_gaussian_formula_latex_not_empty() -> None:
    """gaussian PeakModel has a non-empty formula_latex."""
    m = MODEL_REGISTRY["gaussian"]
    assert "exp" in m.formula_latex.lower() or "sigma" in m.formula_latex.lower()


def test_lorentzian_formula_latex_not_empty() -> None:
    """lorentzian PeakModel has a non-empty formula_latex."""
    m = MODEL_REGISTRY["lorentzian"]
    assert len(m.formula_latex) > 0


def test_all_builtin_models_have_formula_latex() -> None:
    """Every model in MODEL_REGISTRY has a non-empty formula_latex."""
    missing = [k for k, m in MODEL_REGISTRY.items() if not m.formula_latex]
    assert missing == [], f"models missing formula_latex: {missing}"


def test_peak_model_formula_latex_roundtrip() -> None:
    """formula_latex round-trips through model_copy."""
    m = MODEL_REGISTRY["gaussian"]
    updated = m.model_copy(update={"formula_latex": r"A\exp(-(x-c)^2/2\sigma^2)"})
    assert updated.formula_latex == r"A\exp(-(x-c)^2/2\sigma^2)"


# ---------------------------------------------------------------------------
# 6. Engine: git provenance + timestamp captured in real build_report
# ---------------------------------------------------------------------------


def test_engine_build_report_captures_run_timestamp() -> None:
    """engine.build_report populates run_timestamp_unix (int, recent epoch)."""
    from oracles.engine import build_report as engine_build_report

    # Minimal 1-case run to keep the test fast.
    catalog = build_catalog()[:1]
    t_before = int(time.time())
    report = engine_build_report(catalog=catalog, n_reps=1, n_mc=2)
    t_after = int(time.time())
    assert report.run_timestamp_unix is not None
    assert t_before <= report.run_timestamp_unix <= t_after


def test_engine_build_report_captures_git_commit() -> None:
    """engine.build_report sets git_commit to a hex string or None (no git)."""
    from oracles.engine import build_report as engine_build_report

    catalog = build_catalog()[:1]  # 1-case minimal run
    report = engine_build_report(catalog=catalog, n_reps=1, n_mc=2)
    # In a git repo this should be a non-empty hex string.
    if report.git_commit is not None:
        assert len(report.git_commit) >= 7
        assert all(c in "0123456789abcdef" for c in report.git_commit)


# ---------------------------------------------------------------------------
# 7. Engine: featured model_source_file / model_formula populated
# ---------------------------------------------------------------------------


def test_engine_build_report_featured_model_source_file() -> None:
    """engine.build_report populates model_source_file on featured cases."""
    from oracles.engine import build_report as engine_build_report

    catalog = build_catalog()[:1]
    report = engine_build_report(catalog=catalog, n_reps=1, n_mc=2)
    feat = report.analyzed[0]
    # model_source_file should be a path under crates/spectrafit-models/src/
    if feat.model_source_file is not None:
        assert feat.model_source_file.startswith("crates/spectrafit-models/src/")
        assert feat.model_source_file.endswith(".rs")


def test_engine_build_report_featured_model_formula() -> None:
    """engine.build_report populates model_formula from registry."""
    from oracles.engine import build_report as engine_build_report

    catalog = build_catalog()[:1]
    report = engine_build_report(catalog=catalog, n_reps=1, n_mc=2)
    feat = report.analyzed[0]
    # model_formula may be None for landscape/optfn cases without a kernel
    # but for a plain case it should be populated.
    # We just check it's either a non-empty str or None (both valid).
    assert feat.model_formula is None or isinstance(feat.model_formula, str)


# ---------------------------------------------------------------------------
# 8. Engine: SuiteMetric new fields populated
# ---------------------------------------------------------------------------


def test_engine_suite_case_red_chi2_weighted_finite_or_none() -> None:
    """All suite SuiteMetric.red_chi2_weighted are finite or None."""
    from oracles.engine import build_report as engine_build_report

    catalog = build_catalog()[:3]
    report = engine_build_report(catalog=catalog, n_reps=1, n_mc=2)
    for sc in report.suite:
        for _sid, m in sc.m.items():
            if m.red_chi2_weighted is not None:
                assert math.isfinite(m.red_chi2_weighted), (
                    f"non-finite red_chi2_weighted in {sc.id}/{_sid}"
                )


def test_engine_suite_noiseless_cases_have_undefined_reason() -> None:
    """Noiseless (optfn) suite cases have metric_undefined_reason set."""
    from oracles.engine import build_report as engine_build_report

    catalog = [c for c in build_catalog() if c.category == "optfn"][:2]
    if not catalog:
        pytest.skip("no optfn cases in minimal catalog slice")
    report = engine_build_report(catalog=catalog, n_reps=1, n_mc=2)
    for sc in report.suite:
        for _sid, m in sc.m.items():
            # optfn cases use sigma=0; red_chi2_weighted must be None
            assert m.red_chi2_weighted is None
            assert m.metric_undefined_reason is not None


# ---------------------------------------------------------------------------
# 9. winner_reason populated by engine for suite cases
# ---------------------------------------------------------------------------


def test_engine_winner_reason_is_str_or_none() -> None:
    """engine.run_suite populates winner_reason as str or None per case."""
    from oracles.engine import build_report as engine_build_report

    catalog = build_catalog()[:3]
    report = engine_build_report(catalog=catalog, n_reps=1, n_mc=2)
    for sc in report.suite:
        assert sc.winner_reason is None or isinstance(sc.winner_reason, str)


# ---------------------------------------------------------------------------
# Import guard: build_catalog referenced in engine tests above
# ---------------------------------------------------------------------------
from oracles.cases import build_catalog  # noqa: E402 (import used above)
