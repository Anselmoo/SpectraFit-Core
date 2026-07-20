"""Nested-model selection statistics for model adequacy V&V."""

import math
from collections.abc import Callable
from pydantic import BaseModel, ConfigDict
from scipy import stats


class SelectionStats(BaseModel):
    """Selection statistics for nested model comparison.

    Computed via LRT, F-test, and information criteria (AIC/BIC).
    All statistics are "full minus reduced" oriented: negative ΔAIC/ΔBIC means
    the full model is preferred.
    """

    model_config = ConfigDict(extra="forbid")
    lrt_stat: float
    lrt_p: float
    f_stat: float
    f_p: float
    d_aic: float
    d_bic: float


def selection_stats(
    rss_reduced: float, rss_full: float, k_reduced: int, k_full: int, n: int
) -> SelectionStats:
    """Compute nested-model selection statistics.

    Parameters:
    -----------
    rss_reduced : float
        Residual sum of squares for the reduced model
    rss_full : float
        Residual sum of squares for the full model
    k_reduced : int
        Number of parameters in reduced model
    k_full : int
        Number of parameters in full model
    n : int
        Number of observations

    Returns:
    --------
    SelectionStats
        Object containing LRT, F-test, and information-criterion statistics.
        All statistics are "full minus reduced" oriented: negative ΔAIC/ΔBIC means
        the full model is preferred.
    """
    dk = k_full - k_reduced

    # LRT: n*ln(RSS_red/RSS_full) ~ χ²(dk) under H0 (reduced adequate)
    lrt = n * math.log(rss_reduced / rss_full)
    lrt_p = float(stats.chi2.sf(lrt, dk))

    # F-test for nested models
    f = ((rss_reduced - rss_full) / dk) / (rss_full / (n - k_full))
    f_p = float(stats.f.sf(f, dk, n - k_full))

    # AIC/BIC from Gaussian MLE (full − reduced; negative ⇒ full preferred)
    def aic(rss: float, k: int) -> float:
        return n * math.log(rss / n) + 2 * k

    def bic(rss: float, k: int) -> float:
        return n * math.log(rss / n) + k * math.log(n)

    return SelectionStats(
        lrt_stat=lrt,
        lrt_p=lrt_p,
        f_stat=f,
        f_p=f_p,
        d_aic=aic(rss_full, k_full) - aic(rss_reduced, k_reduced),
        d_bic=bic(rss_full, k_full) - bic(rss_reduced, k_reduced),
    )


class NestedAdequacy(BaseModel):
    """Result of a nested-order V&V against a known generative order.

    Compares the (true−1) reduced, true, and (true+1) over-fitted models using
    LRT/F/AIC/BIC to verify that model-selection criteria recover the known order.

    Both AIC and BIC verdicts are reported separately so their agreement (or
    disagreement) is visible.  On the featured real tri-Gaussian, AIC over-selects
    the 4-peak model (ΔAIC = −1.12, i.e. ``over_not_preferred_aic = False``) while
    BIC correctly recovers the true order (ΔBIC = +8.46,
    ``over_not_preferred_bic = True``).  Exposing both criteria makes this known
    AIC tendency observable rather than hidden behind a single collapsed flag.
    """

    model_config = ConfigDict(extra="forbid")
    true_order: int
    reduced_rejected: bool
    """LRT p-value < alpha; the reduced model is significantly worse than the true."""
    over_not_preferred_aic: bool
    """``true_vs_over.d_aic > 0`` — the over-model is *not* preferred by AIC."""
    over_not_preferred_bic: bool
    """BIC of the over-model > BIC of the true model — BIC does not prefer the over-model."""
    selected_order_aic: int
    """Order with the lowest absolute Gaussian-MLE AIC across the three orders."""
    selected_order_bic: int
    """Order with the lowest absolute Gaussian-MLE BIC across the three orders."""
    recovered_true_order_aic: bool
    """True iff the criterion's argmin equals ``true_order``.

    Requires ALL of: ``reduced_rejected`` (LRT rejects the reduced model),
    ``over_not_preferred_aic`` (AIC does not prefer the over-model), AND
    ``selected_order_aic == true_order`` (AIC argmin lands on the true order).
    All three conditions must hold; a subset is insufficient.
    """
    recovered_true_order_bic: bool
    """True iff the criterion's argmin equals ``true_order``.

    Requires ALL of: ``reduced_rejected`` (LRT rejects the reduced model),
    ``over_not_preferred_bic`` (BIC does not prefer the over-model), AND
    ``selected_order_bic == true_order`` (BIC argmin lands on the true order).
    All three conditions must hold; a subset is insufficient.
    """
    reduced_vs_true: SelectionStats
    true_vs_over: SelectionStats


def nested_adequacy(
    true_order: int,
    fit_order: Callable[[int], tuple[float, int]],
    n: int,
    alpha: float = 0.01,
) -> NestedAdequacy:
    """Oracle: verify that nested-model selection criteria recover the known generative order.

    Fits three model orders (true_order−1, true_order, true_order+1) via the supplied
    callback and checks that the reduced model is rejected and the over-model is not
    preferred under BOTH AIC and BIC, thus recovering the true order.

    AIC and BIC verdicts are reported separately.  AIC tends to over-select on finite
    samples (it is not order-consistent); BIC is consistent.  On the featured real
    tri-Gaussian, ΔAIC = −1.12 (AIC prefers the 4-peak model) while ΔBIC = +8.46
    (BIC correctly recovers the true 3-peak order).

    Parameters
    ----------
    true_order:
        Known generative model order (m*).
    fit_order:
        Callable ``fit_order(order) -> (rss, k)`` supplying residual sum of squares
        and parameter count for that order.
    n:
        Number of observations.
    alpha:
        Significance threshold for the LRT reduced-model rejection test.

    Returns:
    -------
    NestedAdequacy
        Pydantic model with per-criterion selection verdicts and recovery flags.
    """
    rss_red, k_red = fit_order(true_order - 1)
    rss_true, k_true = fit_order(true_order)
    rss_over, k_over = fit_order(true_order + 1)

    reduced_vs_true = selection_stats(rss_red, rss_true, k_red, k_true, n)
    true_vs_over = selection_stats(rss_true, rss_over, k_true, k_over, n)

    reduced_rejected = reduced_vs_true.lrt_p < alpha

    # Absolute Gaussian-MLE AIC and BIC per order (scipy-free arithmetic).
    def _aic(rss: float, k: int) -> float:
        return n * math.log(rss / n) + 2 * k

    def _bic(rss: float, k: int) -> float:
        return n * math.log(rss / n) + k * math.log(n)

    aic_by_order = {
        true_order - 1: _aic(rss_red, k_red),
        true_order: _aic(rss_true, k_true),
        true_order + 1: _aic(rss_over, k_over),
    }
    bic_by_order = {
        true_order - 1: _bic(rss_red, k_red),
        true_order: _bic(rss_true, k_true),
        true_order + 1: _bic(rss_over, k_over),
    }

    selected_order_aic = min(aic_by_order, key=lambda o: aic_by_order[o])
    selected_order_bic = min(bic_by_order, key=lambda o: bic_by_order[o])

    # AIC: over-model not preferred when d_aic > 0 (true_vs_over oriented: full − reduced).
    over_not_preferred_aic = true_vs_over.d_aic > 0
    # BIC: over-model not preferred when its absolute BIC exceeds the true model's BIC.
    over_not_preferred_bic = bic_by_order[true_order + 1] > bic_by_order[true_order]

    return NestedAdequacy(
        true_order=true_order,
        reduced_rejected=reduced_rejected,
        over_not_preferred_aic=over_not_preferred_aic,
        over_not_preferred_bic=over_not_preferred_bic,
        selected_order_aic=selected_order_aic,
        selected_order_bic=selected_order_bic,
        recovered_true_order_aic=(
            reduced_rejected
            and over_not_preferred_aic
            and (selected_order_aic == true_order)
        ),
        recovered_true_order_bic=(
            reduced_rejected
            and over_not_preferred_bic
            and (selected_order_bic == true_order)
        ),
        reduced_vs_true=reduced_vs_true,
        true_vs_over=true_vs_over,
    )
