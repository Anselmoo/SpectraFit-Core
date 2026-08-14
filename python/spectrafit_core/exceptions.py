"""Domain exception types raised by :mod:`spectrafit_core`.

Every error this package raises deliberately derives from **both**
:class:`SpectraFitError` — so a caller can catch everything originating here
with one ``except`` clause — and the closest builtin, so existing
``except ValueError`` call sites keep working unchanged.

Errors raised *inside* a Pydantic validator are intentionally left as plain
``ValueError``. Pydantic catches them and re-raises a
``pydantic.ValidationError``, discarding the original type, so a domain type
there would carry no information to the caller. Only errors that reach the
caller unwrapped are typed.
"""

from __future__ import annotations


class SpectraFitError(Exception):
    """Base class for every error raised by :mod:`spectrafit_core`.

    Deliberately *not* a :class:`ValueError` subclass, so that
    ``except SpectraFitError`` stays narrow and does not swallow unrelated
    builtin errors.
    """


class SpecificationError(SpectraFitError, ValueError):
    """A model, graph, parameter, or dataset specification is invalid.

    Raised when a caller-supplied specification is structurally wrong — a
    malformed ``bind(to=...)`` target, or a dataset count that disagrees with
    the graph's slice count — as opposed to a numerical failure during fitting.
    """
