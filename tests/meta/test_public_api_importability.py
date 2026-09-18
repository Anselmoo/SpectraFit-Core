"""Gate: every spectrafit_core.__all__ symbol is importable and present in dir().

Catches renames, deletions, or forward-reference errors in the public API before
a user encounters them at runtime.
"""

from __future__ import annotations

import importlib

import pytest


def _get_module():
    return importlib.import_module("spectrafit_core")


_MODULE = _get_module()
_ALL: list[str] = list(_MODULE.__all__)


@pytest.mark.parametrize("name", _ALL)
def test_all_symbol_is_reachable_via_getattr(name: str) -> None:
    """Every __all__ entry must be retrievable via getattr without raising."""
    obj = getattr(_MODULE, name)
    assert obj is not None


def test_all_symbols_subset_of_dir() -> None:
    """set(__all__) must be a subset of set(dir(spectrafit_core))."""
    missing = set(_ALL) - set(dir(_MODULE))
    assert not missing, f"__all__ names absent from dir(): {sorted(missing)}"


def test_all_has_expected_count() -> None:
    """__all__ must list exactly 21 symbols — catches accidental growth or deletion.

    Was 17 until the exception taxonomy landed (080112a), which added
    ``SpectraFitError`` and ``SpecificationError`` to the public surface without
    updating this count. That is exactly the growth this test exists to catch —
    it did its job; the number simply was not moved with the change.

    Was 19 until ``MeasurementInput`` — the declared parameter type of every
    public entrypoint (``fit``, ``fit_fast``, ``evaluate``,
    ``evaluate_components``, ``FitGraph.eval``) — was exported (API-03) so a
    caller can type-annotate against it.

    Was 20 until ``__version__`` (9d4f693d, S9) was exported so a paper
    reader can query the running version.
    """
    assert len(_ALL) == 21, f"Expected 21 symbols in __all__, got {len(_ALL)}: {sorted(_ALL)}"
