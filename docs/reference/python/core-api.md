---
icon: lucide/book
---

# Python: core API

This page documents the stable, `__all__`-driven surface of `spectrafit_core` —
the contract a library user should rely on. The 33 shape-factory functions
(`gaussian`, `lorentzian`, `voigt`, …) are documented separately on
[Shape factories](shape-factories.md) since they are intentionally excluded
from `__all__`.

## Solvers

::: spectrafit_core.fit
::: spectrafit_core.fit_fast

## Forward evaluation

::: spectrafit_core.evaluate
::: spectrafit_core.evaluate_components

## Result types

::: spectrafit_core.FitResult
::: spectrafit_core.DatasetSlice

## Model dispatch

::: spectrafit_core.ModelType
::: spectrafit_core.ModelNodeSpec

## Solver configuration

::: spectrafit_core.FitOptions

## Graph / joint-fit types

::: spectrafit_core.FitGraph
::: spectrafit_core.GlobalFitGraph
::: spectrafit_core.ExprEdge

## Input data

::: spectrafit_core.MeasurementData

## Parameters

::: spectrafit_core.Parameter
::: spectrafit_core.ParameterResult

## Compose builder

::: spectrafit_core.compose
::: spectrafit_core.ComposeBuilder
