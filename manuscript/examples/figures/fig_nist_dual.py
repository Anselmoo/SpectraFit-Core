"""Figure: NIST StRD residual structure and certified-value agreement, side by side.

Left, the observations with the fitted curve. Middle, the residual. Right, the
agreement of the least accurately recovered parameter with its certified value.

**Why one fitted curve and not two.** The intent was to draw spectrafit-core's fit
against lmfit's. They cannot be told apart: across all 22 datasets the largest
divergence between the two fitted curves is 1.0e-3 in y, on Thurber, and at most
7.7e-5 % of a dataset's own range, on Rat43; on twelve of them it is below 1e-7.
Two lines would superimpose exactly and imply a comparison the picture cannot
make. Both bounds are recomputed at render time and printed in the title, because
an earlier version transcribed a single "0.0001 %" into the title and attributed
it to Thurber -- whose relative divergence is 7.2e-5 %, while the dataset that
actually sets the relative bound is Rat43.

That is the point rather than a limitation, and it is the paper's own argument
about FitBenchmarking in miniature: both solvers agree on the curve, and the
difference between them is only visible in the significant figures of the
recovered parameters -- which is what the right-hand panel plots, for both
backends, as a dumbbell per row. A reader who looks only at fits would conclude
the two are equivalent.

Five choices about space, each made because at 22 datasets the earlier layout
wasted most of its area:

* **The agreement axis is cropped just below the pass threshold**, not started at
  zero: ``x_lo`` is ``THRESHOLD - 0.35``, so the threshold rule itself is on the
  canvas with visible empty space to its left. That emptiness is the disclosure --
  a reader sees that nothing comes near failing rather than being told so. An
  axis from 0 spent a third of the panel on the same emptiness; the reclaimed
  width goes to separating per-parameter ticks that previously overlapped on
  Hahn1 and Gauss3. The worst-parameter dots span 6.50 to 10.59, but the
  per-parameter ticks drawn behind them run out to 11.89 on Gauss2, so the axis
  is sized to the ticks, not to the dots.
* **Each residual carries its own amplitude**, printed at its left edge. "Each on
  its own scale" is the right choice for comparing shape, but stated only in a
  caption a reader still compares heights across rows and concludes Gauss1 is
  noisier than BoxBOD. The number makes the caveat visible where the eye is, and
  the middle column's header repeats it.
* **Row heights scale with the observation count.** A 6-point dataset does not
  need the height a 250-point one does, and the difference buys legibility
  exactly where the points are dense. The spread is deliberately narrow -- the
  ratio runs 1.00 to 1.55 -- so the 6-point rows still resolve their residual.
* **Marker size and opacity scale down above 100 points.** At 250 points uniform
  markers merged into a grey smear that hid the fitted line -- which mattered,
  because the claim being made is that the two fits are indistinguishable, and a
  reader has to be able to see the line to check it.
* **One compact legend under the axis** rather than three lines of title, so the
  vertical space goes to data.

Three further design choices, each made because the earlier single-panel version
stopped working once coverage reached 22 datasets:

* **A residual column of its own.** The residual is the diagnostic the fitted curve
  hides: Kirby2's lone outlier and Bennett5's structure are visible there and
  invisible at thumbnail scale in the data panel.
* **Ticks, not circles, for the per-parameter values.** Gauss1-3 and Hahn1/Thurber
  carry seven or eight parameters each, so open circles produced roughly 110
  overlapping marks competing with the 22 that carry the claim.
* **Tier grouping.** NIST's difficulty tier is the axis a numerical-methods
  reader looks at first, so it is carried by vertical position, a left-margin
  bracket, a boundary rule, a band label and an ordered ink -- deliberately not
  by hue alone; see the grouping note below for the three tries that were.

**The row-alignment bug this version fixes.** The agreement panel is one tall
axis spanning every row (so the threshold rule and the tier bands are unbroken),
but the rows themselves have unequal heights. Placing each dataset's mark at a
uniform integer y therefore drifted it away from its own row: measured against
the previous layout, the displacement ran from -79 px at Rat42 to +50 px at
DanWood at 300 dpi, against a mean row pitch of 127 px -- up to 62 % of a row, and
with the sign flipping down the figure, so in the middle a reader tracking across
from a name landed nearer a neighbour's dot. Marks are now placed at each row's
real centre, taken from the ``GridSpec`` geometry, and the tier bands break in the
gutters between rows. Equal row heights would have fixed it too, at the cost of
the third bullet above.

**Why the tier ink is one hue in three steps.** Difficulty is ordinal -- Higher
beats Average beats Lower -- and three unrelated hues cannot say so. The previous
scheme spent ``#b03a8f``/``#9c5f00``/``#0067d6`` on the three tiers, which are
exactly the three hues ``fig_benchmark_profile.py`` gives to scipy-ls-trf, lmfit
and spectrafit-core: in a figure whose whole claim is that spectrafit-core and
lmfit agree, colouring rows in those two backends' own inks is the worst available
collision. Those three meanings are declined here. Their measured cost was also
real: the three had relative luminances within 1.07x of each other, so they were
the same grey in a greyscale print. The indigo family is the one chart direction
no figure spends on a backend -- ``fig_benchmark_profile.py`` draws scipy-ls-trf
in the magenta above, not in the ``--c-scipy-ls-trf`` token that names it. Indigo's
one other canvas use is ``fig_ladder_stability.py``'s seed-sweep axis -- a per-run
deviation cloud with no backend meaning, which no reader can confuse with a
fitted curve. All three steps clear 4.5:1 on white because the row name is set
in them, and a single-hue ramp is CVD-safe by construction.

**Tier membership is carried by position, not by the ink.** Three attempts to
make hue do it failed in the same way. The first spread the three steps 5.87x in
luminance; the second widened that to 12.33x; the third derived them as one ink
at three opacities so the ordering could not be mis-picked. Each was a better
ORDINAL encoding than the last, and none fixed the actual complaint, which was
that a reader cannot say *which tier this row is in* without comparing its ink
against two others up to twenty rows away, from memory. That is not a contrast
problem, so contrast did not solve it: colour is simply a poor grouping channel
at 22 rows of this height.

``_tier_grouping`` moves membership to position -- a serifed bracket in the left
margin spanning each tier's rows, labelled, set beside the row NAMES where the
reader starts; and a hairline across the full width at each tier boundary, in the
gutter between two rows, so the grouping is visible in all three columns rather
than only where a band is drawn. The ink stays and stays ordinal, now redundant
with position rather than solely responsible -- the state every other encoding in
this figure is already held in.

**Both backends appear in the agreement panel, and only there.** The left column
still draws one curve, for the reason above. The right column draws two dots per
row joined by a connector, because that is where the difference between them is
not invisible: the fitted curves differ by 5e-14 to 8e-7 of a dataset's range,
while the parameters recovered from them differ by up to 3.46 significant figures
and by at least one on 17 of the 22 datasets. The dumbbell is that gap at the
scale it actually has.

**Three readability fixes, from the author failing to read his own panel.**
Shown the dumbbell, the author asked which of the two backends was the more
accurate one -- of a panel built to answer exactly that. Three causes, all
fixed here rather than explained away:

* A vestigial lollipop stem ran from the pass threshold to spectrafit-core's
  dot, passing *underneath* lmfit's ring. The row therefore read as one line
  with a ring sitting on it as a waypoint, not as two values with a gap. The
  dumbbell is now the only line on the row and spans exactly what it connects.
* Nothing said which marker was which without a trip to the legend two thousand
  pixels below. Both are now named in place, once, above the top row.
* The axis said what the quantity was and never which way was better. "More
  significant figures of agreement" is only obviously good if you already know
  the measure, so the axis now carries the direction in words.

None of the three is about the data, and none would have been found by checking
the numbers, which were right throughout.

This is also why the residual difference is NOT drawn, though it was asked for
and is cheap -- both ``resid`` arrays ship in the sidecar. Subtracting them
cancels the observations exactly (both fit the same y), leaving the difference of
the two fitted curves: a quantity of order 1e-8 of range, standing in for a
disagreement worth 3.46 significant figures. That is the substitution of
cost-function space for parameter space this paper faults FitBenchmarking for,
and reprising it inside our own figure would be worse than the original.

Reads `nist_head_to_head.json`, written by `nist_head_to_head.py`.

Run:  uv run --group manuscript python manuscript/examples/figures/fig_nist_dual.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib as mpl
import numpy as np
from matplotlib import pyplot as plt
from matplotlib.gridspec import GridSpec

mpl.use("Agg")

HERE = Path(__file__).resolve().parent
DATA = HERE / "nist_head_to_head.json"
STEM = "fig_nist_dual"
sys.path.insert(0, str(HERE))
from extract_bench_summary import nist_difficulty_tiers

# Difficulty is ordinal, so the tier key is one hue in three lightness steps
# rather than three hues. See the docstring for the three declined meanings
# (scipy-ls-trf, lmfit and spectrafit-core in fig_benchmark_profile.py) and the
# one knowingly shared with fig_ladder_stability.py's seed axis.
#
# These three do NOT carry the grouping on their own — see `_tier_grouping`.
# Three steps of one hue are the right ORDINAL encoding and were twice the wrong
# GROUPING one: a reader asked to say which tier a row belongs to has to compare
# its ink against two others several rows away, from memory. Position does that
# without being asked, so the bracket and the rules below carry membership and
# the ink now only carries rank.
TIER_INK = {"Higher": "#151353", "Average": "#322e9e", "Lower": "#605cde"}
TIER_ORDER = ("Higher", "Average", "Lower")
# The attention hue, spent on the one line every dot is measured against and on
# nothing else in this figure.
C_THRESHOLD = "#d30f45"
# The comparator's outline. Deliberately NOT lmfit's brand green from
# palette.css: on this panel the row's own tier ink already carries meaning, and
# a third saturated hue per row would compete with it. An unfilled ring in a
# neutral ink reads as "the other one" without claiming a channel.
C_RIVAL = "#5b5b60"
INK, INK_MUTED, GRID = "#1d1d1f", "#6e6e73", "#e3e3e0"
THRESHOLD = 4.0
# Layer ladder: 0 background bands, 1 reference rules, 2 raw/secondary marks,
# 3 the primary line, 5 the emphasised mark, 6 every label.
Z_BAND, Z_RULE, Z_RAW, Z_LINE, Z_MARK, Z_LABEL = 0, 1, 2, 3, 5, 6


def load() -> list[dict]:
    """Rows grouped hardest tier first, worst agreement first within a tier."""
    if not DATA.exists():
        msg = f"{DATA} not found — run nist_head_to_head.py first"
        raise SystemExit(msg)
    rows = json.loads(DATA.read_text())
    tiers = nist_difficulty_tiers()
    unknown = sorted(r["name"] for r in rows if r["name"].lower() not in tiers)
    if unknown:
        msg = (
            f"no NIST difficulty tier for {', '.join(unknown)} — rows are grouped, "
            "banded and inked by tier, so an unknown dataset would be drawn in the "
            "wrong band and would silently change the tier counts printed on the "
            "canvas; add its fixture under python/oracles/nist_strd/ or repair the "
            "Difficulty line the fixture is parsed for"
        )
        raise SystemExit(msg)
    for r in rows:
        r["tier"] = tiers[r["name"].lower()]
    return sorted(
        rows,
        key=lambda r: (TIER_ORDER.index(r["tier"]), r["spectrafit"]["lre"]),
    )


def curve_divergence(rows: list[dict]) -> tuple[float, str, float, str]:
    """Largest spectrafit-core/lmfit fitted-curve gap, absolute and range-relative.

    Returns ``(max |dy|, its dataset, max |dy| / range, its dataset)``. The two
    need not name the same dataset, which is why both are derived and printed
    rather than one being transcribed into the title.
    """
    d_abs = d_rel = 0.0
    who_abs = who_rel = ""
    for r in rows:
        ys = np.asarray(r["y"], dtype=float)
        gap = float(
            np.max(
                np.abs(
                    np.asarray(r["spectrafit"]["resid"], dtype=float)
                    - np.asarray(r["lmfit"]["resid"], dtype=float),
                ),
            ),
        )
        rel = gap / float(ys.max() - ys.min())
        if gap > d_abs:
            d_abs, who_abs = gap, r["name"]
        if rel > d_rel:
            d_rel, who_rel = rel, r["name"]
    return d_abs, who_abs, d_rel, who_rel


def _tier_grouping(fig: plt.Figure, rows: list[dict], boxes: list) -> None:
    """Carry tier membership by position: a left bracket and a full-width rule.

    The ink alone could not do this, twice. Three lightness steps of one hue are
    the correct ordinal encoding -- Higher darker than Average darker than Lower,
    which three unrelated hues cannot say -- but ordinal is not the same question
    as *which group is this row in*. Answering that from ink means holding two
    other inks in memory and comparing against rows that may be twenty away. Two
    rounds of widening the steps (5.87x, then 12.33x) did not fix it, because the
    difficulty was never contrast: colour is a poor grouping channel at this row
    count and this row height, however far apart the steps are pushed.

    So membership moves to position, which needs no comparison at all:

    * A bracket in the left margin spanning each tier's rows, serifed at both
      ends and labelled, set beside the row NAMES -- where the reader starts, and
      where the ink was doing the most work and failing.
    * A hairline across the full width at each tier boundary, so the grouping is
      visible in all three columns rather than only where a band is drawn. It
      sits in the gutter between two rows, never over one.

    The ink stays, and stays ordinal. It is now redundant with position rather
    than solely responsible -- the state the rest of this figure already holds
    its encodings in (see the marker-size and dashed-line redundancies above).
    """
    bracket_x, label_x, serif = 0.034, 0.017, 0.008
    start = 0
    for tier in TIER_ORDER:
        k = sum(1 for r in rows if r["tier"] == tier)
        if not k:
            continue
        y_top, y_bot = boxes[start].y1, boxes[start + k - 1].y0
        ink = TIER_INK[tier]
        fig.add_artist(
            plt.Line2D(
                [bracket_x] * 2,
                [y_bot, y_top],
                color=ink,
                lw=1.1,
                transform=fig.transFigure,
            ),
        )
        for y in (y_bot, y_top):
            fig.add_artist(
                plt.Line2D(
                    [bracket_x, bracket_x + serif],
                    [y] * 2,
                    color=ink,
                    lw=1.1,
                    transform=fig.transFigure,
                ),
            )
        fig.text(
            label_x,
            (y_bot + y_top) / 2,
            # "Higher (7)" sits in the left margin of a figure whose subject is
            # accuracy, so it reads as "higher accuracy" to anyone who does not
            # already know NIST's tier names. The word it was missing is the one
            # that says which scale it belongs to.
            f"{tier} difficulty ({k})",
            ha="center",
            va="center",
            rotation=90,
            fontsize=6.8,
            color=ink,
            fontweight="bold",
        )
        # The boundary rule goes in the gutter ABOVE this group, so the topmost
        # group gets none: a rule there would float above the first row with
        # nothing on its far side to separate it from.
        if start:
            y_gap = (boxes[start - 1].y0 + boxes[start].y1) / 2
            fig.add_artist(
                plt.Line2D(
                    [bracket_x, 0.985],
                    [y_gap] * 2,
                    color=GRID,
                    lw=0.7,
                    transform=fig.transFigure,
                    zorder=0,
                ),
            )
        start += k


def plot(rows: list[dict]) -> None:
    """Render the dual figure to PDF and 300 dpi PNG."""
    mpl.rcParams.update(
        {
            "font.size": 8,
            "axes.labelsize": 8,
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
    n = len(rows)
    # Two decimals collapsed Thurber (6.496) and MGH09 (6.498) onto one printed
    # "6.50" -- two distinct values reading as one, on the two rows the text
    # singles out as the weakest and second weakest. Print whatever precision it
    # takes to keep every row's label distinct, the same for all rows so the
    # column stays comparable.
    lre_dp = next(
        (
            dp
            for dp in (2, 3, 4)
            if len({f"{r['spectrafit']['lre']:.{dp}f}" for r in rows}) == len(rows)
        ),
        4,
    )
    counts = np.array([r["n"] for r in rows], dtype=float)
    # Taller rows where the points are dense; a 6-point set needs no more height
    # than its curve.
    ratios = 1.0 + 0.55 * (np.log10(counts) - np.log10(counts.min())) / (
        np.log10(counts.max()) - np.log10(counts.min())
    )
    fig = plt.figure(figsize=(8.4, 0.335 * float(ratios.sum()) + 1.27))
    gs = GridSpec(
        n,
        3,
        figure=fig,
        width_ratios=[1.25, 0.85, 2.35],
        height_ratios=list(ratios),
        hspace=0.34,
        wspace=0.20,
        left=0.128,
        right=0.985,
        top=0.945,
        bottom=0.052,
    )

    # The agreement panel spans every row as one axis so the threshold rule and
    # the tier bands are unbroken, but the rows have unequal heights — so its y
    # coordinate is the fraction of that span, and each mark is placed at its own
    # row's real centre rather than at a uniform integer.
    boxes = [gs[i, 0].get_position(fig) for i in range(n)]
    span = gs[:, 2].get_position(fig)

    def frac(y: float) -> float:
        """Figure-space y as a fraction of the agreement panel's own span."""
        return (y - span.y0) / (span.y1 - span.y0)

    centres = [frac((b.y0 + b.y1) / 2) for b in boxes]
    # Band edges sit in the gutter between two rows, and flush at top and bottom.
    edges = [1.0, *[frac((boxes[i].y0 + boxes[i + 1].y1) / 2) for i in range(n - 1)], 0.0]
    tick_h = 0.20 / n

    lre_all = [v for r in rows for v in r["per_param"].values()]
    x_lo, x_hi = THRESHOLD - 0.35, max(lre_all) * 1.035
    ax_lre = fig.add_subplot(gs[:, 2])

    for i, r in enumerate(rows):
        y = centres[i]
        colour = TIER_INK[r["tier"]]
        xs = np.asarray(r["x"], dtype=float)
        ys = np.asarray(r["y"], dtype=float)
        res = np.asarray(r["spectrafit"]["resid"], dtype=float)
        fitted = ys - res
        order = np.argsort(xs, kind="stable")

        # ---- left: observations with the fitted curve over them
        axd = fig.add_subplot(gs[i, 0])
        dense = r["n"] > 100
        axd.plot(
            xs,
            ys,
            ls="none",
            marker="o",
            ms=1.0 if dense else 1.9,
            mfc="none",
            mew=0.3 if dense else 0.5,
            color=INK_MUTED,
            alpha=0.35 if dense else 0.8,
            zorder=Z_RAW,
        )
        axd.plot(xs[order], fitted[order], lw=1.15, color=colour, zorder=Z_LINE)
        for side in ("top", "right", "bottom", "left"):
            axd.spines[side].set_visible(False)
        axd.set_xticks([])
        axd.set_yticks([])
        axd.text(
            -0.045,
            0.5,
            f"{r['name']}",
            transform=axd.transAxes,
            ha="right",
            va="center",
            fontsize=7.2,
            color=colour,
            fontweight="bold",
            zorder=Z_LABEL,
        )
        axd.text(
            -0.045,
            0.12,
            f"{r['n']}pt · {r['n_params']}p",
            transform=axd.transAxes,
            ha="right",
            va="center",
            fontsize=5.5,
            color=INK_MUTED,
            zorder=Z_LABEL,
        )

        # ---- middle: the residual, with its own amplitude printed
        axs = fig.add_subplot(gs[i, 1])
        lim = float(np.max(np.abs(res))) or 1.0
        # No band behind the trace. There was one, spanning +/- lim/3 -- one third
        # of the row's own maximum excursion, which is arithmetic, not a quantity.
        # Every convention a reader brings says a band behind a residual is a
        # tolerance, a +/-1 sigma envelope or the certified uncertainty, and that
        # excursions outside it are outliers; this one meant none of those and the
        # trace left it on most rows. An unkeyed encoding that invites a specific
        # false reading is worse than no encoding. The zero rule stays: that one
        # does carry meaning.
        axs.axhline(0.0, lw=0.4, color=GRID, zorder=Z_RULE)
        axs.plot(np.arange(res.size), res, lw=0.6, color=colour, zorder=Z_LINE)
        axs.set_ylim(-lim * 1.25, lim * 1.25)
        axs.set_xlim(-1, res.size)
        for side in ("top", "right", "bottom", "left"):
            axs.spines[side].set_visible(False)
        axs.set_xticks([])
        axs.set_yticks([])
        axs.text(
            0.0,
            0.98,
            f"$\\pm${lim:.3g}",
            transform=axs.transAxes,
            ha="left",
            va="top",
            fontsize=5.4,
            color=INK_MUTED,
            zorder=Z_LABEL,
        )

        # ---- right: worst-parameter agreement, every parameter as a tick
        #
        # Both backends, as a dumbbell. This is the one panel where drawing lmfit
        # says something the data panel cannot: the two fitted CURVES differ by
        # between 5e-14 and 8e-7 of a dataset's range, which is why only one is
        # drawn to the left, while the parameters they recover differ by up to
        # 3.46 significant figures, and by at least one on 17 of the 22. The gap
        # between the two dots is that difference, drawn at the scale it actually
        # has. Plotting the residual difference instead would put a 1e-8 wiggle
        # where a 3.46-significant-figure disagreement belongs -- the same
        # substitution of cost-function space for parameter space that this paper
        # faults FitBenchmarking for, so it is declined here rather than reprised.
        worst = r["spectrafit"]["lre"]
        rival = r["lmfit"]["lre"]
        # No stem back to the threshold. It was this panel's lollipop stem when
        # there was one dot per row; with two it ran from the threshold to
        # spectrafit-core's dot *underneath* lmfit's ring, so the row read as a
        # single line with the ring as a waypoint on it. The dumbbell is the only
        # line here now, and it spans exactly the two values it connects.
        for v in r["per_param"].values():
            ax_lre.plot(
                [v, v],
                [y - tick_h, y + tick_h],
                lw=0.9,
                color=colour,
                alpha=0.5,
                zorder=Z_LINE,
            )
        # The connector is drawn in the tier ink but under both dots, so the gap
        # reads as one object rather than two unrelated marks on a shared row.
        ax_lre.plot([rival, worst], [y, y], lw=1.6, color=colour, alpha=0.55, zorder=Z_RAW)
        ax_lre.plot(
            [rival],
            [y],
            "o",
            ms=4.6,
            mfc="white",
            mec=C_RIVAL,
            mew=1.1,
            zorder=Z_MARK,
        )
        ax_lre.plot([worst], [y], "o", ms=5.2, color=colour, zorder=Z_MARK)
        # No in-panel marker labels. They were added when the legend said only
        # "fit (lmfit's coincides)" and named neither dot, so the panel could not
        # be read without a trip to it. The legend now names both backends
        # outright, which makes a second naming inside the panel a duplicate on
        # the row that can least afford one.
        # The number is spectrafit-core's, so it is anchored to spectrafit-core's
        # dot rather than to the left end of the dumbbell -- at the left end it
        # sits beside lmfit's ring on the 21 rows where lmfit is the lower of the
        # two, and reads as labelling it. It carries a white bbox because on that
        # anchor it lands on the connector. Only one number per row is printed:
        # two across 22 rows is a table, and Table 4 already is that table, with
        # all four solvers.
        # ...except where the two nearly coincide, and the bbox anchored to
        # spectrafit-core's dot would cover lmfit's ring outright (BoxBOD, MGH09
        # and Hahn1 sit inside 0.6 of a significant figure). There the label goes
        # left of both, which costs nothing: at that separation there is no dot
        # it could be read as belonging to in preference to the other.
        anchor = worst if abs(worst - rival) >= 1.0 else min(worst, rival)
        ax_lre.annotate(
            f"{worst:.{lre_dp}f}",
            xy=(anchor, y),
            xytext=(-7, 0),
            textcoords="offset points",
            ha="right",
            va="center",
            fontsize=6.4,
            color=colour,
            zorder=Z_LABEL,
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.8},
        )

    start = 0
    for tier in TIER_ORDER:
        k = sum(1 for r in rows if r["tier"] == tier)
        if not k:
            continue
        hi, lo = edges[start], edges[start + k]
        ax_lre.axhspan(lo, hi, color=TIER_INK[tier], alpha=0.045, zorder=Z_BAND)
        start += k

    _tier_grouping(fig, rows, boxes)

    ax_lre.axvline(THRESHOLD, color=C_THRESHOLD, lw=1.2, zorder=Z_RULE)
    ax_lre.set_xlim(x_lo, x_hi)
    ax_lre.set_ylim(0.0, 1.0)
    ax_lre.set_yticks([])
    # No x label. The direction cue used to live here, under the ticks, which is
    # roughly three thousand pixels below the column header that names the
    # measure -- so a reader met the dots, tried to read them, and only then met
    # the sentence saying which way was better. Both belong at the point of first
    # contact, so both are now in the column header above. The caption carries
    # the definition of the measure itself.
    ax_lre.grid(True, axis="x", color=GRID, lw=0.5)
    ax_lre.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax_lre.spines[side].set_visible(False)

    # Each column is a different question, so each is named where it starts --
    # including the third, which used to rely on its own axis label at the foot
    # of the panel. That label now carries only the direction, so the column was
    # unnamed at the top while its two neighbours were named.
    head_y = boxes[0].y1 + 0.006
    for col, text in (
        (0, "observations · fitted curve"),
        (1, "residual · each on its own scale"),
        # The header names the quantity, the direction AND the two markers. The
        # markers were named only in the foot legend, which a reader meets some
        # three thousand pixels after the first dumbbell -- the same
        # distance-from-first-contact defect the direction cue was moved up here
        # to fix. "significant figures" is the quantity; without it the axis is a
        # bare 4-to-12 ruler and the caption is the only place it is defined.
        (
            2,
            # Balanced across two lines: quantity on the first, markers and
            # direction on the second. Carrying quantity + direction on one line
            # and the markers on the other overflowed the column and clipped
            # "more accurate" against the canvas edge.
            (
                "agreement with the certified value, in significant figures\n"
                "$\\bullet$ spectrafit-core   $\\circ$ lmfit"
                "   $\\longrightarrow$  further right is more accurate"
            ),
        ),
    ):
        box = gs[0, col].get_position(fig)
        fig.text(
            (box.x0 + box.x1) / 2,
            head_y,
            text,
            ha="center",
            va="bottom",
            fontsize=6.6,
            color=INK_MUTED,
        )

    n_pass = sum(1 for r in rows if r["spectrafit"]["lre"] >= THRESHOLD)
    d_abs, who_abs, d_rel, who_rel = curve_divergence(rows)
    handles = [
        plt.Line2D(
            [],
            [],
            ls="none",
            marker="o",
            ms=3.4,
            mfc="none",
            mew=0.6,
            color=INK_MUTED,
            label="observation",
        ),
        # "fit (lmfit's coincides)" named the backend that is NOT drawn and left
        # the one that is unnamed, so it read as lmfit's curve. The owner goes
        # first now. Same defect, same fix, in the two column headers below.
        plt.Line2D(
            [],
            [],
            lw=1.3,
            color=INK_MUTED,
            label="spectrafit-core fit",
        ),
        plt.Line2D(
            [],
            [],
            ls="none",
            marker="o",
            ms=5.2,
            color=INK_MUTED,
            label="spectrafit-core, worst parameter",
        ),
        plt.Line2D(
            [],
            [],
            ls="none",
            marker="o",
            ms=4.6,
            mfc="white",
            mec=C_RIVAL,
            mew=1.1,
            label="lmfit, same measure",
        ),
        plt.Line2D(
            [],
            [],
            lw=1.1,
            color=INK_MUTED,
            alpha=0.6,
            marker="|",
            ms=7,
            ls="none",
            label="other parameters",
        ),
        plt.Line2D([], [], lw=1.2, color=C_THRESHOLD, label=f"pass threshold ({THRESHOLD:g})"),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=6,
        frameon=False,
        fontsize=6.8,
        bbox_to_anchor=(0.5, 0.006),
        columnspacing=1.05,
    )
    fig.suptitle(
        f"{n} of 27 NIST StRD datasets — {n_pass}/{n} clear four significant figures\n"
        f"lmfit's fitted curve differs by at most {d_abs:.1e} in y ({who_abs}), "
        f"and by {100 * d_rel:.1e} % of the data range ({who_rel})",
        fontsize=7.4,
        color=INK_MUTED,
        y=0.995,
        va="top",
    )
    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"{STEM}.{ext}", dpi=300)
    plt.close(fig)

    worst_row = min(rows, key=lambda r: r["spectrafit"]["lre"])
    best_row = max(rows, key=lambda r: r["spectrafit"]["lre"])
    below = sum(1 for v in lre_all if v < x_lo)
    tiny = sum(1 for r in rows if _gap(r) < 1e-7)
    print(f"wrote {STEM}.pdf / .png")
    print(f"  datasets              {n} of 27 exercised; {n_pass} clear {THRESHOLD:g} sig figs")
    tier_counts = ", ".join(f"{t} {sum(1 for r in rows if r['tier'] == t)}" for t in TIER_ORDER)
    print(f"  tiers                 {tier_counts}")
    print(f"  worst dataset         {worst_row['name']} at {worst_row['spectrafit']['lre']:.15g}")
    print(f"  best dataset          {best_row['name']} at {best_row['spectrafit']['lre']:.15g}")
    print(f"  per-parameter LRE     {min(lre_all):.15g} to {max(lre_all):.15g}")
    n_lre = len(lre_all)
    print(f"  agreement axis        [{x_lo:.15g}, {x_hi:.15g}]; {below}/{n_lre} off scale")
    print(f"  curve gap, absolute   {d_abs:.15g} in y on {who_abs}")
    print(f"  curve gap, relative   {100 * d_rel:.15g} % of range on {who_rel}")
    print(f"  curve gap below 1e-7  {tiny} of {n} datasets")


def _gap(r: dict) -> float:
    """Largest absolute spectrafit-core/lmfit fitted-curve gap for one dataset."""
    return float(
        np.max(
            np.abs(
                np.asarray(r["spectrafit"]["resid"], dtype=float)
                - np.asarray(r["lmfit"]["resid"], dtype=float),
            ),
        ),
    )


if __name__ == "__main__":
    plot(load())
