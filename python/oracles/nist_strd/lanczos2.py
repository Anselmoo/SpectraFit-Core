r"""NIST StRD Lanczos2 dataset — verbatim from itl.nist.gov.

Model (6 parameters, 24 observations, DOF = 18):

    $$
    y = b1 \cdot e^{-b2 x} + b3 \cdot e^{-b4 x} + b5 \cdot e^{-b6 x} + \varepsilon
    $$

NIST classifies Lanczos2 as **"Average"** difficulty.

Same functional form and same data as Lanczos1; Lanczos2 is the 6-digit
rounding of the generating function, Lanczos1 the 12-digit one.

**Mapping to spectrafit** — two ``DOUBLE_EXPONENTIAL`` nodes, exactly as Lanczos1 does.

Source: https://www.itl.nist.gov/div898/strd/nls/data/lanczos2.shtml
Data file: https://www.itl.nist.gov/div898/strd/nls/data/LINKS/DATA/Lanczos2.dat

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
    "b1": (9.6251029939e-02, 6.6770575477e-04),
    "b2": (1.0057332849e00, 3.3989646176e-03),
    "b3": (8.6424689056e-01, 1.7185846685e-03),
    "b4": (3.0078283915e00, 4.1707005856e-03),
    "b5": (1.5529016879e00, 2.3744381417e-03),
    "b6": (5.0028798100e00, 1.3958787284e-03),
}

RSS: float = 2.2299428125e-11
DOF: int = 18
N_OBS: int = 24

_RAW: list[tuple[float, float]] = [
    (0.0, 2.5134),
    (0.05, 2.04433),
    (0.1, 1.6684),
    (0.15, 1.36642),
    (0.2, 1.12323),
    (0.25, 0.92689),
    (0.3, 0.767934),
    (0.35, 0.638878),
    (0.4, 0.533784),
    (0.45, 0.447936),
    (0.5, 0.377585),
    (0.55, 0.319739),
    (0.6, 0.272013),
    (0.65, 0.232497),
    (0.7, 0.199659),
    (0.75, 0.17227),
    (0.8, 0.149341),
    (0.85, 0.13007),
    (0.9, 0.113812),
    (0.95, 0.100042),
    (1.0, 0.0883321),
    (1.05, 0.0783354),
    (1.1, 0.0697669),
    (1.15, 0.0623931),
]
_DATA = np.asarray(_RAW, dtype=np.float64)
X: np.ndarray = _DATA[:, 0]
Y: np.ndarray = _DATA[:, 1]
