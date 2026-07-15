"""Benchmark backends: spectrafit (subject) + lmfit / jax (cross-verify oracles)."""

from __future__ import annotations

from oracles.backends._base import Backend, BackendOutcome

__all__ = ["Backend", "BackendOutcome", "get_backends"]


def get_backends() -> list[Backend]:
    """Return the available backends (oracles are skipped if their deps are absent)."""
    from oracles.backends._spectrafit import SpectraFitBackend

    backends: list[Backend] = [SpectraFitBackend()]
    try:
        from oracles.backends._lmfit import LmfitBackend

        backends.append(LmfitBackend())
    except ImportError:
        pass
    try:
        from oracles.backends._jax import JaxBackend

        backends.append(JaxBackend())
    except ImportError:
        pass
    # scipy-ls-{lm,trf,dogbox} — three solver-meta entries from one
    # `least_squares` driver (see `_scipy_ls.py`). The roster grows from
    # 3 → 6; subset assertions in tests/test_bench_engine.py + the policy
    # fixes in engine.py keep the gate honest for an oracle's optfn failures.
    try:
        from oracles.backends._scipy_ls import ScipyLeastSquaresBackend

        for method in ("lm", "trf", "dogbox"):
            backends.append(ScipyLeastSquaresBackend(method))  # type: ignore[arg-type]
    except ImportError:
        pass
    return backends
