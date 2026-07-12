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
    """__all__ must list exactly 17 symbols — catches accidental growth or deletion."""
    assert len(_ALL) == 17, f"Expected 17 symbols in __all__, got {len(_ALL)}: {sorted(_ALL)}"
