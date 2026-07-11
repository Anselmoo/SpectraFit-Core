"""NIST StRD Misra1a dataset — verbatim from itl.nist.gov.

Model (2 parameters, 14 observations, DOF = 12):

    y = b1·(1 − exp(−b2·x)) + ε

NIST classifies Misra1a as **"Lower"** difficulty.  Both starting points
(Start 1 and Start 2) should converge to the certified minimum for
well-implemented LM solvers.

**Mapping to spectrafit** — the model maps 1-to-1 to the
``SATURATING_EXPONENTIAL`` kernel:

    SaturatingExponential(amplitude=b1, rate=b2)  ≡  b1·(1 − exp(−b2·x))

No re-parameterization is needed; all projections are identity.

Note: this is the **same functional form** as BoxBOD; the difference is the
dataset (y=volume vs pressure for a piston-cylinder apparatus vs y=BOD).

Source: https://www.itl.nist.gov/div898/strd/nls/data/misra1a.shtml
Data file: https://www.itl.nist.gov/div898/strd/nls/data/LINKS/DATA/Misra1a.dat
"""

from __future__ import annotations

import numpy as np

# NIST-published starting guesses (2 free params).
START1: dict[str, float] = {"b1": 500.0, "b2": 1.0e-4}
START2: dict[str, float] = {"b1": 250.0, "b2": 5.0e-4}

# Certified parameter values + 1σ standard errors (10 significant figures).
CERTIFIED: dict[str, tuple[float, float]] = {
    "b1": (2.3894212918e02, 2.7070075241e00),
    "b2": (5.5015643181e-04, 7.2668688436e-06),
}

# Certified residual statistics.
# Cross-check: sqrt(RSS/DOF) = sqrt(1.2455138894e-01 / 12) ≈ 1.0187876330e-01 ✓
RSS: float = 1.2455138894e-01
DOF: int = 12
N_OBS: int = 14

# 14 (x, y) observations (data file order: y=volume, x=pressure).
_RAW: list[tuple[float, float]] = [
    (77.6, 10.07),
    (114.9, 14.73),
    (141.1, 17.94),
    (190.8, 23.93),
    (239.9, 29.61),
    (289.0, 35.18),
    (332.8, 40.02),
    (378.4, 44.82),
    (434.8, 50.76),
    (477.3, 55.05),
    (536.8, 61.01),
    (593.1, 66.40),
    (689.1, 75.47),
    (760.0, 81.78),
]
_DATA = np.asarray(_RAW, dtype=np.float64)
X: np.ndarray = _DATA[:, 0]
Y: np.ndarray = _DATA[:, 1]
