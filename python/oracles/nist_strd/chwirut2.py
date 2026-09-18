r"""NIST StRD Chwirut2 dataset — verbatim from itl.nist.gov.

Model (3 parameters, 54 observations, DOF = 51):

    $$
    y = \dfrac{e^{-b1 x}}{b2 + b3 x} + \varepsilon
    $$

NIST classifies Chwirut2 as **"Lower"** difficulty.

Ultrasonic response against metal distance, 54 observations. Same functional
form and experiment as Chwirut1, at lower replication.

**Mapping to spectrafit** — one ``EXP_OVER_LINEAR`` node.

Source: https://www.itl.nist.gov/div898/strd/nls/data/chwirut2.shtml
Data file: https://www.itl.nist.gov/div898/strd/nls/data/LINKS/DATA/Chwirut2.dat

Attributes:
    START1: NIST-published starting guess (3 free params), the distant start.
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

START1: dict[str, float] = {"b1": 0.1, "b2": 0.01, "b3": 0.02}
START2: dict[str, float] = {"b1": 0.15, "b2": 0.008, "b3": 0.01}

CERTIFIED: dict[str, tuple[float, float]] = {
    "b1": (1.6657666537e-01, 3.8303286810e-02),
    "b2": (5.1653291286e-03, 6.6621605126e-04),
    "b3": (1.2150007096e-02, 1.5304234767e-03),
}

RSS: float = 5.1304802941e02
DOF: int = 51
N_OBS: int = 54

_RAW: list[tuple[float, float]] = [
    (0.5, 92.9),
    (1.0, 57.1),
    (1.75, 31.05),
    (3.75, 11.5875),
    (5.75, 8.025),
    (0.875, 63.6),
    (2.25, 21.4),
    (3.25, 14.25),
    (5.25, 8.475),
    (0.75, 63.8),
    (1.75, 26.8),
    (2.75, 16.4625),
    (4.75, 7.125),
    (0.625, 67.3),
    (1.25, 41.0),
    (2.25, 21.15),
    (4.25, 8.175),
    (0.5, 81.5),
    (3.0, 13.12),
    (0.75, 59.9),
    (3.0, 14.62),
    (1.5, 32.9),
    (6.0, 5.44),
    (3.0, 12.56),
    (6.0, 5.44),
    (1.5, 32.0),
    (3.0, 13.95),
    (0.5, 75.8),
    (2.0, 20.0),
    (4.0, 10.42),
    (0.75, 59.5),
    (2.0, 21.67),
    (5.0, 8.55),
    (0.75, 62.0),
    (2.25, 20.2),
    (3.75, 7.76),
    (5.75, 3.75),
    (3.0, 11.81),
    (0.75, 54.7),
    (2.5, 23.7),
    (4.0, 11.55),
    (0.75, 61.3),
    (2.5, 17.7),
    (4.0, 8.74),
    (0.75, 59.2),
    (2.5, 16.3),
    (4.0, 8.62),
    (0.5, 81.0),
    (6.0, 4.87),
    (3.0, 14.62),
    (0.5, 81.7),
    (2.75, 17.17),
    (0.5, 81.3),
    (1.75, 28.9),
]
_DATA = np.asarray(_RAW, dtype=np.float64)
X: np.ndarray = _DATA[:, 0]
Y: np.ndarray = _DATA[:, 1]
