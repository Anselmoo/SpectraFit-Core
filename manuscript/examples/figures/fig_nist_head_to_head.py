"""Figure: spectrafit-core against lmfit on the NIST StRD datasets.

The agreement figure answers "does it pass?", and at 22 of 22 that question no
longer has any variance left in it. This one answers the question that does: how
does the library compare with the tool most of its users already have.

Two panels, both dumbbells, both sorted the same way:

* **Accuracy** — significant figures of agreement with the certified values, for
  the least accurately recovered parameter of each dataset. Both backends run
  from NIST's Start 2 at the same tolerance.
* **Function evaluations** — how many times each backend called the model. This
  is the analytic Jacobian made visible: lmfit spends most of its evaluations
  building a finite-difference Jacobian, and spectrafit-core does not build one.

Speed is deliberately NOT plotted. These datasets are 6 to 250 points, so
per-call overhead dominates and the totals (21 ms against 37 ms) say more about
Python call cost than about the solvers. The benchmark suite is where timing is
measured properly.

Reads `nist_head_to_head.json`, written by `nist_head_to_head.py`.

Run:  uv run --group manuscript python manuscript/examples/figures/fig_nist_head_to_head.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
import numpy as np
from matplotlib import pyplot as plt

mpl.use("Agg")

HERE = Path(__file__).resolve().parent
DATA = HERE / "nist_head_to_head.json"
STEM = "fig_nist_head_to_head"

C_SF = "#c1185b"
C_LM = "#0067d6"
C_LOSS = "#9c5f00"
INK, INK_MUTED, GRID = "#1d1d1f", "#6e6e73", "#e3e3e0"


def load() -> list[dict]:
    """Rows sorted by how far spectrafit-core is ahead, worst first."""
    if not DATA.exists():
        msg = f"{DATA} not found — run nist_head_to_head.py first"
        raise SystemExit(msg)
    rows = json.loads(DATA.read_text())
    return sorted(rows, key=lambda r: r["spectrafit"]["lre"] - r["lmfit"]["lre"])


def plot(rows: list[dict]) -> None:
    """Render the head-to-head figure to PDF and 300 dpi PNG."""
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
    n = len(rows)
    fig, (ax_a, ax_f) = plt.subplots(
        1,
        2,
        figsize=(8.0, 0.30 * n + 1.6),
        sharey=True,
        gridspec_kw={"width_ratios": [1.35, 1.0], "wspace": 0.08},
    )
    y = np.arange(n)

    for i, r in enumerate(rows):
        sf, lm = r["spectrafit"]["lre"], r["lmfit"]["lre"]
        # Colour the connector by who wins, so the one loss is visible at a glance
        # rather than having to be read off the marker order.
        won = sf > lm
        ax_a.plot(
            [lm, sf],
            [i, i],
            lw=1.5,
            color=C_SF if won else C_LOSS,
            alpha=0.45,
            zorder=2,
            solid_capstyle="round",
        )
        ax_a.plot([lm], [i], "o", ms=4.6, mfc="white", mec=C_LM, mew=1.3, zorder=3)
        ax_a.plot([sf], [i], "o", ms=5.4, color=C_SF if won else C_LOSS, zorder=4)

        fs, fl = r["spectrafit"]["fev"], r["lmfit"]["fev"]
        ax_f.plot(
            [fl, fs],
            [i, i],
            lw=1.5,
            color=C_SF,
            alpha=0.45,
            zorder=2,
            solid_capstyle="round",
        )
        ax_f.plot([fl], [i], "o", ms=4.6, mfc="white", mec=C_LM, mew=1.3, zorder=3)
        ax_f.plot([fs], [i], "o", ms=5.4, color=C_SF, zorder=4)
        ax_f.annotate(
            f"{fl / fs:.0f}x",
            xy=(fl, i),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            fontsize=6.2,
            color=INK_MUTED,
        )

    ax_a.set_yticks(y)
    ax_a.set_yticklabels([f"{r['name']}  ({r['n_params']}p)" for r in rows], fontsize=7)
    ax_a.set_xlabel("significant figures agreeing with the certified value")
    ax_f.set_xlabel("model evaluations to converge")
    ax_f.set_xscale("log")

    for ax in (ax_a, ax_f):
        ax.grid(True, axis="x", color=GRID, lw=0.5)
        ax.set_axisbelow(True)
        ax.set_ylim(-0.9, n - 0.3)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)

    wins = sum(1 for r in rows if r["spectrafit"]["lre"] > r["lmfit"]["lre"])
    med_ratio = float(np.median([r["lmfit"]["fev"] / r["spectrafit"]["fev"] for r in rows]))
    handles = [
        plt.Line2D([], [], ls="none", marker="o", ms=5.4, color=C_SF, label="spectrafit-core"),
        plt.Line2D(
            [],
            [],
            ls="none",
            marker="o",
            ms=4.6,
            mfc="white",
            mec=C_LM,
            mew=1.3,
            label="lmfit",
        ),
        plt.Line2D([], [], lw=1.5, color=C_LOSS, alpha=0.6, label="lmfit more accurate"),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=3,
        frameon=False,
        fontsize=7,
        bbox_to_anchor=(0.5, 0.008),
    )
    fig.suptitle(
        f"spectrafit-core against lmfit on {n} NIST StRD datasets — "
        f"more accurate on {wins} of {n}, and a median {med_ratio:.0f}x fewer model evaluations\n"
        "same starting values, same convergence tolerance; the evaluation gap is the "
        "analytic Jacobian, which lmfit builds by finite difference",
        fontsize=7.6,
        color=INK_MUTED,
        y=0.985,
    )
    fig.tight_layout(rect=(0, 0.045, 1, 0.94))
    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"{STEM}.{ext}", dpi=300)
    plt.close(fig)
    print(
        f"wrote {STEM}.pdf / .png  ({n} datasets, {wins} wins, median {med_ratio:.1f}x fewer evals)",
    )


if __name__ == "__main__":
    plot(load())
