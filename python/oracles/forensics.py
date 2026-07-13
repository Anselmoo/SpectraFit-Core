"""Forensic snapshots for regressed bench cases (Cycle 11).

When `spc-bench gate` flags cases via `regression_case_ids`, this module
re-runs each one (single rep, single MC) against every supported backend
and writes a matplotlib PNG per case showing:

  - The observed spectrum (`case.x` vs `case.y`)
  - Each backend's fit curve (line)
  - Each backend's residual (subplot below)

The output lands at `.spectrafit_reports/<run_id>/forensics/<case_id>.png`.

Matplotlib is a benchmark-extra dep; importing this module without matplotlib
installed raises a clean ImportError with a hint.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from oracles.backends import Backend

from oracles.cases import BenchCase, build_specs, materialize

_LOG = logging.getLogger("oracles.forensics")


def render_case(
    case_id: str,
    case: BenchCase,
    backends_list: Sequence[Backend],
    out_path: Path,
) -> Path:
    """Fit `case` with each backend, write a 2-row PNG to `out_path`."""
    try:
        import matplotlib.gridspec as gridspec
        import matplotlib.pyplot as plt
    except ImportError as e:
        raise ImportError(
            "matplotlib is required for forensics; install via `uv sync --extra benchmark`"
        ) from e

    # Fit each backend
    fits_by_backend: dict[str, tuple[list[float], list[float]]] = {}
    for backend in backends_list:
        if not backend.is_supported(case):
            continue
        try:
            outcome = backend.fit(case, n_reps=1)
            if outcome and outcome.success:
                residuals = [float(y - f) for y, f in zip(case.y, outcome.best_fit)]
                fits_by_backend[backend.name] = (
                    list(outcome.best_fit),
                    residuals,
                )
        except Exception as exc:  # noqa: BLE001
            _LOG.debug("backend %s failed on case %s: %r", backend.name, case_id, exc)

    # Create figure with two rows (fit + residuals)
    fig = plt.figure(figsize=(11, 6))
    gs = gridspec.GridSpec(2, 1, figure=fig, height_ratios=[3, 1], hspace=0.35)
    ax_fit = fig.add_subplot(gs[0])
    ax_resid = fig.add_subplot(gs[1], sharex=ax_fit)

    # Top row: observed spectrum (markers) + each backend's fit (lines)
    x = case.x
    y = case.y
    ax_fit.plot(x, y, "o", markersize=4, label="observed", alpha=0.6, color="black")

    colors = [
        "tab:blue",
        "tab:orange",
        "tab:green",
        "tab:red",
        "tab:purple",
        "tab:brown",
    ]
    for (backend_name, (fit_curve, _)), color in zip(
        fits_by_backend.items(), colors[: len(fits_by_backend)]
    ):
        ax_fit.plot(x, fit_curve, "-", label=backend_name, linewidth=1.5, color=color)

    ax_fit.set_ylabel("Intensity")
    ax_fit.legend(loc="best", fontsize=8)
    ax_fit.grid(True, alpha=0.3)
    title = f"{case_id} · {case.category}"
    if hasattr(case, "difficulty") and case.difficulty is not None:
        title += f" · diff={case.difficulty:.2f}"
    ax_fit.set_title(title, fontsize=10)

    # Bottom row: residuals for each backend
    for (backend_name, (_, residuals)), color in zip(
        fits_by_backend.items(), colors[: len(fits_by_backend)]
    ):
        ax_resid.plot(x, residuals, "-", label=backend_name, linewidth=1, color=color)

    ax_resid.axhline(0, color="black", linestyle="--", linewidth=0.5, alpha=0.5)
    ax_resid.set_xlabel("X")
    ax_resid.set_ylabel("Residual")
    ax_resid.grid(True, alpha=0.3)

    # Save PNG
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return out_path


def render_regressions(
    run_dir: Path,
    backends: Sequence[Backend] | None = None,
) -> list[Path]:
    """Top-level entry: read manifest, fit each regression_case_id, write PNGs.

    Parameters
    ----------
    run_dir:
        Directory containing ``manifest.json`` for the benchmark run.
    backends:
        Backends to use for fitting. When *None* (the default), the full
        set of available backends is resolved at call time via
        ``oracles.backends.get_backends()``.  Callers that already have a
        backends list (e.g. ``spc-bench forensics`` in the CLI) should pass
        it explicitly so that this module carries **no runtime import** from
        ``benchmark``.
    """
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        _LOG.warning("manifest not found at %s", manifest_path)
        return []

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    regression_case_ids = manifest.get("regression_case_ids") or []

    if not regression_case_ids:
        _LOG.info("no regressions to render in run %s", run_dir.name)
        return []

    # Build the case catalog
    specs = build_specs()
    cases_by_id = {s.id: materialize(s) for s in specs}

    # Resolve backends lazily only when not injected by the caller.
    # The local import keeps the runtime dependency inside benchmark/ and out
    # of the module-level namespace of oracles.forensics.
    if backends is None:
        from oracles.backends import get_backends  # local import — not module-level

        backends = get_backends()

    # Render each regressed case
    forensics_dir = run_dir / "forensics"
    paths_written: list[Path] = []

    for case_id in regression_case_ids:
        if case_id not in cases_by_id:
            _LOG.warning("case %s not found in catalog", case_id)
            continue

        case = cases_by_id[case_id]
        out_path = forensics_dir / f"{case_id}.png"

        try:
            render_case(case_id, case, backends, out_path)
            paths_written.append(out_path)
            _LOG.info("rendered %s → %s", case_id, out_path)
        except Exception as exc:  # noqa: BLE001
            _LOG.error("failed to render %s: %r", case_id, exc)

    return paths_written
