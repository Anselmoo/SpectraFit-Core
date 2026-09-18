r"""NIST StRD MGH09 dataset — verbatim from itl.nist.gov.

Model (4 parameters, 11 observations, DOF = 7):

    $$
    y = b1 \cdot (x^2 + b2 \cdot x) / (x^2 + b3 \cdot x + b4) + \varepsilon
    $$

NIST classifies MGH09 as **"Higher"** difficulty (Kowalik and Osborne, 1978).
This is a rational function; spectrafit maps it 1-to-1 to the
``MGH09_RATIONAL`` kernel:

    Mgh09Rational(amplitude=b1, num_lin=b2, den_lin=b3, den_const=b4)
        $\equiv b1 \cdot (x^2 + b2 \cdot x) / (x^2 + b3 \cdot x + b4)$

No re-parameterization is needed.

Source: https://www.itl.nist.gov/div898/strd/nls/data/mgh09.shtml
Data file: https://www.itl.nist.gov/div898/strd/nls/data/LINKS/DATA/MGH09.dat

Cross-check: $\sqrt{\mathrm{RSS} / \mathrm{DOF}} = \sqrt{3.0750560385e-04 / 7}$
                              $\approx$ 6.6279236552e-03  ✓ (matches certified residual std dev 6.6279236551e-03)

Attributes:
    START1: NIST-published starting guess (4 free params).
    START2: The alternative NIST-published starting guess.
    CERTIFIED: Certified parameter values and 1$\sigma$ standard errors, to 10
        significant figures. Do not round when comparing against a fitted
        result — NIST publishes them at this precision deliberately.
    RSS: Certified residual sum of squares.
    DOF: Degrees of freedom.
    N_OBS: Number of observations.
    X: Independent variable, one entry per observation. NIST's data file
        lists y then x; transposed here to (x, y).
    Y: Dependent variable, one entry per observation.
"""

from __future__ import annotations

import numpy as np

START1: dict[str, float] = {"b1": 25.0, "b2": 39.0, "b3": 41.5, "b4": 39.0}
START2: dict[str, float] = {"b1": 0.25, "b2": 0.39, "b3": 0.415, "b4": 0.39}

CERTIFIED: dict[str, tuple[float, float]] = {
    "b1": (1.9280693458e-01, 1.1435312227e-02),
    "b2": (1.9128232873e-01, 1.9633220911e-01),
    "b3": (1.2305650693e-01, 8.0842031232e-02),
    "b4": (1.3606233068e-01, 9.0025542308e-02),
}

RSS: float = 3.0750560385e-04
DOF: int = 7
N_OBS: int = 11

_RAW: list[tuple[float, float]] = [
    (4.000000e00, 1.957000e-01),
    (2.000000e00, 1.947000e-01),
    (1.000000e00, 1.735000e-01),
    (5.000000e-01, 1.600000e-01),
    (2.500000e-01, 8.440000e-02),
    (1.670000e-01, 6.270000e-02),
    (1.250000e-01, 4.560000e-02),
    (1.000000e-01, 3.420000e-02),
    (8.330000e-02, 3.230000e-02),
    (7.140000e-02, 2.350000e-02),
    (6.250000e-02, 2.460000e-02),
]
_DATA = np.asarray(_RAW, dtype=np.float64)
X: np.ndarray = _DATA[:, 0]
Y: np.ndarray = _DATA[:, 1]
