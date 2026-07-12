"""TDD red-first: Finding #6 — dead model_key in tied grid.

_TIED_GRID entry at index 2 declares model_key="gaussian" but the
match arm hardcodes pseudo_voigt. The grid entry must say pseudo_voigt
so the model_key field is not misleading/dead.
"""

from __future__ import annotations

def test_tied_grid_shared_fraction_model_key_is_pseudo_voigt() -> None:
    """_TIED_GRID shared_fraction entry must have model_key 'pseudo_voigt', not 'gaussian'."""
    from oracles.cases import _TIED_GRID

    shared_fraction_entries = [
        (model_key, tie_kind, condition)
        for model_key, tie_kind, condition in _TIED_GRID
        if tie_kind == "shared_fraction"
    ]
    assert shared_fraction_entries, "No shared_fraction entry in _TIED_GRID"
    for model_key, tie_kind, condition in shared_fraction_entries:
        assert model_key == "pseudo_voigt", (
            f"_TIED_GRID shared_fraction entry has model_key={model_key!r}; "
            "expected 'pseudo_voigt' to match the match arm that hardcodes pseudo_voigt peaks"
        )


def test_tied_grid_condition_tag_matches_model_key() -> None:
    """Each _TIED_GRID entry's condition tag should reflect the actual model used."""
    from oracles.cases import _TIED_GRID

    for model_key, tie_kind, condition in _TIED_GRID:
        if tie_kind == "shared_fraction":
            # The condition tag "pseudo_voigt/shared-fraction" must align with model_key
            assert condition.startswith("pseudo_voigt"), (
                f"condition={condition!r} does not start with 'pseudo_voigt' "
                f"but model_key={model_key!r} — one of them is wrong"
            )
