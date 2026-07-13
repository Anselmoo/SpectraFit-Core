"""Asymmetric IR band lineshape recipe."""

from __future__ import annotations

import random

from . import register_lineshape


@register_lineshape("asym_ir")
def build(rng: random.Random, variant: str) -> tuple[list, str]:  # noqa: ARG001
    """Asymmetric IR band (Gaussian x logistic sigmoid) on a linear background."""
    from oracles.cases import AsymIrSpec, _linear_bg  # lazy — avoids circular import at module load

    return [
        AsymIrSpec(
            amplitude=round(rng.uniform(4.0, 7.0), 3),
            center=round(rng.uniform(-1.0, 1.0), 3),
            sigma=round(rng.uniform(0.6, 1.1), 3),
            k=round(rng.uniform(0.6, 1.4), 3),
        ),
        _linear_bg(rng),
    ], "asymmetric IR band"
