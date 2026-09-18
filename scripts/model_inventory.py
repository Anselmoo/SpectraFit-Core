#!/usr/bin/env python3
"""Emit the registered model inventory as a manuscript table.

The manuscript counted its models and never named one. A spectroscopist deciding
whether to try the library asks "is my lineshape in there?" first, and the paper
could not answer it. This generates the answer from
``oracles.models.MODEL_REGISTRY`` so the table cannot drift from the code.

Categories are assigned here rather than read from the registry, which carries no
category field. That mapping is checked for completeness on every run: a model
added to the registry and not categorised raises, so the failure mode is a loud
error rather than a model silently missing from the paper.

Usage::

    python3 scripts/model_inventory.py                  # markdown table
    python3 scripts/model_inventory.py --format json
    python3 scripts/model_inventory.py --check          # exit 1 on drift
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

METHOD = ROOT / "manuscript/draft/sections/method.md"
BEGIN = "<!-- models:begin -->"
END = "<!-- models:end -->"

CATEGORY: dict[str, str] = {
    # Symmetric and quasi-symmetric peak shapes.
    "gaussian": "Peak",
    "lorentzian": "Peak",
    "voigt": "Peak",
    "true_voigt": "Peak",
    "pseudo_voigt": "Peak",
    "pearson7": "Peak",
    "students_t": "Peak",
    "moffat": "Peak",
    "log_normal": "Peak",
    # Asymmetric peak shapes, the ones core-level and vibrational work needs.
    "skewed_gaussian": "Asymmetric peak",
    "exp_gaussian": "Asymmetric peak",
    "split_gaussian": "Asymmetric peak",
    "split_pearson7": "Asymmetric peak",
    "doniach_sunjic": "Asymmetric peak",
    "fano": "Asymmetric peak",
    "breit_wigner": "Asymmetric peak",
    "asym_ir": "Asymmetric peak",
    "harmonic_ir": "Asymmetric peak",
    # Edge and step functions.
    "arctan_step": "Step",
    "erfc_step": "Step",
    "tanh_step": "Step",
    # Backgrounds and baselines.
    "constant": "Background",
    "linear": "Background",
    "quadratic": "Background",
    "power_law_offset": "Background",
    # Decay, saturation and dispersion forms.
    "double_exponential": "Decay / saturation",
    "saturating_exponential": "Decay / saturation",
    "power_saturation": "Decay / saturation",
    "kww": "Decay / saturation",
    "cauchy_dispersion": "Dispersion",
    "tauc": "Dispersion",
    # Reference problems carried for certified-value checking.
    "mgh09_rational": "Reference problem",
    "rational_cubic": "Reference problem",
    "generalised_logistic": "Reference problem",
    "exp_over_linear": "Reference problem",
}

ORDER = [
    "Peak",
    "Asymmetric peak",
    "Step",
    "Background",
    "Decay / saturation",
    "Dispersion",
    "Reference problem",
]


def inventory() -> dict[str, list[dict[str, object]]]:
    """Group the live registry by category, failing on an uncategorised model."""
    from oracles.models import MODEL_REGISTRY

    keys = set(MODEL_REGISTRY)
    uncategorised = sorted(keys - set(CATEGORY))
    if uncategorised:
        msg = (
            f"model(s) in MODEL_REGISTRY with no category in this script: "
            f"{', '.join(uncategorised)}. Add them to CATEGORY so they reach the "
            f"manuscript table."
        )
        raise SystemExit(msg)
    stale = sorted(set(CATEGORY) - keys)
    if stale:
        msg = f"category map names model(s) not in MODEL_REGISTRY: {', '.join(stale)}"
        raise SystemExit(msg)

    grouped: dict[str, list[dict[str, object]]] = {c: [] for c in ORDER}
    for key in sorted(keys):
        entry = MODEL_REGISTRY[key]
        grouped[CATEGORY[key]].append(
            {
                "key": key,
                "params": list(entry.param_names),
                "jax": bool(getattr(entry, "jax_supported", False)),
            },
        )
    return grouped


def render_markdown(grouped: dict[str, list[dict[str, object]]]) -> str:
    """Render the grouped inventory as the marked block method.md carries."""
    total = sum(len(v) for v in grouped.values())
    lines = [BEGIN, "", f"| Category | Models ({total} registered) |", "|---|---|"]
    for cat in ORDER:
        items = grouped[cat]
        if not items:
            continue
        names = ", ".join(f"`{i['key']}`" for i in items)
        lines.append(f"| {cat} | {names} |")
    lines += ["", END]
    return "\n".join(lines)


def main() -> int:
    """Print the inventory table, or check the manuscript against the registry."""
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--format", choices=("markdown", "json"), default="markdown")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    grouped = inventory()
    if args.format == "json":
        print(json.dumps(grouped, indent=2))
        return 0

    block = render_markdown(grouped)
    if not args.check:
        print(block)
        return 0

    text = METHOD.read_text()
    if BEGIN not in text or END not in text:
        print(f"error: {METHOD} carries no {BEGIN} block", file=sys.stderr)
        return 1
    current = text[text.index(BEGIN) : text.index(END) + len(END)]
    if current.strip() == block.strip():
        print("model inventory: method.md matches the registry")
        return 0
    print(
        "model inventory: method.md has DRIFTED from MODEL_REGISTRY.\n"
        "Regenerate with:\n  python3 scripts/model_inventory.py",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
