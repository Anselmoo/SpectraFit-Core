"""TDD red-first: Finding #2 — model_source_file must resolve to an existing file.

Every key in MODEL_REGISTRY must map to an EXISTING Rust source file under
crates/spectrafit-models/src/.  A key→file mapping must be explicit for divergent
keys (e.g., true_voigt → voigt_true.rs, exp_gaussian → emg.rs, etc.).

This is the durable guard: a future divergent key is caught by the parametrized
test rather than silently producing a 404-style path in the contract.
"""

from __future__ import annotations

import os

import pytest

from oracles.models import MODEL_REGISTRY

# Root of the git repository — traverse up from this test file.
# tests/unit/benchmark/ is 3 levels below the repo root.
_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
_MODELS_SRC = os.path.join(_REPO_ROOT, "crates", "spectrafit-models", "src")

# All registry keys (excluding landscape/optfn placeholders not in the Rust engine).
_REGISTRY_KEYS = list(MODEL_REGISTRY.keys())


@pytest.mark.parametrize("key", _REGISTRY_KEYS)
def test_model_source_file_exists_for_registry_key(key: str) -> None:
    """model_source_file resolved from the explicit key→file map must exist on disk."""
    # Import the mapping that the engine uses (post-fix).
    from oracles.engine import _MODEL_SOURCE_MAP

    filename = _MODEL_SOURCE_MAP.get(key, f"{key}.rs")
    path = os.path.join(_MODELS_SRC, filename)
    assert os.path.isfile(path), (
        f"Registry key {key!r} maps to {filename!r} "
        f"but {path} does not exist. "
        "Add or correct the entry in _MODEL_SOURCE_MAP."
    )


def test_model_source_map_covers_all_known_divergent_keys() -> None:
    """The explicit divergent-key entries are present in _MODEL_SOURCE_MAP."""
    from oracles.engine import _MODEL_SOURCE_MAP

    # Known divergences confirmed from the brief and the Rust src listing.
    known_divergent = {
        "true_voigt": "voigt_true.rs",
        "exp_gaussian": "emg.rs",
        "doniach_sunjic": "doniach.rs",
        "constant": "polynomial.rs",
        "linear": "polynomial.rs",
        "quadratic": "polynomial.rs",
        "arctan_step": "step.rs",
        "tanh_step": "step.rs",
        "erfc_step": "step.rs",
        "double_exponential": "exponential.rs",
    }
    for key, expected_file in known_divergent.items():
        if key not in MODEL_REGISTRY:
            continue  # skip if key not in registry (landscape-only)
        actual = _MODEL_SOURCE_MAP.get(key)
        assert actual == expected_file, (
            f"Expected _MODEL_SOURCE_MAP[{key!r}] == {expected_file!r}, got {actual!r}"
        )
