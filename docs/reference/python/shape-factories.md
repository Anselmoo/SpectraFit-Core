---
icon: lucide/flask-conical
description: The 33 shape-factory functions in spectrafit_core.compose used to build a fit graph declaratively, from peak shapes to baselines and steps.
---

# Python: shape factories

`spectrafit_core.compose` exposes 33 shape-factory functions used to build a
fit graph declaratively (via `compose(...)`) or directly. They are importable
from the top-level package (`from spectrafit_core import gaussian`) or from
`spectrafit_core.compose`, but are intentionally excluded from `__all__` so
that `from spectrafit_core import *` stays narrow to the
[core API](core-api.md). See the [model formula reference](../models/index.md)
for the mathematical definition of each shape.

## Peak shapes

::: spectrafit_core.compose.gaussian
::: spectrafit_core.compose.lorentzian
::: spectrafit_core.compose.voigt
::: spectrafit_core.compose.true_voigt
::: spectrafit_core.compose.pseudo_voigt
::: spectrafit_core.compose.pearson7
::: spectrafit_core.compose.split_pearson7
::: spectrafit_core.compose.moffat
::: spectrafit_core.compose.students_t
::: spectrafit_core.compose.fano
::: spectrafit_core.compose.breit_wigner
::: spectrafit_core.compose.skewed_gaussian
::: spectrafit_core.compose.split_gaussian
::: spectrafit_core.compose.exp_gaussian
::: spectrafit_core.compose.doniach_sunjic
::: spectrafit_core.compose.asym_ir
::: spectrafit_core.compose.gaussian2d

## Baselines and steps

::: spectrafit_core.compose.constant
::: spectrafit_core.compose.linear
::: spectrafit_core.compose.quadratic
::: spectrafit_core.compose.arctan_step
::: spectrafit_core.compose.tanh_step
::: spectrafit_core.compose.erfc_step

## Kinetics and dispersion

::: spectrafit_core.compose.double_exponential
::: spectrafit_core.compose.kww
::: spectrafit_core.compose.log_normal
::: spectrafit_core.compose.harmonic_ir
::: spectrafit_core.compose.tauc
::: spectrafit_core.compose.cauchy_dispersion

## Saturation and rational models

::: spectrafit_core.compose.saturating_exponential
::: spectrafit_core.compose.power_saturation
::: spectrafit_core.compose.power_law_offset
::: spectrafit_core.compose.mgh09_rational
