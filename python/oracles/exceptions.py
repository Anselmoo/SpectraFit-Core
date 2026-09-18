"""Domain exception types raised by :mod:`oracles`.

Every error this package raises deliberately derives from **both**
:class:`OracleError` — so a caller can catch everything originating here with
one ``except`` clause — and the closest builtin, so existing
``except ValueError`` / ``except KeyError`` call sites keep working unchanged.

Errors raised *inside* a Pydantic validator are intentionally left as plain
``ValueError``. Pydantic catches them and re-raises a
``pydantic.ValidationError``, discarding the original type, so a domain type
there would carry no information to the caller. Only errors that reach the
caller unwrapped are typed.

Two builtin raises are also left alone on purpose, because the builtin is
already the semantically correct type: the ``ImportError`` guarding the
optional ``matplotlib`` dependency in :mod:`oracles.forensics`, and the
``typer`` / ``fastapi`` exceptions raised by :mod:`oracles.cli` and
:mod:`oracles.api`, which are transport-layer control flow confined to those
two modules.
"""

from __future__ import annotations


class OracleError(Exception):
    """Base class for every error raised by :mod:`oracles`.

    Deliberately *not* a :class:`ValueError` subclass, so that
    ``except OracleError`` stays narrow and does not swallow unrelated builtin
    errors.
    """


class RegistryError(OracleError, ValueError):
    """A registry entry is duplicated or structurally invalid.

    Raised by the model, lineshape, landscape, claim, and provenance
    registries when a key is registered twice, or when an identifier does not
    match the required shape (for example a claim id that is not a dotted
    namespace).
    """


class UnknownKeyError(OracleError, KeyError):
    """A registry lookup names a key that was never registered.

    Derives from :class:`KeyError` rather than :class:`ValueError` because it
    is a failed mapping lookup, and callers already treat it as one.
    """


class ContractError(OracleError, ValueError):
    """A report payload violates the ``BenchReport`` contract.

    Covers schema-version migration failures — no migration path, a missing
    ``schemaVersion`` field, or a migration step that failed to advance the
    version.
    """


class CaseSpecError(OracleError, ValueError):
    """A benchmark case recipe is invalid.

    Raised when a case references a model that is not a peak (or edge-peak)
    shape, or names a lineshape recipe that does not exist.
    """


class BackendError(OracleError, ValueError):
    """A benchmark backend cannot handle the requested configuration.

    Raised for dispatch failures — an unsupported solver method, or a model
    shape with no kernel implemented for that backend.
    """


class BackendUnavailableError(OracleError, RuntimeError):
    """A required backend or compiled extension is not installed.

    Distinct from :class:`BackendError`: the backend is absent from the
    environment rather than present-but-unable to service the request, so the
    fix is an install/build step rather than a different configuration.
    """


class AuditError(OracleError, ValueError):
    """An audit integrity invariant does not hold.

    Raised when the audit runner finds that audited claims do not resolve to
    the evidence the ledger requires.
    """
