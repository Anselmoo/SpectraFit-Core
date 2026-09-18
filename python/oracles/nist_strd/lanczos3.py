r"""NIST StRD Lanczos3 dataset — verbatim from itl.nist.gov.

Model (6 parameters, 24 observations, DOF = 18):

    $$
    y = b1 \cdot e^{-b2 x} + b3 \cdot e^{-b4 x} + b5 \cdot e^{-b6 x} + \varepsilon
    $$

NIST classifies Lanczos3 as **"Lower"** difficulty.

Same functional form as Lanczos1 and Lanczos2, on the same x grid; this is the
5-digit rounding, which is why NIST rates it Lower rather than Average.

**Mapping to spectrafit** — two ``DOUBLE_EXPONENTIAL`` nodes, exactly as Lanczos1 does.

Source: https://www.itl.nist.gov/div898/strd/nls/data/lanczos3.shtml
Data file: https://www.itl.nist.gov/div898/strd/nls/data/LINKS/DATA/Lanczos3.dat

Attributes:
    START1: NIST-published starting guess (6 free params), the distant start.
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

START1: dict[str, float] = {"b1": 1.2, "b2": 0.3, "b3": 5.6, "b4": 5.5, "b5": 6.5, "b6": 7.6}
START2: dict[str, float] = {"b1": 0.5, "b2": 0.7, "b3": 3.6, "b4": 4.2, "b5": 4.0, "b6": 6.3}

CERTIFIED: dict[str, tuple[float, float]] = {
    "b1": (8.6816414977e-02, 1.7197908859e-02),
    "b2": (9.5498101505e-01, 9.7041624475e-02),
    "b3": (8.4400777463e-01, 4.1488663282e-02),
    "b4": (2.9515951832e00, 1.0766312506e-01),
    "b5": (1.5825685901e00, 5.8371576281e-02),
    "b6": (4.9863565084e00, 3.4436403035e-02),
}

RSS: float = 1.6117193594e-08
DOF: int = 18
N_OBS: int = 24

_RAW: list[tuple[float, float]] = [
    (0.0, 2.5134),
    (0.05, 2.0443),
    (0.1, 1.6684),
    (0.15, 1.3664),
    (0.2, 1.1232),
    (0.25, 0.9269),
    (0.3, 0.7679),
    (0.35, 0.6389),
    (0.4, 0.5338),
    (0.45, 0.4479),
    (0.5, 0.3776),
    (0.55, 0.3197),
    (0.6, 0.272),
    (0.65, 0.2325),
    (0.7, 0.1997),
    (0.75, 0.1723),
    (0.8, 0.1493),
    (0.85, 0.1301),
    (0.9, 0.1138),
    (0.95, 0.1),
    (1.0, 0.0883),
    (1.05, 0.0783),
    (1.1, 0.0698),
    (1.15, 0.0624),
]
_DATA = np.asarray(_RAW, dtype=np.float64)
X: np.ndarray = _DATA[:, 0]
Y: np.ndarray = _DATA[:, 1]
