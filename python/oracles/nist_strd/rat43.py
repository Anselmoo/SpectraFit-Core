r"""NIST StRD Rat43 dataset — verbatim from itl.nist.gov.

Model (4 parameters, 15 observations, DOF = 11):

    $$
    y = \dfrac{b1}{\left(1 + e^{\,b2 - b3 x}\right)^{1/b4}} + \varepsilon
    $$

NIST classifies Rat43 as **"Higher"** difficulty.

Richards curve: onion-bulb dry weight against growing time. Uses all four
parameters of the generalised_logistic kernel; Rat42 is this curve at b4 = 1.

**Mapping to spectrafit** — one ``GENERALISED_LOGISTIC`` node, all four parameters free.

Source: https://www.itl.nist.gov/div898/strd/nls/data/rat43.shtml
Data file: https://www.itl.nist.gov/div898/strd/nls/data/LINKS/DATA/Rat43.dat

Attributes:
    START1: NIST-published starting guess (4 free params), the distant start.
    START2: The alternative NIST-published starting guess.
    CERTIFIED: Certified parameter values and 1$\sigma$ standard errors, to 10
        significant figures. Do not round when comparing against a fitted
        result — NIST publishes them at this precision deliberately.
    RSS: Certified residual sum of squares.
    DOF: Degrees of freedom, $N_\mathrm{obs} - N_\mathrm{params} = 15 - 4 = 11$.
        (This docstring and the constant previously recorded 9, a transcription
        error: $\sqrt{\mathrm{RSS}/11} = 2.8262414662\times10^{1}$ reproduces NIST's
        published residual standard deviation exactly, while $\sqrt{\mathrm{RSS}/9}$
        does not. Corrected 2026-08-21.)
    N_OBS: Number of observations.
    X: Independent variable, one entry per observation. Reordered from the
        data file, which lists y first.
    Y: Dependent variable, one entry per observation.
"""

from __future__ import annotations

import numpy as np

START1: dict[str, float] = {"b1": 100.0, "b2": 10.0, "b3": 1.0, "b4": 1.0}
START2: dict[str, float] = {"b1": 700.0, "b2": 5.0, "b3": 0.75, "b4": 1.3}

CERTIFIED: dict[str, tuple[float, float]] = {
    "b1": (6.9964151270e02, 1.6302297817e01),
    "b2": (5.2771253025e00, 2.0828735829e00),
    "b3": (7.5962938329e-01, 1.9566123451e-01),
    "b4": (1.2792483859e00, 6.8761936385e-01),
}

RSS: float = 8.7864049080e03
DOF: int = 11
N_OBS: int = 15

_RAW: list[tuple[float, float]] = [
    (1.0, 16.08),
    (2.0, 33.83),
    (3.0, 65.8),
    (4.0, 97.2),
    (5.0, 191.55),
    (6.0, 326.2),
    (7.0, 386.87),
    (8.0, 520.53),
    (9.0, 590.03),
    (10.0, 651.92),
    (11.0, 724.93),
    (12.0, 699.56),
    (13.0, 689.96),
    (14.0, 637.56),
    (15.0, 717.41),
]
_DATA = np.asarray(_RAW, dtype=np.float64)
X: np.ndarray = _DATA[:, 0]
Y: np.ndarray = _DATA[:, 1]
