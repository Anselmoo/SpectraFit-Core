"""Figure: agreement with NIST StRD certified values, per dataset.

Reads the sidecar written by `extract_bench_summary.py` and plots, for each NIST
Statistical Reference Dataset exercised, how many significant figures the fitted
parameters agree with the certified values to. The pass threshold is drawn as a
line, and every dataset's *worst* parameter is what is plotted — a dataset is
only as good as the parameter it recovers least well.

Reproduce:

    uv run --group manuscript python manuscript/examples/figures/extract_bench_summary.py <run-dir>
    uv run --group manuscript python manuscript/examples/figures/fig_nist_accuracy.py

Outputs, written next to this file:
    fig_nist_accuracy.pdf   vector, for submission
    fig_nist_accuracy.png   300 dpi raster

Two deliberate choices about honesty:

* The figure plots the per-dataset **minimum** across parameters, not the mean.
  A mean would let one badly-recovered parameter hide behind seven good ones,
  which is precisely the failure a certified-value check exists to catch. The
  full per-parameter spread is drawn behind the minimum as light ticks, so the
  reader can see what was averaged away and judge for themselves.
* Coverage is stated on the figure, not just in the caption. The suite exercises
  a subset of the datasets NIST publishes, and a plot showing only passes
  invites the reading that everything available was tried. The subtitle names
  both numbers.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import matplotlib as mpl
import numpy as np
from matplotlib import pyplot as plt

HERE = Path(__file__).resolve().parent
SUMMARY = HERE / "bench_summary.json"

# Single-hue encoding: this figure has one series (agreement), so magnitude is
# carried by position on a common axis and colour does no categorical work.
# Corporate tokens (docs/stylesheets/tokens/palette.css): systemBlue for the
# measured quantity, systemPink for the threshold line it must clear. Strokes
# use the AA-passing `-text` variants. Only one series here, so magnitude is
# carried by position on a common axis and hue does no categorical work.
# Colour encodes NIST's difficulty tier, from the --c-chart-* ramp
# (docs/stylesheets/tokens/palette.css). Three tiers is inside the two-hue
# ceiling problem noted there, so the tiers are ALSO ordered on the axis
# (hardest at top) and named in the y-tick labels' colour and the legend —
# hue is never the only carrier.
TIER_COLOUR = {
    "Higher": "#b03a8f",  # --c-chart-4
    "Average": "#9c5f00",  # --c-chart-2
    "Lower": "#0067d6",  # --c-chart-1
    "unknown": "#8e8e93",
}
C_UNKNOWN = "#8e8e93"
C_THRESHOLD = "#d30f45"  # systemPink-text — the pass threshold
INK = "#1d1d1f"
INK_MUTED = "#6e6e73"
GRID = "#e3e3e0"


def load_summary() -> dict:
    """Load the sidecar, failing with the command that produces it."""
    if not SUMMARY.exists():
        msg = (
            f"{SUMMARY} not found — run extract_bench_summary.py against a "
            "benchmark run directory first"
        )
        raise SystemExit(msg)
    return json.loads(SUMMARY.read_text())


def plot(summary: dict) -> None:
    """Render the NIST agreement figure to PDF and 300 dpi PNG."""
    nist = summary.get("nist")
    if not nist:
        msg = (
            "the sidecar carries no NIST block — the run's trust.json was "
            "missing or contained no nist_validation"
        )
        raise SystemExit(msg)

    # Group by NIST's own difficulty tier, hardest first. That is the axis a
    # numerical-methods reviewer reads: clearing Lower-difficulty datasets is
    # expected, clearing Higher-difficulty ones is the correctness claim.
    # Within a tier, worst agreement first.
    # matplotlib's y=0 is the BOTTOM, so Lower ranks first here in order to be
    # drawn lowest and leave Higher at the top, where the eye lands. Within a
    # tier, worst agreement sits highest — the two things a reviewer looks for
    # (hardest problem, weakest recovery) end up in the same corner.
    order = {"Lower": 0, "Average": 1, "Higher": 2, "unknown": 3}
    datasets = sorted(
        nist["datasets"],
        key=lambda d: (
            order.get(d.get("difficulty", "unknown"), 3),
            -(d.get("min_sig_figs") or 0.0),
        ),
    )
    threshold = nist.get("threshold_sig_figs") or 4.0

    mpl.rcParams.update(
        {
            "font.size": 8,
            "axes.labelsize": 8,
            "legend.fontsize": 7,
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "axes.edgecolor": INK_MUTED,
            "axes.linewidth": 0.6,
            "xtick.color": INK_MUTED,
            "ytick.color": INK_MUTED,
            "text.color": INK,
            "axes.labelcolor": INK,
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
        },
    )
    fig, ax = plt.subplots(figsize=(6.8, 0.38 * len(datasets) + 1.7))
    y = np.arange(len(datasets))

    all_vals = [v for d in datasets for p in d.get("params", []) if (v := p.get("sig_figs_agreed"))]
    mins = [d.get("min_sig_figs") or 0.0 for d in datasets]
    x_max = max([*all_vals, *mins, threshold]) * 1.16
    label_x = x_max * 0.995

    # Cleveland dot-plot, not bars. The quantity here is a THRESHOLD COMPARISON,
    # not a magnitude: a bar growing from zero implies "twice as long is twice
    # as good", which is wrong for significant figures of agreement, and the
    # per-parameter ticks became a secondary layer riding on top of that bar.
    # One hollow dot per parameter with the worst one filled says the same thing
    # with less ink, and stays readable if this ever scales to all 27 datasets.
    for i, d in enumerate(datasets):
        colour = TIER_COLOUR.get(d.get("difficulty", "unknown"), C_UNKNOWN)
        vals = [p.get("sig_figs_agreed") for p in d.get("params", [])]
        vals = [v for v in vals if v is not None]
        worst = d.get("min_sig_figs") or 0.0
        # connector from the threshold to the worst parameter: shows the margin
        # that actually matters, without implying a zero origin
        ax.plot([threshold, worst], [i, i], lw=0.8, color=colour, alpha=0.35, zorder=2)
        others = [v for v in vals if abs(v - worst) > 1e-9]
        if others:
            ax.plot(
                others,
                [i] * len(others),
                ls="none",
                marker="o",
                ms=4.0,
                mfc="none",
                mew=0.9,
                color=colour,
                alpha=0.75,
                zorder=3,
            )
        ax.plot([worst], [i], ls="none", marker="o", ms=5.5, color=colour, zorder=4)
        ax.annotate(
            f"{worst:.1f}",
            xy=(label_x, i),
            va="center",
            ha="right",
            fontsize=6.8,
            color=INK_MUTED,
        )

    ax.axvline(threshold, color=C_THRESHOLD, lw=1.3, zorder=1)
    ax.annotate(
        f"pass threshold: {threshold:g} significant figures",
        xy=(threshold, -0.72),
        xytext=(5, 0),
        textcoords="offset points",
        va="bottom",
        ha="left",
        fontsize=6.8,
        color=C_THRESHOLD,
    )

    ax.set_yticks(y)
    ax.set_yticklabels(
        [f"{d['name']}  ({d['n_params']}p)" for d in datasets],
    )
    for tick, d in zip(ax.get_yticklabels(), datasets, strict=True):
        tick.set_color(TIER_COLOUR.get(d.get("difficulty", "unknown"), C_UNKNOWN))
    ax.set_xlabel("significant figures of agreement with the certified value (LRE)")
    ax.set_xlim(0, x_max)
    ax.set_ylim(-0.95, len(datasets) - 0.3)
    ax.grid(True, axis="x", color=GRID, lw=0.5)
    ax.set_axisbelow(True)

    total = nist.get("total_available")
    tally = Counter(d.get("difficulty", "unknown") for d in datasets)
    tier_txt = " · ".join(f"{tally[t]} {t}" for t in ("Higher", "Average", "Lower") if tally[t])
    n_pass = sum(1 for d in datasets if d.get("passed"))
    # "N of 27" on its own invites "why these N?" — so the subtitle says what
    # the subset IS, not just how big it is.
    # The subset is bounded by what the compiled kernel set can express, not by
    # sampling and not by effort -- so the subtitle says which, and names the
    # remainder as a capability gap rather than an omission.
    ax.set_title(
        f"{len(datasets)} of {total} NIST StRD nonlinear-regression datasets — "
        f"{tier_txt} — {n_pass}/{len(datasets)} pass\n"
        f"every NIST model expressible in the compiled kernel set; the other "
        f"{total - len(datasets)} need kernels the library does not have",
        fontsize=7.2,
        color=INK_MUTED,
        loc="left",
        pad=8,
    )

    handles = [
        plt.Line2D(
            [],
            [],
            ls="none",
            marker="o",
            ms=5.5,
            color=TIER_COLOUR[t],
            label=f"{t} difficulty",
        )
        for t in ("Higher", "Average", "Lower")
        if tally[t]
    ]
    handles += [
        plt.Line2D(
            [],
            [],
            ls="none",
            marker="o",
            ms=4.0,
            mfc="none",
            mew=0.9,
            color=INK_MUTED,
            label="individual parameters",
        ),
        plt.Line2D([], [], lw=1.3, color=C_THRESHOLD, label="pass threshold"),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=len(handles),
        frameon=False,
        fontsize=6.8,
        bbox_to_anchor=(0.5, 0.012),
        columnspacing=1.4,
    )
    fig.subplots_adjust(left=0.21, right=0.985, top=0.90, bottom=0.80 / fig.get_figheight())
    for ext, dpi in (("pdf", None), ("png", 300)):
        fig.savefig(HERE / f"fig_nist_accuracy.{ext}", dpi=dpi)
    plt.close(fig)

    print("wrote fig_nist_accuracy.pdf / .png")
    print(f"  {len(datasets)} of {total} datasets — {tier_txt}; {n_pass}/{len(datasets)} pass")
    # `datasets` is sorted for PLOTTING (hardest tier first, worst agreement
    # first within a tier), which puts the best-agreeing Lower-tier dataset at
    # index 0 — not the worst. Reporting datasets[0] as "worst" printed
    # "Gauss1 (Lower) at 10.58" when the true worst is MGH09 at 6.50.
    worst_i = min(range(len(mins)), key=lambda i: mins[i])
    print(
        f"  worst: {datasets[worst_i]['name']} "
        f"({datasets[worst_i]['difficulty']}) at {mins[worst_i]:.2f} LRE",
    )


if __name__ == "__main__":
    plot(load_summary())
