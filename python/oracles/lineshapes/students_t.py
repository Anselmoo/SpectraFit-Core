"""Student's-t peak lineshape recipe."""

from __future__ import annotations

import random

from . import register_lineshape


@register_lineshape("students_t")
def build(rng: random.Random, variant: str) -> tuple[list, str]:  # noqa: ARG001
    """Student's-t peak (nu degrees of freedom)."""
    from oracles.cases import (
        StudentsTSpec,
    )  # lazy — avoids circular import at module load

    return [
        StudentsTSpec(
            amplitude=round(rng.uniform(3.0, 6.0), 3),
            center=round(rng.uniform(-1.0, 1.0), 3),
            sigma=round(rng.uniform(0.6, 1.1), 3),
            nu=round(rng.uniform(1.5, 6.0), 3),
        )
    ], "Student's-t peak"
