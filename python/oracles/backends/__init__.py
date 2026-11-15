"""Benchmark backends: spectrafit (subject) + lmfit / jax (cross-verify oracles)."""

from __future__ import annotations

from oracles.backends._base import Backend, BackendOutcome
from oracles.backends._tolerance import ToleranceMode, tolerances_for

__all__ = ["ABLATION_BACKENDS", "Backend", "BackendOutcome", "get_backends"]

ABLATION_BACKENDS: frozenset[str] = frozenset({"spectrafit_fd"})
"""Backend names that exist only for ablation runs (#93) and are never part of
the default roster: ``spectrafit_fd`` is the subject with every kernel's analytic
Jacobian replaced by a forward difference. They run only when named explicitly
(``--backends spectrafit,spectrafit_fd,...``), so default runs and the
``benchmark_gate`` see the same roster as before."""


def get_backends(
    tolerance_mode: ToleranceMode = "default",
    *,
    ablation: bool = False,
) -> list[Backend]:
    """Return the available backends (oracles are skipped if their deps are absent).

    Args:
        tolerance_mode: ``"default"`` keeps every library's own stopping tests and
            thresholds (the call each adapter has always made); ``"common"`` hands
            every backend the same setting, ftol = xtol = gtol = $10^{-8}$ (see
            :mod:`oracles.backends._tolerance`).
        ablation: Also include the ablation variants named in
            :data:`ABLATION_BACKENDS` (directly after the subject), at the same
            ``tolerance_mode``. Off by default so every existing caller keeps the
            default roster.

    Note:
        ``scipy-ls-{lm,trf,dogbox}`` contributes three solver-meta entries from
        one ``least_squares`` driver (see ``_scipy_ls.py``), growing the roster
        from 3 to 6. Subset assertions in ``tests/test_bench_engine.py`` plus
        the policy fixes in ``engine.py`` keep the gate honest for an oracle's
        optfn failures.
    """
    from oracles.backends._spectrafit import SpectraFitBackend

    tol = tolerances_for(tolerance_mode)
    backends: list[Backend] = [SpectraFitBackend(tolerances=tol)]
    if ablation:
        backends.append(SpectraFitBackend(jacobian="finite_difference", tolerances=tol))
    try:
        from oracles.backends._lmfit import LmfitBackend

        backends.append(LmfitBackend(tolerances=tol))
    except ImportError:
        pass
    try:
        from oracles.backends._jax import JaxBackend

        backends.append(JaxBackend(tolerances=tol))
    except ImportError:
        pass
    try:
        from oracles.backends._scipy_ls import ScipyLeastSquaresBackend

        backends.extend(
            ScipyLeastSquaresBackend(method, tolerances=tol)  # type: ignore[arg-type]
            for method in ("lm", "trf", "dogbox")
        )
    except ImportError:
        pass
    return backends
