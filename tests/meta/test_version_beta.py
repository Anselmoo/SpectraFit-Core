"""Pin the beta release metadata so an accidental revert to alpha is caught."""

from __future__ import annotations

import tomllib
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def test_version_is_beta() -> None:
    data = tomllib.loads(_PYPROJECT.read_text())
    assert data["project"]["version"] == "0.1.0b1"


def test_classifier_is_beta() -> None:
    data = tomllib.loads(_PYPROJECT.read_text())
    classifiers = data["project"]["classifiers"]
    assert "Development Status :: 4 - Beta" in classifiers
    assert "Development Status :: 3 - Alpha" not in classifiers
