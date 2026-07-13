"""NIST StRD Misra1b dataset — verbatim from itl.nist.gov.

Model (2 parameters, 14 observations, DOF = 12):

    y = b1·(1 − (1 + b2·x/2)^(−2)) + ε

NIST classifies Misra1b as **"Lower"** difficulty.  Both starting points
(Start 1 and Start 2) should converge to the certified minimum for
well-implemented LM solvers.

**Mapping to spectrafit** — the model maps 1-to-1 to the
``POWER_SATURATION`` kernel:

    PowerSaturation(amplitude=b1, rate=b2)  ≡  b1·(1 − (1 + b2·x/2)^(−2))

No re-parameterization is needed; all projections are identity.

Note: Misra1a and Misra1b share the same dataset (x=pressure, y=volume for a
piston-cylinder apparatus); only the functional form differs — exponential
saturation (Misra1a) vs power-law saturation (Misra1b).

Source: https://www.itl.nist.gov/div898/strd/nls/data/misra1b.shtml
Data file: https://www.itl.nist.gov/div898/strd/nls/data/LINKS/DATA/Misra1b.dat
"""

from __future__ import annotations

import numpy as np

# NIST-published starting guesses (2 free params).
START1: dict[str, float] = {"b1": 500.0, "b2": 1.0e-4}
START2: dict[str, float] = {"b1": 300.0, "b2": 2.0e-4}

# Certified parameter values + 1σ standard errors (10 significant figures).
CERTIFIED: dict[str, tuple[float, float]] = {
    "b1": (3.3799746163e02, 3.1643950207e00),
    "b2": (3.9039091287e-04, 4.2547321834e-06),
}

# Certified residual statistics.
# Cross-check: sqrt(RSS/DOF) = sqrt(7.5464681533e-02 / 12) ≈ 7.9301471998e-02 ✓
RSS: float = 7.5464681533e-02
DOF: int = 12
N_OBS: int = 14

# 14 (x, y) observations (data file order: y=volume, x=pressure).
# Same dataset as Misra1a — only the model (functional form) differs.
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
