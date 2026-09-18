r"""``robust`` category: IRLS on outlier-contaminated spectra.

Guards the three things the category promises: every case carries an outlier
recipe and an ``irls:<weight>`` solver hint, ``materialize`` really injects the
contamination (deterministically), and the category is exempt from the
baseline-parity axes exactly like ``optfn`` — an M-estimator on contaminated
data and a least-squares baseline solve *different problems*, so their
$|\Delta r^2|$ is not a regression signal.
"""

from __future__ import annotations

import numpy as np
import pytest
from oracles import cases

_WEIGHTS = ("huber", "bisquare", "cauchy")


@pytest.fixture(scope="module")
def robust_cases() -> list[cases.BenchCase]:
    """The materialized ``robust`` cases, in catalog order."""
    return [c for c in cases.build_catalog() if c.category == "robust"]


def test_registry_has_robust_category_exempt_from_baseline_parity() -> None:
    """``robust`` is registered, non-comparable, and ``optfn`` keeps that flag too."""
    cdef = cases.CATEGORY_REGISTRY["robust"]
    assert cdef.prefix == "RB"
    assert cdef.baseline_comparable is False
    assert cases.CATEGORY_REGISTRY["optfn"].baseline_comparable is False
    assert frozenset({"optfn", "robust"}) == cases.NON_COMPARABLE_CATEGORIES
    comparable = {cid for cid, c in cases.CATEGORY_REGISTRY.items() if c.baseline_comparable}
    assert comparable == set(cases.CATEGORY_REGISTRY) - {"optfn", "robust"}


def test_robust_cases_span_weights_and_contamination_levels(
    robust_cases: list[cases.BenchCase],
) -> None:
    """3 weight functions $\\times$ 2 contamination levels, each with an outlier recipe."""
    assert len(robust_cases) == cases.CATEGORY_COUNTS["robust"] == 6
    hints = [c.solver_hint for c in robust_cases]
    assert all(h.startswith("irls:") for h in hints), hints
    assert {h.removeprefix("irls:") for h in hints} == set(_WEIGHTS)
    fractions = {c.spec.outliers.fraction for c in robust_cases if c.spec.outliers}
    assert fractions == {0.05, 0.15}
    assert all(c.spec.outliers is not None for c in robust_cases)
    assert all(c.spec.recover for c in robust_cases)


def test_only_robust_cases_carry_an_outlier_recipe() -> None:
    """The recipe is a ``robust``-only feature — nothing else is contaminated."""
    for spec in cases.build_specs():
        assert (spec.outliers is not None) == (spec.category == "robust"), spec.id


def test_materialize_injects_the_declared_fraction_of_outliers(
    robust_cases: list[cases.BenchCase],
) -> None:
    """|y − truth| exceeds the noise floor on exactly round(fraction · n) points."""
    for case in robust_cases:
        spec = case.spec
        assert spec.outliers is not None
        clean = cases.curve(case.x, case.comp_true)
        deviation = np.abs(case.y - clean)
        # Gaussian noise at σ_n = spec.noise never reaches 6σ_n on 160 points;
        # an outlier spike is magnitude × max|clean| ≥ 4 × 3 ≫ 6σ_n.
        n_out = int(np.sum(deviation > 6.0 * spec.noise))
        assert n_out == round(spec.outliers.fraction * spec.n_points), case.id
        assert deviation.max() >= 0.5 * spec.outliers.magnitude * float(np.abs(clean).max())


def test_materialize_is_deterministic_for_robust_cases(
    robust_cases: list[cases.BenchCase],
) -> None:
    """Same spec ⇒ bit-identical contaminated y (outlier indices come from the id seed)."""
    for case in robust_cases:
        again = cases.materialize(case.spec)
        np.testing.assert_array_equal(again.y, case.y)


def test_regression_policy_exempts_non_spectrafit_failures_on_robust_cases(
    robust_cases: list[cases.BenchCase],
) -> None:
    """A baseline failing on a robust case is not a suite regression; spectrafit failing is."""
    from oracles.backends._base import Backend, BackendOutcome
    from oracles.engine import _phase_suite_regression

    class _Stub(Backend):
        name = "stub"

        def __init__(self, name: str) -> None:
            self.name = name

        def build(self, case: cases.BenchCase) -> object:
            return None

        def run(self, model: object, case: cases.BenchCase) -> object:
            return None

        def extract(self, raw: object, case: cases.BenchCase) -> BackendOutcome:
            raise NotImplementedError

    case = robust_cases[0]
    lmfit, sf = _Stub("lmfit"), _Stub("spectrafit")
    assert _phase_suite_regression([lmfit], {"lmfit": None}, case) is False
    assert _phase_suite_regression([sf], {"spectrafit": None}, case) is True


@pytest.mark.parametrize("index", range(6))
def test_spectrafit_irls_recovers_truth_under_contamination(
    robust_cases: list[cases.BenchCase],
    index: int,
) -> None:
    """IRLS recovers amplitude/center/sigma to within 5 % despite the outliers.

    The bound is deliberately loose relative to the clean-data precision
    (the same fixture reaches machine precision in the Rust unit tests) so it
    tolerates the 15 % Cauchy case, whose smooth down-weighting leaves a small
    residual pull; anything past 5 % means the loss function is not doing its
    job.
    """
    pytest.importorskip("spectrafit_core")
    from oracles.backends._spectrafit import SpectraFitBackend

    case = robust_cases[index]
    outcome = SpectraFitBackend().fit(case, n_reps=1)
    assert outcome.success, (case.id, case.solver_hint)
    (truth,) = case.comp_true
    for pname in ("amplitude", "center", "sigma"):
        fitted = next(v for k, v in outcome.params.items() if k.endswith(pname))
        true = float(getattr(truth, pname))
        scale = abs(true) if pname != "center" else float(truth.sigma)
        assert abs(fitted - true) <= 0.05 * scale, (case.id, pname, fitted, true)
