"""Shared type alias for optimization-landscape functions.

Defined here (not in oracles.models) to avoid a circular import: the per-landscape
modules are force-imported by opt_func.__init__, which is re-exported by oracles.models,
so importing Array from oracles.models inside opt_func would create a cycle.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

Array = NDArray[np.float64]
