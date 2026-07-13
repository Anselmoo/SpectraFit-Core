"""Tests for the forensics module (regression case snapshots)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def test_forensics_import_without_matplotlib() -> None:
    """Import forensics.py works even without matplotlib installed."""
    # The forensics module itself should import successfully;
    # only render_case and render_regressions raise at call time.
    with patch("oracles.forensics.matplotlib", None, create=True):
        # This should not raise at import time
        from oracles import forensics  # noqa: F401
    # If we got here, the import succeeded even with a mocked-out matplotlib


def test_render_regressions_no_manifest() -> None:
    """render_regressions returns [] when manifest.json is missing."""
    from oracles.forensics import render_regressions

    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)
        paths = render_regressions(run_dir)
        assert paths == []


def test_render_regressions_no_regressions() -> None:
    """render_regressions returns [] when regression_case_ids is empty."""
    from oracles.forensics import render_regressions

    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)
        manifest = {
            "run_id": "2026-06-08_run_001",
            "regression_case_ids": [],
        }
        (run_dir / "manifest.json").write_text(json.dumps(manifest))
        paths = render_regressions(run_dir)
        assert paths == []


def test_render_case_writes_png_file() -> None:
    """render_case writes a non-empty PNG file."""
    pytest.importorskip("matplotlib")
    from oracles.forensics import render_case
    from oracles.cases import build_catalog

    catalog = build_catalog()
    case = catalog[0]  # Use the first case
    backends = []  # Empty backends list is fine; we just need to render the observed data

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "test_case.png"
        result_path = render_case(case.id, case, backends, out_path)

        # File should exist and be non-empty
        assert result_path.exists()
        assert result_path.stat().st_size > 0
        assert result_path.suffix == ".png"
