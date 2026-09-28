"""Unit tests for the agreement-based ``_saturated_categories`` algorithm.

A category is saturated when every case in it shows inter-backend r²
agreement within ``interbackend_tol``, *and* ``min(r²) ≥ r2_floor``.

Saturation is "backends agree at a NEAR-PERFECT fit" — both conditions matter:
agreement (``max-min ≤ interbackend_tol``) AND a real fit-quality floor
(``min(r²) ≥ r2_floor``, default 0.99). Agreement alone is not enough: a case
where every backend is equally mediocre (r² ≈ 0.5) is *not* solved and must not
be reported as saturated (EF-PY-09). The floor blocks both "everyone failed"
and "everyone is so-so".
"""

from __future__ import annotations

from oracles.bench_contract import SuiteCase, SuiteMetric
from oracles.reports import _saturated_categories


def _case(
    cid: str,
    cat: str,
    r2_by_backend: dict[str, float],
) -> SuiteCase:
    return SuiteCase(
        id=cid,
        name=cid,
        category=cat,
        difficulty=0.1,
        m={
            backend: SuiteMetric(
                speedup=1.0,
                r2=r2,
                red_chi2=1.0,
                med_ms=1.0,
                param_err=0.0,
                success=True,
            )
            for backend, r2 in r2_by_backend.items()
        },
        winner=next(iter(r2_by_backend)),
        regression=False,
    )


def test_saturated_when_all_backends_agree_high() -> None:
    """6-backend agreement to 1e-10 at a near-perfect fit → saturated."""
    suite = [
        _case(
            "EZ-001",
            "easy",
            {f"b{i}": 0.999 + 1e-10 * i for i in range(6)},
        ),
        _case(
            "EZ-002",
            "easy",
            {f"b{i}": 0.9991 + 1e-10 * i for i in range(6)},
        ),
    ]
    assert _saturated_categories(suite) == ["easy"]


def test_not_saturated_when_one_case_disagrees() -> None:
    """One case where backends disagree (max-min > tol) breaks saturation."""
    suite = [
        _case("X-001", "edge", {"a": 0.99, "b": 0.991}),
        _case("X-002", "edge", {"a": 0.99, "b": 0.5}),  # 0.49 spread
    ]
    assert _saturated_categories(suite) == []


def test_not_saturated_when_all_backends_failed_equally() -> None:
    """Vacuous saturation (everyone agrees at r²=0.1) blocked by r2_floor."""
    suite = [_case("X-001", "complex", {"a": 0.1, "b": 0.1})]
    assert _saturated_categories(suite) == []


def test_optfn_not_saturated() -> None:
    """Multimodal traps disagree across backends — must not show as saturated."""
    suite = [
        _case("OF-001", "optfn", {"de": 0.95, "lm": 0.5}),
        _case("OF-002", "optfn", {"de": 0.91, "lm": 0.3}),
    ]
    assert _saturated_categories(suite) == []


def test_single_backend_case_not_saturated() -> None:
    """A case with only one backend cannot establish 'inter-backend agreement'."""
    suite = [
        _case("X-001", "scaling", {"only-one": 0.999}),
        _case("X-002", "scaling", {"only-one": 0.998}),
    ]
    assert _saturated_categories(suite) == []


def test_tol_parameter_loosens_classification() -> None:
    """Raising ``interbackend_tol`` flips a near-miss category to saturated."""
    # Both backends above the 0.99 floor, but ~2e-2 apart: a tight tol rejects,
    # a loose tol accepts. (Floor is satisfied; only the agreement tol varies.)
    suite = [_case("X-001", "lineshapes", {"a": 0.991, "b": 0.997})]
    assert _saturated_categories(suite, interbackend_tol=1e-3) == []
    assert _saturated_categories(suite, interbackend_tol=5e-2) == ["lineshapes"]


def test_mediocre_agreement_is_not_saturated() -> None:
    """Backends agreeing at r²≈0.5 is *mediocre*, not 'solved' — must NOT saturate.

    EF-PY-09: the old 0.5 floor let an equally-so-so case (all backends at
    r²≈0.5, spread ≤ tol) be reported as 'saturated / too easy', overstating.
    Saturation means 'backends agree at a near-perfect fit', not 'agree at
    mediocre'. The floor is a real noise ceiling (~0.99), so a 0.5-cluster fails.
    """
    suite = [_case("MED-001", "complex", {"a": 0.50, "b": 0.5005})]
    assert _saturated_categories(suite) == []


def test_near_perfect_agreement_still_saturated() -> None:
    """A category at r²≈0.999 with spread ≤ tol still IS saturated (EF-PY-09)."""
    suite = [_case("HI-001", "easy", {"a": 0.999, "b": 0.9991})]
    assert _saturated_categories(suite) == ["easy"]


def test_multiple_categories_partial_saturation() -> None:
    """Categories evaluated independently — saturated ones surface as a sorted list."""
    suite = [
        # easy: all agree at a near-perfect fit
        _case("EZ-001", "easy", {"a": 0.999, "b": 0.999}),
        _case("EZ-002", "easy", {"a": 0.9991, "b": 0.9991}),
        # complex: also all agree at a near-perfect fit
        _case("CX-001", "complex", {"a": 0.995, "b": 0.995}),
        # optfn: disagree
        _case("OF-001", "optfn", {"a": 0.9, "b": 0.4}),
    ]
    assert _saturated_categories(suite) == ["complex", "easy"]
