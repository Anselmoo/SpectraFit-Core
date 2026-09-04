r"""NIST StRD Eckerle4 dataset — verbatim from itl.nist.gov.

Model (3 parameters, 35 observations, DOF = 32):

    $$
    y = \dfrac{b1}{b2} \cdot e^{-\tfrac{1}{2}\left(\tfrac{x-b3}{b2}\right)^2} + \varepsilon
    $$

NIST classifies Eckerle4 as **"Higher"** difficulty.

A Gaussian whose amplitude is coupled to its width: with sigma = b2 and center
= b3, the NIST amplitude is b1 = A * sigma. No new kernel is needed -- the
coupling lives in the projection.

**Mapping to spectrafit** — one ``GAUSSIAN`` node; b1 is recovered as ``amplitude * sigma``.

Source: https://www.itl.nist.gov/div898/strd/nls/data/eckerle4.shtml
Data file: https://www.itl.nist.gov/div898/strd/nls/data/LINKS/DATA/Eckerle4.dat

Attributes:
    START1: NIST-published starting guess (3 free params), the distant start.
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

START1: dict[str, float] = {"b1": 1.0, "b2": 10.0, "b3": 500.0}
START2: dict[str, float] = {"b1": 1.5, "b2": 5.0, "b3": 450.0}

CERTIFIED: dict[str, tuple[float, float]] = {
    "b1": (1.5543827178e00, 1.5408051163e-02),
    "b2": (4.0888321754e00, 4.6803020753e-02),
    "b3": (4.5154121844e02, 4.6800518816e-02),
}

RSS: float = 1.4635887487e-03
DOF: int = 32
N_OBS: int = 35

_RAW: list[tuple[float, float]] = [
    (400.0, 0.0001575),
    (405.0, 0.0001699),
    (410.0, 0.000235),
    (415.0, 0.0003102),
    (420.0, 0.0004917),
    (425.0, 0.000871),
    (430.0, 0.0017418),
    (435.0, 0.00464),
    (436.5, 0.0065895),
    (438.0, 0.0097302),
    (439.5, 0.0149002),
    (441.0, 0.023731),
    (442.5, 0.0401683),
    (444.0, 0.0712559),
    (445.5, 0.1264458),
    (447.0, 0.2073413),
    (448.5, 0.2902366),
    (450.0, 0.3445623),
    (451.5, 0.3698049),
    (453.0, 0.3668534),
    (454.5, 0.3106727),
    (456.0, 0.2078154),
    (457.5, 0.1164354),
    (459.0, 0.0616764),
    (460.5, 0.03372),
    (462.0, 0.0194023),
    (463.5, 0.0117831),
    (465.0, 0.0074357),
    (470.0, 0.0022732),
    (475.0, 0.00088),
    (480.0, 0.0004579),
    (485.0, 0.0002345),
    (490.0, 0.0001586),
    (495.0, 0.0001143),
    (500.0, 7.1e-05),
]
_DATA = np.asarray(_RAW, dtype=np.float64)
X: np.ndarray = _DATA[:, 0]
Y: np.ndarray = _DATA[:, 1]
