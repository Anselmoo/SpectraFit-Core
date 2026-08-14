"""Figure: the spectrafit-core Rust/Python architecture and its PyO3 boundary.

Draws the two-language system as a layered graph: the Python surface and its
Pydantic mirror on top, the PyO3 wheel boundary in the middle, and the eleven-
crate Rust workspace beneath, laid out by real dependency depth.

Reproduce from a clean clone:

    uv sync --group manuscript
    uv run --group manuscript python manuscript/examples/fecl4/fig_architecture.py

Outputs (written next to this file):
    fig_architecture.pdf   vector, for submission
    fig_architecture.png   300 dpi raster, for preview

The crate layering is not hand-asserted. It is the transitive dependency depth
read out of the eleven `crates/*/Cargo.toml` manifests:

    spectrafit-types        -> (none)
    spectrafit-models       -> types
    spectrafit-trust-region -> types
    spectrafit-graph        -> models, types
    spectrafit-dogleg       -> trust-region
    spectrafit-newton-cg    -> trust-region
    spectrafit-levenberg-marquardt -> trust-region
    spectrafit-varpro       -> graph, models, types
    spectrafit-builder      -> models, types
    spectrafit-solver       -> dogleg, graph, levenberg-marquardt, newton-cg,
                               types, varpro
    spectrafit-core         -> graph, solver, types

`spectrafit-builder` is drawn off to the side on purpose: nothing on the runtime
path depends on it. It is a compile-time exhaustiveness gate, so a new model
variant that is not handled everywhere fails to build rather than failing at
run time.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
from matplotlib import pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = Path(__file__).resolve().parent

# Same validated categorical palette as the case-study figure (dataviz
# six-checks, light surface: all PASS). Layers are filled with a heavy tint of
# their hue and outlined in the hue itself, so the diagram stays legible in
# grayscale and under colour-vision deficiency, where the layer *order* rather
# than the hue carries the meaning.
# Corporate tokens (docs/stylesheets/tokens/palette.css). Unlike the data
# figures, these hues label spatially separated, permanently-labelled boxes
# rather than overlapping series, so the CVD adjacency constraint that limits
# the charts to two hues does not bite here — every box carries its own text.
C_PY = "#0064d2"  # systemBlue-text — Python surface
C_BOUND = "#d30f45"  # systemPink-text — the PyO3 boundary, the emphasised band
C_SOLVE = "#217e38"  # systemGreen-text — solver crates
C_FOUND = "#5856d6"  # systemIndigo — shared foundation crates
INK = "#1d1d1f"
INK_MUTED = "#6e6e73"
SURFACE = "#ffffff"


def tint(hex_colour: str, amount: float) -> tuple[float, float, float]:
    """Blend `hex_colour` toward white; `amount` is the fraction of colour kept."""
    r, g, b = (int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5))
    blend = 1.0 - amount
    return (r * amount + blend, g * amount + blend, b * amount + blend)


def box(
    ax,
    x: float,
    y: float,
    w: float,
    h: float,
    colour: str,
    *,
    fill: float = 0.12,
    lw: float = 1.1,
    ls: str | tuple[int, tuple[int, ...]] = "-",
    radius: float = 0.9,
):
    """Draw a rounded, tinted layer box and return the patch."""
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        linewidth=lw,
        linestyle=ls,
        edgecolor=colour,
        facecolor=tint(colour, fill),
        zorder=2,
    )
    ax.add_patch(patch)
    return patch


def label(
    ax,
    x: float,
    y: float,
    text: str,
    *,
    size: float = 8,
    weight: str = "normal",
    colour: str = INK,
    ha: str = "center",
    va: str = "center",
    style: str = "normal",
    family: str | None = None,
):
    """Place a text label; text always wears ink colours, never a series hue."""
    ax.text(
        x,
        y,
        text,
        ha=ha,
        va=va,
        fontsize=size,
        fontweight=weight,
        color=colour,
        style=style,
        zorder=4,
        family=family or mpl.rcParams["font.family"],
    )


def arrow(
    ax,
    xy_from: tuple[float, float],
    xy_to: tuple[float, float],
    # `tint()` returns an RGB triple, so this accepts both spellings matplotlib
    # does rather than forcing every tinted call site through a hex conversion.
    colour: str | tuple[float, float, float] = INK_MUTED,
    *,
    lw: float = 1.0,
    style: str = "-|>",
    ls: str = "-",
):
    """Draw a dependency arrow from `xy_from` to `xy_to`."""
    ax.add_patch(
        FancyArrowPatch(
            xy_from,
            xy_to,
            arrowstyle=style,
            mutation_scale=9,
            linewidth=lw,
            linestyle=ls,
            color=colour,
            shrinkA=0,
            shrinkB=0,
            zorder=3,
        ),
    )


def draw() -> None:
    """Render the architecture figure to PDF and 300 dpi PNG."""
    mpl.rcParams.update(
        {
            "font.size": 8,
            "figure.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "font.family": "sans-serif",
        },
    )
    fig, ax = plt.subplots(figsize=(7.0, 5.25))
    ax.set_xlim(0, 100)
    ax.set_ylim(-8, 100)
    ax.axis("off")

    mono = {"family": "monospace"}

    # ---------------------------------------------------------------- Python
    box(ax, 4, 84.5, 92, 12.5, C_PY)
    label(ax, 50, 94.0, "Python surface", size=9, weight="bold", colour=C_PY)
    label(ax, 27, 89.6, "compose()   MeasurementData   fit() / fit_fast()", size=7.6, **mono)
    label(
        ax,
        27,
        86.4,
        "user-facing model-construction API",
        size=7,
        colour=INK_MUTED,
        style="italic",
    )
    ax.plot([50, 50], [85.6, 92.2], lw=0.6, color=tint(C_PY, 0.55), zorder=3)
    label(ax, 74, 89.6, "FitGraph   FitOptions   FitResult", size=7.6, **mono)
    label(
        ax,
        74,
        86.4,
        "Pydantic schema mirror — validated at the boundary",
        size=7,
        colour=INK_MUTED,
        style="italic",
    )

    # -------------------------------------------------------------- boundary
    box(ax, 4, 68.0, 92, 11.0, C_BOUND, fill=0.16, lw=1.5)
    label(ax, 50, 76.2, "PyO3 wheel boundary", size=9, weight="bold", colour=C_BOUND)
    label(
        ax,
        50,
        72.6,
        "every  #[pyfunction]  crosses as a JSON string — no shared memory layout",
        size=7.6,
        **mono,
    )
    label(
        ax,
        50,
        69.7,
        "Python↔Rust schema parity enforced at commit time, not at run time",
        size=7,
        colour=INK_MUTED,
        style="italic",
    )

    # Both boundary arrows terminate on the box's TOP edge (y = 79.2), never on
    # its bottom: the pair describes the Python<->boundary hop only. Drawing the
    # result arrow from y = 67.8 (the box's bottom) made it run the full height
    # of the box and strike through its own label text. The boundary<->Rust hop
    # is the separate grey pair below.
    arrow(ax, (30, 84.3), (30, 79.2), C_BOUND, lw=1.3)
    label(ax, 32.2, 81.7, "request JSON", size=6.8, colour=C_BOUND, ha="left")
    arrow(ax, (70, 79.2), (70, 84.3), C_BOUND, lw=1.3)
    label(ax, 67.8, 81.7, "result JSON", size=6.8, colour=C_BOUND, ha="right")

    # ------------------------------------------------------------ Rust core
    box(ax, 4, 3.0, 92, 60.0, INK_MUTED, fill=0.04, lw=0.8, ls=(0, (4, 3)))
    # White bbox so the request-JSON connector reads as passing *behind* the
    # label rather than striking through it.
    ax.text(
        6.5,
        60.4,
        "Rust workspace — 11 crates",
        size=8.4,
        fontweight="bold",
        color=INK_MUTED,
        ha="left",
        va="center",
        zorder=5,
        bbox={"facecolor": SURFACE, "edgecolor": "none", "pad": 2.5},
    )
    label(
        ax,
        91,
        4.6,
        "arrows show dependency direction; only the spine is drawn",
        size=6.4,
        colour=INK_MUTED,
        style="italic",
        ha="right",
    )

    # binding crate
    box(ax, 9, 50.0, 82, 7.4, C_BOUND, fill=0.08)
    label(ax, 50, 55.3, "spectrafit-core", size=8.2, weight="bold", **mono)
    label(
        ax,
        50,
        52.1,
        "PyO3 binding crate — serialises requests and results",
        size=7,
        colour=INK_MUTED,
        style="italic",
    )
    arrow(ax, (30, 67.8), (30, 57.6))
    arrow(ax, (70, 57.6), (70, 67.8))

    # dispatch
    box(ax, 9, 39.8, 82, 7.4, C_SOLVE)
    label(ax, 50, 45.1, "spectrafit-solver", size=8.2, weight="bold", **mono)
    label(
        ax,
        50,
        41.9,
        "structure-routed dispatch — picks the solver family from problem structure",
        size=7,
        colour=INK_MUTED,
        style="italic",
    )
    arrow(ax, (50, 49.8), (50, 47.4))

    # Solver families. The first three delegate to the shared trust-region core;
    # varpro does not — it sits on graph + models instead, which is why it is
    # drawn apart from the trust-region-backed group rather than beside it.
    # No sub-labels here: unlike varpro, these three need no note to explain
    # what they sit on — the shared trust-region box directly beneath them says
    # it. So this is a flat list of names, not (name, note) pairs.
    tr_group = ["levenberg-\nmarquardt", "dogleg", "newton-cg"]
    fw, gap, gx0 = 15.0, 2.0, 9.0
    for i, name in enumerate(tr_group):
        fx = gx0 + i * (fw + gap)
        box(ax, fx, 28.0, fw, 8.2, C_SOLVE, fill=0.08)
        label(ax, fx + fw / 2, 32.1, name, size=7.2, **mono)
        arrow(ax, (fx + fw / 2, 39.6), (fx + fw / 2, 36.4), tint(C_SOLVE, 0.75), lw=0.9)
        arrow(ax, (fx + fw / 2, 27.8), (fx + fw / 2, 25.4), tint(C_SOLVE, 0.75), lw=0.9)

    box(ax, 63, 28.0, 28, 8.2, C_SOLVE, fill=0.08)
    label(ax, 77, 33.0, "varpro", size=7.4, **mono)
    label(ax, 77, 29.9, "separable NLS", size=6.5, colour=INK_MUTED, style="italic")
    arrow(ax, (77, 39.6), (77, 36.4), tint(C_SOLVE, 0.75), lw=0.9)

    # shared trust-region core, under the three families that use it
    box(ax, 9, 17.8, 49.0, 7.4, C_SOLVE, fill=0.14)
    label(ax, 33.5, 22.9, "spectrafit-trust-region", size=7.6, **mono)
    label(
        ax,
        33.5,
        19.8,
        "faer-native trust-region core",
        size=6.5,
        colour=INK_MUTED,
        style="italic",
    )

    # foundation crates
    box(ax, 63, 17.8, 28, 7.4, C_FOUND)
    label(ax, 77, 22.9, "graph · models", size=7.4, **mono)
    label(ax, 77, 19.8, "fit graph · 32 kernels", size=6.5, colour=INK_MUTED, style="italic")
    arrow(ax, (77, 27.8), (77, 25.4), tint(C_FOUND, 0.75), lw=0.9)

    box(ax, 9, 6.2, 82, 7.4, C_FOUND, fill=0.18)
    label(ax, 50, 11.3, "spectrafit-types", size=7.6, weight="bold", **mono)
    label(
        ax,
        50,
        8.2,
        "shared type foundation — the one crate every other crate depends on",
        size=6.6,
        colour=INK_MUTED,
        style="italic",
    )
    arrow(ax, (33.5, 17.6), (33.5, 13.8), tint(C_FOUND, 0.75), lw=0.9)
    arrow(ax, (77, 17.6), (77, 13.8), tint(C_FOUND, 0.75), lw=0.9)

    # builder — nothing on the runtime path depends on it, so it is drawn
    # detached below the workspace rather than wired into the spine.
    box(ax, 9, -6.6, 82, 5.4, INK_MUTED, fill=0.06, lw=0.9, ls=(0, (3, 2)))
    label(
        ax,
        50,
        -3.9,
        "spectrafit-builder — compile-time exhaustiveness gate; "
        "an unhandled model variant fails to build, not at run time",
        size=6.6,
        colour=INK_MUTED,
        style="italic",
    )

    fig.subplots_adjust(left=0.005, right=0.995, top=0.995, bottom=0.005)
    for ext, dpi in (("pdf", None), ("png", 300)):
        fig.savefig(HERE / f"fig_architecture.{ext}", dpi=dpi)
    plt.close(fig)
    print("wrote fig_architecture.pdf / .png")


if __name__ == "__main__":
    draw()
