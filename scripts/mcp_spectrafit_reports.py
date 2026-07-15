#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = ["mcp>=1.0"]
# ///
"""spectrafit-reports MCP server.

Exposes the oracles.reports query surface as four typed MCP tools so Claude
can interrogate benchmark runs without subprocess shellout:

- list_runs      — discover recent runs (newest first)
- latest_results — absolute paths for the newest run's artifacts
- load_manifest  — parsed manifest.json dict with all headline stats
- find_report_html — absolute path to the offline bundle, or null

Usage (stdio):
    uv run python scripts/mcp_spectrafit_reports.py

Register in .mcp.json:
    "spectrafit-reports": {
        "type": "stdio",
        "command": "uv",
        "args": ["run", "python", "scripts/mcp_spectrafit_reports.py"]
    }

The server is safe on a fresh checkout where .spectrafit_reports/ does not yet
exist — all tools return empty lists / null cleanly in that case.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve the project root so `extras` is importable regardless of cwd.
# The script lives at <project_root>/scripts/mcp_spectrafit_reports.py.
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
_PYTHON_DIR = _PROJECT_ROOT / "python"
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from mcp.server.fastmcp import FastMCP  # noqa: E402  (sys.path set up above)

# ---------------------------------------------------------------------------
# Local imports — guarded so the MCP still starts (with degraded responses)
# on a fresh checkout where the bench package isn't installed yet.
# ---------------------------------------------------------------------------
try:
    from oracles.reports import REPORTS_ROOT

    _BENCH_AVAILABLE = True
except ImportError:
    _BENCH_AVAILABLE = False
    REPORTS_ROOT = _PROJECT_ROOT / ".spectrafit_reports"

_RUN_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_run_(\d{3,})$")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reports_root(root: Path = REPORTS_ROOT) -> Path:
    """Return REPORTS_ROOT resolved to an absolute path."""
    if root.is_absolute():
        return root
    return (_PROJECT_ROOT / root).resolve()


def _index_runs(category: str, root: Path) -> list[dict]:
    """Read index.json and return entries for *category*, newest first."""
    index_path = root / "index.json"
    if not index_path.exists():
        return []
    try:
        runs: list[dict] = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return [r for r in runs if r.get("category") == category]


def _find_html(run_dir: Path) -> str | None:
    """Search *run_dir* for report.html; return absolute path str or None."""
    if not run_dir.exists():
        return None
    for candidate in ("report.html", "index.html"):
        p = run_dir / candidate
        if p.exists():
            return str(p.resolve())
    return None


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "spectrafit-reports",
    instructions=(
        "Query spectrafit benchmark run artifacts. "
        "Tools: list_runs, latest_results, load_manifest, find_report_html."
    ),
)


@mcp.tool()
def list_runs(category: str = "benchmark", limit: int = 5) -> list[dict]:
    """List recent benchmark runs (newest first).

    Args:
        category: Report category directory (default: "benchmark").
        limit: Maximum number of runs to return (default: 5).

    Returns:
        List of dicts with keys: run_id (str), date (str), run_dir (str),
        has_report_html (bool). Empty list when no runs exist.
    """
    root = _reports_root()
    runs = _index_runs(category, root)
    result = []
    for entry in runs[:limit]:
        run_id = entry.get("run_id", "")
        run_dir = root / category / run_id
        result.append(
            {
                "run_id": run_id,
                "date": entry.get("date", ""),
                "run_dir": str(run_dir.resolve()),
                "has_report_html": _find_html(run_dir) is not None,
            }
        )
    return result


@mcp.tool()
def latest_results(category: str = "benchmark") -> dict:
    """Return absolute paths for the newest run's benchmark artifacts.

    Args:
        category: Report category directory (default: "benchmark").

    Returns:
        Dict with keys:
          run_dir (str | null)      — absolute path to the run directory
          results_json (str | null) — absolute path to results.json
          manifest_json (str | null)— absolute path to manifest.json
          report_html (str | null)  — absolute path to report.html or null
        All values are null when no run exists.
    """
    root = _reports_root()
    runs = _index_runs(category, root)
    if not runs:
        return {
            "run_dir": None,
            "results_json": None,
            "manifest_json": None,
            "report_html": None,
        }
    entry = runs[0]
    run_id = entry.get("run_id", "")
    run_dir = root / category / run_id
    results_p = run_dir / "results.json"
    manifest_p = run_dir / "manifest.json"
    return {
        "run_dir": str(run_dir.resolve()),
        "results_json": str(results_p.resolve()) if results_p.exists() else None,
        "manifest_json": str(manifest_p.resolve()) if manifest_p.exists() else None,
        "report_html": _find_html(run_dir),
    }


@mcp.tool()
def load_manifest(
    category: str = "benchmark", run_id: str | None = None
) -> dict | None:
    """Return the parsed manifest.json dict for a run.

    Includes the canonical headline stats:
      geomean_speedup_vs_baseline, max_abs_delta_r2,
      spectrafit_win_rate, regressions, regression_case_ids,
      baseline_solver_id, n_cases, date, schema_version, backends.

    Args:
        category: Report category (default: "benchmark").
        run_id: Specific run id (e.g. "2026-06-09_run_001"). Defaults to latest.

    Returns:
        Parsed manifest dict, or null if no run / manifest not found.
    """
    root = _reports_root()
    if run_id is None:
        runs = _index_runs(category, root)
        if not runs:
            return None
        run_id = runs[0].get("run_id", "")
    manifest_p = root / category / run_id / "manifest.json"
    if not manifest_p.exists():
        return None
    try:
        return json.loads(manifest_p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


@mcp.tool()
def find_report_html(
    category: str = "benchmark", run_id: str | None = None
) -> str | None:
    """Return the absolute path to the offline report bundle, or null.

    Args:
        category: Report category (default: "benchmark").
        run_id: Specific run id. Defaults to the latest run.

    Returns:
        Absolute path string to report.html (or index.html) if it exists,
        otherwise null.
    """
    root = _reports_root()
    if run_id is None:
        runs = _index_runs(category, root)
        if not runs:
            return None
        run_id = runs[0].get("run_id", "")
    run_dir = root / category / run_id
    return _find_html(run_dir)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
