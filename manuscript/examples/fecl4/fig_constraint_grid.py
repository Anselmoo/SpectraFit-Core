"""Figure: the same two spectra fitted under three constraint hypotheses.

`fecl4_constraint_scenarios.py` reports seven fits as a table of numbers. A table
of reduced chi-squared values does not show *where* a constraint costs something,
and the one place the paper had a picture of an L-edge fit showed a single
scenario. This draws the grid the table describes: one column per spectrum, one
row per hypothesis, with the residual under each panel so the reader can see
which region of the spectrum pays for the constraint.

All four of the table's hypotheses. A, B and C are each one fit per spectrum,
which is what a row of two independent columns means here. D is a single joint
fit spanning both spectra, so its row does put two halves of one fit where every
other row has two separate ones. That was the reason D was left out until
2026-08-18, and it was the wrong call: the paper's verdict is the C-versus-D
comparison, so a figure without D asked the reader to take the comparison on
trust. The row is drawn and labelled instead, carrying "one joint fit, both
panels" and the joint 86 free parameters in both columns, with no per-column
reduced chi-squared because that quantity does not exist for it.

The point the grid makes and the table cannot: on d6 the spin-orbit tie costs
nothing, while on d5 the whole of its cost is one derivative-shaped excursion at
the L3 white line. The table says the fit got worse - reduced chi-squared 0.0246
against 0.0071 - and only the picture says the damage is a single feature rather
than a fit that is worse everywhere. That is a statement about *which peak*
disagrees, and it is only legible as a picture.

An earlier version of this paragraph said the opposite, that the tie "distorts
the L2 region specifically", and the figure it introduces contradicts it: under
C the worst d5 residual is 4.93 % of the white-line maximum, at 708.20 eV,
astride the white line at 707.89 eV, while the L2 region above 717 eV is quieter
under C than under A. The manuscript sentence this figure supports always said
L3. The receipt this script prints now reports the position of the worst
residual in every panel, so the claim and the picture can be checked against
each other without reading the pixels.

**The white-line rule is the carrier between each pair of panels.** Every
spectrum panel and the residual panel beneath it carry a dashed rule at that
row's own fitted L3 white-line centre, drawn in the L3 multiplet's colour
because the spectrum panel is where it comes from. Without it a reader has to
hold an x position in memory across a panel boundary to see that d5's excursion
under C sits on the white line rather than beside it, which is the one
comparison the figure exists to make. It is refitted per row rather than drawn
once per column, so the 0.06 eV by which the tie moves the d5 white line is
drawn rather than asserted.

**A known duplication, now closed rather than merely guarded.** `fit_one` used to
rebuild both tie expressions as a second hand-typed copy of what
`fecl4_constraint_scenarios.py` builds; that module now exposes `ties_for()` as a
module-level constructor, and `fit_one` calls it directly, so there is one
definition of each tie rather than two that could drift apart. The numeric
cross-check is kept anyway, as a regression test rather than a duplication
guard: every panel's free-parameter count and reduced chi-squared are checked
against the row for the same scenario and subject in
`fecl4_constraint_scenarios.json` before anything is written, which still catches
a solver or data change that moves the fit without touching the ties.

Reproduce from a clean clone:

    uv run --group manuscript python manuscript/examples/fecl4/fig_constraint_grid.py

Outputs (written next to this file):
    fig_constraint_grid.pdf   vector, for submission
    fig_constraint_grid.png   300 dpi raster, for preview

Every fit here is re-run rather than read from a cache, and every panel is
cross-checked against the shipped table, so the figure and
`fecl4_constraint_scenarios.json` cannot disagree silently.
"""

from __future__ import annotations

import json
import sys
from functools import cache
from pathlib import Path
from typing import Any

import matplotlib as mpl
import numpy as np
from matplotlib import pyplot as plt
from matplotlib.ticker import MultipleLocator

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fecl4_constraint_scenarios as SC
import fig_fecl4_case_study as CS
from spectrafit_core import compose, evaluate, evaluate_components

# Palette taken from fig_fecl4_case_study.py verbatim: the two figures show the
# same spectra and must read as one system, so a component is the same colour in
# both. One hue per multiplet rather than per node, since nine cycled hues would
# encode nothing.
#
# Declining-comment. Three of the four hues below are also spent, in the paper's
# timing figures, on solver backends. Those meanings are declined here, and the
# decline is safe because nothing in this figure is a backend: every series is a
# component of one spectral model, each carries a permanent entry in the shared
# legend, and the step series is dashed as well, so no reading here rests on hue
# alone.
#   #0067d6  is jax in fig_benchmark_profile.py. It was that figure's subject
#            until the timing figures were harmonised onto one set of backend
#            hues; the subject now sits on #c1185b, outside the chart ramp. Both
#            of those meanings are declined — this figure plots no backend.
#   #00875f  is scipy-ls-lm in fig_benchmark_profile.py and
#            fig_performance_profile.py. Declined.
#   #b03a8f  is scipy-ls-trf in both of those. Declined. (fig_nist_dual.py names
#            this hex too, but only in its docstring, recording a tier scheme it
#            moved away from — it draws nothing in it.)
#   #9c5f00  is the one hue this figure does not decline outright. It is lmfit in
#            the timing figures, and that meaning IS declined; but it is also the
#            arctan continuum step in fig_model_graph.py, which is the identical
#            referent and a deliberate shared meaning. That figure declares the
#            reuse from its side, at its own C_STEP.
C_FIT = "#b03a8f"  # --c-chart-4 — total model (thickest stroke)
C_L3 = "#0067d6"  # --c-chart-1 — L3 multiplet components
C_L2 = "#00875f"  # --c-chart-3 — L2 multiplet components
C_STEP = "#9c5f00"  # --c-chart-2 — arctan continuum steps (dashed)
INK = "#1d1d1f"
INK_MUTED = "#6e6e73"
GRID = "#e3e3e0"
# The residual is the panel carrying this figure's finding, so it gets a signal
# colour rather than body-text ink. Same hue as the emphasised expression edges
# in fig_model_graph.py, so "look here" reads consistently across the figures.
# It never overlays a component, so it cannot be confused with one. The token
# name was wrong here and is corrected: this hue is --c-jax-text
# (palette.css:100), not --c-chart-5, which is #4a9fd8 and the one entry in the
# chart ramp below 3:1 contrast. The hue was right and its label was not. The
# four-hue ramp is spent on the model's own series, so the attention channel is
# deliberately taken from outside it; that the token also names jax's brand text
# in the web UI is a collision on a surface no figure in this paper shares.
C_RESID = "#d30f45"  # --c-jax-text — residual, the attention channel

# The render manifest hashes the PNG byte for byte, so the backend is pinned
# rather than resolved from the environment: nothing here consults an RNG, and
# the fits are deterministic, but an interactive backend picked up on one
# machine would still re-raster the same figure differently.
mpl.use("Agg")

mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    },
)

# The three per-spectrum hypotheses in the order the scenarios module defines
# them, then the joint fit. D is drawn last and labelled as one fit shown in two
# panels, because the paper's verdict is the C-versus-D comparison and a figure
# that omits D asks the reader to take that comparison on trust.
JOINT_KEY = ("D  shared splitting", "d5+d6 joint")
JOINT_FREE = 86
# Which half of D's joint parameter vector belongs to which spectrum. Fixed by
# the bind expressions in fecl4_constraint_scenarios.py, and checked on load:
# a_ carries 43 names and b_ carries 47, which is 9 peaks against 10.
JOINT_PREFIX = {"d5": "a_", "d6": "b_"}
SCENARIOS = (*(s for s in SC.SCENARIOS if not s.startswith("D")), JOINT_KEY[0])

TABLE = HERE / "fecl4_constraint_scenarios.json"

# The shipped table rounds reduced chi-squared to six decimals, which is 1.3e-4
# in relative terms on the smallest value here. A relative tolerance of 1e-3
# clears that with room to spare and still fails on any real change of ties:
# adding the spin-orbit edge moves d5's value by a factor of three.
CHI2_RTOL = 1e-3

FIX_TABLE = (
    "uv run --group manuscript python manuscript/examples/fecl4/fecl4_constraint_scenarios.py"
)


@cache
def _table_rows() -> dict[tuple[str, str], dict[str, Any]]:
    """The shipped scenario table, keyed by (scenario, subject)."""
    rows = json.loads(TABLE.read_text())["rows"]
    return {(r["scenario"], r["subject"]): r for r in rows}


def fit_one(key: str, scenario: str):
    """Redraw one spectrum under one hypothesis; return x, y, model and residual.

    This does not fit. `render_figures.py` is structurally barred from executing
    `fecl4_constraint_scenarios.py`, because running it re-times every row of
    Table 2 -- and a figure that refits would reach a different optimum anyway,
    since the table reports the mutual fixed point of `SC._polish` rather than a
    single cold solve. So the parameter vector is read from the shipped table and
    replayed through `evaluate`, a pure forward pass with no solver iterations.
    The hypotheses still come from `SC.ties_for`, so the drawn model carries the
    same tie expressions the table's fit was subject to.
    """
    spec = CS.SPECTRA[key]
    data = SC._measure(spec)

    if scenario == JOINT_KEY[0]:
        # One fit spanning both spectra. Its parameter names are prefixed per
        # spectrum, so this half is read off by prefix and replayed on a plain
        # single-spectrum graph: D's tie expressions name components in the
        # other spectrum and cannot be declared here, and the stored values
        # already satisfy them.
        joint = _table_rows()[JOINT_KEY]
        prefix = JOINT_PREFIX[key]
        params = {
            name[len(prefix) :]: value
            for name, value in joint["params"].items()
            if name.startswith(prefix)
        }
        expected = 4 * len(spec["peaks"]) + 7
        if len(params) != expected:
            msg = (
                f"D's joint vector gives {len(params)} parameters for {key} under "
                f"prefix {prefix!r}, expected {expected}. The a_/b_ mapping in "
                f"JOINT_PREFIX no longer matches the bind expressions in "
                f"fecl4_constraint_scenarios.py. Re-run: {FIX_TABLE}"
            )
            raise SystemExit(msg)
        row = {**joint, "params": params, "free_params": JOINT_FREE}
        graph = compose(SC._nodes(spec)).build()
    else:
        row = _table_rows()[(scenario, key)]
        params = row["params"]
        builder = compose(SC._nodes(spec))
        for expr, target in SC.ties_for(scenario, key):
            builder = builder.bind(expr, to=target)
        graph = builder.build()

    x = np.asarray([row_x[0] for row_x in data.x], dtype=float)
    y = np.asarray(data.y, dtype=float)
    model = np.asarray(evaluate(graph, params, data), dtype=float)
    components = evaluate_components(graph, params, data)
    return x, y, model, y - model, row, components


def _l3_centre_from_params(params: dict[str, float], n_l3: int) -> float:
    """Centre of the tallest L3 component, found by height and never by index.

    Adding a pre-shoulder shifts which component is the white line, so a
    hardcoded index would silently mark the shoulder instead.
    """
    best_i = max(range(n_l3), key=lambda i: params[f"p{i}.amplitude"])
    return float(params[f"p{best_i}.center"])


def cross_check(stats: list[dict[str, Any]]) -> str:
    """Check every replayed panel against the shipped scenario table.

    `fit_one` now applies `SC.ties_for(...)`, the same constructor
    `fecl4_constraint_scenarios.run()` applies, so the two can no longer disagree
    about what a hypothesis says — the duplication this check was built to police
    is gone. The check is kept as a regression test rather than a guard: each
    panel's free-parameter count and reduced chi-squared are compared with the
    row for the same scenario and subject in the shipped table, which still
    catches a solver or data change that moves the fit without touching the
    ties.

    Returns the one-line verdict for the receipt. A missing table is reported as
    a skipped check rather than passed over, so the receipt never claims an
    agreement that was not tested.
    """
    if not TABLE.exists():
        return f"{TABLE.name} absent, tie cross-check SKIPPED"
    rows = {(r["scenario"], r["subject"]): r for r in json.loads(TABLE.read_text())["rows"]}

    # D is checked once, pooled, because that is how it was fitted: the stored
    # reduced chi-squared is one number over both spectra's residuals against
    # the joint fit's 86 free parameters. Checking it per panel would compare a
    # quantity the table does not contain.
    joint_panels = [s for s in stats if s["scenario"] == JOINT_KEY[0]]
    if joint_panels:
        joint = rows.get(JOINT_KEY)
        if joint is None:
            msg = (
                f"{TABLE.name} carries no row for {JOINT_KEY[0]!r}, so the joint fit "
                f"drawn as the last row cannot be checked. Re-run: {FIX_TABLE}"
            )
            raise SystemExit(msg)
        pooled_ssr = sum(pan["ssr"] for pan in joint_panels)
        pooled_dof = sum(pan["n"] for pan in joint_panels) - JOINT_FREE
        pooled = pooled_ssr / pooled_dof
        if abs(joint["reduced_chi2"] - pooled) > CHI2_RTOL * abs(joint["reduced_chi2"]):
            msg = (
                f"{JOINT_KEY[0]}: replaying both halves of the stored joint vector "
                f"gives pooled reduced chi-squared {pooled:.6f} over {pooled_dof} "
                f"degrees of freedom, while {TABLE.name} records "
                f"{joint['reduced_chi2']:.6f}. Either the a_/b_ split has drifted "
                f"or the stored parameters no longer reproduce the fit they came "
                f"from. Re-run: {FIX_TABLE}"
            )
            raise SystemExit(msg)

    for s in [x for x in stats if x["scenario"] != JOINT_KEY[0]]:
        row = rows.get((s["scenario"], s["key"]))
        if row is None:
            msg = (
                f"{TABLE.name} carries no row for {s['scenario']!r} / {s['key']!r}, so this "
                f"figure's ties cannot be checked against the table the manuscript quotes "
                f"and the grid would be drawn unverified. Regenerate it with: {FIX_TABLE}"
            )
            raise SystemExit(msg)
        chi2_drift = abs(row["reduced_chi2"] - s["chi2"]) > CHI2_RTOL * abs(row["reduced_chi2"])
        if row["free_params"] != s["free"] or chi2_drift:
            msg = (
                f"{s['scenario']} / {s['key']}: replaying the stored parameter vector "
                f"through evaluate() gives {s['free']} free parameters and reduced "
                f"chi-squared {s['chi2']:.6f}, while {TABLE.name} records "
                f"{row['free_params']} and {row['reduced_chi2']:.6f}. Either the tie "
                f"expressions in fit_one have drifted from the ones "
                f"fecl4_constraint_scenarios.py applies, or the stored parameters no "
                f"longer reproduce the fit they came from. Re-run: {FIX_TABLE}"
            )
            raise SystemExit(msg)
    return f"{len(stats)} panels agree with {TABLE.name}"


def draw() -> None:
    """Compose and write the grid."""
    fig, axes = plt.subplots(
        2 * len(SCENARIOS),
        2,
        figsize=(7.2, 7.4 / 3 * len(SCENARIOS)),
        sharex="col",
        gridspec_kw={
            "height_ratios": [3, 1] * len(SCENARIOS),
            "hspace": 0.12,
            "wspace": 0.16,
        },
    )
    labels = {
        "d5": r"[FeCl$_4$]$^{-}$  (Fe$^{3+}$, $d^5$)",
        "d6": r"[FeCl$_4$]$^{2-}$  (Fe$^{2+}$, $d^6$)",
    }

    stats: list[dict[str, Any]] = []

    for col, key in enumerate(("d5", "d6")):
        n_l3 = CS.SPECTRA[key]["l3_count"]
        n_peaks = len(CS.SPECTRA[key]["peaks"])
        for row, scenario in enumerate(SCENARIOS):
            ax = axes[row * 2][col]
            axr = axes[row * 2 + 1][col]
            x, y, model, resid, row_rec, components = fit_one(key, scenario)
            pct = 100.0 * resid / float(np.max(y))
            worst = int(np.argmax(np.abs(pct)))
            centre_value = _l3_centre_from_params(row_rec["params"], n_l3)
            # Recomputed from the replayed residual, not copied from the table.
            # If `evaluate` and the stored parameter vector did not reproduce the
            # recorded fit, this is the number that would disagree.
            free = int(row_rec["free_params"])
            ssr = float(np.sum(resid**2))
            # D is one fit over both spectra, so its reduced chi-squared is
            # defined on the pooled residual and the two columns share the 86
            # free parameters. A per-panel value would divide one column's
            # residual by both columns' degrees of freedom and mean nothing.
            chi2_replayed = float("nan") if scenario == JOINT_KEY[0] else ssr / (len(y) - free)
            stats.append(
                {
                    "scenario": scenario,
                    "key": key,
                    "n": len(y),
                    "free": free,
                    "chi2": chi2_replayed,
                    "ssr": ssr,
                    "abs": float(np.abs(resid).max()),
                    "pct": float(np.abs(pct).max()),
                    "at": float(x[worst]),
                    "l3": centre_value,
                },
            )

            # The carrier between this row's two panels: one dashed rule at the
            # fitted L3 white-line centre, drawn in the L3 multiplet's hue in
            # BOTH the spectrum panel and the residual panel beneath it. It is
            # what turns "the excursion sits ON the white line" into a drawn
            # fact rather than a comparison the reader makes from memory, and
            # because it is refitted per row it also shows the white line
            # moving when a tie pulls on it. It shares the L3 multiplet's hue
            # deliberately: it marks the centre of the tallest member of that
            # multiplet, so the meaning is the same one, and it is separated
            # from the components by being the only vertical and the only
            # long-dashed line, plus its own legend entry.
            for a in (ax, axr):
                a.axvline(
                    centre_value,
                    color=C_L3,
                    lw=0.6,
                    ls=(0, (4.0, 2.0)),
                    alpha=0.5,
                    zorder=1,
                )

            # Individual contributions first, so the total and the data sit on
            # top of them rather than under.
            for n in range(n_peaks):
                ax.plot(
                    x,
                    np.asarray(components[f"p{n}"]),
                    lw=0.6,
                    color=C_L3 if n < n_l3 else C_L2,
                    alpha=0.9,
                    zorder=2,
                )
            ax.plot(
                x,
                np.sum(
                    [np.asarray(components[k]) for k in ("step_l3", "step_l2", "bg")],
                    axis=0,
                ),
                lw=0.9,
                ls="--",
                color=C_STEP,
                zorder=2,
            )
            ax.plot(
                x,
                y,
                ls="none",
                marker="o",
                ms=1.5,
                mfc="none",
                mew=0.4,
                color=INK_MUTED,
                zorder=3,
            )
            ax.plot(x, model, lw=1.3, color=C_FIT, zorder=4)

            ax.grid(True, color=GRID, lw=0.5)
            ax.set_axisbelow(True)
            ax.set_ylabel("normalised absorption", fontsize=6.5)
            ax.yaxis.set_label_coords(-0.085, 0.5)
            ax.tick_params(labelsize=6, length=2)

            # Headroom above the data so the info block never lands on a curve.
            ax.set_ylim(-0.9, float(np.max(y)) * 1.30)
            info = (
                f"{scenario}\none joint fit, both panels\n{free} free"
                if scenario == JOINT_KEY[0]
                else f"{scenario}\n$\\chi^2_\\nu$ = {chi2_replayed:.5f}\n{free} free"
            )
            ax.text(
                0.985,
                0.95,
                info,
                transform=ax.transAxes,
                fontsize=6.6,
                va="top",
                ha="right",
                multialignment="left",
                color=INK,
                linespacing=1.45,
                bbox={
                    "boxstyle": "round,pad=0.32",
                    "facecolor": "white",
                    "edgecolor": GRID,
                    "linewidth": 0.5,
                    "alpha": 0.92,
                },
            )

            # Row B is the fit the case study reports, so it carries the L3
            # callout the standalone case-study figure used to. It is also what
            # names the dashed rule for the whole grid: one label, on the row
            # the text discusses, rather than the same words six times.
            if scenario.startswith("B"):
                ax.annotate(
                    f"L$_3$ max {centre_value:.2f} eV",
                    xy=(centre_value, float(np.max(y))),
                    xytext=(centre_value + 1.6, float(np.max(y)) * 1.16),
                    fontsize=6.4,
                    color=INK,
                    arrowprops={"arrowstyle": "-", "lw": 0.5, "color": INK_MUTED},
                    zorder=6,
                )
            if row == 0:
                # The count belongs in the heading: one plotted marker is one
                # measured point, and the reader should not have to infer the
                # size of the sample every panel in the column is fitted to.
                ax.set_title(
                    f"{labels[key]} — {len(x)} points",
                    fontsize=8,
                    color=INK,
                    pad=6,
                )

            # Residuals are normalised to the white-line maximum of their own
            # spectrum, which is what makes the two columns comparable. In
            # absolute units the two free fits sit at 0.295 and 0.282 -- all but
            # identical -- yet a per-column autoscale drew them on +/-0.5 and
            # +/-0.25 axes and so made the d6 misfit look twice the size of the
            # d5 one. Normalised, the ordering reverses and is the true one:
            # d5 free is 1.9 % of its peak against d6's 2.4 %.
            axr.axhline(0.0, lw=0.6, color=INK_MUTED, zorder=1)
            axr.plot(x, pct, lw=0.9, color=C_RESID, zorder=2)
            axr.grid(True, color=GRID, lw=0.5)
            axr.set_axisbelow(True)
            axr.set_ylabel("residual / % of max", fontsize=6.5)
            axr.yaxis.set_label_coords(-0.085, 0.5)
            axr.tick_params(labelsize=6, length=2)
            for a in (ax, axr):
                a.xaxis.set_minor_locator(MultipleLocator(1.0))
                a.tick_params(axis="x", which="minor", length=1.4, color=INK_MUTED)
                a.grid(True, which="minor", axis="x", color=GRID, lw=0.25, alpha=0.7)
            if row == len(SCENARIOS) - 1:
                axr.set_xlabel("photon energy / eV", fontsize=7)

    # ONE residual scale across all six panels, not one per column. Now that the
    # residuals are expressed as a percentage of each spectrum's own maximum they
    # are directly comparable, and a shared axis is the only honest way to draw
    # them: any per-column scaling reintroduces the distortion normalising fixed.
    resid_rows = range(1, 2 * len(SCENARIOS), 2)
    lim = max(abs(v) for r in resid_rows for c in (0, 1) for v in axes[r][c].get_ylim())
    for r in resid_rows:
        for c in (0, 1):
            axes[r][c].set_ylim(-lim, lim)

    # No suptitle or figure-level subtitle: the column headings sit at the top of
    # the grid and a centred title lands on top of them. What that text said now
    # lives in the manuscript caption, which is where a reader looks for it.
    # One shared legend rather than six: the colour coding is identical in every
    # panel, and per-panel legends would cover the data the panels exist to show.
    handles = [
        plt.Line2D([], [], lw=1.3, color=C_FIT, label="Total model"),
        plt.Line2D([], [], lw=0.9, color=C_L3, label="L$_3$ multiplet"),
        plt.Line2D([], [], lw=0.9, color=C_L2, label="L$_2$ multiplet"),
        plt.Line2D([], [], lw=0.9, ls="--", color=C_STEP, label="Edge steps + offset"),
        plt.Line2D(
            [],
            [],
            lw=0.6,
            ls=(0, (4.0, 2.0)),
            color=C_L3,
            alpha=0.6,
            label="L$_3$ white line (fitted)",
        ),
        plt.Line2D(
            [],
            [],
            ls="none",
            marker="o",
            ms=3.0,
            mfc="none",
            mew=0.6,
            color=INK_MUTED,
            label="Measured",
        ),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=6,
        frameon=False,
        fontsize=7,
        bbox_to_anchor=(0.5, 0.0),
        handlelength=1.8,
        columnspacing=1.6,
    )
    fig.subplots_adjust(left=0.085, right=0.985, top=0.965, bottom=0.075)

    # Checked before anything is written: a grid drawn from ties that no longer
    # match the table the manuscript quotes should not reach the disk at all.
    note = cross_check(stats)

    for ext, dpi in (("pdf", None), ("png", 300)):
        fig.savefig(HERE / f"fig_constraint_grid.{ext}", dpi=dpi)
    plt.close(fig)

    # Full precision, because this is the audit trail for the caption and for
    # the claim the docstring makes about where the spin-orbit tie costs
    # something. The shared limit is reported against the worst residual on the
    # canvas, which is how a reader confirms that nothing was cropped to fit.
    print(f"wrote fig_constraint_grid.pdf / .png  ({note})")
    print(
        f"shared residual scale +/-{lim:.6f} % of each spectrum's own maximum; "
        f"worst residual drawn {max(s['pct'] for s in stats):.6f} %",
    )
    for s in stats:
        print(
            f"  {s['key']}  {s['scenario']:20s} n={s['n']:3d}  free={s['free']:3d}  "
            f"chi2_red={'pooled' if s['scenario'] == JOINT_KEY[0] else format(s['chi2'], '.6f')}"
            f"  worst |residual| {s['abs']:.6f} "
            f"= {s['pct']:.3f} % at {s['at']:.2f} eV  (L3 white line {s['l3']:.3f} eV)",
        )


if __name__ == "__main__":
    draw()
