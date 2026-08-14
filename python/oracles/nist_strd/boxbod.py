r"""NIST StRD BoxBOD dataset — verbatim from itl.nist.gov.

Model (2 parameters, 6 observations, DOF = 4):

    $$
    y = b1 \cdot (1 - \exp(-b2 \cdot x)) + \varepsilon
    $$

NIST classifies BoxBOD as **"Higher"** difficulty.  The problem is sensitive
to starting values — Start 1 (b1=1, b2=1) often fails to converge or lands
on a different local minimum for gradient-based LM solvers.  Start 2
(b1=100, b2=0.75) is the robust guess that reaches the certified minimum.

**Mapping to spectrafit** — the model maps 1-to-1 to the
``SATURATING_EXPONENTIAL`` kernel:

    SaturatingExponential(amplitude=b1, rate=b2)  $\equiv b1 \cdot (1 - \exp(-b2 \cdot x))$

No re-parameterization is needed; all projections are identity.

Source: https://www.itl.nist.gov/div898/strd/nls/data/boxbod.shtml
Data file: https://www.itl.nist.gov/div898/strd/nls/data/LINKS/DATA/BoxBOD.dat
"""

from __future__ import annotations

import numpy as np

START1: dict[str, float] = {"b1": 1.0, "b2": 1.0}
"""Info:
    NIST-published starting guess (2 free params).

    - `START2`: the alternative NIST-published starting guess
    - `CERTIFIED`: the values this should converge to
"""
START2: dict[str, float] = {"b1": 100.0, "b2": 0.75}

CERTIFIED: dict[str, tuple[float, float]] = {
    "b1": (2.1380940889e02, 1.2354515176e01),
    "b2": (5.4723748542e-01, 1.0455993237e-01),
}
r"""Info:
    Certified parameter values + 1$\sigma$ standard errors (10 significant figures).

Warning:
    Values are given to 10 significant figures per NIST's publication --
    do not round when comparing against a fitted result.
"""

RSS: float = 1.1680088766e03
"""Info:
    Certified residual statistics.

    - `DOF`: degrees of freedom
    - `N_OBS`: number of observations
"""
DOF: int = 4
N_OBS: int = 6

_RAW: list[tuple[float, float]] = [
    (1.0, 109.0),
    (2.0, 149.0),
    (3.0, 149.0),
    (5.0, 191.0),
    (7.0, 213.0),
    (10.0, 224.0),
]
"""Info:
    6 (x, y) observations (data file order: y then x, transposed here
    to x, y).
"""
_DATA = np.asarray(_RAW, dtype=np.float64)
X: np.ndarray = _DATA[:, 0]
Y: np.ndarray = _DATA[:, 1]
