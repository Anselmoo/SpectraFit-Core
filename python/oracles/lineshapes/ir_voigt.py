"""IR n-band true Voigt lineshape recipe."""

from __future__ import annotations

import random

from . import register_lineshape


@register_lineshape("ir_voigt")
def build(rng: random.Random, variant: str) -> tuple[list, str]:
    """IR multi-band spectrum: n true-Voigt peaks on a linear background.

    ``variant`` is the string representation of the integer band count.
    """
    from oracles.cases import (
        _asym,
        _binned_centers,
        _linear_bg,
    )  # lazy — avoids circular import at module load

    n = int(variant)
    peaks = [
        _asym(rng, "true_voigt", rng.uniform(3.0, 6.0), c, rng.uniform(0.4, 0.8))
        for c in _binned_centers(rng, n, -4.0, 4.0)
    ]
    return [*peaks, _linear_bg(rng)], f"IR {n}-band (true Voigt + bg)"
