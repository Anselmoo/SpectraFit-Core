r"""NIST StRD Thurber dataset — verbatim from itl.nist.gov.

Model (7 parameters, 37 observations, DOF = 30):

    $$
    y = \dfrac{b1 + b2 x + b3 x^2 + b4 x^3}{1 + b5 x + b6 x^2 + b7 x^3} + \varepsilon
    $$

NIST classifies Thurber as **"Higher"** difficulty.

Cubic over cubic, electron mobility against log-density. Same functional form
as Hahn1; NIST rates it Higher because the certified parameters are far less
well determined from the 37 observations.

**Mapping to spectrafit** — one ``RATIONAL_CUBIC`` node, all seven parameters free.

Source: https://www.itl.nist.gov/div898/strd/nls/data/thurber.shtml
Data file: https://www.itl.nist.gov/div898/strd/nls/data/LINKS/DATA/Thurber.dat

Attributes:
    START1: NIST-published starting guess (7 free params), the distant start.
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

START1: dict[str, float] = {
    "b1": 1000.0,
    "b2": 1000.0,
    "b3": 400.0,
    "b4": 40.0,
    "b5": 0.7,
    "b6": 0.3,
    "b7": 0.03,
}
START2: dict[str, float] = {
    "b1": 1300.0,
    "b2": 1500.0,
    "b3": 500.0,
    "b4": 75.0,
    "b5": 1.0,
    "b6": 0.4,
    "b7": 0.05,
}

CERTIFIED: dict[str, tuple[float, float]] = {
    "b1": (1.2881396800e03, 4.6647963344e00),
    "b2": (1.4910792535e03, 3.9571156086e01),
    "b3": (5.8323836877e02, 2.8698696102e01),
    "b4": (7.5416644291e01, 5.5675370270e00),
    "b5": (9.6629502864e-01, 3.1333340687e-02),
    "b6": (3.9797285797e-01, 1.4984928198e-02),
    "b7": (4.9727297349e-02, 6.5842344623e-03),
}

RSS: float = 5.6427082397e03
DOF: int = 30
N_OBS: int = 37

_RAW: list[tuple[float, float]] = [
    (-3.067, 80.574),
    (-2.981, 84.248),
    (-2.921, 87.264),
    (-2.912, 87.195),
    (-2.84, 89.076),
    (-2.797, 89.608),
    (-2.702, 89.868),
    (-2.699, 90.101),
    (-2.633, 92.405),
    (-2.481, 95.854),
    (-2.363, 100.696),
    (-2.322, 101.06),
    (-1.501, 401.672),
    (-1.46, 390.724),
    (-1.274, 567.534),
    (-1.212, 635.316),
    (-1.1, 733.054),
    (-1.046, 759.087),
    (-0.915, 894.206),
    (-0.714, 990.785),
    (-0.566, 1090.109),
    (-0.545, 1080.914),
    (-0.4, 1122.643),
    (-0.309, 1178.351),
    (-0.109, 1260.531),
    (-0.103, 1273.514),
    (0.01, 1288.339),
    (0.119, 1327.543),
    (0.377, 1353.863),
    (0.79, 1414.509),
    (0.963, 1425.208),
    (1.006, 1421.384),
    (1.115, 1442.962),
    (1.572, 1464.35),
    (1.841, 1468.705),
    (2.047, 1447.894),
    (2.2, 1457.628),
]
_DATA = np.asarray(_RAW, dtype=np.float64)
X: np.ndarray = _DATA[:, 0]
Y: np.ndarray = _DATA[:, 1]
