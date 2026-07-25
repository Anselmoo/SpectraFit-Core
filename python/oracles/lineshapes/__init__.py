"""Lineshape recipe registry — per-shape modules self-register here.

Mirrors the MODEL_REGISTRY pattern in oracles.models. Adding the next
lineshape is a new file under lineshapes/ + an @register_lineshape
decorator; nothing else needs to change in the dispatch layer.

Plan C C3.
"""

from __future__ import annotations

import random
from collections.abc import Callable

# Type alias: a recipe function takes (rng, variant) and returns (comps, name).
LineshapeRecipeFn = Callable[[random.Random, str], tuple[list, str]]

LINESHAPE_RECIPE_REGISTRY: dict[str, LineshapeRecipeFn] = {}


def register_lineshape(key: str) -> Callable[[LineshapeRecipeFn], LineshapeRecipeFn]:
    """Decorator: register a lineshape recipe function under ``key``."""

    def deco(fn: LineshapeRecipeFn) -> LineshapeRecipeFn:
        if key in LINESHAPE_RECIPE_REGISTRY:
            raise ValueError(f"lineshape {key!r} already registered")
        LINESHAPE_RECIPE_REGISTRY[key] = fn
        return fn

    return deco


# Force import of every per-shape module so they self-register at package-import time.
from . import (  # noqa: F401, E402
    asym_ir,
    breit_wigner,
    cauchy_dispersion,
    harmonic_ir,
    ir_voigt,
    k_edge,
    kww,
    l_edge,
    mgh09_rational,
    mixed_asym,
    moffat,
    power_law_offset,
    power_saturation,
    saturating_exponential,
    single,
    split_gauss,
    split_p7,
    students_t,
    tauc,
    xps_doublet,
)
