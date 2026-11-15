"""The Jacobian-ablation backend variant ``spectrafit_fd`` (#93).

``spectrafit_fd`` is the subject backend with ``FitOptions.jacobian =
"finite_difference"``: the same graph, data, solver hint and iteration budget,
so the only difference to ``spectrafit`` in an ablation run is the Jacobian.
"""

from __future__ import annotations

from oracles.backends import ABLATION_BACKENDS, get_backends
from oracles.backends._spectrafit import SpectraFitBackend
from oracles.cases import build_specs, materialize


def _case():
    spec = next(s for s in build_specs() if s.category == "easy")
    return materialize(spec)


def test_default_backend_is_analytic_and_named_spectrafit() -> None:
    backend = SpectraFitBackend()
    assert backend.name == "spectrafit"
    _graph, _data, options = backend.build(_case())
    assert options.jacobian == "analytic"


def test_fd_variant_differs_only_in_the_jacobian_option() -> None:
    case = _case()
    g_an, d_an, o_an = SpectraFitBackend().build(case)
    fd = SpectraFitBackend(jacobian="finite_difference")
    assert fd.name == "spectrafit_fd"
    g_fd, d_fd, o_fd = fd.build(case)
    assert o_fd.jacobian == "finite_difference"
    assert o_fd.model_dump(exclude={"jacobian"}) == o_an.model_dump(exclude={"jacobian"})
    assert g_fd.model_dump() == g_an.model_dump()
    assert d_fd.model_dump() == d_an.model_dump()


def test_fd_variant_fits_a_case() -> None:
    outcome = SpectraFitBackend(jacobian="finite_difference").fit(_case(), n_reps=1)
    assert outcome is not None
    assert outcome.backend == "spectrafit_fd"
    assert outcome.success


def test_get_backends_adds_the_variant_only_on_request() -> None:
    assert set(ABLATION_BACKENDS) == {"spectrafit_fd"}
    default_names = [b.name for b in get_backends()]
    assert "spectrafit_fd" not in default_names
    ablation_names = [b.name for b in get_backends(ablation=True)]
    assert ablation_names[:2] == ["spectrafit", "spectrafit_fd"]
    assert [n for n in ablation_names if n not in ABLATION_BACKENDS] == default_names
