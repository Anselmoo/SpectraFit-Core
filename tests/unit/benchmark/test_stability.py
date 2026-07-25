"""Reps-ladder stability aggregation (`spc-bench stability`) unit tests.

Builds synthetic contract-valid reports via ``oracles.synth.build_report`` and
perturbs the suite metrics deterministically (a pure multiplicative scale per
reps rung), so every expected number — geomean, median, and the relative
deviation vs the N=100 reference — is hand-computable in closed form:
``geomean(k·s) = k·geomean(s)`` and ``median(k·s) = k·median(s)`` for ``k > 0``,
hence ``rel_dev = |k - 1|`` exactly.
"""

from __future__ import annotations

import math
from pathlib import Path
from statistics import median

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from oracles.cli import app
from oracles.stability import (
    CONVERGENCE_RTOL,
    backend_headline,
    build_stability_study,
    render_markdown,
)
from oracles.synth import build_report

# Multiplicative perturbation per rung: reps-1 is 5% off the reference (outside
# the 2% band), reps-10 is 1% off (inside), reps-100 IS the reference (k=1).
_SCALE_BY_REPS = {1: 1.05, 10: 1.01, 100: 1.0}


def _write_ladder(root: Path) -> None:
    """Write reps-{1,10,100}/results.json with deterministically scaled metrics."""
    for reps, scale in _SCALE_BY_REPS.items():
        report = build_report()  # deterministic (seeded) synthetic report
        for case in report.suite:
            for metric in case.m.values():
                metric.speedup *= scale
                metric.med_ms *= scale
        run_dir = root / f"reps-{reps}"
        run_dir.mkdir(parents=True)
        (run_dir / "results.json").write_text(
            report.model_dump_json(by_alias=True), encoding="utf-8"
        )


def test_rel_dev_math_and_converged_verdict(tmp_path: Path) -> None:
    _write_ladder(tmp_path)
    study = build_stability_study(tmp_path)

    assert study.reference_reps == 100
    assert study.reps_ladder == [1, 10, 100]
    assert study.tolerance == CONVERGENCE_RTOL == 0.02
    assert study.backends, "synthetic report carries the full solver roster"

    for backend in study.backends:
        assert [p.reps for p in backend.points] == [1, 10, 100]
        p1, p10, p100 = backend.points
        # geomean(k·s) = k·geomean(s) → rel_dev = |k − 1| exactly (mod fp noise)
        assert p1.rel_dev_geomean == pytest.approx(0.05, rel=1e-9)
        assert p10.rel_dev_geomean == pytest.approx(0.01, rel=1e-9)
        assert p100.rel_dev_geomean == 0.0
        # medians scale identically
        assert p1.rel_dev_median_speedup == pytest.approx(0.05, rel=1e-9)
        assert p1.rel_dev_median_ms == pytest.approx(0.05, rel=1e-9)
        assert p100.rel_dev_median_speedup == 0.0
        assert p100.rel_dev_median_ms == 0.0
        # absolute values scale too: v_1 = 1.05·v_100, v_10 = 1.01·v_100
        assert p1.geomean_speedup == pytest.approx(1.05 * p100.geomean_speedup)
        assert p10.median_ms == pytest.approx(1.01 * p100.median_ms)

    # 5% > 2% at reps=1; 1% ≤ 2% at reps=10 → converged at N=10.
    assert study.converged_at_reps == 10


def test_headline_matches_hand_computation() -> None:
    report = build_report()
    speedups = [
        case.m["spectrafit"].speedup for case in report.suite if "spectrafit" in case.m
    ]
    med_ms = [
        case.m["spectrafit"].med_ms for case in report.suite if "spectrafit" in case.m
    ]
    expected_geomean = math.exp(
        math.fsum(math.log(s) for s in speedups) / len(speedups)
    )

    headline = backend_headline(report, "spectrafit")
    assert headline is not None
    assert headline.geomean_speedup == pytest.approx(expected_geomean, rel=1e-12)
    assert headline.median_speedup == pytest.approx(median(speedups), rel=1e-12)
    assert headline.median_ms == pytest.approx(median(med_ms), rel=1e-12)


def test_unknown_backend_headline_is_none() -> None:
    report = build_report()
    assert backend_headline(report, "no-such-solver") is None


def test_malformed_dir_raises_validation_error(tmp_path: Path) -> None:
    # A directory with no reps-* subdirs is a caller error → ValidationError
    # from the LadderLayout min_length=1 constraint.
    (tmp_path / "not-a-reps-dir").mkdir()
    with pytest.raises(ValidationError):
        build_stability_study(tmp_path)


def test_missing_dir_raises_validation_error(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        build_stability_study(tmp_path / "does-not-exist")


def test_markdown_table_and_verdict(tmp_path: Path) -> None:
    _write_ladder(tmp_path)
    study = build_stability_study(tmp_path)
    md = render_markdown(study)

    # One row per rung, one column per backend, verdict + canonical note.
    assert "| 1 |" in md
    assert "| 10 |" in md
    assert "| 100 |" in md
    assert "spectrafit" in md
    assert "converged at N=10" in md
    assert "canonical publication run" in md
    # reps-1 cells carry the signed +5.0% deviation vs the N=100 reference.
    assert "+5.0%" in md


def test_cli_stability_smoke(tmp_path: Path) -> None:
    ladder = tmp_path / "deep"
    _write_ladder(ladder)
    out = tmp_path / "out"

    runner = CliRunner()
    result = runner.invoke(app, ["stability", str(ladder), "--out", str(out)])

    assert result.exit_code == 0, result.output
    assert (out / "stability.json").exists()
    assert (out / "stability.md").exists()
    assert "converged at N=10" in result.output


def test_cli_stability_missing_dir_exits_2(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app, ["stability", str(tmp_path / "nope"), "--out", str(tmp_path / "out")]
    )
    assert result.exit_code == 2
