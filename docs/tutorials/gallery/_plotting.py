"""Shared plotting convention for the ``docs/tutorials/gallery`` scripts.

This module is **gallery-internal tooling** — it is not part of the public
``spectrafit_core`` package and carries no API stability guarantee. It exists
so the sibling example scripts in this directory (``fitting.py``,
``3d_fitting.py``, ``multi_dataset_1d.py``, ``multi_dataset_2d.py``,
``shared_params.py``) share one visual language instead of each rolling its
own ad-hoc matplotlib calls.

Import it as a plain sibling module, e.g.::

    from _plotting import plot_fit, savefig

Dependency-light by design: matplotlib + numpy only (no seaborn, no
spectrafit_core import) so it stays trivially importable from any gallery
script.

Note on dimensionality: ``plot_fit`` only ever draws a 2-D (x, y) curve view.
For genuinely 3-D data (e.g. ``3d_fitting.py``), the caller is responsible
for first projecting or slicing down to a 2-D (x, y) representation (a
line-out, a marginal, a fixed-axis slice, ...) before calling ``plot_fit`` —
this helper does not do any 3-D plotting itself.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, cast

import matplotlib.pyplot as plt
import numpy as np

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure
    from numpy.typing import ArrayLike

# --------------------------------------------------------------------------
# Gallery-wide style
# --------------------------------------------------------------------------
# Folded in here (rather than a separate _style.py) to keep the gallery's
# dependency footprint to a single sibling import. Applied at import time so
# every script that does `from _plotting import plot_fit` picks it up for
# free, without an extra setup call.

FIGSIZE: tuple[float, float] = (7.0, 5.0)
"""Default figure size (inches) for a plot with no residuals subplot."""

FIGSIZE_WITH_RESIDUALS: tuple[float, float] = (7.0, 6.0)
"""Default figure size (inches) when a residuals subplot is added."""

SAVE_DPI: int = 150
"""Fixed DPI used by :func:`savefig` for all gallery PNGs."""

_DATA_COLOR = "#4C72B0"
_FIT_COLOR = "#C44E52"
_COMPONENT_COLORS = ("#55A868", "#8172B2", "#CCB974", "#64B5CD", "#DD8452")

_STATIC_DIR = Path(__file__).parent / "_static"

plt.rcParams.update(
    {
        "figure.dpi": 100,
        "savefig.dpi": SAVE_DPI,
        "font.size": 11,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.labelsize": 11,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "legend.frameon": False,
        "legend.fontsize": 9,
        "lines.linewidth": 1.8,
        "scatter.marker": "o",
    }
)


def _iter_components(
    components: Mapping[str, ArrayLike] | Iterable[tuple[str, ArrayLike]] | None,
) -> Iterable[tuple[str, ArrayLike]]:
    """Normalize the ``components`` argument to an iterable of (label, array).

    Accepts either a dict (``{"peak_1": y1, "peak_2": y2}``) or an iterable of
    ``(label, array)`` pairs — whichever reads more naturally at the call
    site (a dict is convenient when components come from a keyed structure
    like a fit graph's nodes; a list of pairs is convenient when order matters
    and labels are generated on the fly, e.g. ``[("peak", y1), ("bg", y2)]``).
    """
    if components is None:
        return []
    if isinstance(components, Mapping):
        return cast("list[tuple[str, ArrayLike]]", list(components.items()))
    return list(components)


def plot_fit(
    x: ArrayLike,
    y: ArrayLike,
    y_fit: ArrayLike,
    *,
    residuals: ArrayLike | None = None,
    components: Mapping[str, ArrayLike] | Iterable[tuple[str, ArrayLike]] | None = None,
    title: str | None = None,
    ax: Axes | None = None,
) -> tuple[Figure, Axes]:
    """Plot data + fitted curve (+ optional residuals, + optional components).

    Parameters
    ----------
    x, y : array-like
        The observed data, drawn as a semi-transparent scatter.
    y_fit : array-like
        The fitted curve, drawn as a solid line on top of the data.
    residuals : array-like, optional
        If given, a residuals subplot is added below the main plot (shared
        x-axis), with a dashed zero line. Ignored (with no error) if ``ax``
        is given — see below.
    components : mapping or iterable of (label, array), optional
        Individual model components (e.g. per-peak contributions) overlaid
        as dashed lines, each with its own legend entry. Accepts either a
        ``dict`` or a list of ``(label, array)`` pairs.
    title : str, optional
        Main axes title.
    ax : matplotlib Axes, optional
        If given, plot into this axes and return it as-is — no residuals
        subplot is created in this case, since the caller already owns the
        figure layout and is expected to place/size a residuals axes itself
        if it wants one. If ``None`` (the default), a new figure is created
        via ``plt.subplots`` (sized from :data:`FIGSIZE` /
        :data:`FIGSIZE_WITH_RESIDUALS`, adding a residuals row when
        ``residuals`` is given).

    Returns:
    -------
    (fig, ax) : tuple[Figure, Axes]
        The figure and the *main* axes (not the residuals axes). When ``ax``
        was passed in, ``fig`` is ``ax.get_figure()`` — the return shape is
        always a 2-tuple regardless of whether a new figure was created, so
        callers do not need to special-case ``ax is None``.

    Notes:
    -----
    This function only ever draws a 2-D (x, y) view. For 3-D data, project or
    slice to 2-D before calling this — see the module docstring.
    """
    x = np.asarray(x)
    y = np.asarray(y)
    y_fit = np.asarray(y_fit)

    if ax is not None:
        _draw_main(ax, x, y, y_fit, components=components, title=title)
        # `Axes.get_figure()` is typed as `Figure | SubFigure | None`; in
        # practice an axes we were handed always has a real parent Figure.
        return cast("Figure", ax.get_figure()), ax

    if residuals is not None:
        fig, (ax_main, ax_res) = plt.subplots(
            2,
            1,
            figsize=FIGSIZE_WITH_RESIDUALS,
            sharex=True,
            gridspec_kw={"height_ratios": [3, 1], "hspace": 0.08},
        )
        _draw_main(ax_main, x, y, y_fit, components=components, title=title)
        _draw_residuals(ax_res, x, residuals)
        ax_main.set_xlabel("")  # xlabel lives on the shared bottom axes
        return fig, ax_main

    fig, ax_main = plt.subplots(figsize=FIGSIZE)
    _draw_main(ax_main, x, y, y_fit, components=components, title=title)
    return fig, ax_main


def _draw_main(
    ax: Axes,
    x: np.ndarray,
    y: np.ndarray,
    y_fit: np.ndarray,
    *,
    components: Mapping[str, ArrayLike] | Iterable[tuple[str, ArrayLike]] | None,
    title: str | None,
) -> None:
    ax.scatter(x, y, s=18, alpha=0.45, color=_DATA_COLOR, label="data", zorder=2)
    ax.plot(x, y_fit, color=_FIT_COLOR, linestyle="-", label="fit", zorder=3)

    for i, (label, comp) in enumerate(_iter_components(components)):
        color = _COMPONENT_COLORS[i % len(_COMPONENT_COLORS)]
        ax.plot(
            x,
            np.asarray(comp),
            color=color,
            linestyle="--",
            linewidth=1.4,
            label=label,
            zorder=1,
        )

    if title:
        ax.set_title(title)
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.legend(loc="best")


def _draw_residuals(ax: Axes, x: np.ndarray, residuals: ArrayLike) -> None:
    residuals = np.asarray(residuals)
    ax.axhline(0.0, color="0.4", linestyle="--", linewidth=1.0, zorder=1)
    ax.scatter(x, residuals, s=14, alpha=0.55, color=_DATA_COLOR, zorder=2)
    ax.set_xlabel("x")
    ax.set_ylabel("residuals")


def savefig(fig: Figure, name: str, *, static_dir: Path | str | None = None) -> Path:
    """Save ``fig`` as ``<static_dir>/<name>.png`` at the fixed gallery DPI.

    Parameters
    ----------
    fig : matplotlib Figure
        The figure to save (e.g. the one returned by :func:`plot_fit`).
    name : str
        File stem (no extension, no path separators) — the PNG is written
        to ``<static_dir>/<name>.png``.
    static_dir : Path or str, optional
        Destination directory. Defaults to
        ``docs/tutorials/gallery/_static`` (created if it does not exist).

    Returns:
    -------
    Path
        The full path the figure was written to.
    """
    out_dir = Path(static_dir) if static_dir is not None else _STATIC_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{name}.png"
    fig.savefig(out_path, dpi=SAVE_DPI, bbox_inches="tight")
    return out_path
