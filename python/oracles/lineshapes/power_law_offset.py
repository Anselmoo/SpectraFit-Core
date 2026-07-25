"""Power-law-with-offset (Bennett5-like) lineshape recipe."""

from __future__ import annotations

import random

from . import register_lineshape


@register_lineshape("power_law_offset")
def build(rng: random.Random, variant: str) -> tuple[list, str]:  # noqa: ARG001
    """Bennett5-like decay ``amplitude·(offset+x)^(−1/shape)`` on a positive-x grid (0-8).

    ``offset`` is held at ~5 (>> the grid's |x_min|=0) so ``offset + x > 0`` everywhere,
    keeping the fractional power's base positive (mirrors the parity-test offset=5.0,
    shape≈0.93 safe values); no negative-base power, no NaN.
    """
    from oracles.cases import PowerLawOffsetSpec  # lazy — avoids circular import

    return [
        PowerLawOffsetSpec(
            amplitude=round(rng.uniform(2.0, 5.0), 3),
            offset=round(rng.uniform(4.0, 6.0), 3),
            shape=round(rng.uniform(0.8, 1.1), 3),
        )
    ], "Bennett5 power law with offset"
