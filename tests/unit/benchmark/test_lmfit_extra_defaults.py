"""Unit tests: PeakModel.extra_defaults wired into LmfitBackend.build.

P3 anti-regression: when a comp_guess component does not supply an explicit
value for a param listed in PeakModel.extra_defaults, LmfitBackend.build must
initialise that lmfit Parameter to the extra_defaults value instead of
raising KeyError or silently using an arbitrary default.

The canonical example is pseudo_voigt / fraction = 0.5 (PeakModel.extra_defaults
= {"fraction": 0.5}). Before the fix the parameter-init dict comprehension was
``{n: float(cp[n]) for n in pm.param_names}``, which would KeyError on any param
absent from comp.to_params(); after the fix it falls back to extra_defaults.

We test this by constructing a BenchCase directly with a patched comp_guess that
omits ``fraction`` from to_params(), bypassing Pydantic validation via direct
dict-construction to exercise the fallback code path.
"""

from __future__ import annotations

import pytest

pytest.importorskip("lmfit")

from oracles.backends._lmfit import LmfitBackend
from oracles.cases import CaseSpec, PseudoVoigtSpec, materialize
from oracles.models import MODEL_REGISTRY


def _pv_spec() -> CaseSpec:
    """A pseudo_voigt case with an explicit fraction of 0.4."""
    return CaseSpec(
        id="TST-PV-EXTRA-001",
        name="pseudo_voigt extra_defaults test",
        category="easy",
        difficulty=0.3,
        components=[PseudoVoigtSpec(amplitude=3.0, center=0.0, sigma=0.8, fraction=0.4)],
        x_min=-5.0,
        x_max=5.0,
        n_points=100,
        noise=0.02,
        guess_scale=0.0,  # no jitter — fraction stays at truth value
    )


def test_extra_defaults_applied_when_fraction_absent_from_guess(monkeypatch) -> None:
    """fraction initialised from extra_defaults when absent from comp.to_params().

    We materialize the case first (so curve() / to_params() runs unpatched),
    then patch PseudoVoigtSpec.to_params at the class level before calling
    backend.build() — simulating a comp_guess that supplies only amplitude/center/
    sigma. Before the P3 fix this raised KeyError; after the fix the parameter is
    initialised to PeakModel.extra_defaults["fraction"] = 0.5.
    """
    # Materialize first so curve()/to_params() in cases.py runs with the real method.
    case = materialize(_pv_spec())

    # Now patch PseudoVoigtSpec.to_params so build() sees the "missing fraction" path.
    def _to_params_without_fraction(self) -> dict[str, float]:  # noqa: ANN001
        """Return params dict omitting fraction to trigger the extra_defaults path."""
        return {"amplitude": self.amplitude, "center": self.center, "sigma": self.sigma}

    monkeypatch.setattr(PseudoVoigtSpec, "to_params", _to_params_without_fraction)

    backend = LmfitBackend()
    # Must not raise KeyError — that was the pre-fix failure mode.
    _, params, _, _ = backend.build(case)

    pm = MODEL_REGISTRY["pseudo_voigt"]
    expected_fraction = pm.extra_defaults["fraction"]  # 0.5

    assert "p0_fraction" in params, "fraction parameter missing from built lmfit Parameters"
    assert params["p0_fraction"].value == pytest.approx(expected_fraction), (
        f"Expected fraction={expected_fraction} from extra_defaults, "
        f"got {params['p0_fraction'].value}"
    )


def test_explicit_guess_overrides_extra_defaults() -> None:
    """An explicit guess value (fraction=0.4) must win over extra_defaults (0.5).

    When comp.to_params() DOES include ``fraction``, the explicit value from the
    guess spec is used — extra_defaults are only the last resort.
    """
    case = materialize(_pv_spec())
    backend = LmfitBackend()
    _, params, _, _ = backend.build(case)

    pm = MODEL_REGISTRY["pseudo_voigt"]
    extra_default_fraction = pm.extra_defaults["fraction"]  # 0.5

    # The case was built with fraction=0.4 (not 0.5), so explicit value wins.
    actual = params["p0_fraction"].value
    assert actual == pytest.approx(0.4, abs=1e-9), (
        f"Expected fraction=0.4 (explicit guess), got {actual}"
    )
    # Sanity: confirm extra_defaults is 0.5, so the test is meaningful.
    assert extra_default_fraction == pytest.approx(0.5)
    assert actual != pytest.approx(extra_default_fraction), (
        "fraction==extra_default by coincidence — adjust the test fixture"
    )
