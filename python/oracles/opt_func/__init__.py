"""Optimization-landscape registry — per-landscape modules self-register here.

Mirrors the LINESHAPE_RECIPE_REGISTRY pattern in oracles.lineshapes. Adding the next
landscape is a new file under opt_func/ + a @register_landscape decorator; nothing else
needs to change in the dispatch layer.
"""

from __future__ import annotations

from collections.abc import Callable

from oracles.opt_func._types import Array

LANDSCAPE_REGISTRY: dict[str, Callable[[Array], Array]] = {}


def register_landscape(
    key: str,
) -> Callable[[Callable[[Array], Array]], Callable[[Array], Array]]:
    """Decorator: register an optimization-landscape function under ``key``."""

    def deco(fn: Callable[[Array], Array]) -> Callable[[Array], Array]:
        if key in LANDSCAPE_REGISTRY:
            raise ValueError(f"landscape {key!r} already registered")
        LANDSCAPE_REGISTRY[key] = fn
        return fn

    return deco


def get_landscape(name: str) -> Callable[[Array], Array]:
    """Look up a registered optimization-landscape by name (named error if absent)."""
    try:
        return LANDSCAPE_REGISTRY[name]
    except KeyError:  # pragma: no cover - guarded by CaseSpec validation
        raise KeyError(
            f"unknown landscape {name!r}; registered: {sorted(LANDSCAPE_REGISTRY)}"
        ) from None


def landscape(name: str, x: Array) -> Array:
    """Evaluate a named optimization-function slice on ``x``."""
    return get_landscape(name)(x)


# Force import of every per-landscape module so they self-register at package-import time.
from . import (  # noqa: F401, E402
    ackley,
    alpine,
    bohachevsky,
    cosine_mixture,
    cross_in_tray,
    drop_wave,
    egg_holder,
    griewank,
    levy,
    perm_beta,
    rastrigin,
    rosenbrock,
    salomon,
    schwefel,
    shubert,
    sphere,
    styblinski_tang,
    sum_squares,
    trid,
    zirilli,
)
