"""The docs gate (homepage proof strip and performance page) applies the known-failure list.

``docs/_render_benchmark_summary.py`` recomputes the run's default gate from
``manifest.json`` with the list in :mod:`oracles.known_failures`: listed cases that
regress are shown as known failures with their case id and failure class, and every
other regression still fails the gate. The issue field of an entry never reaches the
rendered output. All manifests here are synthetic.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from oracles.cli import GateThresholds, build_gate_report
from oracles.known_failures import KNOWN_FAILURES, KnownFailure

SHIPPED_IDS = ["CX-009", "CX-010", "CX-014", "CX-015", "CX-017", "CX-020"]
RENDERER_PATH = Path(__file__).resolve().parents[3] / "docs" / "_render_benchmark_summary.py"


def _load_renderer() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_render_benchmark_summary", RENDERER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


renderer = _load_renderer()


def _manifest(
    regression_ids: list[str],
    *,
    geomean: float = 17.49,
    max_dr2: float = 1.0e-5,
    nonfinite: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "run_id": "2026-01-01_run_001",
        "date": "2026-01-01",
        "n_cases": 160,
        "baseline_solver_id": "lmfit",
        "geomean_speedup_vs_baseline": geomean,
        "spectrafit_win_rate": 0.8,
        "max_abs_delta_r2": max_dr2,
        "regressions": len(regression_ids),
        "regression_case_ids": regression_ids,
        "nonfinite_dr2_case_ids": nonfinite or [],
        "gate_state": "fail" if regression_ids else "pass",
    }


def _render_both(manifest: dict[str, Any], *, ci_runner: bool = False) -> tuple[str, str]:
    gate = renderer.gate_view(manifest)
    hero = renderer._format_hero_proof(manifest, gate, ci_runner=ci_runner)
    page = renderer._format_summary(manifest, {}, gate, ci_runner=ci_runner)
    return hero, page


def test_shipped_list_holds_exactly_the_six_cases() -> None:
    assert [kf.case_id for kf in KNOWN_FAILURES] == SHIPPED_IDS


def test_gate_passes_with_exactly_the_six_listed_cases_regressing() -> None:
    manifest = _manifest(list(SHIPPED_IDS))
    gate = renderer.gate_view(manifest)
    assert gate.state == "pass"
    assert gate.regressions == 0
    assert [row.case_id for row in gate.known_failures] == SHIPPED_IDS
    assert [row.failure_class for row in gate.known_failures] == [
        kf.failure_class for kf in KNOWN_FAILURES
    ]

    hero, page = _render_both(manifest)
    assert "Gate: PASS" in hero
    assert "0 regressions" in hero
    assert "6 known failures: CX-009, CX-010, CX-014, CX-015, CX-017, CX-020" in hero
    assert "✅ **PASS**" in page
    assert "| Regressions | 0 |" in page
    assert "| Known failures | 6 |" in page
    for kf in KNOWN_FAILURES:
        assert f"| `{kf.case_id}` | `{kf.failure_class}` |" in page


def test_docs_verdict_matches_the_benchmark_gate_kernel() -> None:
    for regression_ids in ([], list(SHIPPED_IDS), [*SHIPPED_IDS, "OF-001"], ["OF-001"]):
        manifest = _manifest(regression_ids)
        expected = build_gate_report(manifest, GateThresholds())
        gate = renderer.gate_view(manifest)
        assert gate.state == expected.overall
        assert gate.regressions == len(expected.regression_ids)


@given(
    listed=st.lists(st.sampled_from(SHIPPED_IDS), unique=True),
    others=st.lists(
        st.from_regex(r"[A-Z]{2}-[0-9]{3}", fullmatch=True).filter(
            lambda cid: cid not in SHIPPED_IDS,
        ),
        min_size=1,
        max_size=5,
        unique=True,
    ),
)
def test_any_unlisted_regression_fails_the_gate(listed: list[str], others: list[str]) -> None:
    manifest = _manifest([*listed, *others])
    gate = renderer.gate_view(manifest)
    assert gate.state == "fail"
    assert gate.regressions == len(others)
    assert [row.case_id for row in gate.known_failures] == [
        cid for cid in SHIPPED_IDS if cid in listed
    ]
    hero, page = _render_both(manifest)
    assert "Gate: FAIL" in hero
    assert f"{len(others)} regressions" in hero
    assert "❌ **FAIL**" in page
    assert f"| Regressions | {len(others)} |" in page


@given(listed=st.lists(st.sampled_from(SHIPPED_IDS), unique=True))
def test_listed_regressions_alone_never_fail_the_gate(listed: list[str]) -> None:
    gate = renderer.gate_view(_manifest(listed))
    assert gate.state == "pass"
    assert gate.regressions == 0
    assert len(gate.known_failures) == len(listed)


@pytest.mark.parametrize(
    "overrides",
    [
        {"geomean": 0.5},
        {"max_dr2": 1.0e-2},
        {"nonfinite": ["EZ-001"]},
    ],
    ids=["speed", "accuracy", "nonfinite-accuracy"],
)
def test_speed_and_accuracy_failures_still_fail(overrides: dict[str, Any]) -> None:
    gate = renderer.gate_view(_manifest(list(SHIPPED_IDS), **overrides))
    assert gate.state == "fail"
    assert gate.regressions == 0
    assert len(gate.known_failures) == len(SHIPPED_IDS)


def test_no_known_failure_metric_without_listed_regressions() -> None:
    hero, page = _render_both(_manifest([]))
    assert "known failure" not in hero
    assert "| Known failures | 0 |" in page
    assert "## Known failures" not in page


@pytest.mark.parametrize("count", range(1, len(SHIPPED_IDS) + 1))
def test_known_failure_metric_agrees_in_number(count: int) -> None:
    listed = SHIPPED_IDS[:count]
    hero, _ = _render_both(_manifest(listed))
    noun = "known failure" if count == 1 else "known failures"
    assert f"{count} {noun}: {', '.join(listed)}</span>" in hero
    if count == 1:
        assert "known failures" not in hero


def test_known_failures_section_states_the_removal_rule_and_the_report_html_caveat() -> None:
    _, page = _render_both(_manifest(list(SHIPPED_IDS)))
    section = " ".join(page.split("## Known failures", 1)[1].split())
    assert "An entry is removed from the list when its removal condition holds." in section
    assert (
        "The interactive report (report.html) still counts these cases as regressions "
        "until it is updated."
    ) in section
    assert "no longer fails" not in section


def test_manifest_without_case_ids_keeps_the_stored_verdict() -> None:
    manifest = _manifest(list(SHIPPED_IDS))
    del manifest["regression_case_ids"]
    gate = renderer.gate_view(manifest)
    assert gate.state == "fail"
    assert gate.regressions == len(SHIPPED_IDS)
    assert gate.known_failures == []


def test_issue_and_removal_condition_never_rendered_for_shipped_entries() -> None:
    hero, page = _render_both(_manifest(list(SHIPPED_IDS)), ci_runner=True)
    for kf in KNOWN_FAILURES:
        for text in (hero, page):
            assert kf.issue not in text
            assert kf.removal_condition not in text


def test_issue_field_never_rendered_for_any_entry() -> None:
    entry = KnownFailure(
        case_id="ZZ-999",
        issue="ISSUE-SENTINEL-not-for-rendering",
        failure_class="stationary_refused_by_gate",
        removal_condition="REMOVAL-SENTINEL-not-for-rendering",
    )
    manifest = _manifest(["ZZ-999"])
    gate = renderer.gate_view(manifest, (entry,))
    assert gate.state == "pass"
    hero = renderer._format_hero_proof(manifest, gate, ci_runner=True)
    page = renderer._format_summary(manifest, {}, gate, ci_runner=True)
    for text in (hero, page):
        assert "ZZ-999" in text
        assert "ISSUE-SENTINEL" not in text
        assert "REMOVAL-SENTINEL" not in text
    assert "`stationary_refused_by_gate`" in page
    assert set(type(gate.known_failures[0]).model_fields) == {"case_id", "failure_class"}


def test_speed_figures_labelled_as_ci_runner_measurements_only_in_ci() -> None:
    manifest = _manifest(list(SHIPPED_IDS))
    hero_ci, page_ci = _render_both(manifest, ci_runner=True)
    assert "17.49&times; geomean vs. lmfit, measured on a CI runner" in hero_ci
    assert "| Geomean speedup vs. `lmfit` (measured on a CI runner) | 17.49× |" in page_ci
    assert "Timings were measured on a CI runner" in page_ci

    hero_local, page_local = _render_both(manifest, ci_runner=False)
    for text in (hero_local, page_local):
        assert "CI runner" not in text


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({"CI": "true"}, True),
        ({"CI": "TRUE"}, True),
        ({"CI": "false"}, False),
        ({"CI": ""}, False),
        ({}, False),
    ],
    ids=["true", "upper-case", "false", "empty", "unset"],
)
def test_running_in_ci_reads_the_ci_variable(environ: dict[str, str], expected: bool) -> None:
    assert renderer.running_in_ci(environ) is expected


def test_running_in_ci_defaults_to_the_process_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CI", "true")
    assert renderer.running_in_ci() is True
    monkeypatch.delenv("CI")
    assert renderer.running_in_ci() is False
