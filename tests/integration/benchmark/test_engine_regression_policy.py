"""Regression-flag policy pins (Cycle 4 · Phase 1).

`SuiteCase.regression` used to be set on ANY supported backend's
`o.success = False`, ignoring the case category. That made every healthy
run look red on the eyes-on-glass GateBadge — 9 of 11 regressions on
the 2026-06-06 sample were oracle (lmfit / jax / scipy-ls-*) failures
on `optfn` cases, which CLAUDE.md explicitly excludes from the
accuracy-axis gate ("Backend Comparison Fairness").

These tests pin the corrected policy:

* `subject` (spectrafit) failure on ANY category → `regression = True`.
* `oracle` (non-spectrafit) failure on `optfn` → `regression = False`.
* `oracle` failure on any non-optfn category → `regression = True`.
* All-success on all backends → `regression = False`.

They drive `run_suite` with synthetic Backend stubs whose `fit` is
overridden — `_safe_fit` calls `backend.fit` directly, so the
abstract `build`/`run`/`extract` template methods never execute and
the test runs deterministically in milliseconds.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from oracles.backends._base import Backend, BackendOutcome
from oracles.engine import run_suite


class _StubBackend(Backend):
    """Backend whose `fit` returns a synthetic outcome with a chosen `success`.

    `build`/`run`/`extract` are stubbed (never called because `fit` is
    overridden) so ABC accepts the subclass. The Pydantic `BackendOutcome`
    is constructed with valid-but-trivial values for every required field.
    """

    def __init__(self, name: str, *, success: bool) -> None:
        # `Backend.name` is a class attribute (`str`); set per-instance here.
        self.name = name
        self._success = success

    def is_supported(self, case: Any) -> bool:  # noqa: ARG002
        return True

    def build(self, case: Any) -> Any:  # noqa: ARG002 - never called
        raise NotImplementedError

    def run(self, model: Any, case: Any) -> Any:  # noqa: ARG002 - never called
        raise NotImplementedError

    def extract(self, raw: Any, case: Any) -> BackendOutcome:  # noqa: ARG002 - never called
        raise NotImplementedError

    def fit(self, case: Any, n_reps: int = 1) -> BackendOutcome:  # noqa: ARG002
        return BackendOutcome(
            backend=self.name,
            success=self._success,
            r2=1.0 if self._success else 0.0,
            chi2=0.5,
            reduced_chi2=1.0,
            aic=0.0,
            bic=0.0,
            n_iter=2,
            params={},
            param_stderr={},
            best_fit=np.zeros(4),
            cost_history=[1.0, 0.5],
            gradient_norm_history=[1.0, 0.5],
            history_source="real",
            timing_ms=[10.0],
            supported=True,
        )


class _StubCase:
    """Duck-typed BenchCase carrying only the fields `run_suite` touches.

    `run_suite` reads `case.id`, `case.name`, `case.category`, `case.difficulty`,
    `case.spec.noise` (σ for the σ-weighted reduced-χ²), `case.y` (point count for
    the dof), and `case.comp_true` (via the deep-dive helpers, which we don't
    trigger here). It also calls `outcome.param_error(case)` which inspects
    `case.recover`/`case.comp_true`; setting `recover=False` short-circuits
    that to `nan`, which `np.nan_to_num` cleans up.

    NOTE on the coupling: `run_suite` reaches into `case.spec.noise` and `case.y`,
    so this stub must mirror that surface. The cleaner fix (tracked in the hotspots
    backlog) is for `run_suite` to receive σ explicitly rather than spelunk the spec.
    `y` length matches the stub outcome's `best_fit` (4) so the χ²_red broadcast aligns.
    """

    def __init__(self, case_id: str, category: str) -> None:
        self.id = case_id
        self.name = f"synthetic {case_id}"
        # σ for the σ-weighted reduced-χ² (engine reads case.spec.noise).
        self.spec = SimpleNamespace(noise=0.02)
        # observed vector; length 4 matches the stub outcome's best_fit so the
        # (y − fit)/σ computation broadcasts cleanly.
        self.y = np.zeros(4)
        self.category = category
        self.difficulty = 0.1
        self.comp_true: list = []
        self.recover = False


@pytest.mark.parametrize(
    ("case_id", "category", "spectrafit_ok", "oracle_ok", "expected_regression"),
    [
        # All-success on a regular case → no regression.
        ("EZ-001", "easy", True, True, False),
        # Subject (spectrafit) fails on a regular case → regression.
        ("CX-017", "complex", False, True, True),
        # Oracle fails on a regular case → regression.
        ("CX-020", "complex", True, False, True),
        # Oracle fails on optfn → policy says NOT a regression (the fix).
        ("OF-004", "optfn", True, False, False),
        # Subject fails on optfn → STILL a regression (subject failures count
        # everywhere because spectrafit is the SUT).
        ("OF-005", "optfn", False, True, True),
        # All-success on optfn → no regression.
        ("OF-010", "optfn", True, True, False),
        # Both fail on optfn → subject failure still wins.
        ("OF-013", "optfn", False, False, True),
        # Both fail on non-optfn → regression (either path triggers it).
        ("ED-007", "edge", False, False, True),
    ],
)
def test_regression_policy_excludes_oracle_optfn_failures(
    case_id: str,
    category: str,
    spectrafit_ok: bool,
    oracle_ok: bool,
    expected_regression: bool,
) -> None:
    case = _StubCase(case_id, category)
    backends = [
        _StubBackend("spectrafit", success=spectrafit_ok),
        _StubBackend("lmfit", success=oracle_ok),
    ]
    suite = run_suite([case], backends, n_reps=1, baseline_solver_id="lmfit")  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
    assert len(suite) == 1
    assert suite[0].regression is expected_regression, (
        f"case {case_id} ({category}): spectrafit_ok={spectrafit_ok} "
        f"oracle_ok={oracle_ok} expected regression={expected_regression}, "
        f"got {suite[0].regression}"
    )


def test_regression_policy_subject_failure_dominates_across_categories() -> None:
    """Spectrafit-only failure surfaces on every category — including optfn.

    Anti-regression for the *next* potential drift: if someone tightens the
    policy further and accidentally suppresses subject failures on optfn,
    this test catches it. The subject is the SUT; we never silence it.
    """
    categories = (
        "easy",
        "complex",
        "optfn",
        "edge",
        "scaling",
        "lineshapes",
        "reality",
    )
    cases = [_StubCase(f"X-{i}", c) for i, c in enumerate(categories)]
    backends = [
        _StubBackend("spectrafit", success=False),
        _StubBackend("lmfit", success=True),
    ]
    suite = run_suite(cases, backends, n_reps=1, baseline_solver_id="lmfit")  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
    assert all(row.regression for row in suite), [
        (row.id, row.category, row.regression) for row in suite
    ]


def test_regression_policy_oracle_optfn_silenced_in_isolation() -> None:
    """An oracle-only failure on optfn does NOT raise the regression flag.

    Explicit, dedicated check for the exact pattern that was previously red
    (9 of 11) on the 2026-06-06 sample: scipy-ls-dogbox failing OF-004 etc.
    """
    case = _StubCase("OF-004", "optfn")
    backends = [
        _StubBackend("spectrafit", success=True),
        _StubBackend("scipy-ls-dogbox", success=False),
    ]
    suite = run_suite([case], backends, n_reps=1, baseline_solver_id="lmfit")  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
    assert suite[0].regression is False
