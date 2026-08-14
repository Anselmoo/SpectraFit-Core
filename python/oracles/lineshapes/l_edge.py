"""XAS L-edge L3/L2 doublet lineshape recipe."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from . import register_lineshape

if TYPE_CHECKING:
    from oracles.cases import Component


@register_lineshape("l_edge")
def build(rng: random.Random, variant: str) -> tuple[list[Component], str]:
    r"""L3 (lower energy, $\approx 2\times$) + L2 white lines (2:1 branching) on an arctan edge."""
    from oracles.cases import (
        _asym,
        _edge,
    )  # lazy — avoids circular import at module load

    # L3 (lower energy, $\approx 2\times$) + L2 white lines (2:1 branching) on an arctan edge.
    sep = rng.uniform(2.0, 3.0)
    s = rng.uniform(0.5, 0.9)
    a3 = rng.uniform(4.0, 6.0)
    return [
        _edge(rng, "arctan_step", -sep / 2 - 1.2),
        _asym(rng, "true_voigt", a3, -sep / 2, s),
        _asym(rng, "true_voigt", a3 / 2.0, sep / 2, s),
    ], "XAS L-edge L3/L2 doublet (2:1, true Voigt)"
