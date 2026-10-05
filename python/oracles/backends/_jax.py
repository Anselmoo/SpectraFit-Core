r"""jax + optimistix oracle — vectorized GPU/CPU challenger backend.

Supports any case whose components all carry a jax kernel (the registry's derived
``jax_supported`` flag, i.e. ``PeakModel.jax_evaluate is not None`` — today every
registered shape) via an optimistix Levenberg–Marquardt solve under ``jax.jit`` (so
the one-off compile cost is paid once at warm-up, then amortized — exactly the story
the report's amortization panel tells). Two case classes remain unsupported and are
omitted from the suite for jax: **global** (multimodal) cases, whose multi-start
search optimistix's local LM driver does not implement, and **tied-parameter**
cases, whose ``expr_edges`` optimistix has no way to express. Neither is a missing
kernel — porting more shapes cannot reach them.

Both the per-component shape layout (which kernel, how many params) and the kernel
itself are read from the model registry, not a private map — so a new jax shape is
one ``jax_evaluate=`` entry in :mod:`oracles.jax_kernels`, with no edit here.

## Compile budget — why the compiled-executable cache is bounded

Every distinct compiled XLA executable costs mmap regions — LLVM's
``SectionMemoryManager`` maps each section separately — and jax retains them for the
life of the process. The kernel caps a process at ``vm.max_map_count`` mappings
(65530 by default). Past that, ``mmap`` returns ``ENOMEM``, which surfaces as
``LLVM compilation error: Cannot allocate memory`` with tens of GB of RAM still free,
and the process aborts.

Warning:
    The limit that kills a full run is a count of mappings, **not** a quantity of
    memory. Peak RSS stays near 2 GB on a 31 GiB host while the run dies. Profiling
    bytes will not find this, and no ``XLA_FLAGS`` thread or codegen setting moves it.

A full benchmark run compiles far more than one executable per case:
:func:`oracles._engine_profile._scaling` re-materializes every analyzed case at
``n_points`` 128/512/2048, so the 127 jax-eligible cases produce roughly 360–384
distinct executables $\approx$ 68k–73k mappings — over the cap. That is why every rung of the
FAIR reps ladder died with ``SIGABRT``/``SIGSEGV``. Driving jax alone compiles only the
127 base shapes ($\approx$ 24k mappings) and stays under the cap, which is why a standalone
probe never reproduced the failure. Monte-Carlo refits add nothing: they reuse the
base shape.

``jax.clear_caches()`` alone releases the mappings (measured: 8708 → 823 mappings after
40 fits). :func:`_residual_for`'s memo does **not** need clearing, so the amortization
rationale documented there stays intact.

Note:
    The budget is a fixed **count** rather than a reading of live map pressure on
    purpose: a run has to compile and clear at the same points on every host, or two
    machines running one commit produce different jax timings and the ladder stops
    being recomputable. Override with ``SPECTRAFIT_BENCH_JAX_COMPILE_BUDGET``.

Measured over the full 127-case × 4-shape compile load, against the 65530 cap:

| budget | clears | peak mappings | headroom | peak RSS |
| -----: | -----: | ------------: | -------: | -------: |
|    128 |      3 |        41 314 |     37 % |  2.87 GB |
|     64 |      6 |        22 706 |     65 % |  1.98 GB |

64 is the default. 128 bounds the run, but 37 % is too little margin for a host whose
``vm.max_map_count`` is below the kernel default or a jax release that maps more
sections per executable. Halving the budget doubles the clears — a few extra minutes of
recompilation on a run that takes hours — and buys back nearly a third of the cap.

Bounding the cache also removes a measurement bias. Uncapped, jax silently reuses a
compile whenever a later case repeats an earlier case's layout — the catalog's 127
eligible cases cover only 96 distinct base ``(layout, n_points)`` pairs — an advantage
lmfit and the scipy backends never get.
"""

from __future__ import annotations

import functools
import os
from typing import Any, override

import numpy as np

from oracles.backends._base import (
    Backend,
    BackendOutcome,
    r2_score,
    reconstruct_history,
)
from oracles.cases import BenchCase, curve
from oracles.exceptions import BackendError

_R2_CEILING_TOL = 1e-3

# Distinct compiled executables kept before the cache is dropped. See "Compile budget"
# in the module docstring for the mmap accounting this number comes from.
_DEFAULT_COMPILE_BUDGET = 64
_COMPILE_BUDGET_ENV = "SPECTRAFIT_BENCH_JAX_COMPILE_BUDGET"


def _layout(case: BenchCase) -> tuple[tuple[str, int], ...]:
    """Static per-component (model_key, n_params) layout, in registry param order."""
    from oracles.models import get_model

    return tuple((c.model, len(get_model(c.model).param_names)) for c in case.comp_guess)


def _flat_guess(case: BenchCase) -> list[float]:
    """Flatten the guess params in canonical (registry) order across components."""
    from oracles.models import get_model

    flat: list[float] = []
    for c in case.comp_guess:
        params = c.to_params()
        flat += [params[name] for name in get_model(c.model).param_names]
    return flat


class JaxBackend(Backend):
    """Fit jax-supported peak-shape cases with jax + optimistix Levenberg–Marquardt."""

    name = "jax"

    def __init__(self, compile_budget: int | None = None) -> None:
        import jax

        jax.config.update("jax_enable_x64", True)  # noqa: FBT003 — jax.config.update's own signature, not ours
        import optimistix  # noqa: F401  (availability check)

        env = os.environ.get(_COMPILE_BUDGET_ENV)
        budget = compile_budget if compile_budget is not None else int(env) if env else None
        self.compile_budget = max(1, budget if budget is not None else _DEFAULT_COMPILE_BUDGET)
        # Distinct executables live since the last clear, and how often we have cleared.
        # The run records the clear count so a reader can see the cache was bounded.
        self._compiled: set[tuple[tuple[tuple[str, int], ...], int]] = set()
        self.n_cache_clears = 0

    def _charge_compile(self, case: BenchCase) -> None:
        """Account one ``(layout, n_points)`` executable, clearing at the budget.

        Called before every build. A key already seen since the last clear is free — it
        is the reuse the memoized residual exists to get. Crossing the budget drops the
        whole compiled population at once; the next fit recompiles, which is the cost of
        not aborting the run. See "Compile budget" in the module docstring for why the
        trigger is a fixed count and where 128 comes from.
        """
        import jax

        key = (_layout(case), int(np.asarray(case.x).size))
        if key in self._compiled:
            return
        if len(self._compiled) >= self.compile_budget:
            jax.clear_caches()
            self._compiled.clear()
            self.n_cache_clears += 1
        self._compiled.add(key)

    @override
    def is_supported(self, case: BenchCase) -> bool:
        """Support local fits whose every component carries a jax kernel.

        Tied-param cases (with expr_edges) are excluded: jax's optimistix
        solver cannot express parameter constraints via expression edges.
        Global (multi-start) cases are excluded for the same kind of reason —
        the driver here is a single-start local LM.
        """
        from oracles.models import get_model

        if case.spec.expr_edges:
            return False
        # Gate on comp_guess — the list _layout/_flat_guess/extract actually evaluate
        # (it equals comp_true's shapes today, but this keeps the check aligned).
        return case.solver_hint != "global" and all(
            get_model(c.model).jax_supported for c in case.comp_guess
        )

    @override
    def build(self, case: BenchCase) -> Any:
        """Build (y0, x, y, layout) from the case guess (layout is static metadata)."""
        import jax.numpy as jnp

        self._charge_compile(case)
        y0 = jnp.asarray(_flat_guess(case), dtype=jnp.float64)
        return y0, jnp.asarray(case.x), jnp.asarray(case.y), _layout(case)

    @override
    def run(self, model: Any, case: BenchCase) -> Any:
        """Run the optimistix LM solve (optimistix JIT-compiles internally)."""
        import optimistix as optx

        y0, x, y, layout = model
        solver = optx.LevenbergMarquardt(rtol=1e-8, atol=1e-8)
        return optx.least_squares(
            _residual_for(layout),
            solver,
            y0,
            args=(x, y),
            max_steps=200,
            throw=False,
        )

    @override
    def extract(self, raw: Any, case: BenchCase) -> BackendOutcome:
        r"""Map the optimistix solution to a normalized outcome.

        Note:
            optimistix's tight rtol/atol keeps LM iterating past convergence, so
            a clean single-peak fit can stop at ``max_steps``
            (``RESULTS.successful`` never set) despite reaching the noise
            ceiling — the $r^2$ of the noiseless truth curve against the noisy
            data, i.e. the best any backend can reach on this case. A solve that
            reaches it has recovered the fit even if optimistix stopped on
            ``max_steps`` rather than its (very tight) convergence test, so such
            a solve is accepted as successful when its $r^2$ is within
            ``_R2_CEILING_TOL`` of the ceiling. This is a post-hoc *label* only —
            solver stopping tolerances stay matched across backends (benchmark
            fairness), so the regression count reflects real failures, not an
            over-strict convergence flag (see EZ-033: $r^2 \approx 0.9996$ yet
            ``success=False`` before).
        """
        import jax.numpy as jnp
        import optimistix as optx

        from oracles.models import get_model

        sol = raw
        layout = _layout(case)
        p = np.asarray(sol.value, dtype=float)
        n_steps = int(sol.stats.get("num_steps", 0)) if hasattr(sol, "stats") else 0
        converged = getattr(sol, "result", None) == optx.RESULTS.successful
        params: dict[str, float] = {}
        offset = 0
        for i, c in enumerate(case.comp_guess):
            names = get_model(c.model).param_names
            for k, name in enumerate(names):
                params[f"p{i}.{name}"] = float(p[offset + k])
            offset += len(names)
        best_fit = np.asarray(
            _model(jnp.asarray(sol.value), jnp.asarray(case.x), layout),
            dtype=float,
        )
        fit_r2 = r2_score(case.y, best_fit)
        truth_curve = np.asarray(curve(case.x, case.comp_true), dtype=float)
        ceiling_r2 = r2_score(case.y, truth_curve)
        recovered = fit_r2 >= ceiling_r2 - _R2_CEILING_TOL
        chi2 = float(np.sum((case.y - best_fit) ** 2))
        n = len(case.y)
        n_free = len(p)
        dof = max(n - n_free, 1)
        # Gaussian log-likelihood AIC/BIC (N*ln(chi2/N) + …), matching lmfit so the
        # information criteria are comparable across backends.
        ll = n * np.log(max(chi2, 1e-30) / n)
        # Honest reconstructed trace from the REAL initial residual (at the guess),
        # not a fabricated multiplier — each component summed with its own kernel.
        init_curve = np.zeros_like(case.x)
        for c in case.comp_guess:
            init_curve = init_curve + get_model(c.model).one(case.x, c.to_params())
        cost0 = 0.5 * float(np.sum((case.y - init_curve) ** 2))
        cost, grad = reconstruct_history(cost0, 0.5 * chi2, max(2, min(n_steps, 40)))
        return BackendOutcome(
            backend=self.name,
            success=bool(np.isfinite(p).all() and (converged or recovered)),
            r2=fit_r2,
            chi2=chi2,
            reduced_chi2=chi2 / dof,
            aic=float(ll + 2 * n_free),
            bic=float(ll + n_free * np.log(n)),
            n_iter=n_steps,
            params=params,
            param_stderr=dict.fromkeys(params),
            best_fit=best_fit,
            cost_history=cost,
            gradient_norm_history=grad,
            history_source="reconstructed",
            fit_dof=dof,
        )


def _kernel(model_key: str, seg: Any, x: Any) -> Any:
    """One jax peak kernel, looked up in the registry; ``model_key`` is static.

    A registry lookup rather than a ``match`` over shape names: the kernels live
    in :mod:`oracles.jax_kernels` and are registered on ``PeakModel.jax_evaluate``,
    so this function never needs editing when a shape is ported. Parameters are
    splatted **by name** in canonical registry order, so a future param reorder
    cannot silently mis-map a segment onto the wrong argument.
    """
    from oracles.models import get_model

    model = get_model(model_key)
    kernel = model.jax_evaluate
    if kernel is None:  # pragma: no cover - is_supported gates the shape set
        msg = f"_kernel: shape {model_key!r} has no jax kernel"
        raise BackendError(msg)
    return kernel(x, **{name: seg[i] for i, name in enumerate(model.param_names)})


def _model(p: Any, x: Any, layout: tuple[tuple[str, int], ...]) -> Any:
    """Sum each component's jax kernel over a flat param vector, per static layout."""
    import jax.numpy as jnp

    out = jnp.zeros_like(x)
    offset = 0
    for model_key, n in layout:
        out = out + _kernel(model_key, p[offset : offset + n], x)
        offset += n
    return out


@functools.cache
def _residual_for(layout: tuple[tuple[str, int], ...]):
    """Residual callable for a static layout, memoized by layout identity.

    Identical layouts reuse one callable identity, so optimistix/jax compile once
    per distinct layout and reuse it across reps + same-shaped cases — restoring the
    warm-up amortization a fresh per-call closure would defeat (every call re-traces).
    """

    def residual(p: Any, args: Any) -> Any:
        x, y = args
        return _model(p, x, layout) - y

    return residual
