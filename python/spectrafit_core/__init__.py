"""spectrafit_core — Rust-bound spectral fitting wheel.

Public API (``__all__``):
  fit, fit_fast            — non-linear least-squares solvers
  FitResult, DatasetSlice  — result types
  ModelType, ModelNodeSpec — model dispatch enum + node spec
  FitOptions               — solver configuration
  FitGraph, GlobalFitGraph, ExprEdge — graph / joint-fit types
  MeasurementData          — input data model
  MeasurementInput         — MeasurementData | Sequence[MeasurementData] type alias
  Parameter, ParameterResult — parameter types
  evaluate, evaluate_components — forward-evaluation helpers
  compose                  — builder function / entry point for shape factories
  ComposeBuilder           — builder class returned by ``compose()``
  SpectraFitError, SpecificationError — domain exception types
  __version__              — installed distribution version (or ``"0+unknown"``)

Shape factory functions (``gaussian``, ``lorentzian``, ``voigt``, …) are
accessible via ``from spectrafit_core import <name>`` or
``from spectrafit_core.compose import <name>`` for backward compatibility,
but are intentionally absent from ``__all__`` so that
``from spectrafit_core import *`` stays narrow.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .compose import ComposeBuilder as ComposeBuilder

# Backward-compat re-exports: factory functions remain importable via
# `from spectrafit_core import <name>` but are excluded from __all__.
# The `x as x` alias idiom tells ruff these are intentional re-exports.
from .compose import arctan_step as arctan_step
from .compose import asym_ir as asym_ir
from .compose import breit_wigner as breit_wigner
from .compose import cauchy_dispersion as cauchy_dispersion
from .compose import compose as compose
from .compose import constant as constant
from .compose import doniach_sunjic as doniach_sunjic
from .compose import double_exponential as double_exponential
from .compose import erfc_step as erfc_step
from .compose import exp_gaussian as exp_gaussian
from .compose import exp_over_linear as exp_over_linear
from .compose import fano as fano
from .compose import gaussian as gaussian
from .compose import gaussian2d as gaussian2d
from .compose import generalised_logistic as generalised_logistic
from .compose import harmonic_ir as harmonic_ir
from .compose import kww as kww
from .compose import linear as linear
from .compose import log_normal as log_normal
from .compose import lorentzian as lorentzian
from .compose import mgh09_rational as mgh09_rational
from .compose import moffat as moffat
from .compose import pearson7 as pearson7
from .compose import power_law_offset as power_law_offset
from .compose import power_saturation as power_saturation
from .compose import pseudo_voigt as pseudo_voigt
from .compose import quadratic as quadratic
from .compose import rational_cubic as rational_cubic
from .compose import saturating_exponential as saturating_exponential
from .compose import skewed_gaussian as skewed_gaussian
from .compose import split_gaussian as split_gaussian
from .compose import split_pearson7 as split_pearson7
from .compose import students_t as students_t
from .compose import tanh_step as tanh_step
from .compose import tauc as tauc
from .compose import true_voigt as true_voigt
from .compose import voigt as voigt
from .data import MeasurementData, MeasurementInput
from .evaluate import evaluate, evaluate_components
from .exceptions import SpecificationError, SpectraFitError
from .fit import fit, fit_fast
from .graph import ExprEdge, FitGraph, GlobalFitGraph
from .models import ModelNodeSpec, ModelType
from .options import FitOptions
from .parameters import Parameter, ParameterResult
from .result import DatasetSlice, FitResult

try:
    __version__ = version("spectrafit-core")
except PackageNotFoundError:
    # Editable/unbuilt checkout with no installed distribution metadata.
    __version__ = "0+unknown"

__all__ = [  # noqa: RUF022 - deliberately categorized (see the module docstring above), not alphabetical
    # Solvers
    "fit",
    "fit_fast",
    # Result types
    "FitResult",
    "DatasetSlice",
    # Model types
    "ModelType",
    "ModelNodeSpec",
    # Solver configuration
    "FitOptions",
    # Graph / joint-fit types
    "FitGraph",
    "GlobalFitGraph",
    "ExprEdge",
    # Input data
    "MeasurementData",
    "MeasurementInput",
    # Parameter types
    "Parameter",
    "ParameterResult",
    # Forward evaluation
    "evaluate",
    "evaluate_components",
    # Compose builder (entry point + class)
    "compose",
    "ComposeBuilder",
    # Domain exceptions
    "SpectraFitError",
    "SpecificationError",
    # Package metadata
    "__version__",
]
