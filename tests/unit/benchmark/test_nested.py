from oracles.nested import selection_stats, nested_adequacy


def test_full_model_strongly_preferred_rejects_reduced():
    # n=100 points, reduced k=4, full k=7; full RSS far smaller → reduced inadequate
    s = selection_stats(rss_reduced=50.0, rss_full=10.0, k_reduced=4, k_full=7, n=100)
    assert s.lrt_p < 0.01  # LRT rejects the reduced model
    assert s.f_p < 0.01  # F-test agrees
    assert s.d_aic < 0  # full model preferred (lower AIC)
    assert s.d_bic < 0


def test_no_improvement_does_not_prefer_full():
    # equal RSS, full just adds params → full penalised, reduced adequate
    s = selection_stats(rss_reduced=10.0, rss_full=9.999, k_reduced=4, k_full=7, n=100)
    assert s.lrt_p > 0.05  # cannot reject the reduced model
    assert s.d_aic > 0  # AIC prefers the reduced (fewer params)


# ── Task 4.2: nested_adequacy tests ──────────────────────────────────────────


def _sharp_plateau_fit_order(order: int) -> tuple[float, int]:
    """RSS drops sharply up to true_order=3, then plateaus.

    order=2 (reduced):  rss=200, k=5
    order=3 (true):     rss=10,  k=8
    order=4 (over):     rss=9.9, k=11  (near-plateau — no real improvement)
    """
    match order:
        case 2:
            return (200.0, 5)
        case 3:
            return (10.0, 8)
        case 4:
            return (9.9, 11)
        case _:
            raise ValueError(f"Unexpected order: {order}")


def _overfit_reward_fit_order(order: int) -> tuple[float, int]:
    """RSS keeps dropping past true_order — simulates overfit-reward oracle.

    order=2 (reduced):  rss=200, k=5
    order=3 (true):     rss=10,  k=8
    order=4 (over):     rss=1.0, k=11  (large drop → over-model preferred by BIC too)
    """
    match order:
        case 2:
            return (200.0, 5)
        case 3:
            return (10.0, 8)
        case 4:
            return (1.0, 11)
        case _:
            raise ValueError(f"Unexpected order: {order}")


def _aic_over_selects_fit_order(order: int) -> tuple[float, int]:
    """AIC marginal improvement: small RSS drop past true_order that AIC rewards but BIC penalises.

    Designed so that ΔAIC(true vs over) < 0 (AIC prefers the over-model) but
    ΔBIC(true vs over) > 0 (BIC does not prefer the over-model).

    n=200, true_order=3:
      order=2 (reduced):  rss=500, k=6   (clearly worse)
      order=3 (true):     rss=20,  k=9
      order=4 (over):     rss=19,  k=12  (tiny RSS gain — AIC marginal, BIC penalises 3 extra params)

    With n=200:
      ΔAIC = 200·ln(19/200) - 200·ln(20/200) + 2·(12-9)
           = 200·ln(19/20) + 6
           ≈ 200·(-0.05129) + 6 ≈ -10.26 + 6 = -4.26  → AIC < 0, over preferred by AIC
      ΔBIC = 200·ln(19/20) + (12-9)·ln(200)
           ≈ -10.26 + 3·5.298 ≈ -10.26 + 15.89 = 5.63  → BIC > 0, BIC does NOT prefer over

    So over_not_preferred_aic=False, over_not_preferred_bic=True — criteria disagree.
    """
    match order:
        case 2:
            return (500.0, 6)
        case 3:
            return (20.0, 9)
        case 4:
            return (19.0, 12)
        case _:
            raise ValueError(f"Unexpected order: {order}")


def _i1_corner_case_fit_order(order: int) -> tuple[float, int]:
    """I1 corner case: LRT rejects the reduced model AND the over-model is not preferred
    by BIC (pairwise), BUT the three-way BIC argmin lands on the REDUCED order — so
    ``selected_order_bic != true_order`` despite the two component flags being True.

    This exploits the gap between the two-condition definition (old code) and the full
    definition that also requires ``selected_order_bic == true_order`` (new code).

    n=100, true_order=3, alpha=0.01:
      order=2 (reduced): rss=13.0, k=2
      order=3 (true):    rss=10.0, k=10
      order=4 (over):    rss=9.9,  k=13

    BIC(n=100, ln(100)≈4.605):
      BIC(red)  = 100·ln(13/100) + 2·4.605  ≈ -204.0 + 9.21  = -194.8  ← minimum
      BIC(true) = 100·ln(10/100) + 10·4.605 ≈ -230.3 + 46.05 = -184.2
      BIC(over) = 100·ln(9.9/100)+13·4.605  ≈ -231.3 + 59.87 = -171.4

    → selected_order_bic = 2 (reduced), NOT 3 (true).

    LRT(red vs true) = 100·ln(13/10) = 26.24, dk=8, χ²(8) p ≈ 0.001 < 0.01 → rejected.
    over_not_preferred_bic = (BIC_over > BIC_true) = (-171.4 > -184.2) = True.

    Old code: recovered_true_order_bic = True and True = True  ← WRONG
    New code: recovered_true_order_bic = True and True and (2 == 3) = False  ← CORRECT
    """
    match order:
        case 2:
            return (13.0, 2)
        case 3:
            return (10.0, 10)
        case 4:
            return (9.9, 13)
        case _:
            raise ValueError(f"Unexpected order: {order}")


def test_nested_adequacy_recovers_true_order():
    """Sharp-plateau oracle: both AIC and BIC selection criteria recover m*=3."""
    result = nested_adequacy(true_order=3, fit_order=_sharp_plateau_fit_order, n=100)
    assert result.true_order == 3
    assert result.reduced_rejected is True  # reduced (order=2) is rejected
    assert result.over_not_preferred_aic is True  # over-model not preferred by AIC
    assert result.over_not_preferred_bic is True  # over-model not preferred by BIC
    assert result.recovered_true_order_aic is True  # AIC recovers true order
    assert result.recovered_true_order_bic is True  # BIC recovers true order
    assert result.selected_order_aic == 3  # AIC argmin is the true order
    assert result.selected_order_bic == 3  # BIC argmin is the true order


def test_nested_adequacy_detects_broken_selection_bic():
    """Overfit-reward oracle: over-model IS preferred by BIC → guard detects broken selection."""
    result = nested_adequacy(true_order=3, fit_order=_overfit_reward_fit_order, n=100)
    assert result.over_not_preferred_bic is False  # BIC also prefers over-model
    assert result.recovered_true_order_bic is False  # BIC selection failed


def test_nested_adequacy_aic_bic_disagree():
    """AIC/BIC split: AIC over-selects (criteria disagree) — oracle detects the nuance.

    With the ``_aic_over_selects_fit_order`` fixture and n=200:
      over_not_preferred_aic = False  (AIC prefers the extra peak)
      over_not_preferred_bic = True   (BIC correctly rejects the extra peak)
    """
    result = nested_adequacy(true_order=3, fit_order=_aic_over_selects_fit_order, n=200)
    # Criteria disagree
    assert result.over_not_preferred_aic != result.over_not_preferred_bic, (
        f"Expected AIC/BIC to disagree: "
        f"over_not_preferred_aic={result.over_not_preferred_aic}, "
        f"over_not_preferred_bic={result.over_not_preferred_bic}, "
        f"d_aic={result.true_vs_over.d_aic:.4f}, d_bic={result.true_vs_over.d_bic:.4f}"
    )
    assert result.over_not_preferred_aic is False  # AIC over-selects
    assert result.over_not_preferred_bic is True  # BIC correctly rejects extra peak
    # Only BIC recovers the true order
    assert result.recovered_true_order_aic is False
    assert result.recovered_true_order_bic is True
    # BIC argmin is the true order; AIC argmin is the over-model
    assert result.selected_order_bic == 3
    assert result.selected_order_aic == 4


def test_nested_adequacy_i1_corner_case_reduced_wins_bic_argmin():
    """I1 corner case: LRT rejects reduced AND over not preferred by BIC (pairwise),
    but the three-way BIC argmin lands on the reduced order — NOT the true order.

    The OLD definition (``reduced_rejected and over_not_preferred_bic``) would
    incorrectly return ``recovered_true_order_bic = True`` here.
    The NEW definition also requires ``selected_order_bic == true_order``, which
    is False → ``recovered_true_order_bic`` must be False.

    Fixture numbers (n=100, true_order=3):
      BIC(red=2)=-194.8 < BIC(true=3)=-184.2 < BIC(over=4)=-171.4
      LRT p≈0.001 < 0.01 (reduced rejected); BIC_over > BIC_true (over not preferred)
      but selected_order_bic == 2 ≠ 3 (true order).
    """
    result = nested_adequacy(true_order=3, fit_order=_i1_corner_case_fit_order, n=100)
    # Preconditions: both component flags are True (this is why the old code was wrong)
    assert result.reduced_rejected is True, "LRT must reject the reduced model"
    assert result.over_not_preferred_bic is True, (
        "BIC pairwise: over-model not preferred"
    )
    # The argmin lands on the reduced order, not the true order
    assert result.selected_order_bic == 2, (
        f"selected_order_bic should be 2 (reduced), got {result.selected_order_bic}"
    )
    assert result.selected_order_bic != result.true_order, (
        "selected_order_bic must differ from true_order in this corner case"
    )
    # The fix: recovered must be False because the argmin is not the true order
    assert result.recovered_true_order_bic is False, (
        "recovered_true_order_bic must be False when selected_order_bic != true_order "
        "(I1 corner case: old code returned True incorrectly)"
    )


def test_nested_adequacy_fields_populated():
    """SelectionStats fields are present on the returned object."""
    result = nested_adequacy(true_order=3, fit_order=_sharp_plateau_fit_order, n=100)
    # reduced_vs_true: comparing order=2 vs order=3
    assert result.reduced_vs_true.lrt_stat > 0
    assert 0.0 <= result.reduced_vs_true.lrt_p <= 1.0
    # true_vs_over: comparing order=3 vs order=4
    assert result.true_vs_over.lrt_stat >= 0
    assert 0.0 <= result.true_vs_over.lrt_p <= 1.0
