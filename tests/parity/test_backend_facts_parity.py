"""The per-backend median reduction is implemented twice; pin both to one golden.

``_backend_facts`` in ``python/oracles/reports.py`` is a hand port of
``backendFacts()`` in ``web/src/series/backendFacts.ts``. The dashboard computes
those medians in the browser from the served report; the docs performance page
cannot (``results.json`` is ~49 MB and hook-blocked), so the Python side caches
the same reduction into ``manifest.json``.

Two implementations of one statistic, in two languages, whose outputs are
published side by side on the same Pages host under the same run id. Nothing
compared them. ``_backend_facts``'s own docstring claimed "tests/parity/ is
where that mirroring is enforced" — that was false when written; this file is
what makes it true.

The failure it guards is quiet: change the median convention in the TS (lower
median instead of mean-of-two-middles), or the ``Number.isFinite`` guard, or what
counts toward ``successRate``, and the dashboard shows one number while the docs
page shows another for the same run. No build breaks. A human comparing two
screens would have to notice a fourth-decimal difference.

Rather than executing TypeScript from pytest, both sides assert against the same
golden fixture — ``fixtures/backend_facts_golden.json``, mirrored by
``web/src/series/__tests__/backendFacts.golden.test.ts``. Either implementation
drifting fails its own suite, in its own language, without needing a cross-language
runner in CI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from oracles.reports import _backend_facts

GOLDEN = Path(__file__).parent / "fixtures" / "backend_facts_golden.json"


class _Metric:
    """Duck-typed stand-in for SuiteMetric — only the fields the reduction reads."""

    def __init__(self, med_ms: float, r2: float, speedup: float, success: bool) -> None:
        self.med_ms = med_ms
        self.r2 = r2
        self.speedup = speedup
        self.success = success


class _Case:
    def __init__(self, m: dict[str, _Metric]) -> None:
        self.m = m


class _Report:
    def __init__(self, suite: list[_Case]) -> None:
        self.suite = suite


@pytest.fixture(scope="module")
def golden() -> dict[str, Any]:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def _report_from(golden: dict[str, Any]) -> _Report:
    return _Report(
        [
            _Case({k: _Metric(**v) for k, v in case["m"].items()})
            for case in golden["suite"]
        ]
    )


def test_golden_fixture_is_shared_with_the_typescript_side() -> None:
    """The fixture must stay reachable from web/, or the mirror silently halves."""
    mirror = (
        Path(__file__).resolve().parents[2]
        / "web"
        / "src"
        / "series"
        / "__tests__"
        / "backendFacts.golden.test.ts"
    )
    assert GOLDEN.is_file(), f"missing golden fixture {GOLDEN}"
    assert mirror.is_file(), (
        f"missing {mirror}. Both implementations must assert against "
        f"{GOLDEN.name}; deleting one half turns this into a single-language test "
        "that cannot detect divergence."
    )


@pytest.mark.parametrize("backend", ["alpha", "beta"])
def test_python_reduction_matches_golden(backend: str, golden: dict[str, Any]) -> None:
    """``_backend_facts`` reproduces the shared golden exactly."""
    facts = _backend_facts(_report_from(golden))
    assert backend in facts, f"{backend} missing from _backend_facts output"
    expected = golden["expected"][backend]
    for field, want in expected.items():
        got = facts[backend][field]
        assert got == pytest.approx(want), (
            f"{backend}.{field}: python={got} golden={want}. If this is an "
            "intentional change to the reduction, update the golden AND "
            "web/src/series/backendFacts.ts together — they are one statistic."
        )


def test_absent_backend_is_not_counted(golden: dict[str, Any]) -> None:
    """A backend missing from a case contributes nothing to that case.

    Called out separately because it is the branch most likely to diverge: the
    TS does `if (m == null) continue` before incrementing, and an equivalent
    Python port that iterated `case.m.values()` instead of looking the id up
    would silently agree on every backend that ran everywhere, and disagree only
    for a partially-run one like jax (58 of 151 cases in the real suite).
    """
    facts = _backend_facts(_report_from(golden))
    assert facts["beta"]["cases_run"] == 3, "beta appears in 3 of 4 golden cases"
    assert facts["alpha"]["cases_run"] == 4
