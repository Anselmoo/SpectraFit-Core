"""Backend adapter base: normalized outcome + the timing-loop template method.

The solve is timed in isolation (the ``run`` call only) so model construction and
result serialization never pollute the comparison. Per the QUESTIONS.md finding,
the spectrafit adapter times via ``fit_fast`` for the same reason.

Pydantic-first: :class:`BackendOutcome` is a Pydantic model (``arbitrary_types_allowed``
for the numpy ``best_fit``) so a language server (pyright) can check every consumer.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from oracles.cases import RECOVERABLE_PARAMS, BenchCase
from oracles.models import Array


class BackendOutcome(BaseModel):
    """Normalized result of fitting one case with one backend."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    backend: str
    success: bool
    r2: float
    chi2: float
    reduced_chi2: float
    aic: float
    bic: float
    n_iter: int
    params: dict[str, float]
    param_stderr: dict[str, float | None]
    best_fit: Array
    cost_history: list[float]
    gradient_norm_history: list[float]
    history_source: Literal["real", "reconstructed"]
    # Per-iteration free-parameter vectors θₖ (same length as cost_history),
    # ordered by ``params_param_order``. Raw material for the convergence-to-truth
    # metric dₖ = ‖(θₖ − θ_true)/s‖₂ on synthetic cases. Empty for backends that
    # do not expose a parameter trajectory (only spectrafit's faer LM does today).
    params_history: list[list[float]] = Field(default_factory=list)
    # Ordered free-parameter names indexing each ``params_history`` entry.
    params_param_order: list[str] = Field(default_factory=list)
    timing_ms: list[float] = Field(default_factory=list)
    supported: bool = True
    jacobian_condition_number: float | None = None
    # The actual degrees of freedom (n − n_free) the backend used to compute
    # ``reduced_chi2``.  Set by each adapter's ``extract()``; the engine's audit
    # sidecar writes this value so W2a can recompute reduced-χ² with the SAME dof.
    # None means "unknown" — the engine falls back to n − len(params) (total).
    fit_dof: int | None = None

    def param_error(self, case: BenchCase) -> float:
        """Max relative shape-parameter-recovery error (%) vs truth, ``nan`` if N/A.

        Components are matched truth↔fitted by graph index (the catalog bins peak
        centers so same-model peaks stay resolvable and don't swap).
        """
        if not case.recover:
            return float("nan")
        errs: list[float] = []
        for i, comp in enumerate(case.comp_true):
            cp = comp.to_params()
            for key in RECOVERABLE_PARAMS:
                true = cp.get(key)
                if true is None or abs(true) < 1e-8:
                    continue
                fit_key = f"p{i}.{key}"
                if fit_key not in self.params:
                    return float("nan")
                errs.append(abs(self.params[fit_key] - true) / abs(true) * 100.0)
        return max(errs) if errs else float("nan")


def reconstruct_history(
    initial_cost: float, final_cost: float, n_iter: int
) -> tuple[list[float], list[float]]:
    """Deterministic labelled proxy trace for backends without a native one."""
    if n_iter < 2 or not (np.isfinite(initial_cost) and np.isfinite(final_cost)):
        return [], []
    if initial_cost <= final_cost:
        cost = [float(initial_cost)] * n_iter
    else:
        ratio = (final_cost / initial_cost) ** (1.0 / (n_iter - 1))
        cost = [float(initial_cost * ratio**i) for i in range(n_iter)]
    grad = [
        float(np.sqrt(max(c, 0.0)) * (0.05 if i == n_iter - 1 else 1.0))
        for i, c in enumerate(cost)
    ]
    return cost, grad


def r2_score(y: Array, best_fit: Array) -> float:
    """Coefficient of determination."""
    ss_res = float(np.sum((y - best_fit) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0


class Backend(ABC):
    """Template-method backend: build (untimed) → run (timed) → extract."""

    name: str

    def is_supported(self, case: BenchCase) -> bool:
        """Whether this backend can fit *case* (default: yes)."""
        return True

    @abstractmethod
    def build(self, case: BenchCase) -> Any:
        """Construct the solver-ready model object (called outside the timer)."""

    @abstractmethod
    def run(self, model: Any, case: BenchCase) -> Any:
        """Execute the solve (this call is what gets timed)."""

    @abstractmethod
    def extract(self, raw: Any, case: BenchCase) -> BackendOutcome:
        """Map a native solve result to a :class:`BackendOutcome` (no timing)."""

    def _warmup(self, case: BenchCase) -> None:
        """One untimed solve (JIT/compile warm-up); override if needed."""
        self.run(self.build(case), case)

    def fit(self, case: BenchCase, n_reps: int = 5) -> BackendOutcome:
        """Time *n_reps* solves; extract metrics from the last (timed) solve.

        Metrics come from a solve that was actually timed (no extra untimed solve),
        so timing and reported metrics share provenance — important for stochastic
        solvers (e.g. seeded lmfit DE).
        """
        self._warmup(case)
        times: list[float] = []
        raw = None
        for _ in range(max(1, n_reps)):
            model = self.build(case)
            t0 = time.perf_counter()
            raw = self.run(model, case)
            times.append((time.perf_counter() - t0) * 1000.0)
        outcome = self.extract(raw, case)
        outcome.timing_ms = times
        return outcome
