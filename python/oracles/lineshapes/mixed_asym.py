"""Mixed skewed-Gaussian + EMG lineshape recipe."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from . import register_lineshape

if TYPE_CHECKING:
    from oracles.cases import Component


@register_lineshape("mixed_asym")
def build(rng: random.Random, variant: str) -> tuple[list[Component], str]:
    """Mixed skewed-Gaussian + EMG (exp_gaussian) doublet."""
    from oracles.cases import _asym  # lazy — avoids circular import at module load

    return [
        _asym(
            rng,
            "skewed_gaussian",
            rng.uniform(3.0, 6.0),
            -2.0,
            rng.uniform(0.7, 1.0),
        ),
        _asym(
            rng,
            "exp_gaussian",
            rng.uniform(3.0, 6.0),
            2.0,
            rng.uniform(0.7, 1.0),
        ),
    ], "mixed skewed-Gaussian + EMG"
