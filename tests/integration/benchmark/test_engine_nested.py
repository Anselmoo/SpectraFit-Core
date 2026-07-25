"""Integration test: engine populates nested_adequacy for the featured case.

TDD red-first:
  Step 1 — write this failing test (field is None / absent).
  Step 2 — run, confirm fail.
  Step 3 — implement fit_order + engine wiring.
  Step 4 — run, confirm pass.

The featured case is a known tri-Gaussian (3 peaks, true_order = 3).
We assert that nested-model selection recovers the true order under BIC, and
that the documented AIC/BIC disagreement is present (AIC over-selects the
4-peak model while BIC correctly recovers the true 3-peak order).

Featured RSS numbers: m2=13.12 / m3=0.192 / m4=0.185, k=6/9/12, n=180
  ΔAIC(true vs over) ≈ −1.12  → AIC marginally prefers the 4-peak model
  ΔBIC(true vs over) ≈ +8.46  → BIC correctly rejects the 4-peak model

Scope: featured case only — NOT the full suite (too slow for a test).
"""

from __future__ import annotations

import pytest

from oracles.backends import get_backends
from oracles.engine import run_featured
from oracles.cases import build_catalog, featured_case


@pytest.fixture(scope="module")
def featured_nested_adequacy():
    """Run the featured pipeline on the tri-Gaussian case; return nested_adequacy."""
    catalog = build_catalog()
    case = featured_case(catalog)
    backends = get_backends()
    result = run_featured(
        case,
        backends,
        n_reps=1,
        n_mc=2,
        ngrid=[128],
    )
    return result.nested_adequacy


def test_nested_adequacy_is_populated(featured_nested_adequacy) -> None:
    """Engine must populate nested_adequacy (not None) for the featured case."""
    assert featured_nested_adequacy is not None, (
        "run_featured did not populate nested_adequacy for the featured case; "
        "the engine wiring is missing."
    )


def test_nested_adequacy_true_order(featured_nested_adequacy) -> None:
    """The featured case is a 3-peak tri-Gaussian — true_order must be 3."""
    na = featured_nested_adequacy
    assert na is not None
    assert na.true_order == 3, f"Expected true_order=3, got {na.true_order}"


def test_nested_adequacy_recovers_true_order_bic(featured_nested_adequacy) -> None:
    """BIC must recover the true order (reduced rejected + BIC over not preferred).

    Featured numbers: RSS m2=13.12/m3=0.192/m4=0.185, k=6/9/12, n=180
      ΔBIC(true vs over) ≈ +8.46 → BIC correctly rejects the 4-peak over-model.
    """
    na = featured_nested_adequacy
    assert na is not None
    details = (
        f"true_order={na.true_order}, "
        f"selected_order_bic={na.selected_order_bic}, "
        f"reduced_rejected={na.reduced_rejected}, "
        f"over_not_preferred_bic={na.over_not_preferred_bic}, "
        f"recovered_true_order_bic={na.recovered_true_order_bic}, "
        f"LRT_p(red vs true)={na.reduced_vs_true.lrt_p:.4g}, "
        f"ΔAIC(true vs over)={na.true_vs_over.d_aic:.4g}, "
        f"ΔBIC(true vs over)={na.true_vs_over.d_bic:.4g}"
    )
    assert na.recovered_true_order_bic is True, (
        f"BIC did not recover the true order. Details: {details}"
    )
    assert na.selected_order_bic == na.true_order, (
        f"selected_order_bic={na.selected_order_bic} != true_order={na.true_order}. "
        f"Details: {details}"
    )


def test_nested_adequacy_aic_bic_disagree_on_featured(featured_nested_adequacy) -> None:
    """Documented nuance: AIC over-selects (criteria disagree) on the featured case.

    Featured numbers: RSS m2=13.12/m3=0.192/m4=0.185, k=6/9/12, n=180
      ΔAIC(true vs over) ≈ −1.12 → AIC marginallyprefers 4-peak model
      ΔBIC(true vs over) ≈ +8.46 → BIC correctly rejects 4-peak model

    ``over_not_preferred_aic`` MUST be False (AIC over-selects) and
    ``over_not_preferred_bic`` MUST be True (BIC correctly recovers true order).
    Do NOT loosen these assertions — the nuance is the design intent.
    """
    na = featured_nested_adequacy
    assert na is not None
    details = (
        f"ΔAIC={na.true_vs_over.d_aic:.4g}, ΔBIC={na.true_vs_over.d_bic:.4g}, "
        f"over_not_preferred_aic={na.over_not_preferred_aic}, "
        f"over_not_preferred_bic={na.over_not_preferred_bic}"
    )
    assert na.over_not_preferred_aic is False, (
        f"Expected AIC to over-select (over_not_preferred_aic=False) on the "
        f"featured tri-Gaussian. Details: {details}"
    )
    assert na.over_not_preferred_bic is True, (
        f"Expected BIC to correctly reject the over-model "
        f"(over_not_preferred_bic=True). Details: {details}"
    )
