"""Derive the cross-implementation parameter agreement the Validation section quotes.

The manuscript faults an existing benchmark for comparing cost-function values
rather than fitted parameters, then for a long time reported only the
coefficient of determination itself -- the aggregate it criticises. This script
computes the parameter-level figure from the committed run.

``param_err`` is each backend's **max relative shape-parameter recovery error
against the planted truth**, in per cent (``oracles.backends._base.param_error``).
Two traps are handled explicitly rather than silently:

* ``engine.py`` stores ``nan_to_num(..., nan=0.0)``, so a case with no planted
  truth arrives as ``0.0`` and is indistinguishable from perfect recovery.
  Cases where every backend reads exactly ``0.0`` are dropped, not counted.
* Ranking backends by who "wins" each case is meaningless here: the pairwise
  differences sit in the far decimals, so a win count would report numerical
  noise as a result. The script prints the count and the relative gap together
  so the gap disqualifies the count.

Run:  uv run python manuscript/examples/figures/measure_param_agreement.py
"""

from __future__ import annotations

import json
import statistics as st
from pathlib import Path

SUMMARY = Path(__file__).with_name("bench_summary.json")
OUT = Path(__file__).with_name("param_agreement.json")
BACKENDS = (
    "spectrafit",
    "lmfit",
    "jax",
    "scipy-ls-lm",
    "scipy-ls-trf",
    "scipy-ls-dogbox",
)
WELL_CONDITIONED_PCT = 10.0


def main() -> None:
    """Compute the agreement figures and write the JSON sidecar."""
    cases = json.loads(SUMMARY.read_text())["cases"]
    shared = [
        c for c in cases if all(c["m"].get(b, {}).get("param_err") is not None for b in BACKENDS)
    ]
    # Drop the no-truth cases that the nan->0.0 conversion disguises.
    with_truth = [c for c in shared if not all(c["m"][b]["param_err"] == 0.0 for b in BACKENDS)]
    good = [
        c
        for c in with_truth
        if max(c["m"][b]["param_err"] for b in BACKENDS) < WELL_CONDITIONED_PCT
    ]

    per_backend = {
        b: {
            "median_pct": st.median([c["m"][b]["param_err"] for c in good]),
            "worst_pct": max(c["m"][b]["param_err"] for c in good),
        }
        for b in BACKENDS
    }
    spreads = [
        max(c["m"][b]["param_err"] for b in BACKENDS)
        - min(c["m"][b]["param_err"] for b in BACKENDS)
        for c in good
    ]
    gaps = [
        abs(c["m"]["spectrafit"]["param_err"] - c["m"]["lmfit"]["param_err"])
        / max(c["m"]["spectrafit"]["param_err"], c["m"]["lmfit"]["param_err"])
        for c in with_truth
        if max(c["m"]["spectrafit"]["param_err"], c["m"]["lmfit"]["param_err"]) > 0
    ]

    # Reporting only `good` would condition the statistic on the outcome it
    # measures -- backends "agree" on a subset chosen because they all already
    # succeeded. The excluded strata are reported alongside it for that reason.
    excluded = [c for c in with_truth if c not in good]
    ratios = sorted(
        max(c["m"][b]["param_err"] for b in BACKENDS)
        / max(min(c["m"][b]["param_err"] for b in BACKENDS), 1e-12)
        for c in excluded
    )
    result = {
        "excluded_stratum": {
            "n": len(excluded),
            "median_worst_to_best_ratio": st.median(ratios),
            "max_worst_to_best_ratio": max(ratios),
            "median_param_err_pct": st.median(
                [c["m"]["spectrafit"]["param_err"] for c in excluded],
            ),
        },
        "n_all_six": len(shared),
        "n_with_truth": len(with_truth),
        "n_well_conditioned": len(good),
        "well_conditioned_threshold_pct": WELL_CONDITIONED_PCT,
        "per_backend": per_backend,
        "max_cross_backend_spread_pct_points": max(spreads),
        "median_spectrafit_vs_lmfit_relative_gap": st.median(gaps),
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(
        f"all six: {result['n_all_six']}, with truth: {result['n_with_truth']}, "
        f"well-conditioned: {result['n_well_conditioned']}",
    )
    for b, v in per_backend.items():
        print(f"  {b:16s} median {v['median_pct']:.4f} %  worst {v['worst_pct']:.4f} %")
    print(f"max cross-backend spread: {result['max_cross_backend_spread_pct_points']:.4f} pp")
    print(
        f"median spectrafit-vs-lmfit relative gap: "
        f"{result['median_spectrafit_vs_lmfit_relative_gap']:.2e}",
    )
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
