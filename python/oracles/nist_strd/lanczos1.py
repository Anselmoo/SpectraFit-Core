"""NIST StRD Lanczos1 dataset — verbatim from itl.nist.gov.

Model (6 parameters, 24 observations, DOF = 18):

    y = b1·exp(-b2·x) + b3·exp(-b4·x) + b5·exp(-b6·x)

NIST classifies Lanczos1 as **"Average"** difficulty.  In practice the
problem is exceptionally sensitive: the data are synthetically generated
from exact parameter values, so the certified RSS is
1.4307867721e-25 — essentially at machine-epsilon scale.  Any LM solver
that reaches the global minimum will achieve RSS ≈ 1e-22 to 1e-25
(floating-point arithmetic noise floor), but convergence from the
first starting guess (start1) is fragile because the cost surface has
near-degenerate curvature at that scale.

**Composition in spectrafit** — this is the first NIST StRD problem wired
with *no Gaussians*: three exponential terms only.  spectrafit's catalog
has no single three-exponential kernel, so the three terms are composed
from TWO ``DoubleExponential`` nodes:

* **Node ``exp12``**: ``DoubleExponential(A1=b1, lam1=b2, A2=b3, lam2=b4)``
  — first two terms, four free parameters.
* **Node ``exp3``**: ``DoubleExponential(A1=b5, lam1=b6, A2=0[vary=False],
  lam2=1.0[vary=False])`` — third term only; A2 is pinned at 0 to nullify
  the second slot; lam2 is arbitrary (irrelevant when A2=0).
  Two free parameters.

Total free parameters: 4 + 2 = 6, matching NIST's DOF = N − p = 24 − 6 = 18.

Source: https://www.itl.nist.gov/div898/strd/nls/data/lanczos1.shtml
"""

from __future__ import annotations

import numpy as np

# NIST-published starting guesses (6 free params).
START1 = {"b1": 1.2, "b2": 0.3, "b3": 5.6, "b4": 5.5, "b5": 6.5, "b6": 7.6}

START2 = {"b1": 0.5, "b2": 0.7, "b3": 3.6, "b4": 4.2, "b5": 4.0, "b6": 6.3}

# Certified parameter values + 1σ standard errors (10 significant figures).
CERTIFIED: dict[str, tuple[float, float]] = {
    "b1": (9.5100000027e-02, 5.3347304234e-11),
    "b2": (1.0000000001e00, 2.7473038179e-10),
    "b3": (8.6070000013e-01, 1.3576062225e-10),
    "b4": (3.0000000002e00, 3.3308253069e-10),
    "b5": (1.5575999998e00, 1.8815731448e-10),
    "b6": (5.0000000001e00, 1.1057500538e-10),
}

# Certified residual statistics.
RSS = 1.4307867721e-25
DOF = 18
N_OBS = 24

# 24 (x, y) observations.
_RAW = [
    (0.0, 2.513400000000e00),
    (5.000000000000e-02, 2.044333373291e00),
    (1.000000000000e-01, 1.668404436564e00),
    (1.500000000000e-01, 1.366418021208e00),
    (2.000000000000e-01, 1.123232487372e00),
    (2.500000000000e-01, 9.268897180037e-01),
    (3.000000000000e-01, 7.679338563728e-01),
    (3.500000000000e-01, 6.388775523106e-01),
    (4.000000000000e-01, 5.337835317402e-01),
    (4.500000000000e-01, 4.479363617347e-01),
    (5.000000000000e-01, 3.775847884350e-01),
    (5.500000000000e-01, 3.197393199326e-01),
    (6.000000000000e-01, 2.720130773746e-01),
    (6.500000000000e-01, 2.324965529032e-01),
    (7.000000000000e-01, 1.996589546065e-01),
    (7.500000000000e-01, 1.722704126914e-01),
    (8.000000000000e-01, 1.493405660168e-01),
    (8.500000000000e-01, 1.300700206922e-01),
    (9.000000000000e-01, 1.138119324644e-01),
    (9.500000000000e-01, 1.000415587559e-01),
    (1.000000000000e00, 8.833209084540e-02),
    (1.050000000000e00, 7.833544019350e-02),
    (1.100000000000e00, 6.976693743449e-02),
    (1.150000000000e00, 6.239312536719e-02),
]
_DATA = np.asarray(_RAW, dtype=np.float64)
X: np.ndarray = _DATA[:, 0]
Y: np.ndarray = _DATA[:, 1]
