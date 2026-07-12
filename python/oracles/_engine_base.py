"""Shared low-level primitives for the ``oracles.engine`` package (G27 split).

These three names are the only symbols the extracted engine submodules
(``_engine_profile``, ``_engine_nested``) need from the engine core, so they
live in a dependency-free leaf module to break what would otherwise be an
import cycle (core imports the groups for orchestration; the groups import
these primitives back). ``engine`` re-imports all three, so
``from oracles.engine import _safe_fit`` / ``_finite`` / ``ProfileContext``
paths keep working unchanged.
"""

from __future__ import annotations

import logging
import math

from pydantic import BaseModel, ConfigDict

from oracles.backends import Backend, BackendOutcome
from oracles.cases import BenchCase

_LOG = logging.getLogger("oracles.engine")
_RUNS_SCHED = [1, 2, 5, 10, 25, 50]
_NGRID = [128, 256, 512, 1024, 2048, 4096]
_WARMUP_SCHED = [1, 5, 10, 25, 50, 100]


# spectrafit_core is the compiled Rust extension. Probed at module load so the optional
# dependency is visible, instead of being hidden inside a broad except in _correlation.
try:
    import spectrafit_core  # noqa: F401  (availability probe; `fit` imported lazily by callers)

    _HAS_SPECTRAFIT = True
except ImportError:
    _HAS_SPECTRAFIT = False


class ProfileContext(BaseModel):
    """Run-level constants shared across every backend in a featured run.

    Computed once before the per-backend loop; carried as one object so the
    ``_build_profile`` signature separates what varies per backend from what does not.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    baseline: float
    min_aic: float
    min_bic: float
    ngrid: list[int]
    n_mc: int


def _finite(x: float, default: float = 0.0) -> float:
    """Return *x* if finite, else *default* — keeps NaN/Inf out of the contract.

    Callers should choose a *default* that is obviously impossible for the metric:
    - ``r2`` uses ``-1.0`` (impossible for a fit result; distinguishable from 0.0
      which is a legitimate R² value on a constant model).
    - ``red_chi2`` uses ``0.0`` (chi² is non-negative; 0.0 is a safe sentinel
      for a failed/missing chi² because ``success=False`` is the authoritative flag).
    """
    return float(x) if math.isfinite(x) else default


def _safe_fit(backend: Backend, case: BenchCase, n_reps: int) -> BackendOutcome | None:
    """Fit guarded — return None on any backend failure, logging the cause.

    One bad fit must not sink the whole run, but the failure is logged (case id +
    backend + exception) so a systematically broken backend is visible instead of
    silently masquerading as an unsupported case.
    """
    if not backend.is_supported(case):
        return None
    try:
        return backend.fit(case, n_reps=n_reps)
    except Exception as exc:  # noqa: BLE001 - report, don't abort the run
        _LOG.warning("backend %s failed on case %s: %r", backend.name, case.id, exc)
        return None
