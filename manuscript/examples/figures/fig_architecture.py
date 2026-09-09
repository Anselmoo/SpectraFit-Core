"""Figure: the spectrafit-core Rust/Python architecture and its PyO3 boundary.

Draws the two-language system as a layered graph: the Python surface and its
Pydantic mirror on top, the PyO3 wheel boundary in the middle, and the eleven-
crate Rust workspace beneath, laid out by real dependency depth.

Reproduce from a clean clone:

    uv sync --group manuscript
    uv run --group manuscript python manuscript/examples/figures/fig_architecture.py

Outputs (written next to this file):
    fig_architecture.pdf   vector, for submission
    fig_architecture.png   300 dpi raster, for preview

Every count that appears on the canvas is read at render time, not typed in:
the crate count and the dependency-edge tally come from `crates/*/Cargo.toml`,
and the kernel count from the `model_manifest!` block in
`crates/spectrafit-types/src/types.rs`. An earlier version transcribed
"32 kernels" and it went stale — the manifest now carries 37 — which is the
reason none of these digits is a literal any more.

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

Only part of that dependency graph is drawn, and the omission is priced on the
canvas rather than left to the reader. The 21 edges in the manifests reduce
transitively to 13; drawing all 21 adds eight arrows that reach a crate the
spine already reaches — `spectrafit-core` to `spectrafit-types` runs the full
height of the workspace past four boxes it has nothing to do with — so the
figure draws the reduction. Of those 13, `graph -> models` is collapsed inside
the merged `graph · models` node and `builder -> models` is the deliberate
detachment, leaving the 11 arrows on the canvas. The line at the foot of the
workspace states all three numbers, computed from the manifests each run.

Variable projection is labelled as adopted, not implemented here: its crate
wraps the third-party `varpro` crate, which links LAPACK (Apple Accelerate on
macOS, Netlib elsewhere). Without that word the four family boxes read as four
things this project wrote, and one of them is not. The other third-party edges
— `faer` under every trust-region family, `nalgebra`, `pyo3` — are not drawn,
because every crate in the workspace has one and a mark carried by every box
carries nothing. The `lm-legacy` parity oracle is likewise absent: it is a
solver string inside `spectrafit-solver`, not a crate, so it has no box in this
figure's vocabulary and belongs to the dispatch discussion instead.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import matplotlib as mpl
from matplotlib import pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

# Pinned as in the other figure scripts: the render manifest hashes the PNG
# byte-for-byte, and an interactive backend can resolve fonts differently.
mpl.use("Agg")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
CRATES = REPO / "crates"
TYPES_RS = CRATES / "spectrafit-types" / "src" / "types.rs"

# Same validated categorical palette as the case-study figure (dataviz
# six-checks, light surface: all PASS). Layers are filled with a heavy tint of
# their hue and outlined in the hue itself, so the diagram stays legible in
# grayscale and under colour-vision deficiency, where the layer *order* rather
# than the hue carries the meaning.
# Corporate tokens (docs/stylesheets/tokens/palette.css). Unlike the data
# figures, these hues label spatially separated, permanently-labelled boxes
# rather than overlapping series, so the CVD adjacency constraint that limits
# the charts to two hues does not bite here — every box carries its own text.
#
# Hue is a local key in this paper, never a global one, so each of these four
# declines a meaning the same hex carries in another figure. What makes the
# decline safe is that no box here is a data series: every one wears a
# permanent text label, and in greyscale the layer *order* still reads.
#   #0064d2 is `--c-spectrafit-text`, this project's own brand hue, and is the
#     multiplet peak component in fig_model_graph.py. Declined: here it names
#     the Python surface layer, and this figure plots no measurement at all, so
#     no reader can mistake the band for a series.
#     It also has a near-twin, #0067d6 (`--c-chart-1`), which the paper's timing
#     figures now spend on jax. The two hexes are indistinguishable at 300 dpi,
#     so in print there is effectively one blue carrying "Python surface" here
#     and "jax" there. That is tolerable only because neither is a series in the
#     other's figure and both are permanently labelled — but it is the reason
#     this figure must never gain a second blue, and the reason a reader
#     comparing figures should read the label rather than the hue.
#   #d30f45 is the reserved attention channel. It is spent once, on one
#     referent — the PyO3 boundary — and reappears on `spectrafit-core` only
#     because that crate *is* the boundary's Rust half.
#   #217e38 is `--c-lmfit-text`, the comparator's brand hue in the benchmark
#     figures. Declined: no comparator appears in this figure, and the solver
#     crates are the one group that has to read as a family.
#   #5856d6 is `--c-scipy-ls-trf` and is fig_ladder_stability.py's seed-sweep
#     axis. Declined for the same reason: neither a backend nor an axis is on
#     this canvas.
C_PY = "#0064d2"  # systemBlue-text — Python surface
C_BOUND = "#d30f45"  # systemPink-text — the PyO3 boundary, the emphasised band
C_SOLVE = "#217e38"  # systemGreen-text — solver crates
C_FOUND = "#5856d6"  # systemIndigo — shared foundation crates
INK = "#1d1d1f"
INK_MUTED = "#6e6e73"
SURFACE = "#ffffff"


def workspace_edges() -> dict[str, frozenset[str]]:
    """Read the intra-workspace dependency graph out of the crate manifests.

    Returns crate name -> its `spectrafit-*` dependencies. Iteration is over a
    sorted glob and the values are frozensets consumed in sorted order, so the
    counts printed on the canvas cannot depend on filesystem order.
    """
    manifests = sorted(CRATES.glob("*/Cargo.toml"))
    if not manifests:
        msg = (
            f"no crate manifests under {CRATES} — the crate layering, the edge "
            "tally and the crate count on the canvas are all read from them, "
            "so the workspace half of the figure cannot be drawn. Run this "
            "script from inside a checkout of the repository."
        )
        raise SystemExit(msg)
    graph = {}
    for path in manifests:
        deps = tomllib.loads(path.read_text(encoding="utf-8")).get("dependencies", {})
        graph[path.parent.name] = frozenset(d for d in deps if d.startswith("spectrafit-"))
    return graph


def transitive_reduction(graph: dict[str, frozenset[str]]) -> set[tuple[str, str]]:
    """Drop every edge that a longer path in `graph` already provides.

    The workspace is a DAG, so an edge `a -> b` is redundant exactly when some
    other dependency of `a` also reaches `b`. That is the set the figure draws:
    the arrows that carry information a reader cannot infer.
    """

    def reach(node: str, seen: set[str]) -> set[str]:
        for dep in sorted(graph.get(node, ())):
            if dep not in seen:
                seen.add(dep)
                reach(dep, seen)
        return seen

    kept = set()
    for node in sorted(graph):
        deps = sorted(graph[node])
        for dep in deps:
            others: set[str] = set()
            for sibling in deps:
                if sibling != dep:
                    reach(sibling, others)
            if dep not in others:
                kept.add((node, dep))
    return kept


def kernel_count() -> int:
    """Count the model kernels registered in the `model_manifest!` macro block."""
    if not TYPES_RS.exists():
        msg = (
            f"{TYPES_RS} is missing — the kernel count printed under "
            "`graph · models` is read from its `model_manifest!` block, and an "
            "authored number there is exactly the literal that went stale once "
            "already. Run this script from inside a checkout of the repository."
        )
        raise SystemExit(msg)
    text = TYPES_RS.read_text(encoding="utf-8")
    start = text.find("\nmodel_manifest! {")
    end = text.find("\n}", start + 1)
    variants = re.findall(r'^\s+\w+\s*=>\s*"[a-z0-9_]+"', text[start:end], re.MULTILINE)
    if start < 0 or not variants:
        msg = (
            f"found no `model_manifest!` variants in {TYPES_RS} — the macro was "
            "renamed or restructured, and the kernel count cannot be derived. "
            "Fix the parse rather than typing the number back in."
        )
        raise SystemExit(msg)
    return len(variants)


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
    graph = workspace_edges()
    n_crates = len(graph)
    n_edges = sum(len(deps) for deps in graph.values())
    reduced = transitive_reduction(graph)
    n_detached = sum(src == "spectrafit-builder" for src, _ in reduced)
    n_collapsed = ("spectrafit-graph", "spectrafit-models") in reduced
    n_drawn = len(reduced) - n_detached - n_collapsed
    n_kernels = kernel_count()

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
    # Two units lower than the content needs, to seat the two-line edge tally
    # below `spectrafit-types` without crowding it.
    box(ax, 4, 1.0, 92, 62.0, INK_MUTED, fill=0.04, lw=0.8, ls=(0, (4, 3)))
    # White bbox so the request-JSON connector reads as passing *behind* the
    # label rather than striking through it.
    ax.text(
        6.5,
        60.4,
        f"Rust workspace — {n_crates} crates",
        size=8.4,
        fontweight="bold",
        color=INK_MUTED,
        ha="left",
        va="center",
        zorder=5,
        bbox={"facecolor": SURFACE, "edgecolor": "none", "pad": 2.5},
    )
    # Hiding two thirds of the edges buys the whole layout, so the price is
    # paid here in derived numbers rather than in the caption.
    label(
        ax,
        91,
        5.0,
        f"arrows show dependency direction; the {n_edges} manifest edges "
        f"reduce transitively to {len(reduced)}",
        size=6.4,
        colour=INK_MUTED,
        style="italic",
        ha="right",
    )
    label(
        ax,
        91,
        2.6,
        f"{n_drawn} of those are drawn — graph → models is collapsed into one "
        "node, and builder is detached",
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
        "the caller names a solver family, or asks for auto to derive it from the graph",
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
    # The only family box that is not this project's own code. Without the
    # word, four boxes in one hue read as four things written here.
    label(
        ax,
        77,
        29.9,
        "separable NLS · third-party varpro",
        size=5.9,
        colour=INK_MUTED,
        style="italic",
    )
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
    label(
        ax,
        77,
        19.8,
        f"fit graph · {n_kernels} kernels",
        size=6.5,
        colour=INK_MUTED,
        style="italic",
    )
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
    print(f"  crates in the workspace      : {n_crates}")
    print(f"  dependency edges in manifests: {n_edges}")
    print(f"  after transitive reduction   : {len(reduced)}")
    print(f"  collapsed into graph · models: {int(n_collapsed)}")
    print(f"  detached (builder)           : {n_detached}")
    print(f"  arrows drawn                 : {n_drawn}")
    print(f"  model kernels in manifest    : {n_kernels}")


if __name__ == "__main__":
    draw()
