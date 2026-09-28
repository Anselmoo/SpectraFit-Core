"""``_per_case_points`` — paired per-case (ms, r2, speedup) records per backend.

Added for the docs Performance page's Pareto scatter and speedup-distribution
charts, which need real per-case spread rather than `_backend_facts`'s single
median per backend. The one behavior worth pinning: a case with a non-finite
value in ONE field must not silently desynchronize the pairing for that
backend (see `_per_case_points`'s own docstring for why this differs from
`_backend_facts`'s independent-per-field filtering).

Uses duck-typed stand-ins for `SuiteMetric`/`SuiteCase`/`BenchReport` (the same
pattern `tests/parity/test_backend_facts_parity.py` uses) rather than the real
Pydantic models: `SuiteMetric`'s own field validator rejects non-finite
`speedup`/`r2`/`med_ms` at construction time, so a real instance can never
hold the NaN/Inf inputs this test needs to exercise the isfinite guard.
"""

from __future__ import annotations

import math
from typing import Any

from oracles.reports import _per_case_points


class _Metric:
    def __init__(self, med_ms: float, r2: float, speedup: float) -> None:
        self.med_ms = med_ms
        self.r2 = r2
        self.speedup = speedup


class _Case:
    def __init__(self, m: dict[str, _Metric]) -> None:
        self.m = m


class _Report:
    def __init__(self, suite: list[_Case]) -> None:
        self.suite = suite


def _report(*cases: dict[str, _Metric]) -> Any:
    return _Report([_Case(m) for m in cases])


def test_finite_case_produces_a_paired_record() -> None:
    report = _report({"spectrafit": _Metric(med_ms=0.4, r2=0.999, speedup=15.0)})
    points = _per_case_points(report)
    assert points["spectrafit"] == [{"ms": 0.4, "r2": 0.999, "speedup": 15.0}]


def test_nonfinite_ms_drops_the_case_for_that_backend_entirely() -> None:
    """A non-finite `med_ms` must exclude the whole record, not just that field.

    Independently filtering `ms`/`r2` the way `_backend_facts` does would leave
    `r2` present with no matching `ms` -- a silent misalignment for any
    consumer that zips the two lists positionally.
    """
    report = _report({"spectrafit": _Metric(med_ms=math.nan, r2=0.999, speedup=10.0)})
    points = _per_case_points(report)
    assert "spectrafit" not in points


def test_nonfinite_speedup_keeps_the_ms_r2_pair_without_a_speedup_key() -> None:
    report = _report({"spectrafit": _Metric(med_ms=0.4, r2=0.999, speedup=math.inf)})
    points = _per_case_points(report)
    assert points["spectrafit"] == [{"ms": 0.4, "r2": 0.999}]


def test_a_backend_absent_from_a_case_contributes_no_record() -> None:
    report = _report(
        {"spectrafit": _Metric(med_ms=0.4, r2=0.999, speedup=10.0)},
        {"lmfit": _Metric(med_ms=6.0, r2=0.999, speedup=1.0)},
    )
    points = _per_case_points(report)
    assert len(points["spectrafit"]) == 1
    assert len(points["lmfit"]) == 1
