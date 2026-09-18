r"""Figure: a win only counts if it is bigger than the margin you would defend.

WHY THIS EXISTS. Both accuracy comparisons in this project are reported as raw
win counts: "spectrafit-core is most accurate on 16 of the 22", "the composite
win rate is 133 of 151". A raw win count treats a difference in the eleventh
decimal exactly like a difference of two significant figures. It answers *who
was ahead*, which is almost never the question; the question is *whether being
ahead mattered*.

THE STANDARD FIX, and the one drawn here, is an **equivalence margin** -- the
smallest difference anyone would act on, sometimes called a region of practical
equivalence. Fix a margin, and every paired comparison becomes a win, a tie or a
loss rather than a win or a loss. The usual failure with margins is that the
author picks the one that flatters the result, so this figure does not pick one:
the left column sweeps the margin across its whole plausible range and lets the
reader read off their own. The right column shows the effect sizes the counts
are made of, because a count without its distribution can hide anything.

BOTH COMPARISONS ARE PUT IN ONE UNIT, the log-relative error: the number of
significant figures a fitted value shares with the reference. NIST's tables are
already in it. The synthetic suite records a maximum relative parameter error in
per cent, which is the same quantity logged, so `2 - log10(err%)` converts it
with no free parameter. That is what makes a single margin, half a significant
figure, mean the same thing in both rows.

WHAT IT FINDS. The two rows answer in opposite directions, and that contrast is
the whole point of drawing them together.

* **Against NIST** (row 1, certified values, external to this project) the win
  survives almost intact. At a half-figure margin it is 19 wins, 2 ties, 1 loss
  of 22; the median difference is +2.0 significant figures. Demand a full two
  figures and it is still 11 wins and no losses. This is a material win.
* **Against lmfit on our own synthetic suite** (row 2) it evaporates. The raw
  count reads 56 wins against 72 losses, which looks like a finding. Raise the
  margin to *five hundredths* of a significant figure and it is 0 wins, 150
  ties, 1 loss. Every one of those 128 signed results is noise on a scale no
  reader would act on. Even CX-017, the case drawn at +66 % in
  `fig_speed_accuracy_joint.py`, is only 0.22 of a significant figure.

So the honest reading is that the accuracy claim rests on NIST and not on the
head-to-head, and that the head-to-head win rate should not be quoted as an
accuracy result in either direction. That is a stronger statement than the
manuscript currently makes, and it is more favourable to the project than the
raw count it replaces.

Reproduce from a clean clone:

    uv run --group manuscript python manuscript/examples/figures/fig_weighted_win.py

Reads `manuscript/examples/figures/nist_table2.json` and `bench_summary.json`.
Writes `fig_weighted_win.pdf` and `.png` beside this file. Nothing else is
touched; no existing figure is overwritten.
"""

from __future__ import annotations

import json
import math
import statistics as st
from pathlib import Path
from typing import Any, NamedTuple

import matplotlib as mpl
import numpy as np
from matplotlib.axes import Axes

mpl.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
STEM = "fig_weighted_win"
NIST = HERE / "nist_table2.json"
SUMMARY = HERE / "bench_summary.json"

C_WIN = "#1f7a4d"  # ahead by more than the margin
C_TIE = "#c9c9c4"  # inside the margin, so not a result
C_LOSS = "#c1185b"  # behind by more than the margin, the subject crimson
INK = "#1d1d1f"
INK_MUTED = "#6e6e73"
GRID = "#e3e3e0"

# Half a significant figure: the difference at which a reported value's last
# useful digit changes. Marked, never assumed -- the sweep is the argument.
MARGIN = 0.5


class Paired(NamedTuple):
    """One paired comparison, in significant figures shared with the reference."""

    label: str
    delta: float  # spectrafit-core minus the comparator; positive is better


def load(path: Path) -> Any:
    """Read one shipped artifact, naming it if it is missing."""
    if not path.exists():
        msg = f"{path} is missing; this figure reads shipped artifacts and re-runs nothing."
        raise SystemExit(msg)
    return json.loads(path.read_text(encoding="utf-8"))


def nist_pairs() -> list[Paired]:
    """Per NIST dataset, our significant figures minus lmfit's."""
    out = []
    for row in load(NIST)["datasets"]:
        ours, theirs = row["columns"].get("spectrafit_core"), row["columns"].get("lmfit")
        if ours is None or theirs is None:
            continue
        out.append(Paired(row["name"], float(ours) - float(theirs)))
    return out


def suite_pairs() -> list[Paired]:
    """Per suite case, the same difference, converted from a per-cent error.

    `param_err` is a maximum relative parameter error in per cent, so
    `2 - log10(err%)` is the log-relative error: the significant figures the
    recovered value shares with the planted truth. Same definition NIST uses,
    which is what lets one margin serve both rows.
    """
    summary = load(SUMMARY)
    base = summary["baseline_solver_id"]
    out = []
    for case in summary["cases"]:
        ours, theirs = case["m"].get("spectrafit"), case["m"].get(base)
        if not ours or not theirs:
            continue
        pe_o, pe_t = ours.get("param_err"), theirs.get("param_err")
        if pe_o is None or pe_t is None:
            continue
        if any(math.isnan(v) for v in (pe_o, pe_t)):
            continue
        sig = lambda pct: 2.0 - math.log10(max(pct, 1e-15))
        out.append(Paired(case["id"], sig(pe_o) - sig(pe_t)))
    return out


def tally(pairs: list[Paired], margin: float) -> tuple[int, int, int]:
    """Wins, ties and losses at one margin. A tie is |difference| <= margin."""
    win = sum(1 for p in pairs if p.delta > margin)
    loss = sum(1 for p in pairs if p.delta < -margin)
    return win, len(pairs) - win - loss, loss


def panel_sweep(ax: Axes, pairs: list[Paired], top: float, title: str) -> dict[str, Any]:
    """Win / tie / loss as the margin grows, so no single threshold is assumed."""
    grid = np.linspace(0.0, top, 240)
    counts = np.array([tally(pairs, m) for m in grid], dtype=float)
    n = len(pairs)

    ax.stackplot(
        grid,
        counts[:, 0] / n * 100,
        counts[:, 1] / n * 100,
        counts[:, 2] / n * 100,
        colors=(C_WIN, C_TIE, C_LOSS),
        labels=("win", "tie (inside margin)", "loss"),
        edgecolor="white",
        linewidth=0.4,
    )
    ax.set_xlim(0, top)
    ax.set_ylim(0, 100)
    ax.set_xlabel("equivalence margin  (significant figures)")
    ax.set_ylabel("share of comparisons  (%)")
    ax.set_title(title, fontsize=8.2, color=INK)
    ax.grid(True, axis="y", color="white", lw=0.5)
    ax.set_axisbelow(False)

    at = tally(pairs, MARGIN)
    if top >= MARGIN:
        ax.axvline(MARGIN, color=INK, lw=0.9, ls=(0, (3, 2)), zorder=5)
        room = top * 0.7 > MARGIN
        ax.annotate(
            f"at {MARGIN:g}: {at[0]} win / {at[1]} tie / {at[2]} loss",
            xy=(MARGIN, 100),
            xytext=(4 if room else -4, -10),
            textcoords="offset points",
            ha="left" if room else "right",
            va="top",
            fontsize=6.5,
            color=INK,
            bbox={
                "boxstyle": "round,pad=0.3",
                "facecolor": "white",
                "edgecolor": GRID,
                "linewidth": 0.5,
                "alpha": 0.94,
            },
        )
    ax.legend(loc="lower right", frameon=False, fontsize=6.4, handlelength=1.2)
    return {"n": n, "at_margin": at, "raw": tally(pairs, 0.0)}


def panel_effects(ax: Axes, pairs: list[Paired], title: str, *, label_each: bool) -> None:
    """The effect sizes the counts are made of, against the margin band."""
    order = sorted(pairs, key=lambda p: p.delta)
    ys = np.arange(len(order))
    deltas = [p.delta for p in order]
    colours = [C_WIN if d > MARGIN else C_LOSS if d < -MARGIN else INK_MUTED for d in deltas]

    ax.axvspan(-MARGIN, MARGIN, color=C_TIE, alpha=0.5, zorder=1)
    ax.axvline(0.0, color=INK, lw=0.8, zorder=2)
    ax.hlines(ys, 0, deltas, color=colours, lw=1.0, alpha=0.85, zorder=3)
    ax.scatter(deltas, ys, s=14, color=colours, zorder=4, linewidths=0)

    if label_each:
        ax.set_yticks(ys)
        ax.set_yticklabels([p.label for p in order], fontsize=5.8)
    else:
        ax.set_yticks([])
        ax.set_ylabel(f"{len(order)} cases, sorted", fontsize=7)
    ax.set_ylim(-1, len(order))
    # The band has to be visibly a band. When every point sits inside it, an
    # x-range clipped to the data hides the edges and the panel looks like an
    # empty axis with a grey wash.
    reach = max(MARGIN * 1.35, max(abs(v) for v in deltas) * 1.1)
    if max(abs(v) for v in deltas) < MARGIN:
        ax.set_xlim(-reach, reach)
    ax.set_xlabel("significant figures gained over lmfit")
    ax.set_title(title, fontsize=8.2, color=INK)
    ax.grid(True, axis="x", color=GRID, lw=0.5)
    ax.set_axisbelow(True)

    med = st.median(deltas)
    ax.annotate(
        f"median {med:+.3f}\nrange {min(deltas):+.3f} to {max(deltas):+.3f}",
        xy=(0.97, 0.05),
        xycoords="axes fraction",
        ha="right",
        va="bottom",
        fontsize=6.4,
        color=INK,
        linespacing=1.5,
        bbox={
            "boxstyle": "round,pad=0.3",
            "facecolor": "white",
            "edgecolor": GRID,
            "linewidth": 0.5,
            "alpha": 0.94,
        },
    )
    ax.text(
        -MARGIN,
        len(order) - 0.5,
        f" practically equivalent, ±{MARGIN:g}",
        ha="left",
        va="top",
        fontsize=6.0,
        color=INK_MUTED,
    )


def draw() -> None:
    """Compose and write the figure."""
    nist, suite = nist_pairs(), suite_pairs()

    mpl.rcParams.update(
        {
            "font.size": 8,
            "axes.labelsize": 7.6,
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
    fig, axes = plt.subplots(2, 2, figsize=(9.2, 7.4), gridspec_kw={"width_ratios": (1.15, 1.0)})

    a = panel_sweep(axes[0][0], nist, 3.0, "(A) NIST certified values: the win survives")
    panel_effects(axes[0][1], nist, "(B) by dataset, 22 of them", label_each=True)
    c = panel_sweep(axes[1][0], suite, 0.5, "(C) lmfit head-to-head: the win evaporates")
    panel_effects(axes[1][1], suite, "(D) by case, 151 of them", label_each=False)

    def _span(ax: Axes) -> float:
        lo, hi = ax.get_xlim()
        return hi - lo

    # Read off the axes rather than stated: the ratio changed once already when
    # panel D's limits were widened to make its equivalence band visible, and a
    # hardcoded number would still have been sitting here saying 30x.
    sweep_ratio = _span(axes[0][0]) / _span(axes[1][0])
    effect_ratio = _span(axes[0][1]) / _span(axes[1][1])
    fig.text(
        0.5,
        0.012,
        "Both rows are in one unit, the log-relative error, so one margin means the same thing in "
        f"each. The x-scales differ by {sweep_ratio:.0f}x between (A) and (C), and by "
        f"{effect_ratio:.0f}x between (B) and (D).",
        ha="center",
        va="bottom",
        fontsize=6.4,
        color=INK_MUTED,
    )
    fig.subplots_adjust(left=0.075, right=0.975, top=0.955, bottom=0.085, wspace=0.26, hspace=0.32)

    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"{STEM}.{ext}", dpi=300)
    plt.close(fig)

    print(f"wrote {STEM}.pdf / .png")
    for name, res in (("NIST ", a), ("suite", c)):
        raw, at = res["raw"], res["at_margin"]
        print(
            f"  {name} n={res['n']:3d}  raw {raw[0]}/{raw[1]}/{raw[2]}  ->  "
            f"at margin {MARGIN:g}: {at[0]}/{at[1]}/{at[2]}  (win/tie/loss)",
        )
    dv = sorted(p.delta for p in suite)
    first = next((m for m in np.linspace(0, 0.5, 501) if tally(suite, m)[0] == 0), None)
    print(f"  suite wins reach zero at a margin of {first:.3f} significant figures")
    print(f"  suite median difference {st.median(dv):+.4f}, worst {min(dv):+.4f}")


if __name__ == "__main__":
    draw()
