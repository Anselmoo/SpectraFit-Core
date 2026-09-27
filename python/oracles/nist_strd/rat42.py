r"""NIST StRD Rat42 dataset — verbatim from itl.nist.gov.

Model (3 parameters, 9 observations, DOF = 6):

    $$
    y = \dfrac{b1}{1 + e^{\,b2 - b3 x}} + \varepsilon
    $$

NIST classifies Rat42 as **"Higher"** difficulty.

Plain logistic: pasture yield against growing time. The generalised_logistic
kernel covers it with the shape exponent held fixed at 1, so no separate
logistic kernel is needed.

**Mapping to spectrafit** — one ``GENERALISED_LOGISTIC`` node with ``shape`` fixed at 1.

Source: https://www.itl.nist.gov/div898/strd/nls/data/rat42.shtml
Data file: https://www.itl.nist.gov/div898/strd/nls/data/LINKS/DATA/Rat42.dat

Attributes:
    START1: NIST-published starting guess (3 free params), the distant start.
    START2: The alternative NIST-published starting guess.
    CERTIFIED: Certified parameter values and 1$\sigma$ standard errors, to 10
        significant figures. Do not round when comparing against a fitted
        result — NIST publishes them at this precision deliberately.
    RSS: Certified residual sum of squares.
    DOF: Degrees of freedom.
    N_OBS: Number of observations.
    X: Independent variable, one entry per observation. Derived from 9
        (x, y) observations, reordered from the data file, which lists y
        first.
    Y: Dependent variable, one entry per observation.
"""

from __future__ import annotations

import numpy as np

START1: dict[str, float] = {"b1": 100.0, "b2": 1.0, "b3": 0.1}
START2: dict[str, float] = {"b1": 75.0, "b2": 2.5, "b3": 0.07}

CERTIFIED: dict[str, tuple[float, float]] = {
    "b1": (7.2462237576e01, 1.7340283401e00),
    "b2": (2.6180768402e00, 8.8295217536e-02),
    "b3": (6.7359200066e-02, 3.4465663377e-03),
}

RSS: float = 8.0565229338e00
DOF: int = 6
N_OBS: int = 9

_RAW: list[tuple[float, float]] = [
    (9.0, 8.93),
    (14.0, 10.8),
    (21.0, 18.59),
    (28.0, 22.33),
    (42.0, 39.35),
    (57.0, 56.11),
    (63.0, 61.73),
    (70.0, 64.62),
    (79.0, 67.08),
]
_DATA = np.asarray(_RAW, dtype=np.float64)
X: np.ndarray = _DATA[:, 0]
Y: np.ndarray = _DATA[:, 1]
