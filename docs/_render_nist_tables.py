"""Render ``docs/reference/nist-strd.md`` from the NIST StRD Table 2 benchmark artifact.

Run before ``zensical build`` (wired into ``poe docs_build`` and ``poe docs_serve``,
mirroring ``docs/tutorials/gallery/_render.py`` and ``docs/_render_benchmark_summary.py``):
one small, deterministic, data-derived page regenerated at docs-build time rather than
a hand-maintained table that silently drifts from the numbers a NIST StRD run actually
produced.

    uv run --group docs python docs/_render_nist_tables.py

Reads ``manuscript/examples/figures/nist_table2.json`` — a committed artifact (kept on
the public GitHub mirror by ``scripts/publish_exclusions.py``, which strips
``manuscript/draft/*`` and ``manuscript/readiness/*`` but deliberately keeps
``manuscript/examples/*``) written by ``nist_table2.py``: per-dataset log-relative-error
("significant figures of agreement") of each backend's fitted parameters against NIST's
certified values, plus the same measure applied to spectrafit-core's fitted standard
errors against NIST's certified standard deviations (the ``sigma`` column).

Never fails the docs build: if the artifact is missing or unparseable, this writes a
"no data yet" placeholder page and exits 0 — a docs build must not depend on the
artifact having been (re-)generated first. Deterministic: no timestamps, no wall-clock,
no dict-ordering dependence — datasets are sorted explicitly (difficulty, then name)
and every derived summary number (per-backend minimum, threshold-clearing count,
per-difficulty count) is recomputed from the artifact on every run rather than
hardcoded, so a changed artifact changes the page instead of silently going stale.

Also reads ``python/oracles/nist_strd/<name>.py`` for each tabulated dataset — every
one of those fixture modules carries, in its own docstring, a ``Source:`` line
pointing at NIST's certified-value page for that problem (and occasionally a
parenthetical literature attribution, e.g. MGH09's "(Kowalik and Osborne, 1968)").
That provenance previously reached no reader; this generator now surfaces it next to
each dataset name instead of retyping it. Reading is best-effort and per-dataset: a
missing or unparseable fixture module degrades that one row to a plain (unlinked)
name rather than failing the whole build, preserving the "never fails" property above.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DOCS_DIR = Path(__file__).parent
REPO_ROOT = DOCS_DIR.parent
PAGE_PATH = DOCS_DIR / "reference" / "nist-strd.md"
DATA_PATH = REPO_ROOT / "manuscript" / "examples" / "figures" / "nist_table2.json"
NIST_STRD_DIR = REPO_ROOT / "python" / "oracles" / "nist_strd"

# Matches the "Source: <url>" line every python/oracles/nist_strd/*.py fixture
# docstring carries (see e.g. bennett5.py), pointing at NIST's certified-value page.
_SOURCE_RE = re.compile(r"^Source:\s*(\S+)\s*$", re.MULTILINE)

# Matches a "(Name and Name, YYYY)"-shaped parenthetical literature attribution —
# the only one found across the 22 fixtures is MGH09's "(Kowalik and Osborne,
# 1968)" — without matching unrelated parentheticals (RSS values, cross-checks)
# that appear elsewhere in the same docstrings.
_LITERATURE_RE = re.compile(r"\(([A-Z][\w.'-]+(?:\s+(?:and|&)\s+[A-Z][\w.'-]+)*,\s*\d{4})\)")

# Significant-figures-of-agreement threshold this page reports each backend's
# clearing count against — matches the value ``nist_table2.py`` itself treats as
# "adequate" agreement for a NIST StRD nonlinear-regression certified result.
SIG_FIGS_THRESHOLD = 4.0

# Table/summary column order: the four fitted-value backends first (spectrafit-core's
# own identity, then the three comparison backends), sigma last since it measures a
# different quantity (fitted standard errors, not fitted parameter values) than the
# other four.
_BACKEND_LABELS: dict[str, str] = {
    "spectrafit_core": "spectrafit-core",
    "lmfit": "lmfit",
    "scipy_lm": "scipy-lm",
    "scipy_trf": "scipy-trf",
    "sigma": "sigma",
}
_VALUE_COLUMNS = ("spectrafit_core", "lmfit", "scipy_lm", "scipy_trf", "sigma")

# Sort key for the main table: Higher difficulty first, then Average, then Lower —
# hardest datasets (the ones most likely to expose a backend weakness) lead the page.
_DIFFICULTY_ORDER = {"Higher": 0, "Average": 1, "Lower": 2}

_NO_DATA_PAGE = """\
---
icon: lucide/table-2
description: NIST StRD nonlinear regression certified-value agreement, per backend — regenerated from the committed benchmark artifact.
---

<!--
  GENERATED FILE — do not hand-edit.
  Written by docs/_render_nist_tables.py from manuscript/examples/figures/nist_table2.json
  on every docs build (poe docs_build / poe docs_serve). Edits made directly to this
  file are overwritten on the next build.
-->

# NIST StRD nonlinear regression benchmark

No NIST StRD benchmark artifact
(`manuscript/examples/figures/nist_table2.json`) is available for this build yet —
this page is normally generated from it.

See [NIST StRD validation methodology](../explanation/nist-validation.md) for what
this benchmark checks and how to reproduce it.
"""


def _fmt_value(value: float | None) -> str:
    """Format one agreement figure to 3 decimal places, or an em-dash for ``null``."""
    if value is None:
        return "—"
    return f"{value:.3f}"


def _dataset_provenance(name: str) -> tuple[str | None, str | None]:
    """Return ``(source_url, literature_note)`` parsed from *name*'s fixture docstring.

    Reads ``python/oracles/nist_strd/<name lowercased>.py`` — the dataset's own
    fixture module — rather than hardcoding a URL pattern, so a changed or removed
    ``Source:`` line changes this page instead of silently drifting from it. Returns
    ``(None, None)`` (never raises) if the module is missing or carries neither
    pattern, so one unreadable fixture degrades to a plain dataset name rather than
    failing the whole page.
    """
    module_path = NIST_STRD_DIR / f"{name.lower()}.py"
    try:
        text = module_path.read_text(encoding="utf-8")
    except OSError:
        return None, None
    source_match = _SOURCE_RE.search(text)
    literature_match = _LITERATURE_RE.search(text)
    return (
        source_match.group(1) if source_match else None,
        literature_match.group(1) if literature_match else None,
    )


def _dataset_name_cell(name: str) -> str:
    """Render one dataset's table cell: its name, linked to NIST's source page.

    Falls back to the plain *name* when no ``Source:`` URL is recoverable (see
    :func:`_dataset_provenance`). Appends a parenthetical literature attribution
    when the fixture's docstring carries one — only MGH09 does, as
    "(Kowalik and Osborne, 1968)", with no further bibliographic detail available
    in the repository, so none is fabricated here.
    """
    source_url, literature_note = _dataset_provenance(name)
    cell = f"[{name}]({source_url})" if source_url else name
    if literature_note:
        cell = f"{cell} ({literature_note})"
    return cell


def _compute_summary(
    datasets: list[dict],
) -> tuple[dict[str, float | None], dict[str, tuple[int, int]]]:
    """Per-backend minimum agreement and (clearing count, evaluated count) across *datasets*.

    "Evaluated count" is the denominator for the clearing fraction — it excludes
    ``null`` entries (the ``sigma`` column has two: NIST StRD datasets Eckerle4 and
    DanWood have no certified standard-deviation reference, so spectrafit-core's fitted
    sigma has nothing to compare against there) rather than treating a missing value as
    a failure to clear the threshold.
    """
    minimums: dict[str, float | None] = {}
    clears: dict[str, tuple[int, int]] = {}
    for column in _VALUE_COLUMNS:
        values = [ds["columns"][column] for ds in datasets if ds["columns"][column] is not None]
        minimums[column] = min(values) if values else None
        cleared = sum(1 for v in values if v >= SIG_FIGS_THRESHOLD)
        clears[column] = (cleared, len(values))
    return minimums, clears


def _format_page(data: dict) -> str:
    """Render the full markdown page from the parsed artifact."""
    datasets = sorted(
        data["datasets"],
        key=lambda ds: (_DIFFICULTY_ORDER[ds["difficulty"]], ds["name"]),
    )
    tol = data["tolerance"]
    measure = data["measure"]
    start_point_label = data["start_point_label"]

    rows = []
    for ds in datasets:
        c = ds["columns"]
        cells = [
            _dataset_name_cell(ds["name"]),
            ds["difficulty"],
            str(ds["n_params"]),
            str(ds["n_obs"]),
            _fmt_value(c["spectrafit_core"]),
            _fmt_value(c["lmfit"]),
            _fmt_value(c["scipy_lm"]),
            _fmt_value(c["scipy_trf"]),
            _fmt_value(c["sigma"]),
        ]
        rows.append("| " + " | ".join(cells) + " |")
    table = "\n".join(rows)

    minimums, clears = _compute_summary(datasets)
    n_total = len(datasets)
    summary_rows = []
    for column in _VALUE_COLUMNS:
        cleared, evaluated = clears[column]
        summary_rows.append(
            "| "
            + " | ".join(
                [
                    _BACKEND_LABELS[column],
                    _fmt_value(minimums[column]),
                    f"{cleared}/{evaluated}",
                ],
            )
            + " |",
        )
    summary_table = "\n".join(summary_rows)

    difficulty_counts: dict[str, int] = {}
    for ds in datasets:
        difficulty_counts[ds["difficulty"]] = difficulty_counts.get(ds["difficulty"], 0) + 1
    difficulty_line = " / ".join(
        f"{difficulty_counts.get(level, 0)} {level}" for level in ("Lower", "Average", "Higher")
    )

    return f"""\
---
icon: lucide/table-2
description: NIST StRD nonlinear regression certified-value agreement, per backend — regenerated from the committed benchmark artifact.
---

<!--
  GENERATED FILE — do not hand-edit.
  Written by docs/_render_nist_tables.py from manuscript/examples/figures/nist_table2.json
  on every docs build (poe docs_build / poe docs_serve). Edits made directly to this
  file are overwritten on the next build.
-->

# NIST StRD nonlinear regression benchmark

Per-dataset agreement between each backend's fitted result and NIST's certified
values, across all {n_total} NIST Statistical Reference Datasets (StRD) nonlinear
regression problems this repository benchmarks against. See
[NIST StRD validation methodology](../explanation/nist-validation.md) for how this
benchmark is run and what "agreement" means as a validation method.

## Run conditions

- Start point: `{data["start_point"]}` ({start_point_label})
- Tolerances: `ftol={tol["ftol"]:g}`, `xtol={tol["xtol"]:g}`, `gtol={tol["gtol"]:g}`
- Agreement measure: {measure}

## Results by dataset

Sorted by difficulty (Higher, then Average, then Lower), then by dataset name.
Agreement values are significant figures (higher is better), capped at 15; an
em-dash marks a dataset with no certified reference to compare against. Each
dataset name links to NIST's own certified-value page for that problem.

| Dataset | Difficulty | Params | Points | spectrafit-core | lmfit | scipy-lm | scipy-trf | sigma |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{table}

## Summary

Minimum agreement across all {n_total} datasets, and how many of the evaluated
datasets each backend clears {SIG_FIGS_THRESHOLD:g} significant figures of
agreement on (the "evaluated" denominator excludes datasets with no certified
reference for that column — see the sigma row).

| Backend | Minimum agreement | Clears {SIG_FIGS_THRESHOLD:g} sig figs |
| --- | ---: | ---: |
{summary_table}

Dataset difficulty breakdown: {difficulty_line}.
"""


def render() -> None:
    """Write ``docs/reference/nist-strd.md`` from the committed NIST StRD artifact.

    Falls back to a "no data yet" placeholder — and still exits 0 from ``main()`` —
    if the artifact is missing or fails to parse, so a docs build never depends on
    the artifact having been (re-)generated first.
    """
    PAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        page = _format_page(data)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"[nist-strd] no usable artifact at {DATA_PATH} ({exc}); writing placeholder")
        page = _NO_DATA_PAGE
    PAGE_PATH.write_text(page, encoding="utf-8")
    print(f"[nist-strd] wrote {PAGE_PATH}")


def main() -> int:
    """Entry point: render the page and return an exit code (always 0 — see :func:`render`)."""
    render()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
