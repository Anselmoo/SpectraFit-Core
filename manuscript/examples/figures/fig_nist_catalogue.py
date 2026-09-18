"""Figure: all 27 NIST StRD nonlinear-regression reference sets.

Shows what the certified-value check is drawn from and, equally, what it is not:
the 22 datasets this library fits are filled, the 5 it cannot are open on a grey
ground. A coverage claim of "22 of 27" is a number a reader has to trust; this is
the same claim as a picture they can check.

Data provenance is split deliberately:

* The 22 implemented datasets are read from this repository's own fixtures under
  ``oracles.nist_strd``, so the figure cannot drift from what the audit actually
  fits.
* The 5 unimplemented ones have no fixture — that is what unimplemented means —
  so their observations ship alongside this script in
  ``manuscript/examples/nist_unimplemented/datasets.json``, transcribed from the
  NIST data files. Without them the figure could not show the gap it exists to
  show, and fetching them at render time would make the figure depend on a
  network.

Why these five remain: Nelson has two predictors and a log-link, ENSO is a sum of
sinusoids, and MGH10, Misra1c and Misra1d each need a kernel shared with nothing
else. They are capability gaps with names, not an unexplained remainder.

Run:  uv run --group manuscript python manuscript/examples/figures/fig_nist_catalogue.py
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import matplotlib as mpl
import numpy as np
from matplotlib import pyplot as plt

mpl.use("Agg")

HERE = Path(__file__).resolve().parent
UNIMPL = HERE.parent / "nist_unimplemented" / "datasets.json"
STEM = "fig_nist_catalogue"

TIER_COLOUR = {"Higher": "#b03a8f", "Average": "#9c5f00", "Lower": "#0067d6"}
TIER_ORDER = ("Lower", "Average", "Higher")
INK, INK_MUTED, GRID = "#1d1d1f", "#6e6e73", "#e3e3e0"

# module stem -> the name NIST publishes, for the 22 that have fixtures
FIXTURES = {
    "misra1a": "Misra1a",
    "misra1b": "Misra1b",
    "chwirut1": "Chwirut1",
    "chwirut2": "Chwirut2",
    "lanczos3": "Lanczos3",
    "gauss1": "Gauss1",
    "gauss2": "Gauss2",
    "danwood": "DanWood",
    "lanczos1": "Lanczos1",
    "lanczos2": "Lanczos2",
    "gauss3": "Gauss3",
    "mgh17": "MGH17",
    "kirby2": "Kirby2",
    "hahn1": "Hahn1",
    "roszman1": "Roszman1",
    "mgh09": "MGH09",
    "thurber": "Thurber",
    "boxbod": "BoxBOD",
    "rat42": "Rat42",
    "rat43": "Rat43",
    "eckerle4": "Eckerle4",
    "bennett5": "Bennett5",
}


def load() -> list[dict]:
    """Every dataset, tier-ordered, each marked implemented or not."""
    import sys

    sys.path.insert(0, str(HERE))
    from extract_bench_summary import nist_difficulty_tiers

    tiers = nist_difficulty_tiers()
    rows = []
    for stem, name in FIXTURES.items():
        mod = importlib.import_module(f"oracles.nist_strd.{stem}")
        rows.append(
            {
                "name": name,
                "tier": tiers.get(stem, "Lower"),
                "x": mod.X,
                "y": mod.Y,
                "implemented": True,
            },
        )
    if UNIMPL.exists():
        for name, d in json.loads(UNIMPL.read_text()).items():
            rows.append(
                {
                    "name": name,
                    "tier": d["tier"],
                    "x": np.asarray(d["x"]),
                    "y": np.asarray(d["y"]),
                    "implemented": False,
                },
            )
    return sorted(rows, key=lambda r: (TIER_ORDER.index(r["tier"]), r["name"].lower()))


def plot(rows: list[dict]) -> None:
    """Render the catalogue to PDF and 300 dpi PNG."""
    mpl.rcParams.update(
        {
            "font.size": 7,
            "axes.labelsize": 6.5,
            "xtick.labelsize": 5.5,
            "ytick.labelsize": 5.5,
            "axes.edgecolor": INK_MUTED,
            "axes.linewidth": 0.5,
            "xtick.color": INK_MUTED,
            "ytick.color": INK_MUTED,
            "text.color": INK,
            "axes.labelcolor": INK,
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
        },
    )
    ncol = 5
    nrow = -(-len(rows) // ncol)
    fig, axes = plt.subplots(nrow, ncol, figsize=(9.6, 1.85 * nrow + 0.9))
    for ax in axes.flat:
        ax.set_visible(False)

    for i, r in enumerate(rows):
        ax = axes.flat[i]
        ax.set_visible(True)
        colour = TIER_COLOUR[r["tier"]]
        impl = r["implemented"]
        dense = len(r["x"]) > 100
        ax.plot(
            r["x"],
            r["y"],
            ls="none",
            marker="o",
            ms=1.4 if dense else 2.4,
            mfc=colour if impl else "none",
            mec=colour,
            mew=0.55,
            alpha=0.5 if dense else 0.95,
        )
        ax.set_title(
            f"{r['name']}   n={len(r['x'])}",
            fontsize=6.8,
            color=INK if impl else INK_MUTED,
            fontweight="bold" if impl else "normal",
            pad=3,
        )
        ax.grid(True, color=GRID, lw=0.4)
        ax.set_axisbelow(True)
        ax.tick_params(length=1.8)
        if not impl:
            ax.patch.set_facecolor("#f7f7f7")

    tally = {t: sum(1 for r in rows if r["tier"] == t) for t in TIER_ORDER}
    n_impl = sum(1 for r in rows if r["implemented"])
    handles = [
        plt.Line2D(
            [],
            [],
            ls="none",
            marker="o",
            ms=5,
            mfc=TIER_COLOUR[t],
            mec=TIER_COLOUR[t],
            label=f"{t} ({tally[t]})",
        )
        for t in TIER_ORDER
    ] + [
        plt.Line2D(
            [],
            [],
            ls="none",
            marker="o",
            ms=5,
            mfc="white",
            mec=INK_MUTED,
            mew=0.9,
            label=f"not implemented ({len(rows) - n_impl})",
        ),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=4,
        frameon=False,
        fontsize=7,
        bbox_to_anchor=(0.5, 0.008),
    )
    fig.suptitle(
        f"The {len(rows)} NIST StRD nonlinear-regression reference sets — "
        f"filled markers are the {n_impl} this library fits",
        fontsize=9,
        color=INK,
        y=0.995,
    )
    fig.tight_layout(rect=(0, 0.028, 1, 0.985))
    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"{STEM}.{ext}", dpi=200)
    plt.close(fig)
    print(f"wrote {STEM}.pdf / .png  ({len(rows)} datasets, {n_impl} implemented)")
    for t in TIER_ORDER:
        got = sum(1 for r in rows if r["tier"] == t and r["implemented"])
        print(f"   {t:8s} {got}/{tally[t]}")


if __name__ == "__main__":
    plot(load())
