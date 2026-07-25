"""Error-recovery paths in oracles.forensics (BLE001 sites).

render_case  (line 61):  a backend that raises during .fit() is skipped;
                          the PNG is still written with an empty-data plot.
render_regressions (line 172): a render_case failure is caught and logged;
                                the function returns [] without re-raising.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import oracles.forensics as _forensics_mod
from oracles.backends._base import Backend, BackendOutcome
from oracles.forensics import render_case, render_regressions


# ---------------------------------------------------------------------------
# Minimal stubs (duck-typed, no heavy catalog machinery)
# ---------------------------------------------------------------------------


class _FakeCase:
    """Minimal BenchCase substitute — only the attributes forensics.py reads."""

    x = np.linspace(0.0, 5.0, 20)
    y = np.ones(20)
    category = "easy"


class _RaisingBackend(Backend):
    """Backend stub that always raises RuntimeError on .fit()."""

    name = "failing"

    def is_supported(self, case: Any) -> bool:  # noqa: ARG002
        return True

    def build(self, case: Any) -> Any:  # noqa: ARG002
        raise NotImplementedError

    def run(self, model: Any, case: Any) -> Any:  # noqa: ARG002
        raise NotImplementedError

    def extract(self, raw: Any, case: Any) -> BackendOutcome:  # noqa: ARG002
        raise NotImplementedError

    def fit(self, case: Any, n_reps: int = 1) -> BackendOutcome:  # noqa: ARG002
        raise RuntimeError("injected backend error")


class _FakeSpec:
    """Minimal CaseSpec stub with just an .id."""

    id = "reg-001"


# ---------------------------------------------------------------------------
# Site 1: render_case BLE001 (line 61) — backend raises
# ---------------------------------------------------------------------------


def test_render_case_skips_raising_backend_and_writes_png(tmp_path: Path) -> None:
    """BLE001 at line 61: backend RuntimeError is caught; PNG still written."""
    pytest.importorskip("matplotlib", reason="requires --extra benchmark")
    out = tmp_path / "case.png"
    result = render_case(
        "test-id",
        _FakeCase(),  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
        [_RaisingBackend()],
        out,
    )
    assert result == out
    assert out.exists()


# ---------------------------------------------------------------------------
# Site 2: render_regressions BLE001 (line 172) — render_case raises
# ---------------------------------------------------------------------------


def test_render_regressions_catches_render_case_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BLE001 at line 172: render_case failure caught; returns [] without re-raising."""
    (tmp_path / "manifest.json").write_text(
        json.dumps({"regression_case_ids": ["reg-001"]})
    )

    def _always_raise(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected render failure")

    monkeypatch.setattr(_forensics_mod, "build_specs", lambda: [_FakeSpec()])
    monkeypatch.setattr(_forensics_mod, "materialize", lambda s: _FakeCase())
    monkeypatch.setattr(_forensics_mod, "render_case", _always_raise)

    paths = render_regressions(tmp_path, backends=[])
    assert paths == []


# ---------------------------------------------------------------------------
# Bonus: render_regressions early-exit paths (no BLE001 — pure branch coverage)
# ---------------------------------------------------------------------------


def test_render_regressions_returns_empty_when_no_regressions(tmp_path: Path) -> None:
    """Returns [] immediately when regression_case_ids is empty."""
    (tmp_path / "manifest.json").write_text(json.dumps({"regression_case_ids": []}))
    paths = render_regressions(tmp_path, backends=[])
    assert paths == []


def test_render_regressions_returns_empty_when_manifest_missing(tmp_path: Path) -> None:
    """Returns [] without raising when manifest.json is absent."""
    paths = render_regressions(tmp_path, backends=[])
    assert paths == []
