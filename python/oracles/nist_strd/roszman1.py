r"""NIST StRD Roszman1 dataset — verbatim from itl.nist.gov.

Model (4 parameters, 25 observations, DOF = 21):

    $$
    y = b1 - b2 x - \dfrac{\arctan\!\left(b3/(x-b4)\right)}{\pi} + \varepsilon
    $$

NIST classifies Roszman1 as **"Average"** difficulty.

On this data b3/(x-b4) is negative throughout, so arctan(z) = -pi/2 -
arctan(1/z) and the NIST form becomes a unit arctan step plus a line. The
branch matters: assuming the positive branch converges successfully to a curve
that is wrong by a constant.

**Mapping to spectrafit** — ``LINEAR`` + ``ARCTAN_STEP`` with amplitude fixed at 1.

Source: https://www.itl.nist.gov/div898/strd/nls/data/roszman1.shtml
Data file: https://www.itl.nist.gov/div898/strd/nls/data/LINKS/DATA/Roszman1.dat

Attributes:
    START1: NIST-published starting guess (4 free params), the distant start.
    START2: The alternative NIST-published starting guess.
    CERTIFIED: Certified parameter values and 1$\sigma$ standard errors, to 10
        significant figures. Do not round when comparing against a fitted
        result — NIST publishes them at this precision deliberately.
    RSS: Certified residual sum of squares.
    DOF: Degrees of freedom.
    N_OBS: Number of observations.
    X: Independent variable, one entry per observation. Reordered from the
        data file, which lists y first.
    Y: Dependent variable, one entry per observation.
"""

from __future__ import annotations

import numpy as np

START1: dict[str, float] = {"b1": 0.1, "b2": -1e-05, "b3": 1000.0, "b4": -100.0}
START2: dict[str, float] = {"b1": 0.2, "b2": -5e-06, "b3": 1200.0, "b4": -150.0}

CERTIFIED: dict[str, tuple[float, float]] = {
    "b1": (2.0196866396e-01, 1.9172666023e-02),
    "b2": (-6.1953516256e-06, 3.2058931691e-06),
    "b3": (1.2044556708e03, 7.4050983057e01),
    "b4": (-1.8134269537e02, 4.9573513849e01),
}

RSS: float = 4.9484847331e-04
DOF: int = 21
N_OBS: int = 25

_RAW: list[tuple[float, float]] = [
    (-4868.68, 0.252429),
    (-4868.09, 0.252141),
    (-4867.41, 0.251809),
    (-3375.19, 0.297989),
    (-3373.14, 0.296257),
    (-3372.03, 0.295319),
    (-2473.74, 0.339603),
    (-2472.35, 0.337731),
    (-2469.45, 0.33382),
    (-1894.65, 0.38951),
    (-1893.4, 0.386998),
    (-1497.24, 0.438864),
    (-1495.85, 0.434887),
    (-1493.41, 0.427893),
    (-1208.68, 0.471568),
    (-1206.18, 0.461699),
    (-1206.04, 0.461144),
    (-997.92, 0.513532),
    (-996.61, 0.506641),
    (-996.31, 0.505062),
    (-834.94, 0.535648),
    (-834.66, 0.533726),
    (-710.03, 0.568064),
    (-530.16, 0.612886),
    (-464.17, 0.624169),
]
_DATA = np.asarray(_RAW, dtype=np.float64)
X: np.ndarray = _DATA[:, 0]
Y: np.ndarray = _DATA[:, 1]
