"""Cross-backend metric parity: spectrafit vs lmfit vs jax agree where they should.

The benchmark presents spectrafit as the *subject* and lmfit / jax as independent
cross-verification *oracles*. For a well-posed, clean fit all three must converge to
the same solution, so their goodness-of-fit metrics (r², reduced-χ², and — critically —
AIC and BIC) must agree to tolerance.

This guards a real bug: spectrafit-core once computed AIC/BIC with the *raw* χ² as the
deviance (`aic = χ² + 2k`) while lmfit/jax use the standard Gaussian log-likelihood
form (`-2logL = n·ln(χ²/n)`). The two scales are incomparable, which made the report's
cross-backend ΔAIC spuriously rank lmfit "most accurate" at identical fit quality.
See crates/spectrafit-solver/src/postfit.rs.
"""

from __future__ import annotations

import itertools

import pytest

pytest.importorskip(
    "lmfit", reason="benchmark extra (lmfit) required for backend parity"
)

from oracles.backends import get_backends  # noqa: E402
from oracles.cases import build_catalog  # noqa: E402


def _clean_case():
    """A clean, well-posed single-Gaussian case (EZ-001) — all backends must agree."""
    for c in build_catalog():
        if c.id == "EZ-001":
            return c
    raise AssertionError("EZ-001 (single gaussian · clean) not found in catalog")


def _supported_outcomes():
    case = _clean_case()
    out = {}
    for b in get_backends():
        if b.is_supported(case):
            out[b.name] = b.fit(case, n_reps=1)
    return out


def test_at_least_two_backends_available() -> None:
    """Parity is only meaningful with >=2 backends (spectrafit + an oracle)."""
    assert len(_supported_outcomes()) >= 2


@pytest.mark.parametrize("metric", ["r2", "reduced_chi2", "aic", "bic"])
def test_backends_agree_on_metric(metric: str) -> None:
    """Every supported backend agrees on the metric for a clean well-posed fit.

    AIC/BIC are the load-bearing assertion: they only agree across backends if all
    use the same (standard log-likelihood) information-criterion convention.
    """
    outs = _supported_outcomes()
    succeeded = {n: o for n, o in outs.items() if o.success}
    assert len(succeeded) >= 2, f"need >=2 successful backends, got {list(succeeded)}"

    values = {n: float(getattr(o, metric)) for n, o in succeeded.items()}
    for (na, va), (nb, vb) in itertools.combinations(values.items(), 2):
        # AIC/BIC are O(1e3) here; r²/χ² are O(1). Use a scale-aware tolerance.
        tol = 1e-3 + 1e-3 * max(abs(va), abs(vb))
        assert abs(va - vb) <= tol, (
            f"{metric}: {na}={va:.6f} vs {nb}={vb:.6f} disagree (tol {tol:.3g})"
        )


def test_aic_and_bic_are_distinct() -> None:
    """AIC and BIC must NOT be equal — their penalty terms differ (2k vs k·ln n).

    (A regression guard: a copy/paste bug that made AIC == BIC would pass the
    cross-backend test above but is still wrong.)
    """
    outs = _supported_outcomes()
    for name, o in outs.items():
        if o.success:
            assert abs(o.aic - o.bic) > 1e-6, f"{name}: AIC ({o.aic}) == BIC ({o.bic})"
