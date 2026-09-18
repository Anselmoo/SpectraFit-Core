r"""NIST StRD DanWood dataset — verbatim from itl.nist.gov.

Model (2 parameters, 6 observations, DOF = 4):

    $$
    y = b1 \cdot x^{b2} + \varepsilon
    $$

NIST classifies DanWood as **"Lower"** difficulty.

A pure power law, which is ``power_law_offset`` A(b+x)^(-1/s) with the offset
fixed at zero and s = -1/b2.

**Mapping to spectrafit** — one ``POWER_LAW_OFFSET`` node with ``offset`` fixed at 0.

Source: https://www.itl.nist.gov/div898/strd/nls/data/danwood.shtml
Data file: https://www.itl.nist.gov/div898/strd/nls/data/LINKS/DATA/DanWood.dat

Attributes:
    START1: NIST-published starting guess (2 free params), the distant start.
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

START1: dict[str, float] = {"b1": 1.0, "b2": 5.0}
START2: dict[str, float] = {"b1": 0.7, "b2": 4.0}

CERTIFIED: dict[str, tuple[float, float]] = {
    "b1": (7.6886226176e-01, 1.8281973860e-02),
    "b2": (3.8604055871e00, 5.1726610913e-02),
}

RSS: float = 4.3173084083e-03
DOF: int = 4
N_OBS: int = 6

_RAW: list[tuple[float, float]] = [
    (1.309, 2.138),
    (1.471, 3.421),
    (1.49, 3.597),
    (1.565, 4.34),
    (1.611, 4.882),
    (1.68, 5.66),
]
_DATA = np.asarray(_RAW, dtype=np.float64)
X: np.ndarray = _DATA[:, 0]
Y: np.ndarray = _DATA[:, 1]
