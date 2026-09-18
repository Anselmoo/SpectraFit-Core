"""Figure: a declaration ledger — the model an analyst writes, and the numbers it leaves free.

The manuscript's central abstraction is that a model is a graph of named
components whose relationships are stated as expression edges, and that an
expression edge *removes a free parameter*. The paper described that in prose.
Three separate readers reported that they understood the words and could not
picture the thing. Earlier versions of this figure drew boxes near boxes and did
not fix it, because a box beside a box shows adjacency and the claim is about
subtraction. This draws the subtraction.

Reproduce from a clean clone:

    uv run --group manuscript python manuscript/examples/figures/fig_model_graph.py

Outputs (written next to this file):
    fig_model_graph.pdf   vector, for submission
    fig_model_graph.png   300 dpi raster, for preview

The composition: two registers holding different kinds of thing
---------------------------------------------------------------
The canvas splits in two, and the split is a split of *kind*, not of scale —
which is why a hairline divider separates them rather than whitespace alone.

**Left, what the analyst declares.** The component graph: the peak nodes (with
one ellipsis standing for a contiguous run of them), the two `arctan_step`
nodes, the `constant` background, and below them the expression edges. Each node
lists the parameter *names* it declares, and each group heading gives the kernel
and the count, so the three component counts add back to the total in the
subtitle. The expression edges sit in the same register because an expression is
something the analyst declares too.

**Right, what the fit is left to determine.** One cell per declared parameter,
enumerated by owning component in node order, so every component's parameters
form a contiguous run and the run lengths read off the page as 4, 4, ..., 3, 3,
1. Each run is tinted with its component's hue and captioned with its node name,
which carries the mapping from the left register without a leader line per node.
The grid's *shape* is a function of the parameter dictionary: add a peak upstream
and the grid grows four cells with nobody editing this file.

**The expression edges are the only objects that cross the divider,** and each
terminates on the single cell it removes. Those cells are the only ones drawn
unfilled and dashed — the mark that matters is the one mark that is not filled.
That is the whole argument: "an expression edge removes a free parameter" stops
being a sentence and becomes a struck cell with an arrow in it. The three-step
ledger beneath the grid then states the same fact as arithmetic, read from the
scenarios artifact rather than typed: 43 free, then 42, then 41.

This figure is the structural key to the constraint grid
--------------------------------------------------------
The two figures divide one subject. Here is what each hypothesis *is*: which
parameter it sets, from which expression, and which scenario first applies it.
There, in `fig_constraint_grid.py`, is what each hypothesis *costs*: the same
three scenarios refitted, with the residual under each panel. Neither repeats the
other, and neither owns the constraint. The definition lives once in
`fecl4_constraint_scenarios.py`, which serialises it into the sidecar this figure
reads.

What is authored and what is derived
------------------------------------
The layout is authored, like `fig_architecture.py`. Nothing else is. Component
names, the parameter names each component declares, every count, the grid's row
and run structure and the free-parameter ledger all come from the two sidecars.
The arrowhead is derived from each tie's own `target`, so an edge always lands on
the node the expression actually sets: an earlier version hard-coded `p7`, which
is the d5 spectrum's L2 white line but not d6's — it was correct by coincidence,
and encoded one spectrum's indices as though they were the model's.

Four things are authored prose rather than data, and are marked as such where
they appear: the kernel names in the group headings (`pseudo_voigt`,
`arctan_step`, `constant`), the plain-language gloss of the physics each tie
encodes, the register captions, and every coordinate.

A graph is a graph, and a plot is a plot
----------------------------------------
This figure reads names and counts and never a fitted value. That is one rule,
and it settles a question earlier versions kept re-opening.

Those versions printed each peak's fitted centre — "centre 706.4 eV" — under its
node, and that one decision dragged in four separate problems. It made the figure
a report of a particular solve, so the edges drawn (scenario C's) and the values
printed (the case study's, which applies the 2:1 tie and *not* the spin-orbit
tie) came from different fits: under the committed one,
`p1.center + step_l2.center - step_l3.center` evaluates to 718.2 eV against the
721.6 eV actually returned for p7, so a reader who checked the arithmetic on the
figure's own terms would find it did not close. It forced a special case for p8,
whose amplitude the solver drove to 3.0e-09 — its own floor — leaving a centre
with a 1.2e+08 eV standard error that no honest label could state. It needed a
guard to refuse any node undetermined for some *other* reason. And it still
showed only one of the four parameters a peak declares, which is the thing a
reader most needs to see.

Printing the declared parameter names instead answers all four at once. The
arithmetic cannot fail to close because none is offered. p8 needs no special
case, because a declared component declares its parameters whatever the solver
later does with them. The guard disappears. And each box now shows what a
component *is* — a named thing with named parameters — which makes the edge
formulae legible: an edge reads `step_l3.amplitude`, and `amplitude` is visibly
one of the things `step_l3` has.

One guard survives that change and is the one that matters now: the ellipsis
stands behind one shared parameter list, so if two peaks ever declared different
parameters that list would be false, and that is checked.

*Some peaks sit behind one ellipsis, and the ellipsis says how many.* Drawing
all nine costs the row its legibility and adds nothing: the argument needs the L3
white line (p1, the source of the spin-orbit expression) and the L2 white line
(p7, its target), plus one neighbour each for context. The hidden run must be
contiguous and its count is derived, so the reduction is visible rather than
implied. An earlier version labelled the ellipsis "L3 multiplet", which was
simply wrong — the run it stands for is p2 to p6, and p6 is an L2 peak. The grid
on the right hides nothing: it carries a labelled run for every component,
including the ones the left register collapses.

Determinism
-----------
The render manifest hashes the PNG byte for byte. Nothing here consults an RNG,
the backend is pinned to Agg rather than resolved from the environment, and every
string drawn on the canvas is ASCII — a font fallback is a determinism bug too,
and a `->` glyph missing from Helvetica Neue caused exactly that once. Arrows are
drawn as arrows, not typeset as arrowheads.
"""

from __future__ import annotations

import json
import re
from itertools import pairwise
from pathlib import Path
from typing import Any

import matplotlib as mpl
from matplotlib import pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent / "fecl4" / "fecl4_fit_results.json"
TIES = HERE.parent / "fecl4" / "fecl4_constraint_scenarios.json"
SPECTRUM = "d5"

# The peak nodes drawn individually in the left register: the L3 white line and
# its neighbour, then the L2 white line and its neighbour. Everything between
# them is one ellipsis node whose count is derived from the fit rather than typed
# here. The right register collapses nothing.
DRAWN_PEAKS = ("p0", "p1", "p7", "p8")

# Declaration order for a component's parameters, so both the node sublabels and
# the cell runs read the same way every run whatever order the JSON happens to
# serialise them in. Anything unlisted sorts after these, alphabetically — a new
# kernel parameter appears rather than being dropped.
PARAM_ORDER = ("center", "amplitude", "sigma", "fraction", "c")

# Node order for the non-peak components, left to right and, identically, in the
# cell grid. Peaks come first in numeric order; anything unlisted sorts after
# these, alphabetically, so a new component kind appears rather than vanishing.
NODE_ORDER = ("step_l3", "step_l2", "bg")

# Kernel names. Authored prose, not data: the results sidecar records parameter
# names, not the kernel each component was built from. The COUNTS beside them are
# derived, and the three sum to the component total in the subtitle.
KERNEL_PEAK, KERNEL_STEP, KERNEL_BG = "pseudo_voigt", "arctan_step", "constant"

# What each tie encodes, in plain terms. Authored prose: "2:1 edge-jump
# degeneracy" and "spin-orbit splitting" are free to a spectroscopist and opaque
# to the general computational reader this journal also has. Keyed by tie id, so
# a constraint added upstream without a gloss here stops the figure loudly rather
# than being drawn unexplained.
PHYSICS = {
    "step": "a fixed 2:1 intensity ratio between the two absorption edges",
    "spin_orbit": "a fixed energy gap between the two main peaks",
}

# Hues, checked against docs/stylesheets/tokens/palette.css. Each is unique
# within this canvas, and each series carries a second channel — every node holds
# its own monospace name and every cell run is captioned with it — so no hue is
# load-bearing on its own and the figure survives greyscale print.
#
# #0064d2 is `--c-spectrafit-text` (palette.css:95), this project's own brand
# hue. fig_architecture.py spends the same hex on the Python surface layer; that
# meaning is DECLINED here, because this figure has no language split to carry
# and the peaks are the subject rather than a comparator.
C_PEAK = "#0064d2"  # systemBlue-text — multiplet components
# #9c5f00 is `--c-chart-2` (palette.css:148). Deliberate identical reuse: the
# arctan continuum steps carry this hue in fig_constraint_grid.py (its C_STEP)
# for the same referent, and that figure declares the shared meaning from its
# side. The two uses are one meaning, not a collision.
C_STEP = "#9c5f00"  # amber — continuum steps
# Neutral, deliberately not a hue: a constant offset is not a spectroscopic
# species, so it is drawn in the same muted grey as the sublabels rather than
# given a colour of its own. Sharing the hex with INK_MUTED is the point.
C_BG = "#6e6e73"  # grey — baseline
# #d30f45 is `--c-jax-text` (palette.css:100), the paper's reserved attention
# channel. It is spent once, on the expression edges and the cells they strike —
# the one thing this figure exists to show — and never on a component, so it
# cannot be mistaken for one. fig_constraint_grid.py names this figure at its own
# C_RESID when it reuses the hue for the residual.
C_EDGE = "#d30f45"  # systemPink-text — expression edges, the emphasised element
INK = "#1d1d1f"
INK_MUTED = "#6e6e73"
RULE = "#d2d2d7"

# Layer ladder, declared rather than inherited from call order: cells and boxes
# (2) sit under their own labels (3), the edges cross over both (4) because they
# are the figure's message, their formulae ride over the edges (5), and the frame
# text is above everything (6) so a label can never be cut by a box or an arc.
Z_BOX, Z_BOX_LABEL, Z_EDGE, Z_EDGE_LABEL, Z_FRAME = 2, 3, 4, 5, 6

# --- canvas ---------------------------------------------------------------
# One unit of x is 0.072 in and one unit of y is about 0.0729 in, so a square on
# the page is very nearly square in these coordinates.
CANVAS_W, CANVAS_H = 100.0, 48.0
DIVIDER_X = 46.0

# --- left register --------------------------------------------------------
# Five node slots, used by the peak row (all five) and by the step/background row
# (slots 0, 1 and 3).
SLOT_X0, SLOT_W, SLOT_PITCH, N_SLOTS = 1.0, 7.4, 8.7, 5
# Rows are given by their TOP edge and each node is as tall as the number of
# parameters it declares, so the one-parameter background is a small box rather
# than a large empty one. The `constant` node looking slighter than a
# `pseudo_voigt` node is a true statement about the model.
PEAK_ROW_TOP, STEP_ROW_TOP = 34.6, 21.8
NODE_H_BASE, NODE_LINE_PITCH = 4.15, 1.35
BG_SLOT = 3
# Expression entries: three lines each (the equation, the scenario stamp, the
# physics gloss), and the arrow for each leaves at the equation's height.
EDGE_BLOCK_Y, EDGE_BLOCK_PITCH = 10.4, 5.6
# An edge leaves from the end of its own equation, measured off the rendered text
# rather than guessed from a character count, so the arrow starts where the
# expression stops however long the component names upstream become. The gap is
# generous because the measurement is taken at the figure's own dpi while the PNG
# rasterises at 300, and glyph advances round differently between the two — a
# tight gap puts the first dash on the equation's last character.
EDGE_TAIL_GAP = 3.0

# --- right register -------------------------------------------------------
# The grid is anchored at its BOTTOM, so a roster that gains or loses a component
# without changing the row count leaves the ledger and the edge corridor exactly
# where they are.
GRID_X0, GRID_BOTTOM = 48.5, 20.8
CELL_W, CELL_H, CELL_GAP, RUN_GAP = 2.6, 2.6, 0.28, 1.2
ROW_PITCH, RUN_LABEL_DY = 4.9, 0.85
COMPONENTS_PER_ROW = 4
GRID_CEILING = 36.4  # the register's sub-caption; the grid may not reach it
LEDGER_Y, LEDGER_PITCH = 16.9, 2.3
LEDGER_COUNT_X, LEDGER_DELTA_X = 68.0, 69.0
KEY_Y = 1.9
# The horizontal leg of every edge runs below this, so the ledger may not.
EDGE_CORRIDOR_TOP = 11.6

mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    },
)

# The render manifest hashes the PNG byte for byte, so the backend is pinned
# rather than resolved from the environment. Nothing here consults an RNG and the
# layout is authored, but an interactive backend picked up on one machine would
# still re-raster the same figure differently.
mpl.use("Agg")


def _ordered(names: list[str], hint: tuple[str, ...]) -> list[str]:
    """Sort by position in `hint`, with anything unlisted after it, alphabetically."""
    return sorted(names, key=lambda n: (hint.index(n) if n in hint else len(hint), n))


def graph_facts() -> dict[str, Any]:
    """Read the declared model graph — names only, never a fitted value.

    This figure draws a graph, so it reads graph properties: which components
    exist, what each one is called, which parameters each declares, and how many
    of each kind there are. It reads no parameter *value* and no standard error,
    which is what keeps it independent of which solve produced the file.

    Returns:
        The peak, step and background rosters, the parameter names each component
        declares, the full node order the cell grid is enumerated in, and the run
        of peaks the ellipsis stands for.
    """
    if not RESULTS.exists():
        msg = (
            f"{RESULTS} not found — run manuscript/examples/fecl4/"
            "fig_fecl4_case_study.py first, which writes the model declaration "
            "this figure reads its component and parameter names from"
        )
        raise SystemExit(msg)
    doc = json.loads(RESULTS.read_text())
    spec = doc["spectra"][SPECTRUM]
    params: dict[str, dict[str, Any]] = spec["parameters"]

    roster = {key.split(".", 1)[0] for key in params}
    peaks = sorted(
        (name for name in roster if re.fullmatch(r"p\d+", name)),
        key=lambda name: int(name[1:]),
    )
    others = _ordered([name for name in roster if name not in peaks], NODE_ORDER)
    steps = [name for name in others if name.startswith("step_")]
    background = [name for name in others if name not in steps]

    if len(peaks) != int(spec["n_peaks"]):
        msg = (
            f"{RESULTS} reports n_peaks={spec['n_peaks']} for spectrum "
            f"{SPECTRUM!r} but carries parameters for {len(peaks)} — the results "
            "file is internally inconsistent and this figure cannot count from it"
        )
        raise SystemExit(msg)
    missing = [name for name in (*DRAWN_PEAKS, *NODE_ORDER) if name not in roster]
    if missing:
        msg = (
            f"{RESULTS} has no {', '.join(missing)} in spectrum {SPECTRUM!r} — the "
            "case study's node names have changed and this figure needs redrawing"
        )
        raise SystemExit(msg)
    if len(background) != 1:
        msg = (
            f"spectrum {SPECTRUM!r} declares {len(background)} non-peak, non-step "
            f"components ({', '.join(background) or 'none'}) — the left register "
            "has one background slot and the heading says `constant (1)`"
        )
        raise SystemExit(msg)

    declared = {
        component: tuple(
            _ordered(
                [key.split(".", 1)[1] for key in params if key.startswith(f"{component}.")],
                PARAM_ORDER,
            ),
        )
        for component in roster
    }
    # The peak row shows one parameter list above the drawn boxes and behind an
    # ellipsis standing for the rest, so that list has to be true of every peak.
    # If two peaks ever declare different parameters the row is quietly lying.
    sets = {declared[name] for name in peaks}
    if len(sets) != 1:
        msg = (
            f"the {len(peaks)} peaks in spectrum {SPECTRUM!r} do not all declare the "
            f"same parameters ({sorted(sets)}) — one shared parameter list cannot "
            "describe the row and the peaks must be drawn separately"
        )
        raise SystemExit(msg)

    hidden = [name for name in peaks if name not in DRAWN_PEAKS]
    span = peaks[peaks.index(hidden[0]) : peaks.index(hidden[-1]) + 1]
    if hidden != span:
        msg = (
            f"the peaks behind the ellipsis are {', '.join(hidden)}, which is not a "
            "contiguous run — one ellipsis node cannot honestly stand for them and "
            "the row must be redrawn"
        )
        raise SystemExit(msg)

    return {
        "peaks": peaks,
        "steps": steps,
        "background": background[0],
        "declared": declared,
        "node_order": [*peaks, *others],
        "hidden": hidden,
    }


def constraint_ties() -> list[dict[str, str]]:
    """The tie definitions for this spectrum, read from the scenarios sidecar.

    Read rather than transcribed: `fecl4_constraint_scenarios.py` holds the one
    definition of each constraint and serialises it here, so this figure and the
    constraint grid cannot disagree about what a hypothesis says. Reading the
    JSON rather than importing the module keeps this figure free of the compiled
    extension.

    Returns:
        One entry per tie, each carrying its id, expression, target and the
        scenario that introduces it.
    """
    ties = _scenarios_doc().get("ties", {}).get(SPECTRUM)
    if not ties:
        msg = (
            f"{TIES.name} carries no `ties` block for spectrum {SPECTRUM!r} — it "
            "predates the shared tie definition, so this figure has nothing to "
            "draw its edges from. Re-run fecl4_constraint_scenarios.py."
        )
        raise SystemExit(msg)
    unknown = [t["id"] for t in ties if t["id"] not in PHYSICS]
    if unknown:
        msg = (
            f"no plain-language gloss for tie(s) {', '.join(unknown)} — a constraint "
            "was added to fecl4_constraint_scenarios.py and this figure would draw "
            "it unexplained. Add a PHYSICS entry saying what it encodes."
        )
        raise SystemExit(msg)
    return ties


def _scenarios_doc() -> dict[str, Any]:
    """Load the scenarios sidecar, or say exactly which command writes it."""
    if not TIES.exists():
        msg = (
            f"{TIES} not found — it carries the tie definitions and the free-"
            "parameter ledger this figure draws, and transcribing them here is what "
            "made this figure a third copy of one piece of physics. Produce it with:"
            "\n  uv run --group manuscript python "
            "manuscript/examples/fecl4/fecl4_constraint_scenarios.py"
        )
        raise SystemExit(msg)
    return json.loads(TIES.read_text())


def free_parameter_ledger(n_ties: int) -> list[tuple[str, int]]:
    """The scenario-by-scenario free-parameter count for this spectrum.

    Args:
        n_ties: How many expression edges the figure draws, which is how many
            steps the ledger must have after its unconstrained first row.

    Returns:
        One `(scenario label, free parameters)` pair per scenario, in file order.
    """
    rows = [r for r in _scenarios_doc().get("rows", []) if r.get("subject") == SPECTRUM]
    ledger = [(str(r["scenario"]), int(r["free_params"])) for r in rows]
    if len(ledger) != n_ties + 1:
        msg = (
            f"{TIES.name} carries {len(ledger)} scenarios for spectrum {SPECTRUM!r} "
            f"but {n_ties} ties — the ledger is meant to read as one unconstrained "
            "row followed by one row per edge, and it cannot"
        )
        raise SystemExit(msg)
    drops = [before - after for (_, before), (_, after) in pairwise(ledger)]
    if set(drops) != {1}:
        msg = (
            f"the free-parameter ledger for spectrum {SPECTRUM!r} steps by "
            f"{drops} — this figure's entire claim is that one expression edge "
            "removes exactly one free parameter, and the artifact disagrees"
        )
        raise SystemExit(msg)
    return ledger


def cell_grid(node_order: list[str], declared: dict[str, tuple[str, ...]]) -> dict[str, Any]:
    """Lay one cell per declared parameter out in runs, grouped by owning component.

    The grid is enumerated in node order and broken into rows of whole
    components, so a component's parameters are always a contiguous, unwrapped
    run and the run lengths are legible as such.

    Args:
        node_order: Components left to right, exactly as the left register lists
            them.
        declared: The parameter names each component declares.

    Returns:
        The per-parameter cell rectangles keyed `component.parameter`, one
        captioned run per component, and the grid's row count and extent.
    """
    rows = [
        node_order[i : i + COMPONENTS_PER_ROW]
        for i in range(0, len(node_order), COMPONENTS_PER_ROW)
    ]
    top_row_y = GRID_BOTTOM + CELL_H + (len(rows) - 1) * ROW_PITCH
    if top_row_y + RUN_LABEL_DY + 1.2 > GRID_CEILING:
        msg = (
            f"the parameter grid now needs {len(rows)} rows and would reach the "
            "register caption — the roster grew past what this canvas holds. Give "
            "the figure more height, or raise COMPONENTS_PER_ROW and re-check the "
            "row widths."
        )
        raise SystemExit(msg)

    cells: dict[str, tuple[float, float]] = {}
    runs: list[dict[str, Any]] = []
    widest = 0.0
    for index, row in enumerate(rows):
        cell_y = top_row_y - index * ROW_PITCH - CELL_H
        x = GRID_X0
        for component in row:
            run_x0 = x
            for name in declared[component]:
                cells[f"{component}.{name}"] = (x, cell_y)
                x += CELL_W + CELL_GAP
            x -= CELL_GAP
            runs.append({"component": component, "x0": run_x0, "x1": x, "y": cell_y})
            widest = max(widest, x - GRID_X0)
            x += RUN_GAP
    if GRID_X0 + widest > CANVAS_W - 1.0:
        msg = (
            f"the widest grid row now spans {widest:.2f} units and overruns the "
            "canvas — lower COMPONENTS_PER_ROW, or narrow CELL_W"
        )
        raise SystemExit(msg)
    return {"cells": cells, "runs": runs, "n_rows": len(rows), "top": top_row_y}


def tint(hex_colour: str, amount: float) -> tuple[float, float, float]:
    """Blend a hex colour toward white by `amount` (0 = unchanged, 1 = white)."""
    r, g, b = (int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return tuple(c + (1.0 - c) * amount for c in (r, g, b))


def hue_of(component: str, facts: dict[str, Any]) -> str:
    """The component's series colour, from which roster it belongs to."""
    if component in facts["peaks"]:
        return C_PEAK
    if component in facts["steps"]:
        return C_STEP
    return C_BG


def node_height(names: tuple[str, ...]) -> float:
    """How tall a node has to be to hold its id and one line per declared parameter."""
    return NODE_H_BASE + len(names) * NODE_LINE_PITCH


def node(ax, x: float, top: float, title: str, names: tuple[str, ...], colour: str) -> None:
    """Draw one component node: its id above, the parameter names it declares below.

    Nodes in a row hang from a shared top edge and take their height from what
    they declare, so a three-name step and a one-name background each sit as
    deliberately as a four-name peak.
    """
    h = node_height(names)
    y = top - h
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            SLOT_W,
            h,
            boxstyle="round,pad=0.3,rounding_size=1.1",
            linewidth=1.1,
            edgecolor=colour,
            facecolor=tint(colour, 0.92),
            zorder=Z_BOX,
        ),
    )
    ax.text(
        x + SLOT_W / 2,
        y + h - 1.9,
        title,
        ha="center",
        va="center",
        fontsize=6.6,
        color=INK,
        family="monospace",
        zorder=Z_BOX_LABEL,
    )
    middle = ((y + h - 3.3) + (y + 0.9)) / 2
    first = middle + (len(names) - 1) * NODE_LINE_PITCH / 2
    for index, name in enumerate(names):
        ax.text(
            x + SLOT_W / 2,
            first - index * NODE_LINE_PITCH,
            name,
            ha="center",
            va="center",
            fontsize=5.2,
            color=INK_MUTED,
            family="monospace",
            zorder=Z_BOX_LABEL,
        )


def draw_left_register(ax, facts: dict[str, Any]) -> None:
    """The component graph: what the analyst declares, and under what names."""
    declared, peaks, hidden = facts["declared"], facts["peaks"], facts["hidden"]
    peak_params = declared[peaks[0]]

    ax.text(
        SLOT_X0,
        39.4,
        "what the analyst declares",
        fontsize=7.4,
        color=INK,
        weight="bold",
        zorder=Z_FRAME,
    )
    ax.text(
        SLOT_X0,
        37.2,
        "components, and the parameter names each one introduces",
        fontsize=5.8,
        color=INK_MUTED,
        zorder=Z_FRAME,
    )

    # The ellipsis sits where the hidden run sits, between the peaks drawn before
    # it and the ones drawn after, so the row reads in peak order whichever peaks
    # DRAWN_PEAKS names. It carries the same parameter list as every other peak,
    # because every peak declares the same list and that is checked. What it does
    # not carry is a node name, so the run it stands for is stated under the box.
    cut = peaks.index(hidden[0])
    before = [name for name in peaks if name in DRAWN_PEAKS and peaks.index(name) < cut]
    after = [name for name in peaks if name in DRAWN_PEAKS and peaks.index(name) > cut]
    row = [*before, "...", *after]
    if len(row) > N_SLOTS:
        msg = (
            f"the peak row needs {len(row)} slots ({', '.join(row)}) and the left "
            f"register has {N_SLOTS} — hide more peaks behind the ellipsis by "
            "shortening DRAWN_PEAKS, or re-lay-out the register"
        )
        raise SystemExit(msg)
    for index, title in enumerate(row):
        node(ax, SLOT_X0 + index * SLOT_PITCH, PEAK_ROW_TOP, title, peak_params, C_PEAK)
    ax.text(
        SLOT_X0 + len(before) * SLOT_PITCH + SLOT_W / 2,
        PEAK_ROW_TOP - node_height(peak_params) - 1.5,
        f"{hidden[0]}-{hidden[-1]}, {len(hidden)} more",
        ha="center",
        va="center",
        fontsize=5.2,
        color=INK_MUTED,
        zorder=Z_FRAME,
    )
    ax.text(
        SLOT_X0,
        PEAK_ROW_TOP + 0.9,
        f"{KERNEL_PEAK} ({len(peaks)})",
        fontsize=6.6,
        color=C_PEAK,
        family="monospace",
        zorder=Z_FRAME,
    )

    if len(facts["steps"]) > BG_SLOT:
        msg = (
            f"the model declares {len(facts['steps'])} step components and the "
            f"second row keeps only {BG_SLOT} slots clear of the background — the "
            "boxes would be drawn on top of each other"
        )
        raise SystemExit(msg)
    for index, component in enumerate(facts["steps"]):
        node(
            ax,
            SLOT_X0 + index * SLOT_PITCH,
            STEP_ROW_TOP,
            component,
            declared[component],
            C_STEP,
        )
    background = facts["background"]
    node(
        ax,
        SLOT_X0 + BG_SLOT * SLOT_PITCH,
        STEP_ROW_TOP,
        background,
        declared[background],
        C_BG,
    )
    # Each group is named above its own row in its own hue. That is the colour
    # key -- there is no separate legend, because a legend would be a second
    # place to look up a fact the heading already states -- and it is also the
    # component arithmetic: these counts sum to the total in the subtitle, so a
    # reader never has to guess whether p0-p8 are nine components or nine
    # parameters of one.
    heading_y = STEP_ROW_TOP + 0.9
    ax.text(
        SLOT_X0,
        heading_y,
        f"{KERNEL_STEP} ({len(facts['steps'])})",
        fontsize=6.6,
        color=C_STEP,
        family="monospace",
        zorder=Z_FRAME,
    )
    ax.text(
        SLOT_X0 + BG_SLOT * SLOT_PITCH,
        heading_y,
        f"{KERNEL_BG} (1)",
        fontsize=6.6,
        color=C_BG,
        family="monospace",
        zorder=Z_FRAME,
    )


def draw_expressions(ax, ties: list[dict[str, str]]) -> list[tuple[float, float]]:
    """The expression edges, declared in the same register as the components.

    Returns:
        Where each edge's arrow leaves the register, in tie order.
    """
    ax.text(
        SLOT_X0,
        EDGE_BLOCK_Y + 1.9,
        f"expression edges ({len(ties)})",
        fontsize=6.6,
        color=C_EDGE,
        family="monospace",
        zorder=Z_FRAME,
    )
    tails: list[tuple[float, float]] = []
    for index, spec in enumerate(ties):
        y = EDGE_BLOCK_Y - index * EDGE_BLOCK_PITCH
        equation = f"{spec['target']} = {spec['expr']}"
        handle = ax.text(
            SLOT_X0,
            y,
            equation,
            fontsize=5.4,
            color=C_EDGE,
            family="monospace",
            va="center",
            zorder=Z_EDGE_LABEL,
        )
        renderer = ax.figure.canvas.get_renderer()
        extent = handle.get_window_extent(renderer=renderer)
        ends_at = ax.transData.inverted().transform((extent.x1, extent.y1))[0]
        if ends_at + EDGE_TAIL_GAP > DIVIDER_X:
            msg = (
                f"tie {spec['id']!r} reads `{equation}`, which runs to x={ends_at:.1f} "
                f"and reaches the divider at x={DIVIDER_X} — its arrow would start in "
                "the other register. Widen the left register, or shorten the "
                "component names upstream."
            )
            raise SystemExit(msg)
        ax.text(
            SLOT_X0,
            y - 1.8,
            f"added by scenario {spec['introduced_by'].split()[0]}",
            fontsize=5.2,
            color=INK_MUTED,
            va="center",
            zorder=Z_EDGE_LABEL,
        )
        ax.text(
            SLOT_X0,
            y - 3.4,
            PHYSICS[spec["id"]],
            fontsize=5.2,
            color=INK_MUTED,
            va="center",
            zorder=Z_EDGE_LABEL,
        )
        tails.append((ends_at + EDGE_TAIL_GAP, y))
    return tails


def draw_grid(ax, facts: dict[str, Any], grid: dict[str, Any], struck: set[str]) -> None:
    """One cell per declared parameter, in runs, with the struck cells left open."""
    ax.text(
        GRID_X0,
        39.4,
        "what the fit is left to determine",
        fontsize=7.4,
        color=INK,
        weight="bold",
        zorder=Z_FRAME,
    )
    ax.text(
        GRID_X0,
        37.2,
        "one cell per free parameter, in the order the components declare them",
        fontsize=5.8,
        color=INK_MUTED,
        zorder=Z_FRAME,
    )
    for run in grid["runs"]:
        colour = hue_of(run["component"], facts)
        ax.text(
            (run["x0"] + run["x1"]) / 2,
            run["y"] + CELL_H + RUN_LABEL_DY,
            run["component"],
            ha="center",
            va="bottom",
            fontsize=5.2,
            color=colour,
            family="monospace",
            zorder=Z_BOX_LABEL,
        )
    for key, (x, y) in grid["cells"].items():
        colour = hue_of(key.split(".", 1)[0], facts)
        open_cell = key in struck
        ax.add_patch(
            Rectangle(
                (x, y),
                CELL_W,
                CELL_H,
                linewidth=1.0 if open_cell else 0.45,
                edgecolor=C_EDGE if open_cell else tint(colour, 0.45),
                facecolor="none" if open_cell else tint(colour, 0.84),
                linestyle=(0, (2.0, 1.4)) if open_cell else "solid",
                zorder=Z_BOX,
            ),
        )


def draw_open_cell_key(ax) -> None:
    """Say what an open cell means, once, in the register's own dead space.

    This is the one thing about the grid a reader cannot infer from the geometry:
    that the unfilled, dashed cells are unfilled *because* an edge landed on
    them. It is not a legend for the hues — those are named by the group heading
    above each row of nodes and by the caption over each run of cells, and a
    legend would be a second place to look up a fact already stated.
    """
    ax.add_patch(
        Rectangle(
            (GRID_X0, KEY_Y - 1.1),
            2.2,
            2.2,
            linewidth=1.0,
            edgecolor=C_EDGE,
            facecolor="none",
            linestyle=(0, (2.0, 1.4)),
            zorder=Z_FRAME,
        ),
    )
    ax.text(
        GRID_X0 + 3.4,
        KEY_Y,
        "an open cell is a free parameter an expression edge removed",
        va="center",
        fontsize=5.4,
        color=INK_MUTED,
        zorder=Z_FRAME,
    )


def draw_ledger(ax, ledger: list[tuple[str, int]]) -> None:
    """The free-parameter count, scenario by scenario, read from the artifact."""
    ax.text(
        GRID_X0,
        LEDGER_Y + 2.3,
        "free parameters, scenario by scenario",
        fontsize=5.8,
        color=INK_MUTED,
        zorder=Z_FRAME,
    )
    previous: int | None = None
    for index, (scenario, free) in enumerate(ledger):
        y = LEDGER_Y - index * LEDGER_PITCH
        ax.text(
            GRID_X0,
            y,
            scenario,
            fontsize=5.6,
            color=INK_MUTED,
            family="monospace",
            va="center",
            zorder=Z_FRAME,
        )
        ax.text(
            LEDGER_COUNT_X,
            y,
            str(free),
            ha="right",
            va="center",
            fontsize=7.0,
            color=INK,
            weight="bold",
            zorder=Z_FRAME,
        )
        if previous is not None:
            ax.text(
                LEDGER_DELTA_X,
                y,
                f"-{previous - free}",
                va="center",
                fontsize=5.6,
                color=C_EDGE,
                family="monospace",
                zorder=Z_FRAME,
            )
        previous = free
    lowest = LEDGER_Y - (len(ledger) - 1) * LEDGER_PITCH
    if lowest < EDGE_CORRIDOR_TOP:
        msg = (
            f"the ledger now reaches y={lowest:.2f} and would sit in the corridor "
            "the expression edges cross at — an edge would be drawn through it. "
            "Shorten LEDGER_PITCH or give the figure more height."
        )
        raise SystemExit(msg)


def draw_edges(
    ax,
    ties: list[dict[str, str]],
    tails: list[tuple[float, float]],
    grid: dict[str, Any],
    drawn: set[str],
) -> list[str]:
    """Draw each expression edge from its declaration to the one cell it removes.

    The head is derived from the tie's own target, so an edge always lands on the
    parameter the expression actually sets. The route is an elbow: out along the
    corridor beneath the grid, then straight up into the cell's lower edge. An
    arc would have to be threaded between rows of cells, and any arc that misses
    is an arc that appears to strike a cell it does not.

    Returns:
        The struck cell keys, in tie order.
    """
    struck: list[str] = []
    for spec, tail in zip(ties, tails, strict=True):
        referenced = set(re.findall(r"\b([A-Za-z_]\w*)\.", f"{spec['target']} {spec['expr']}"))
        absent = sorted(name for name in referenced if name not in drawn)
        if absent:
            msg = (
                f"tie {spec['id']!r} reads `{spec['target']} = {spec['expr']}`, and it "
                f"names {', '.join(absent)}, which the left register hides behind the "
                "ellipsis — the formula would cite a node the reader cannot see, and "
                "an arrow into it would have nowhere honest to land. Add "
                f"{', '.join(absent)} to DRAWN_PEAKS."
            )
            raise SystemExit(msg)
        target = spec["target"]
        if target not in grid["cells"]:
            msg = (
                f"tie {spec['id']!r} sets {target}, which is not a declared parameter "
                f"of spectrum {SPECTRUM!r} — the scenarios sidecar and the results "
                "sidecar disagree about the model"
            )
            raise SystemExit(msg)
        x, y = grid["cells"][target]
        ax.add_patch(
            FancyArrowPatch(
                tail,
                (x + CELL_W / 2, y),
                connectionstyle="angle,angleA=0,angleB=90,rad=2.4",
                arrowstyle="-|>,head_length=4.5,head_width=2.4",
                linewidth=1.2,
                color=C_EDGE,
                linestyle=(0, (4, 2)),
                shrinkA=0.0,
                shrinkB=0.0,
                zorder=Z_EDGE,
            ),
        )
        struck.append(target)
    return struck


def draw() -> None:
    """Compose and write the figure."""
    facts = graph_facts()
    ties = constraint_ties()
    ledger = free_parameter_ledger(len(ties))
    grid = cell_grid(facts["node_order"], facts["declared"])

    n_cells = len(grid["cells"])
    if n_cells != ledger[0][1]:
        msg = (
            f"spectrum {SPECTRUM!r} declares {n_cells} parameters but "
            f"{TIES.name} reports {ledger[0][1]} free in its unconstrained scenario "
            f"({ledger[0][0]!r}) — the two sidecars describe different models and "
            "the grid would show a count the ledger contradicts"
        )
        raise SystemExit(msg)

    fig, ax = plt.subplots(figsize=(7.2, 3.5))
    ax.set_xlim(0, CANVAS_W)
    ax.set_ylim(0, CANVAS_H)
    ax.axis("off")
    # Before anything is drawn, not after. `draw_expressions` measures rendered
    # text to find where each edge should leave, and a later subplots_adjust
    # would rescale the data transform under the measurement — every arrow then
    # starts about a quarter further right than the equation it belongs to.
    fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)

    ax.text(0, 45.4, "one model graph", fontsize=9.4, color=INK, weight="bold", zorder=Z_FRAME)
    ax.text(
        0,
        42.4,
        f"{len(facts['node_order'])} declared components carrying {n_cells} parameters, "
        f"and {len(ties)} expression edges; each edge removes one free parameter, "
        f"leaving {ledger[-1][1]}",
        fontsize=7.0,
        color=INK_MUTED,
        zorder=Z_FRAME,
    )
    # The registers hold different KINDS of thing -- declarations on one side,
    # unknowns on the other -- so they are separated by a rule rather than by
    # whitespace, and the expression edges are the only marks that cross it.
    ax.plot(
        [DIVIDER_X, DIVIDER_X],
        [1.0, 40.6],
        linewidth=0.6,
        color=RULE,
        solid_capstyle="butt",
        zorder=1,
    )

    draw_left_register(ax, facts)
    tails = draw_expressions(ax, ties)
    drawn = {*DRAWN_PEAKS, *facts["steps"], facts["background"]}
    struck = draw_edges(ax, ties, tails, grid, drawn)
    draw_grid(ax, facts, grid, set(struck))
    draw_ledger(ax, ledger)
    draw_open_cell_key(ax)

    for ext, dpi in (("pdf", None), ("png", 300)):
        fig.savefig(HERE / f"fig_model_graph.{ext}", dpi=dpi)
    plt.close(fig)

    runs = [(run["component"], len(facts["declared"][run["component"]])) for run in grid["runs"]]
    print(
        f"components: {len(facts['node_order'])} "
        f"({len(facts['peaks'])} {KERNEL_PEAK}, {len(facts['steps'])} {KERNEL_STEP}, "
        f"1 {KERNEL_BG}); expression edges: {len(ties)}",
    )
    print(f"cells: {n_cells} in {grid['n_rows']} rows of {COMPONENTS_PER_ROW} components")
    print(f"  runs: {' '.join(f'{name}:{n}' for name, n in runs)}")
    print(f"  run lengths: {'+'.join(str(n) for _, n in runs)} = {sum(n for _, n in runs)}")
    print(
        f"drawn individually: {', '.join(DRAWN_PEAKS)}; behind the ellipsis: "
        f"{len(facts['hidden'])} ({facts['hidden'][0]}-{facts['hidden'][-1]})",
    )
    for component in (facts["peaks"][0], *facts["steps"], facts["background"]):
        print(f"  {component:8s} declares {', '.join(facts['declared'][component])}")
    for spec, target in zip(ties, struck, strict=True):
        x, y = grid["cells"][target]
        print(
            f"  edge {spec['id']:10s} {target} = {spec['expr']}  "
            f"[{spec['introduced_by']}]  struck cell at x={x:.2f} y={y:.2f}",
        )
    print(f"ledger: {' '.join(f'{label}={free}' for label, free in ledger)}")
    print("  no fitted value is read or drawn; this figure is solve-independent")
    print("wrote fig_model_graph.pdf / .png")


if __name__ == "__main__":
    draw()
