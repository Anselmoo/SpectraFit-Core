"""NIST StRD MGH17 (Osborne 1) dataset — verbatim from itl.nist.gov.

Model (5 parameters, 33 observations, DOF = 28):

    y = b1 + b2·exp(−b4·x) + b3·exp(−b5·x)

NIST classifies MGH17 as **"Higher"** difficulty (start-sensitive; the problem
is known to be very sensitive to starting guesses, particularly Start 1 which
is far from the solution).

**Composition in spectrafit** — the model is assembled from two nodes:

* **Node ``bg``**: ``Constant(c=b1)`` — the constant baseline.
* **Node ``exp``**: ``DoubleExponential(A1=b2, lam1=b4, A2=b3, lam2=b5)`` — the
  two decaying exponential terms.

Total free parameters: 1 + 4 = 5, matching NIST's DOF = N − p = 33 − 5 = 28.

Note: b3 is negative in the certified solution, so the DoubleExponential A2
parameter must be allowed to go negative (no lower bound on A2).
lam1 and lam2 (rate constants b4, b5) are constrained min=0.

Source: https://www.itl.nist.gov/div898/strd/nls/data/mgh17.shtml
Data file: https://www.itl.nist.gov/div898/strd/nls/data/LINKS/DATA/MGH17.dat
"""

from __future__ import annotations

import numpy as np

# NIST-published starting guesses (5 free params).
START1 = {"b1": 50.0, "b2": 150.0, "b3": -100.0, "b4": 1.0, "b5": 2.0}

START2 = {"b1": 0.5, "b2": 1.5, "b3": -1.0, "b4": 0.01, "b5": 0.02}

# Certified parameter values + 1σ standard errors (verbatim from NIST .dat file).
CERTIFIED: dict[str, tuple[float, float]] = {
    "b1": (3.7541005211e-01, 2.0723153551e-03),
    "b2": (1.9358469127e00, 2.2031669222e-01),
    "b3": (-1.4646871366e00, 2.2175707739e-01),
    "b4": (1.2867534640e-02, 4.4861358114e-04),
    "b5": (2.2122699662e-02, 8.9471996575e-04),
}

# Certified residual statistics.
# Cross-check: sqrt(5.4648946975e-05 / 28) = 1.3970497866e-03 ✓
RSS = 5.4648946975e-05
RESIDUAL_STD_DEV = 1.3970497866e-03
DOF = 28
N_OBS = 33

# 33 (x, y) observations — NIST file has columns (y, x); reordered here to (x, y).
_RAW = [
    (0.000000e00, 8.440000e-01),
    (1.000000e01, 9.080000e-01),
    (2.000000e01, 9.320000e-01),
    (3.000000e01, 9.360000e-01),
    (4.000000e01, 9.250000e-01),
    (5.000000e01, 9.080000e-01),
    (6.000000e01, 8.810000e-01),
    (7.000000e01, 8.500000e-01),
    (8.000000e01, 8.180000e-01),
    (9.000000e01, 7.840000e-01),
    (1.000000e02, 7.510000e-01),
    (1.100000e02, 7.180000e-01),
    (1.200000e02, 6.850000e-01),
    (1.300000e02, 6.580000e-01),
    (1.400000e02, 6.280000e-01),
    (1.500000e02, 6.030000e-01),
    (1.600000e02, 5.800000e-01),
    (1.700000e02, 5.580000e-01),
    (1.800000e02, 5.380000e-01),
    (1.900000e02, 5.220000e-01),
    (2.000000e02, 5.060000e-01),
    (2.100000e02, 4.900000e-01),
    (2.200000e02, 4.780000e-01),
    (2.300000e02, 4.670000e-01),
    (2.400000e02, 4.570000e-01),
    (2.500000e02, 4.480000e-01),
    (2.600000e02, 4.380000e-01),
    (2.700000e02, 4.310000e-01),
    (2.800000e02, 4.240000e-01),
    (2.900000e02, 4.200000e-01),
    (3.000000e02, 4.140000e-01),
    (3.100000e02, 4.110000e-01),
    (3.200000e02, 4.060000e-01),
]
_DATA = np.asarray(_RAW, dtype=np.float64)
X: np.ndarray = _DATA[:, 0]
Y: np.ndarray = _DATA[:, 1]
