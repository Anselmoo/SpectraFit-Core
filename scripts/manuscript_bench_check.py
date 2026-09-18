"""Check the manuscript's benchmark denominators against the live case registry.

Usage:
    python3 scripts/manuscript_bench_check.py           # report drift, exit 0
    python3 scripts/manuscript_bench_check.py --check   # exit 1 on drift

WHY THIS EXISTS, AND WHY IT IS NOT A GENERATOR.

`tests/meta/test_manuscript_jax_coverage.py` was written to stop the manuscript's
denominators drifting from the catalogue. On 2026-08-18 the catalogue grew
151 -> 154 cases and that guard was made to pass by editing its own expectations
(`EXPECTED_TOTAL` 151 -> 154, `EXPECTED_ELIGIBLE` 127 -> 130) rather than the
prose -- loudly, with a `KNOWN STALE` docstring naming exactly what was deferred,
but the effect is that the guard now asserts `live == a constant tracking live`
and says nothing at all about the manuscript. A detector that can be satisfied by
editing its own expectation is not a detector.

This script closes that specific hole: it compares the numbers the manuscript
STATES against the numbers the registry PRODUCES, so the only way to make it pass
is to change the prose or change the catalogue.

It deliberately does NOT rewrite a `<!-- bench:begin -->` block the way
`scripts/model_inventory.py` and `scripts/extract_dependencies.py` do for their
sections. The manuscript's counts and its performance figures are one coupled
artifact: `evidence.md`'s category table carries `| Asymmetric lineshapes | 24 |`
followed on the same row by measured medians, and its headline 16.4x geomean, the
131-fastest count, the five ladder depths and the seed sweep are all outputs of a
specific run (`2026-08-16_run_037`). Rewriting 24 -> 27 while those columns still
describe a 151-case run would produce a paper that is internally inconsistent --
strictly worse than one that is uniformly stale against a named run. Refreshing
the counts REQUIRES the ladder re-run (`poe terra_ladder`), so this reports and
refuses to paper over.

Scope: registry-derived quantities only. Run-derived figures (geomean, win
counts, max |dr2|, per-category medians, ladder depths) cannot be verified
without the run and are listed in the report as unverifiable, not as passing.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from oracles.cases import CATEGORY_REGISTRY, build_catalog
from oracles.models import get_model

ROOT = Path(__file__).resolve().parent.parent
SECTIONS = ROOT / "manuscript" / "draft" / "sections"

# Registry-derived claims, as (section file, regex capturing the stated integer,
# human label, callable returning the live value). The regexes are deliberately
# anchored on surrounding prose rather than on a bare number: `151` also appears
# as part of `7.151` in the NIST table.
CLAIMS: list[tuple[str, str, str]] = [
    ("evidence.md", r"\|\s*Suite\s*\|\s*(\d+)\s*\|", "suite size (Table: Suite row)"),
    ("evidence.md", r"\|\s*Offered to JAX\s*\|\s*(\d+)\s*\|", "cases offered to JAX"),
    ("evidence.md", r"(\d+)\s+cases in nine categories", "suite size (prose)"),
    ("abstract.md", r"Over a (\d+)-case suite", "suite size (abstract)"),
    ("reuse.md", r"over the same (\d+) cases", "suite size (reuse)"),
]


# The category table is written in prose display names that differ from
# `CategoryDef.label` in three ways: a trailing `*` footnote marker, British
# spelling, and expanded abbreviations. Mapped EXPLICITLY rather than matched
# fuzzily — a fuzzy match that silently binds the wrong row is worse than a
# reported SKIP, and this table is exactly where the one live category drift is
# (Asymmetric lineshapes: 24 stated, 27 registered).
LABEL_ALIASES: dict[str, str] = {
    "Optimization fns": "Optimisation functions",
    "Fixed-param": "Fixed-parameter",
    "Tied/shared-param": "Tied / shared-parameter",
}


def _withheld(case: Any) -> str | None:
    """Mirror ``JaxBackend.is_supported``: why a case is withheld, or None."""
    if case.spec.expr_edges:
        return "expr_edges"
    if case.solver_hint == "global":
        return "global solver hint"
    if any(not get_model(c.model).jax_supported for c in case.comp_guess):
        return "no jax kernel"
    return None


def live() -> dict[str, int]:
    """Return the registry's current counts."""
    suite = build_catalog()
    return {
        "suite": len(suite),
        "jax_eligible": sum(1 for c in suite if _withheld(c) is None),
    }


def _expected_for(label: str, truth: dict[str, int]) -> int:
    return truth["jax_eligible"] if "JAX" in label else truth["suite"]


def main() -> int:
    """Report registry-derived drift; return 1 under ``--check`` when any is found."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="exit 1 on drift")
    args = ap.parse_args()

    truth = live()
    print(f"live registry: {truth['suite']} cases, {truth['jax_eligible']} JAX-eligible")

    drift = 0
    for filename, pattern, label in CLAIMS:
        path = SECTIONS / filename
        if not path.exists():
            print(f"  SKIP  {filename}: not present")
            continue
        text = path.read_text(encoding="utf-8")
        match = re.search(pattern, text)
        if match is None:
            print(f"  SKIP  {label}: pattern found no match in {filename}")
            continue
        stated = int(match.group(1))
        expected = _expected_for(label, truth)
        line = text[: match.start()].count("\n") + 1
        if stated == expected:
            print(f"  ok    {label}: {stated}")
        else:
            drift += 1
            rel = path.relative_to(ROOT)
            print(f"  DRIFT {label}: {rel}:{line} states {stated}, registry says {expected}")

    # Per-category table rows carry a count AND measured medians on the same row.
    print("\nper-category counts (evidence.md Table 4):")
    ev = (SECTIONS / "evidence.md").read_text(encoding="utf-8")
    for cat in CATEGORY_REGISTRY.values():
        # Match on `CategoryDef.label` ("Asymmetric lineshapes"), not the registry
        # key ("lineshapes") — the table is written in display names, and keying on
        # the id silently matched nothing, which is how the 24-vs-27 lineshapes row
        # slipped past an earlier pass of this same check.
        shown = LABEL_ALIASES.get(cat.label, cat.label)
        # `\*?` absorbs the footnote marker several rows carry.
        row = re.search(
            rf"^\|\s*{re.escape(shown)}\*?\s*\|\s*(\d+)\s*\|",
            ev,
            re.IGNORECASE | re.MULTILINE,
        )
        if row is None:
            print(f"  SKIP  {cat.label}: no row matching {shown!r}")
            continue
        stated = int(row.group(1))
        if stated == cat.count:
            print(f"  ok    {cat.label}: {stated}")
        else:
            drift += 1
            line = ev[: row.start()].count("\n") + 1
            where = f"evidence.md:{line}"
            print(f"  DRIFT {cat.label}: {where} states {stated}, registry {cat.count}")

    print(
        "\nNOT CHECKED (run-derived, needs `poe terra_ladder`): geomean and harmonic "
        "speedups, fastest-case counts, max |dr2|, per-category medians, the five "
        "ladder depths, the seed sweep.",
    )

    if drift:
        print(f"\n{drift} registry-derived claim(s) have drifted.", file=sys.stderr)
        print(
            "Refreshing them requires the ladder re-run; the counts and the "
            "performance columns must move together.",
            file=sys.stderr,
        )
        return 1 if args.check else 0
    print("\nNo registry-derived drift.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
