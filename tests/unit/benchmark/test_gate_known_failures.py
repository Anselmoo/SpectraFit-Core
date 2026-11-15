r"""Shrink-only known-failure list for the regression gate (#93).

A case on the list that still regresses is reported as a known failure and does
not fail the gate. A case on the list that ran and did not regress fails the gate
with an instruction to remove the entry, so the list can only shrink. A
regression of a case that is not on the list fails the gate as before.

The mechanism is exercised on an explicit test-local list holding the former
OF-014 entry. The shipped entries are checked separately: each carries an issue,
a failure class and a removal condition, and its default-path end point is
measured to be what the class states.

The end-point measure is the stationarity convention of the EELS cross-check:
let $\theta$ be the free parameters, $r = y - f(\theta)$ and
$\mathrm{RSS} = \lVert r \rVert^2$; $J$ is the central-difference Jacobian with
step $h_i = 6.06 \times 10^{-6} s_i$, $s_i = \max(|\theta_i|, 10^{-3})$, its
columns scaled by $s_i$; a component within $10^{-4}$ of a bound (of the bound
span, or of $\max(|\theta^{(0)}_i|, 1)$ for a one-sided bound) whose gradient
points out of the box is held. With $\delta = \arg\min_d \lVert J d - r \rVert$
over the columns not held, $g_{\mathrm{GN}} = \lVert J \delta \rVert^2 / \mathrm{RSS}$,
and the end point is stationary when $g_{\mathrm{GN}} \le 10^{-6}$.
"""

from __future__ import annotations

import json
import math
import re
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from oracles import cli
from oracles.cli import GateThresholds, _gate_load_suite_ids, app, build_gate_report
from oracles.known_failures import (
    KNOWN_FAILURES,
    KnownFailure,
    classify_known_failures,
    stale_entry_message,
)
from typer.testing import CliRunner

OF014_REMOVAL = "SFC default path reaches RSS within the gate tolerance on OF-014"
OF014_STALE = "remove OF-014 from the known-failure list (#93)"
RUN_IDS = frozenset({"EZ-001", "OF-001", "OF-014"})
OF014 = KnownFailure(
    case_id="OF-014",
    issue="#93",
    failure_class="non_stationary_stop",
    removal_condition=OF014_REMOVAL,
)
LISTED = (OF014,)


def _manifest(regression_ids: list[str]) -> dict[str, Any]:
    return {
        "geomean_speedup_vs_baseline": 12.0,
        "max_abs_delta_r2": 1.0e-4,
        "regression_case_ids": regression_ids,
        "nonfinite_dr2_case_ids": [],
        "baseline_solver_id": "lmfit",
    }


def _axis_state(report: cli.GateReport, axis: str) -> str | None:
    return next((a.state for a in report.axes if a.axis == axis), None)


# ---------------------------------------------------------------------------
# The list itself
# ---------------------------------------------------------------------------


GN_TOL = 1e-6  # stationary: Gauss-Newton predicted decrease / RSS <= this
H_REL, THETA_FLOOR = 6.06e-6, 1e-3  # central-difference step, relative to max(|theta|, floor)
AT_BOUND_REL = 1e-4  # active bound, relative to the span or to max(|start|, 1)


def _default_path_end_point(case_id: str) -> tuple[bool, float, int]:
    """(success, GN decrease / RSS, number held) of the gate's spectrafit fit of one case."""
    from oracles.backends import get_backends
    from oracles.backends._scipy_ls import _build_initial_guess, _predict
    from oracles.cases import build_catalog
    from oracles.models import get_model

    case = next(c for c in build_catalog() if c.id == case_id)
    backend = next(b for b in get_backends(tolerance_mode="default") if b.name == "spectrafit")
    model = backend.build(case)
    result, _best_fit = backend.run(model, case)
    names = [n.replace("_", ".", 1) for n in _build_initial_guess(case).names]
    start = np.asarray(
        [float(c.to_params()[p]) for c in case.comp_guess for p in get_model(c.model).param_names],
    )
    lo, hi = np.full(len(names), -np.inf), np.full(len(names), np.inf)
    free = np.zeros(len(names), dtype=bool)
    for node in model[0].nodes:
        for pname, par in node.parameters.items():
            j = names.index(f"{node.id}.{pname}")
            lo[j], hi[j], free[j] = float(par.min), float(par.max), bool(par.vary)
    theta = np.asarray([float(result.parameters[n].value) for n in names])

    r = case.y - _predict(theta, case)
    rss = float(r @ r)
    idx = np.flatnonzero(free)
    scale = np.maximum(np.abs(theta[idx]), THETA_FLOOR)
    h = H_REL * scale
    jac = np.empty((case.y.size, idx.size))
    for c, j in enumerate(idx):
        up, down = theta.copy(), theta.copy()
        up[j] += h[c]
        down[j] -= h[c]
        jac[:, c] = (_predict(up, case) - _predict(down, case)) / (2.0 * h[c])
    grad = -2.0 * jac.T @ r
    held = np.zeros(idx.size, dtype=bool)
    for c, j in enumerate(idx):
        span = hi[j] - lo[j] if math.isfinite(lo[j]) and math.isfinite(hi[j]) else None
        tol = AT_BOUND_REL * (span if span is not None else max(abs(start[j]), 1.0))
        held[c] = (theta[j] - lo[j] <= tol and grad[c] > 0) or (
            hi[j] - theta[j] <= tol and grad[c] < 0
        )
    js = jac[:, ~held] * scale[~held]
    step, *_ = np.linalg.lstsq(js, r, rcond=None)
    return bool(result.success), float(np.sum((js @ step) ** 2) / rss), int(held.sum())


def test_shipped_entries_carry_issue_class_and_removal_condition() -> None:
    ids = [kf.case_id for kf in KNOWN_FAILURES]
    assert len(ids) == len(set(ids))
    for kf in KNOWN_FAILURES:
        assert re.fullmatch(r"#\d+", kf.issue), kf
        assert kf.failure_class in {"non_stationary_stop", "stationary_refused_by_gate"}, kf
        assert kf.removal_condition.strip(), kf


@pytest.mark.parametrize("entry", KNOWN_FAILURES, ids=lambda kf: kf.case_id)
def test_shipped_entry_end_point_is_as_classified(entry: KnownFailure) -> None:
    success, gn, n_held = _default_path_end_point(entry.case_id)
    assert not success, f"{entry.case_id} reports success; remove the entry"
    match entry.failure_class:
        case "non_stationary_stop":
            assert gn > GN_TOL, f"{entry.case_id}: GN {gn:.3g} is stationary"
        case "stationary_refused_by_gate":
            assert gn <= GN_TOL, f"{entry.case_id}: GN {gn:.3g} is not stationary"
            assert n_held > 0, f"{entry.case_id}: no component held at a bound"


def test_known_failure_entry_is_frozen_and_strict() -> None:
    entry = OF014
    # Only a frozen Pydantic model is hashable.
    assert {entry, entry} == {entry}
    with pytest.raises(ValueError, match="extra"):
        KnownFailure.model_validate(
            {
                "case_id": "X",
                "issue": "#1",
                "failure_class": "non_stationary_stop",
                "removal_condition": "r",
                "note": "n",
            },
        )


def test_stale_entry_message_is_the_removal_instruction() -> None:
    assert stale_entry_message(OF014) == OF014_STALE


# ---------------------------------------------------------------------------
# Kernel: the three required scenarios plus the not-in-run case
# ---------------------------------------------------------------------------


def test_listed_and_failing_passes_the_gate_and_is_reported() -> None:
    report = build_gate_report(
        _manifest(["OF-014"]),
        GateThresholds(),
        run_case_ids=RUN_IDS,
        known_failures=LISTED,
    )
    assert report.overall == "pass"
    assert report.regression_ids == []
    regressions = next(a for a in report.axes if a.axis == "regressions")
    assert regressions.state == "pass"
    assert regressions.value == 0.0
    assert _axis_state(report, "known_failures") == "pass"
    [result] = report.known_failures
    assert result.entry == OF014
    assert result.status == "failing"


def test_listed_and_passing_fails_the_gate() -> None:
    report = build_gate_report(
        _manifest([]),
        GateThresholds(),
        run_case_ids=RUN_IDS,
        known_failures=LISTED,
    )
    assert report.overall == "fail"
    assert _axis_state(report, "known_failures") == "fail"
    known_axis = next(a for a in report.axes if a.axis == "known_failures")
    assert known_axis.value == 1.0
    assert known_axis.threshold == 0.0
    [result] = report.known_failures
    assert result.status == "passing"


def test_unlisted_regression_fails_the_gate_as_before() -> None:
    report = build_gate_report(
        _manifest(["OF-001", "OF-014"]),
        GateThresholds(),
        run_case_ids=RUN_IDS,
        known_failures=LISTED,
    )
    assert report.overall == "fail"
    assert report.regression_ids == ["OF-001"]
    assert _axis_state(report, "regressions") == "fail"
    assert _axis_state(report, "known_failures") == "pass"
    assert [r.status for r in report.known_failures] == ["failing"]


def test_listed_case_absent_from_run_neither_fails_nor_counts() -> None:
    report = build_gate_report(
        _manifest([]),
        GateThresholds(),
        run_case_ids=frozenset({"EZ-001"}),
        known_failures=LISTED,
    )
    assert report.overall == "pass"
    assert _axis_state(report, "known_failures") == "pass"
    assert [r.status for r in report.known_failures] == ["not_in_run"]


def test_without_run_evidence_no_known_failure_axis_but_regression_is_excused() -> None:
    """No suite ids (the axis has no evidence): the axis is absent, a listed
    regression is still excused, and nothing can be called passing."""
    report = build_gate_report(_manifest(["OF-014"]), GateThresholds(), known_failures=LISTED)
    assert _axis_state(report, "known_failures") is None
    assert report.overall == "pass"
    assert [r.status for r in report.known_failures] == ["failing"]
    report_clean = build_gate_report(_manifest([]), GateThresholds(), known_failures=LISTED)
    assert report_clean.overall == "pass"
    assert [r.status for r in report_clean.known_failures] == ["not_in_run"]


def test_injected_empty_list_restores_the_plain_regression_axis() -> None:
    report = build_gate_report(
        _manifest(["OF-014"]),
        GateThresholds(),
        run_case_ids=RUN_IDS,
        known_failures=(),
    )
    assert report.overall == "fail"
    assert report.regression_ids == ["OF-014"]
    assert report.known_failures == []


_IDS = st.sampled_from(["A-1", "A-2", "B-1", "B-2", "C-1"])


@given(
    listed=st.sets(_IDS),
    regressed=st.lists(_IDS, unique=True),
    ran=st.sets(_IDS),
)
def test_classification_partitions_the_list(
    listed: set[str],
    regressed: list[str],
    ran: set[str],
) -> None:
    known = tuple(
        KnownFailure(
            case_id=c,
            issue="#0",
            failure_class="non_stationary_stop",
            removal_condition="r",
        )
        for c in sorted(listed)
    )
    effective, results = classify_known_failures(regressed, frozenset(ran), known)
    assert effective == [c for c in regressed if c not in listed]
    assert [r.entry.case_id for r in results] == sorted(listed)
    for r in results:
        cid = r.entry.case_id
        expected = "failing" if cid in regressed else ("passing" if cid in ran else "not_in_run")
        assert r.status == expected


# ---------------------------------------------------------------------------
# Suite-id loading
# ---------------------------------------------------------------------------


def test_load_suite_ids_reads_every_suite_case(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    path.write_text(json.dumps({"suite": [{"id": "OF-014"}, {"id": "EZ-001"}]}))
    assert _gate_load_suite_ids(path) == frozenset({"OF-014", "EZ-001"})


@pytest.mark.parametrize(
    "payload",
    ["not json", json.dumps({"suite": "x"}), json.dumps({"nosuite": []}), json.dumps([1])],
)
def test_load_suite_ids_returns_none_on_malformed_results(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "results.json"
    path.write_text(payload)
    assert _gate_load_suite_ids(path) is None


def test_load_suite_ids_returns_none_when_file_missing(tmp_path: Path) -> None:
    assert _gate_load_suite_ids(tmp_path / "results.json") is None


# ---------------------------------------------------------------------------
# CLI: exit codes and the reported lines
# ---------------------------------------------------------------------------


def _run_gate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    regression_ids: list[str],
    *args: str,
    suite_ids: frozenset[str] = RUN_IDS,
) -> Any:
    run_dir = tmp_path / "benchmark" / "run_001"
    run_dir.mkdir(parents=True)
    suite = [{"id": cid} for cid in sorted(suite_ids)]
    (run_dir / "results.json").write_text(json.dumps({"suite": suite}))
    (run_dir / "manifest.json").write_text(json.dumps(_manifest(regression_ids)))
    monkeypatch.setattr(cli, "latest_run_dir", lambda _category: run_dir)
    monkeypatch.setattr(cli, "latest_results", lambda _category: run_dir / "results.json")
    monkeypatch.setattr(cli, "read_perf_baseline", lambda: None)
    # The shipped list is empty; the CLI paths run on the test-local list.
    monkeypatch.setattr(cli, "_gate_evaluate", partial(cli._gate_evaluate, known_failures=LISTED))
    return CliRunner().invoke(app, ["gate", *args])


def test_cli_listed_and_failing_passes_and_reports(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = _run_gate(monkeypatch, tmp_path, ["OF-014"])
    assert result.exit_code == 0, result.output
    assert "regression gate passed" in result.output
    assert (
        f"known failure OF-014 (#93): still failing, not counted as a regression; "
        f"remove when: {OF014_REMOVAL}"
    ) in result.output


def test_cli_listed_and_passing_fails_with_removal_instruction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = _run_gate(monkeypatch, tmp_path, [])
    assert result.exit_code == 1
    assert "REGRESSION GATE FAILED:" in result.output
    assert f" - {OF014_STALE}" in result.output


def test_cli_unlisted_regression_fails_as_before(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = _run_gate(monkeypatch, tmp_path, ["OF-001", "OF-014"])
    assert result.exit_code == 1
    assert " - 1 case(s) regressed (max allowed 0): OF-001" in result.output


def test_cli_listed_case_not_in_run_is_reported_without_failing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = _run_gate(monkeypatch, tmp_path, [], suite_ids=frozenset({"EZ-001"}))
    assert result.exit_code == 0, result.output
    assert "known failure OF-014 (#93): not in this run" in result.output


def test_cli_json_reports_known_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = _run_gate(monkeypatch, tmp_path, [], "--json")
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "fail"
    assert OF014_STALE in payload["failures"]
    assert payload["regression_case_ids"] == []
    assert payload["known_failures"] == [
        {
            "case_id": "OF-014",
            "issue": "#93",
            "failure_class": "non_stationary_stop",
            "removal_condition": OF014_REMOVAL,
            "status": "passing",
        },
    ]
    assert set(payload["axes"]) == {"speed", "accuracy", "regressions"}
