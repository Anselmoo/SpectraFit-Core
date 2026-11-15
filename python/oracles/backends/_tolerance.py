r"""Stopping-tolerance modes of the benchmark: library defaults or one common setting.

``default`` leaves every backend's library call exactly as it is, so each solver stops
by its own library's tests and default thresholds. ``common`` hands every backend the
same frozen :class:`StopTolerances` (ftol = xtol = gtol = $10^{-8}$), which each adapter
passes to the tests its library has:

- spectrafit: ``FitOptions.tolerance`` (one knob for all three tests, so the three
  values must be equal);
- lmfit ``leastsq``: ``fit_kws={"ftol", "xtol", "gtol"}`` (reaches
  ``scipy.optimize.leastsq``); differential evolution has none of the three tests and
  keeps its own stop;
- scipy ``least_squares``: ``ftol``, ``xtol``, ``gtol``;
- optimistix ``LevenbergMarquardt``: ``rtol`` and ``atol`` of its Cauchy test (step and
  residual change); it has no gradient test, and the single pair needs ftol = xtol.

What each test compares still differs between libraries; ``common`` equalises the
thresholds, not the definitions. Budgets (evaluation and step limits) are not
stopping tolerances and are the same in both modes.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ToleranceMode = Literal["default", "common"]
TOLERANCE_MODES: tuple[ToleranceMode, ...] = ("default", "common")


class StopTolerances(BaseModel):
    """Thresholds of the three classical least-squares stopping tests."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ftol: float = Field(gt=0.0)
    """Relative change of the cost."""
    xtol: float = Field(gt=0.0)
    """Relative change of the parameters."""
    gtol: float = Field(gt=0.0)
    """Size of the (scaled) gradient."""


COMMON_TOLERANCES = StopTolerances(ftol=1e-8, xtol=1e-8, gtol=1e-8)
"""The common setting: every test at $10^{-8}$, where the backend has the test."""


def tolerances_for(mode: ToleranceMode) -> StopTolerances | None:
    """The setting a mode hands to every backend (``None`` = library defaults).

    Raises:
        ValueError: ``mode`` is not one of :data:`TOLERANCE_MODES`.
    """
    match mode:
        case "default":
            return None
        case "common":
            return COMMON_TOLERANCES
        case _:
            msg = f"unknown tolerance mode {mode!r} (expected one of {TOLERANCE_MODES})"
            raise ValueError(msg)
