r"""Figure: the reported speedup, tested for stability along two independent axes.

The manuscript quotes one geometric mean, taken from the deepest of five
repetition depths. The figure exists to support one sentence -- **the reported
16.45x does not depend on how often we timed it, or on which random data we
drew** -- and to show what the number is made of while it says so.

**Panel A, repetition depth** (`manuscript/examples/ladder/`). The same 151
cases, the same seed, timed 2, 5, 10, 25 and 50 times. Does the measurement
settle as you time more? Drawn as a scattered boxplot: every one of the 755
per-case measurements is a dot, the box gives the quartiles, and the aggregate
trend line rides on top so the headline is never lost in the cloud.

**Panel B, random seed** (`manuscript/examples/seed-sweep/`). 50 independent
seeds, all at one fixed effective depth of 5. Does the result depend on which
synthetic draw you got? Drawn as a violin with all 50 draws beeswarmed inside
it, so the density and the individual sample are both visible.

**The panels do NOT share a y-axis, and that is deliberate.** They plot
different KINDS of quantity: panel A is per-CASE (one number per problem, spread
over tens of per cent) and panel B is per-RUN (one number per whole 151-case
suite, spread over a few per cent). Any single scale serves one of them and
crushes the other -- which is exactly how two earlier versions of this figure
failed, once in each direction. Both axes are in the same units, per cent
deviation from the reported headline, and both are labelled with the kind of
quantity they carry; the scale change is made obvious by two connectors that
carry the seed range out of panel A and open it up into the whole of panel B.

**The tie between the panels is the shaded seed band.** The full seed-sweep
range is drawn across panel A as a thin band, and that is the comparison the
figure exists to make: every one of the 50 independent re-draws of the data
lands inside a sliver of the spread that individual cases show anyway. Its edges
are drawn as lines over the cloud, because a fill alone is invisible under 755
translucent dots.

**What the cloud is, and one scaling bug fixed in this rewrite.** Each dot is
one case at one depth, divided by that same case's geometric mean across all
five depths, and then put back on the speedup scale. The pairing is legitimate
because the catalogue fingerprint is identical at every depth: it is the same
151 problems each time, so the shape answers "how much does an individual case
move when you time it more often". The interquartile width narrows from 6.0
percentage points at depth 2 to 3.2 at depth 50, which is the convergence the
ladder exists to demonstrate.

The reference is the geometric mean and NOT the median. With five depths the
median is itself one of the five observations, so every case would sit at
exactly 1.0 at one depth -- 41 of 151 cases at the deepest rung -- pinning a
quartile there and collapsing one whisker to zero length. The geometric mean
across depths is attained by no case, so nothing is pinned. That reasoning was
right and is kept.

The bug: the earlier version put each depth's paired ratios back on scale by
multiplying by THAT DEPTH'S aggregate. Since the ratios already carry the depth
effect, that applied it twice, and the cloud's own geometric mean drifted away
from the aggregate line drawn through it -- 15.80x against a plotted 15.97x at
depth 2, 16.75x against 16.45x at depth 50, an error growing to 1.9 % and in
opposite directions at the two ends, which would have visibly tilted the cloud
against its own trend line. The fix is to multiply by the GRAND geometric mean
over all cases and depths (16.143273x), after which each depth's cloud has a
geometric mean equal to its plotted aggregate to every digit, by construction.

**An earlier version drew this as an error bar, and that was wrong.** Error bars
imply a symmetry these distributions do not have: the spread is skewed low at
shallow depths and high at deep ones, because a short run more often catches a
case slow than fast. A box with all its points shown states that; a +/- bar
hides it.

**The interval belongs to panel B and to panel B only.** Panel A is deliberately
not given a confidence interval. That interval is easy to compute and it would
be misleading: bootstrapping over cases is a statement about resampling the
catalogue, and this catalogue is a fixed hand-designed set, not a draw from a
population. For that claim the catalogue is the population, so there is no
sampling error to display. It is a fine gate statistic; it is a bad error bar.

Panel B is the opposite case, and that is the whole reason the second dataset
was run. Each of the 50 seeds drives the same generator over the same 151-case
recipe and lands on its own catalogue, so the 50 headline geometric means
genuinely are a sample, and a different draw would have given a different one.
There the mean has a sampling error and quoting an interval for it is the
correct summary. The interval is computed in log space, because the quantity
being averaged is itself a geometric mean and the paper aggregates
multiplicatively throughout; at this dispersion (2.4 %) it differs from the
arithmetic interval by under 0.04 %, so the choice is internal consistency
rather than anything the manuscript quotes.

**The interval cannot be moved onto the headline.** The sweep runs at effective
depth 5 and the headline is at depth 50. Seed-to-seed scatter (about +/- 2.4 %,
one standard deviation) and the depth trend (about 4 % from the shallowest
aggregate to the deepest) are two separate effects measured on two separate
axes; neither is a confidence interval for the other. Neither moves the
conclusion, which is the point. That belongs in the caption and is not written
on the canvas.

**Where the two datasets meet.** The ladder's depth-5 rung and the whole sweep
run at the same effective depth, and the sweep's own recorded catalogue
fingerprint is `181a87d3...` -- the same fingerprint the ladder records, and the
draw the sweep's first seed 20260603 produces. So the two experiments overlap at
one point, and the ladder's aggregate there lands at the 34th percentile of the
seed distribution: an unremarkable draw, neither flattering nor unlucky. That
crossing is drawn on panel B as a dashed rule.

The same crossing measures something neither dataset can measure alone. The two
runs of seed 20260603 at depth 5 are separate processes -- the sweep started
under two hours after the ladder finished, on the same host and branch at a
different commit -- and they report 15.784640x and 15.865745x, 0.51 % apart,
with the accuracy invariants identical to every recorded digit. Same data, same
depth, different process: that difference is run-to-run timing noise and nothing
else, and it is smaller than either axis this figure plots.

**No jitter is random.** Both point layouts are deterministic functions of the
data, because the render manifest hashes the PNG and an RNG would make it differ
between machines. Panel A uses a golden-ratio additive sequence assigned in
ascending order of value, which spreads neighbours in y as far apart in x as a
low-discrepancy sequence can. Panel B uses lane-search beeswarm packing, so
pile-up is accumulated rather than smeared.

**What is deliberately not on the canvas.** No multi-line prose boxes: two of
them, 8 and 7 lines, used to take about a third of this figure and compete with
the data they annotated, and all of it was caption material. The accuracy
statistics are down to a single grey line at the figure foot, since accuracy is
a third topic that `validation.md` already states in full: across depths max
|$\Delta r^2$| and the win rate are identical at every depth to every recorded
digit -- which is what distinguishes "the timings are noisy" from "the result is
unstable" -- while across seeds they move a little, because the data moved.

The seed panel's regression tally is caption material too. 44 of the 50 seeds
flag no regression; the other six flag exactly one case each (CX-016, CX-017 or
CX-018), and on all 50 seeds spectrafit solved all 151 cases, so those six are
comparator failures. Re-read from the per-seed manifests rather than inherited:
the failing backend is SciPy's LM on all six seeds, lmfit on four of them and
SciPy's dogbox on two -- an earlier version of this figure said "lmfit on four,
dogbox on two" and simply omitted the one backend that failed every time. The
gate's flag fires when ANY supported backend fails a case, which is right for a
gate and wrong to summarise as "spectrafit regressed".

The one quantity that WOULD be a metrological error bar -- the dispersion of the
timed repetitions behind each case's median -- is still not recoverable:
`engine.py` takes the median and drops the raw array, and `SuiteMetric` has no
dispersion field. Adding it means changing the contract and re-running, not
changing this figure. The seed sweep does not substitute for it; it varies the
data, not the clock.

Reads `manuscript/examples/ladder/ladder.json` with its per-rung `manifest.json`
files, and `manuscript/examples/seed-sweep/sweep.json`, all of which ship with
the paper.

Run:  uv run --group manuscript python manuscript/examples/figures/fig_ladder_stability.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib as mpl
import numpy as np
from matplotlib import patheffects as pe
from matplotlib import pyplot as plt
from matplotlib.patches import ConnectionPatch, Rectangle

mpl.use("Agg")

HERE = Path(__file__).resolve().parent
LADDER = HERE.parent / "ladder" / "ladder.json"
RUNGS = HERE.parent / "ladder" / "rungs"
SWEEP = HERE.parent / "seed-sweep" / "sweep.json"
STEM = "fig_ladder_stability"

# Two runs, two colours -- the panels are not two views of one dataset. Both are
# from the Apple systemColor-derived palette in docs/stylesheets/tokens/palette.css.
# systemBlue (#0064d2/#0067d6) is deliberately NOT used: it is lmfit/Python
# elsewhere in the paper, and neither panel here is about the comparator.
C_LADDER = "#c1185b"  # the subject crimson used throughout the paper
C_SEED = "#5856d6"  # systemIndigo
INK = "#1d1d1f"
INK_MUTED = "#6e6e73"
GRID = "#e3e3e0"

# Student t, 97.5 %, df = 49 -- the sweep has 50 seeds and the standard deviation is
# estimated from the same 50, so the interval is a t interval rather than a normal
# one. Hard-coded to keep this script on numpy alone; at n = 50 the normal 1.96
# would move either endpoint by under 0.05 %, so nothing quoted from this figure
# depends on the choice.
T_CRIT_50 = 2.0096

# Diameter in points of one per-case dot (panel A, 755 of them) and one per-seed
# dot (panel B, 50). Panel A's is small and heavily translucent so 151 overlapping
# points read as shading; panel B's is large enough to be counted, which is why the
# beeswarm exists. The beeswarm needs the seed size as a collision radius, so both
# are constants rather than literals that could drift apart.
CASE_PT = 2.2
SEED_PT = 4.6

# Golden ratio, used as the increment of the additive low-discrepancy sequence that
# jitters panel A. Applied in ascending order of value, it puts points that are
# adjacent in y about as far apart in x as a deterministic rule can, which is what
# keeps a dense cloud from banding.
PHI_FRAC = 0.6180339887498949


def load_ladder() -> list[dict]:
    """Read the per-depth headline figures, shallowest first."""
    if not LADDER.exists():
        msg = (
            f"{LADDER} not found -- the repetition ladder is the first stability "
            f"axis and panel A cannot be drawn without it"
        )
        raise SystemExit(msg)
    rungs = json.loads(LADDER.read_text())["rungs"]
    if not rungs:
        msg = f"{LADDER} carries no rungs"
        raise SystemExit(msg)
    return sorted(rungs, key=lambda r: r["reps_effective"])


def load_sweep() -> list[dict]:
    """Read the 50 per-seed rungs of the fixed-depth seed sweep, seed order.

    Every value the seed panel plots is taken from this file rather than
    transcribed, so a re-run of the sweep redraws the panel without anyone
    editing a literal into the figure.
    """
    if not SWEEP.exists():
        msg = (
            f"{SWEEP} not found -- the seed sweep is the second stability axis and "
            f"panel B cannot be drawn without it"
        )
        raise SystemExit(msg)
    doc = json.loads(SWEEP.read_text())
    rungs = doc.get("rungs") or []
    if not rungs:
        msg = f"{SWEEP} carries no rungs"
        raise SystemExit(msg)
    depths = {r["reps_effective"] for r in rungs}
    if len(depths) != 1:
        # The whole point of this axis is that depth is held fixed while the seed
        # varies. A mixed-depth file would silently confound the two axes.
        msg = f"{SWEEP} mixes effective depths {sorted(depths)}; expected exactly one"
        raise SystemExit(msg)
    return sorted(rungs, key=lambda r: r["seed"])


def geomeans(rungs: list[dict]) -> np.ndarray:
    """Headline geometric-mean speedups, in the order given."""
    return np.array(
        [r["headline"]["geomean_speedup_vs_baseline"] for r in rungs],
        dtype=float,
    )


def paired_cloud(rungs: list[dict]) -> np.ndarray | None:
    """Per-case speedups, paired across depths and put back on the speedup scale.

    Returns a ``(n_depths, n_cases)`` array, or ``None`` when the per-rung
    manifests are unavailable, so the figure degrades to a plain trend line
    rather than inventing a distribution.

    Each case is divided by its OWN geometric mean across the five depths, which
    is what makes the cloud a statement about movement rather than about which
    problems happen to be fast. The reference is the geometric mean and not the
    median: with five depths the median is one of the five observations, so every
    case would sit at exactly 1.0 at one depth and pin a quartile there.

    The result is then multiplied by the GRAND geometric mean over all cases and
    all depths -- not, as an earlier version did, by each depth's own aggregate.
    The paired ratios already carry the depth effect; multiplying by the depth
    aggregate applies it a second time and slides each depth's cloud away from
    the trend line drawn through it. With the grand mean, every depth's cloud has
    a geometric mean equal to that depth's plotted aggregate by construction.
    """
    per_depth = []
    for r in rungs:
        man = RUNGS / f"rung_{r['reps_effective']:03d}" / "manifest.json"
        if not man.exists():
            return None
        pts = json.loads(man.read_text()).get("per_case_points", {}).get("spectrafit")
        if not pts:
            return None
        per_depth.append([c["speedup"] for c in pts])
    matrix = np.asarray(per_depth, dtype=float)
    if matrix.ndim != 2:
        return None
    per_case = np.exp(np.mean(np.log(matrix), axis=0))
    grand = float(np.exp(np.mean(np.log(per_case))))
    return matrix / per_case * grand


def seed_summary(values: np.ndarray) -> dict[str, float]:
    """Point estimate, dispersion and 95 % CI of the mean for the 50 seeds.

    Computed in log space; see the module docstring for why, and for the measured
    size of the difference against an arithmetic interval.

    The standard deviation is reported on the raw scale, where "+/- 2.4 % of the
    mean" is what a reader wants; the interval is the one on the mean, which is
    narrower than the spread by the usual root-n and must not be confused with
    it.
    """
    n = len(values)
    log = np.log(values)
    half = T_CRIT_50 * float(log.std(ddof=1)) / math.sqrt(n)
    geo = math.exp(float(log.mean()))
    return {
        "n": float(n),
        "geomean": geo,
        "sd": float(values.std(ddof=1)),
        "cv_pct": float(values.std(ddof=1)) / geo * 100.0,
        "ci_lo": math.exp(float(log.mean()) - half),
        "ci_hi": math.exp(float(log.mean()) + half),
        "lo": float(values.min()),
        "hi": float(values.max()),
    }


def golden_jitter(values: np.ndarray, width: float) -> np.ndarray:
    """Deterministic x offsets for a dense point cloud, spread by value order.

    An RNG would make the PNG differ between machines and the render manifest
    hashes it, so the offsets come from an additive golden-ratio sequence
    instead. Handing successive terms out in ascending order of *values* means
    points that land next to each other vertically get offsets that are far apart
    horizontally, which is what stops 151 overlapping dots from forming visible
    bands.
    """
    n = len(values)
    seq = ((np.arange(n, dtype=float) * PHI_FRAC) % 1.0 - 0.5) * width
    out = np.empty(n, dtype=float)
    out[np.argsort(values, kind="stable")] = seq
    return out


def swarm(values: np.ndarray, ylo: float, yhi: float, w_in: float, h_in: float) -> np.ndarray:
    """Accumulated beeswarm offsets, in data units about the centre of a unit axis.

    Panel B has 50 points and they must stay individually countable, so this
    packs rather than jitters: sort by value, then place each point in the
    innermost free lane, where "free" means no already-placed point is within one
    marker diameter in both directions. Pile-up therefore shows as width. No RNG,
    so the layout is a function of the data alone.

    The panel's real width and height in inches are passed in so the collision
    radius is the marker's own size rather than a guess in data units.
    """
    step_in = SEED_PT / 72.0 * 1.08
    dx = step_in / w_in
    dy = step_in / h_in
    span = yhi - ylo
    placed: list[tuple[float, float]] = []
    out = np.zeros(len(values), dtype=float)
    for idx in np.argsort(values, kind="stable"):
        yf = (float(values[idx]) - ylo) / span
        lane = 0
        while True:
            for cand in (0.0,) if lane == 0 else (lane * dx, -lane * dx):
                if all(abs(yf - py) >= dy or abs(cand - px) >= dx for px, py in placed):
                    out[idx] = cand
                    placed.append((cand, yf))
                    break
            else:
                lane += 1
                continue
            break
    return out


def _box(ax: plt.Axes, x: float, col: np.ndarray, width: float) -> None:
    """One outline-only box-and-whisker at *x*, drawn over its own points.

    No fill: the whole point of a scattered boxplot is that the raw points stay
    visible, and a filled box would hide the densest part of its own sample. The
    whiskers are the usual 1.5 x IQR reach, and nothing is drawn for the points
    beyond them because those points are already on the figure individually.
    """
    q1, med, q3 = (float(v) for v in np.percentile(col, [25, 50, 75]))
    reach = 1.5 * (q3 - q1)
    lo = float(col[col >= q1 - reach].min())
    hi = float(col[col <= q3 + reach].max())
    ax.plot([x, x], [lo, q1], lw=0.8, color=INK, zorder=5)
    ax.plot([x, x], [q3, hi], lw=0.8, color=INK, zorder=5)
    for cap in (lo, hi):
        ax.plot([x - width * 0.22, x + width * 0.22], [cap, cap], lw=0.8, color=INK, zorder=5)
    ax.add_patch(
        Rectangle(
            (x - width / 2, q1),
            width,
            q3 - q1,
            facecolor="none",
            edgecolor=INK,
            lw=0.9,
            zorder=5,
        ),
    )
    ax.plot([x - width / 2, x + width / 2], [med, med], lw=1.5, color=INK, zorder=6)


def _depth_panel(
    ax: plt.Axes,
    rungs: list[dict],
    cloud: np.ndarray | None,
    headline: float,
    seed_band: tuple[float, float],
) -> int:
    """Panel A: scattered boxplot per depth, trend line on top. Returns points cropped."""
    eff = [int(r["reps_effective"]) for r in rungs]
    pos = np.arange(len(rungs), dtype=float)
    geo = geomeans(rungs)
    trend = (geo / headline - 1.0) * 100.0

    ax.axhspan(*seed_band, color=C_SEED, alpha=0.10, lw=0, zorder=0)
    for edge in seed_band:
        # The fill alone is invisible under 755 translucent dots, so the band's
        # extent is carried by its edges, drawn over the cloud.
        ax.axhline(edge, color=C_SEED, lw=0.7, alpha=0.85, zorder=7)

    off = 0
    if cloud is not None:
        dev = (cloud / headline - 1.0) * 100.0
        # Crop on the 1st/99th percentile of the pooled sample, rounded outward to
        # a multiple of 5. One case at depth 2 runs to 8.3x its own cross-depth
        # mean (214.28x raw), and letting a single point set the scale would press
        # the entire distribution into a flat line. The number of points that fall
        # outside is counted from the data and stated on the panel, so the crop is
        # disclosed rather than silent.
        lo = math.floor(float(np.percentile(dev, 1)) / 5.0) * 5.0
        hi = math.ceil(float(np.percentile(dev, 99)) / 5.0) * 5.0
        ax.set_ylim(lo, hi)
        off = int(((dev < lo) | (dev > hi)).sum())
        for i, col in enumerate(dev):
            ax.plot(
                pos[i] + golden_jitter(col, 0.60),
                col,
                ls="none",
                marker="o",
                ms=CASE_PT,
                color=C_LADDER,
                alpha=0.26,
                markeredgewidth=0,
                zorder=2,
            )
            _box(ax, pos[i], col, 0.52)
        ax.annotate(
            f"{off} of {dev.size} per-case points off scale "
            f"({dev.min():.0f} % to +{dev.max():.0f} %)",
            xy=(0.012, 0.014),
            xycoords="axes fraction",
            ha="left",
            va="bottom",
            fontsize=6.2,
            color=INK_MUTED,
        )

    # White marker edges so the aggregate stays the panel's primary message and
    # does not dissolve into a cloud drawn in the same hue.
    ax.plot(
        pos,
        trend,
        "-o",
        color=C_LADDER,
        lw=1.8,
        ms=5.2,
        mec="white",
        mew=0.9,
        zorder=8,
    )
    # The aggregate values sit in a row along the top rather than beside their own
    # markers: the trend line runs THROUGH the boxes, so a label at the marker lands
    # inside a box or on a median line at three of the five depths. Set in the trend
    # line's own colour, and column-aligned with it, so the row reads as its values.
    for x, g in zip(pos, geo, strict=True):
        ax.annotate(
            f"{g:.2f}x",
            xy=(x, 0.972),
            xycoords=ax.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=6.6,
            color=C_LADDER,
            zorder=9,
            path_effects=[pe.withStroke(linewidth=2.0, foreground="white")],
        )
    ax.annotate(
        "all 50 seeds",
        xy=(0.012, seed_band[1]),
        xycoords=ax.get_yaxis_transform(),
        xytext=(0, 4),
        textcoords="offset points",
        ha="left",
        va="bottom",
        fontsize=6.5,
        color=C_SEED,
        zorder=9,
        path_effects=[pe.withStroke(linewidth=2.0, foreground="white")],
    )

    ax.set_xticks(pos)
    ax.set_xticklabels([str(e) for e in eff])
    ax.set_xlim(-0.62, len(pos) - 0.38)
    ax.set_xlabel("timed solves per case (effective depth)")
    ax.set_ylabel(f"per-case deviation from {headline:.2f}x  (%)")
    ax.set_title(
        f"A · repetition depth — {len(rungs)} depths × {cloud.shape[1] if cloud is not None else 151} cases, every point drawn",
        fontsize=7.2,
        color=INK_MUTED,
        loc="left",
        pad=7,
    )
    return off


def _seed_panel(
    ax: plt.Axes,
    dev: np.ndarray,
    stat: dict[str, float],
    depth: int,
    cross: float,
    below: float,
) -> None:
    """Panel B: violin of the 50 seed aggregates with every draw beeswarmed inside."""
    headline = stat["headline"]
    span = float(dev.max() - dev.min())
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(float(dev.min()) - 0.13 * span, float(dev.max()) + 0.13 * span)

    ylo, yhi = ax.get_ylim()
    box = ax.get_position()
    fig = ax.get_figure()
    offsets = swarm(dev, ylo, yhi, box.width * fig.get_figwidth(), box.height * fig.get_figheight())

    ci_lo = (stat["ci_lo"] / headline - 1.0) * 100.0
    ci_hi = (stat["ci_hi"] / headline - 1.0) * 100.0
    mean = (stat["geomean"] / headline - 1.0) * 100.0

    # Outline-only violin: the confidence band is also a translucent indigo shape,
    # and two overlapping fills in one hue read as a third, meaningless value.
    parts = ax.violinplot([dev], positions=[0.5], widths=0.74, showextrema=False)
    for body in parts["bodies"]:
        body.set_facecolor("none")
        body.set_edgecolor(C_SEED)
        body.set_alpha(0.9)
        body.set_linewidth(0.9)

    ax.axhspan(ci_lo, ci_hi, color=C_SEED, alpha=0.16, lw=0, zorder=1)
    ax.axhline(mean, color=C_SEED, lw=1.2, zorder=5)
    ax.plot(
        0.5 + offsets,
        dev,
        ls="none",
        marker="o",
        ms=SEED_PT,
        color=C_SEED,
        alpha=0.85,
        markeredgewidth=0,
        zorder=4,
    )
    ax.axhline(cross, color=INK_MUTED, lw=0.8, ls=(0, (2.4, 1.8)), zorder=6)

    ax.annotate(
        f"mean {stat['geomean']:.2f}x",
        xy=(0.035, mean),
        xycoords=ax.get_yaxis_transform(),
        xytext=(0, 3),
        textcoords="offset points",
        ha="left",
        va="bottom",
        fontsize=6.5,
        color=C_SEED,
        zorder=9,
    )
    ax.annotate(
        "95 % CI",
        xy=(0.965, ci_hi),
        xycoords=ax.get_yaxis_transform(),
        xytext=(0, 3),
        textcoords="offset points",
        ha="right",
        va="bottom",
        fontsize=6.5,
        color=C_SEED,
        zorder=9,
    )
    ax.annotate(
        f"ladder depth {depth}\n{below * 100:.0f}th percentile",
        xy=(0.965, cross),
        xycoords=ax.get_yaxis_transform(),
        xytext=(0, -4),
        textcoords="offset points",
        ha="right",
        va="top",
        fontsize=6.5,
        color=INK_MUTED,
        linespacing=1.35,
        zorder=9,
        path_effects=[pe.withStroke(linewidth=2.0, foreground="white")],
    )

    ax.set_xticks([])
    ax.set_xlabel("one dot per seed")
    ax.set_ylabel(f"per-run deviation from {headline:.2f}x  (%)")
    ax.set_title(
        f"B · random seed — {int(stat['n'])} draws, fixed depth {depth}",
        fontsize=7.2,
        color=INK_MUTED,
        loc="left",
        pad=7,
    )


def plot(rungs: list[dict], seeds: list[dict]) -> None:
    """Render the two-axis stability figure to PDF and 300 dpi PNG."""
    depth = int(seeds[0]["reps_effective"])
    match = [r for r in rungs if r["reps_effective"] == depth]
    if not match:
        msg = (
            f"the ladder has no rung at effective depth {depth}, so the two datasets "
            f"have no depth in common and the cross-check cannot be drawn"
        )
        raise SystemExit(msg)

    headline = float(rungs[-1]["headline"]["geomean_speedup_vs_baseline"])
    seed_geo = geomeans(seeds)
    stat = seed_summary(seed_geo)
    stat["headline"] = headline
    seed_dev = (seed_geo / headline - 1.0) * 100.0
    shared = float(match[0]["headline"]["geomean_speedup_vs_baseline"])
    cross = (shared / headline - 1.0) * 100.0
    below = float((seed_geo < shared).mean())
    worst_dr2 = max(
        max(r["headline"]["max_abs_delta_r2"] for r in rungs),
        max(r["headline"]["max_abs_delta_r2"] for r in seeds),
    )

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
    fig, (ax_depth, ax_seed) = plt.subplots(
        1,
        2,
        figsize=(7.6, 4.2),
        gridspec_kw={"width_ratios": (1.95, 1.0)},
    )
    # A fixed layout rather than tight_layout: the beeswarm needs the panel's real
    # width and height in inches BEFORE the points are placed, and a layout solver
    # that runs afterwards would invalidate them. The wide gutter is deliberate --
    # the two panels have DIFFERENT y scales, and two tick ladders with room around
    # them is the plainest way to say so.
    fig.subplots_adjust(left=0.082, right=0.905, top=0.905, bottom=0.155, wspace=0.30)

    for ax in (ax_depth, ax_seed):
        ax.grid(True, axis="y", color=GRID, lw=0.5)
        ax.set_axisbelow(True)

    off = _depth_panel(
        ax_depth,
        rungs,
        paired_cloud(rungs),
        headline,
        (float(seed_dev.min()), float(seed_dev.max())),
    )
    _seed_panel(ax_seed, seed_dev, stat, depth, cross, below)

    # Two connectors carrying the seed band out of panel A and opening it into the
    # whole of panel B. They are the figure's statement that the scale changes, and
    # they say by how much without a word of prose.
    for edge in (float(seed_dev.min()), float(seed_dev.max())):
        fig.add_artist(
            ConnectionPatch(
                xyA=(1.0, edge),
                coordsA=ax_depth.get_yaxis_transform(),
                xyB=(0.0, edge),
                coordsB=ax_seed.get_yaxis_transform(),
                color=C_SEED,
                lw=0.6,
                alpha=0.55,
                ls=(0, (3.0, 2.0)),
            ),
        )

    secax = ax_seed.secondary_yaxis(
        "right",
        functions=(lambda r: headline * (1.0 + r / 100.0), lambda a: (a / headline - 1.0) * 100.0),
    )
    y0, y1 = ax_seed.get_ylim()
    a0, a1 = headline * (1.0 + y0 / 100.0), headline * (1.0 + y1 / 100.0)
    secax.set_yticks([t / 2.0 for t in range(math.ceil(a0 * 2), math.floor(a1 * 2) + 1)])
    secax.set_ylabel("speedup vs lmfit  (x)", fontsize=7.4)
    secax.tick_params(labelsize=7, colors=INK_MUTED)

    for ax in (ax_depth, ax_seed):
        ax.yaxis.set_major_formatter(lambda v, _pos: f"{v:+.0f}" if round(v, 6) else "0")

    # One line, because accuracy is a third topic and validation.md carries it in
    # full -- but leaving it off the figure entirely would let a reader take this
    # for a timing-stability argument alone.
    fig.text(
        0.5,
        0.014,
        f"accuracy invariant across both axes: max |$\\Delta r^2$| $\\leq$ {worst_dr2:.1e}",
        ha="center",
        va="bottom",
        fontsize=6.6,
        color=INK_MUTED,
    )

    for ext, dpi in (("pdf", 300), ("png", 300)):
        fig.savefig(HERE / f"{STEM}.{ext}", dpi=dpi)
    plt.close(fig)

    ladder_geo = geomeans(rungs)
    print(
        f"wrote {STEM}.pdf / .png  "
        f"(headline {headline:.6f}x; "
        f"{len(rungs)} depths {ladder_geo.min():.6f}-{ladder_geo.max():.6f}x, "
        f"{off} per-case points cropped; "
        f"{len(seeds)} seeds at depth {depth} {stat['lo']:.6f}-{stat['hi']:.6f}x "
        f"= {seed_dev.min():+.2f} to {seed_dev.max():+.2f} %, "
        f"geomean {stat['geomean']:.6f}x, sd {stat['sd']:.6f} ({stat['cv_pct']:.3f} %), "
        f"95 % CI [{stat['ci_lo']:.6f}, {stat['ci_hi']:.6f}]; "
        f"ladder depth-{depth} {shared:.6f}x = {below * 100:.0f}th pct; "
        f"worst |dr2| {worst_dr2:.3e})",
    )


if __name__ == "__main__":
    plot(load_ladder(), load_sweep())
