"""Breit-Wigner-Fano resonance lineshape recipe."""

from __future__ import annotations

import random

from . import register_lineshape


@register_lineshape("breit_wigner")
def build(rng: random.Random, variant: str) -> tuple[list, str]:  # noqa: ARG001
    """Breit-Wigner-Fano resonance on a linear background."""
    from oracles.cases import BreitWignerSpec, _linear_bg  # lazy — avoids circular import at module load

    return [
        BreitWignerSpec(
            amplitude=round(rng.uniform(2.0, 5.0), 3),
            center=round(rng.uniform(-1.0, 1.0), 3),
            sigma=round(rng.uniform(0.6, 1.2), 3),
            q=round(rng.uniform(0.8, 1.6), 3),
        ),
        _linear_bg(rng),
    ], "Breit-Wigner-Fano resonance"
