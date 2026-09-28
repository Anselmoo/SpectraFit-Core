"""Cauchy refractive-index dispersion lineshape recipe."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from . import register_lineshape

if TYPE_CHECKING:
    from oracles.cases import Component


@register_lineshape("cauchy_dispersion")
def build(rng: random.Random, variant: str) -> tuple[list[Component], str]:
    r"""Cauchy refractive-index dispersion on a positive-$\lambda$ grid.

    $n(\lambda)=a+b/\lambda^2+c/\lambda^4$.
    """
    from oracles.cases import (
        CauchyDispersionSpec,
    )  # lazy — avoids circular import at module load

    return [
        CauchyDispersionSpec(
            a=round(rng.uniform(1.3, 1.7), 3),
            b=round(rng.uniform(0.2, 0.8), 3),
            c=round(rng.uniform(0.02, 0.15), 4),
        ),
    ], "Cauchy refractive-index dispersion"
