"""XANES K-edge lineshape recipe."""

from __future__ import annotations

import random

from . import register_lineshape


@register_lineshape("k_edge")
def build(rng: random.Random, variant: str) -> tuple[list, str]:  # noqa: ARG001
    """XANES K-edge (edge + white-line peak in true Voigt)."""
    from oracles.cases import (
        _asym,
        _edge,
    )  # lazy — avoids circular import at module load

    return [
        _edge(rng, "arctan_step", rng.uniform(-2.5, -1.5)),
        _asym(
            rng,
            "true_voigt",
            rng.uniform(4.0, 6.0),
            rng.uniform(-0.5, 0.5),
            rng.uniform(0.6, 1.0),
        ),
    ], "XANES K-edge (edge + white-line)"
