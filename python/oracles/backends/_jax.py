"""jax + optimistix oracle — vectorized GPU/CPU challenger backend.

Supports any case whose components are all jax-implemented peak shapes (the
registry's ``jax_supported`` flag — currently gaussian / lorentzian / pseudo-Voigt
/ voigt) via an optimistix Levenberg–Marquardt solve under ``jax.jit`` (so the
one-off compile cost is paid once at warm-up, then amortized — exactly the story
the report's amortization panel tells). Fano, background/step shapes, and global
(multimodal) cases are reported unsupported; the suite simply omits jax there.

The per-component shape layout (which kernel, how many params) is derived from the
model registry, not a private map — so a new jax shape is one ``jax_supported=True``
flag plus its kernel branch in :func:`_kernel`.
"""

from __future__ import annotations

import functools
from typing import Any

import numpy as np

from oracles.backends._base import (
    Backend,
    BackendOutcome,
    r2_score,
    reconstruct_history,
)
from oracles.cases import BenchCase, curve

# optimistix's tight rtol/atol keeps LM iterating past convergence, so a clean
# single-peak fit can stop at ``max_steps`` (RESULTS.successful never set) despite
# reaching the noise ceiling. Accept such a solve as successful when its r² is within
# this tolerance of the truth-curve r² (the best attainable given the case's noise).
# This is a post-hoc *label* only — solver stopping tolerances stay matched across
# backends (benchmark fairness), so the regression count reflects real failures, not
# an over-strict convergence flag (see EZ-033: r²≈0.9996 yet success=False before).
_R2_CEILING_TOL = 1e-3


def _layout(case: BenchCase) -> tuple[tuple[str, int], ...]:
    """Static per-component (model_key, n_params) layout, in registry param order."""
    from oracles.models import get_model

    return tuple(
        (c.model, len(get_model(c.model).param_names)) for c in case.comp_guess
    )


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

    def __init__(self) -> None:
        import jax

        jax.config.update("jax_enable_x64", True)
        import optimistix  # noqa: F401  (availability check)

    def is_supported(self, case: BenchCase) -> bool:
        """Support local fits whose every component is a jax-implemented peak shape.

        Tied-param cases (with expr_edges) are excluded: jax's optimistix
        solver cannot express parameter constraints via expression edges.
        """
        from oracles.models import get_model

        if case.spec.expr_edges:
            return False
        # Gate on comp_guess — the list _layout/_flat_guess/extract actually evaluate
        # (it equals comp_true's shapes today, but this keeps the check aligned).
        return case.solver_hint != "global" and all(
            get_model(c.model).jax_supported for c in case.comp_guess
        )

    def build(self, case: BenchCase) -> Any:
        """Build (y0, x, y, layout) from the case guess (layout is static metadata)."""
        import jax.numpy as jnp

        y0 = jnp.asarray(_flat_guess(case), dtype=jnp.float64)
        return y0, jnp.asarray(case.x), jnp.asarray(case.y), _layout(case)

    def run(self, model: Any, case: BenchCase) -> Any:
        """Run the optimistix LM solve (optimistix JIT-compiles internally)."""
        import optimistix as optx

        y0, x, y, layout = model
        solver = optx.LevenbergMarquardt(rtol=1e-8, atol=1e-8)
        return optx.least_squares(
            _residual_for(layout), solver, y0, args=(x, y), max_steps=200, throw=False
        )

    def extract(self, raw: Any, case: BenchCase) -> BackendOutcome:
        """Map the optimistix solution to a normalized outcome."""
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
            _model(jnp.asarray(sol.value), jnp.asarray(case.x), layout), dtype=float
        )
        fit_r2 = r2_score(case.y, best_fit)
        # Noise ceiling: the r² of the noiseless truth curve against the noisy data —
        # the best any backend can reach on this case. A solve that reaches it has
        # recovered the fit even if optimistix stopped on max_steps rather than its
        # (very tight) convergence test.
        truth_curve = np.asarray(curve(case.x, case.comp_true), dtype=float)
        ceiling_r2 = r2_score(case.y, truth_curve)
        recovered = fit_r2 >= ceiling_r2 - _R2_CEILING_TOL
        chi2 = float(np.sum((case.y - best_fit) ** 2))
        n = len(case.y)
        n_free = len(p)
        dof = max(n - n_free, 1)
        # Gaussian log-likelihood AIC/BIC (N·ln(chi2/N) + …), matching lmfit so the
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
            param_stderr={k: None for k in params},
            best_fit=best_fit,
            cost_history=cost,
            gradient_norm_history=grad,
            history_source="reconstructed",
            fit_dof=dof,
        )


def _kernel(model_key: str, seg: Any, x: Any) -> Any:
    """One jax peak kernel; ``model_key`` is static so branches resolve at trace time."""
    import jax.numpy as jnp

    from oracles.models import get_model

    a, c, s = seg[0], seg[1], seg[2]
    z = ((x - c) / s) ** 2
    match model_key:
        case "gaussian":
            return a * jnp.exp(-0.5 * z)
        case "lorentzian":
            return a * (1.0 / (1.0 + z))
        case "pseudo_voigt" | "voigt":
            # Read `fraction` by name so a future param reorder can't silently mis-map.
            fi = get_model(model_key).param_names.index("fraction")
            frac = jnp.clip(seg[fi], 0.0, 1.0)
            lorentz = 1.0 / (1.0 + z)
            gauss = jnp.exp(-0.5 * z)
            return a * (frac * lorentz + (1.0 - frac) * gauss)
        case _:  # pragma: no cover - is_supported gates the shape set
            raise ValueError(f"_kernel: shape {model_key!r} has no jax kernel")


def _model(p: Any, x: Any, layout: tuple[tuple[str, int], ...]) -> Any:
    """Sum each component's jax kernel over a flat param vector, per static layout."""
    import jax.numpy as jnp

    out = jnp.zeros_like(x)
    offset = 0
    for model_key, n in layout:
        out = out + _kernel(model_key, p[offset : offset + n], x)
        offset += n
    return out


@functools.lru_cache(maxsize=None)
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
