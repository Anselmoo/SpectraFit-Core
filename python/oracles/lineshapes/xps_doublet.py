"""XPS spin-orbit doublet lineshape recipe."""

from __future__ import annotations

import random

from . import register_lineshape


@register_lineshape("xps_doublet")
def build(rng: random.Random, variant: str) -> tuple[list, str]:  # noqa: ARG001
    """XPS spin-orbit doublet (Doniach-Sunjic + linear background)."""
    from oracles.cases import _asym, _linear_bg  # lazy — avoids circular import at module load

    sep = rng.uniform(1.6, 2.6)
    a = rng.uniform(4.0, 6.0)
    s = rng.uniform(0.6, 0.9)
    return [
        _asym(rng, "doniach_sunjic", a, -sep / 2, s),
        _asym(rng, "doniach_sunjic", a * 0.5, sep / 2, s),
        _linear_bg(rng),
    ], "XPS spin-orbit doublet (Doniach–Šunjić + bg)"
