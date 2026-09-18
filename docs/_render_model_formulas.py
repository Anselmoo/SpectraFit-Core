r"""Sync the Formula column of ``docs/reference/models/index.md`` from ``oracles.models.MODEL_REGISTRY``.

Run before ``zensical build`` (wired into ``poe docs_build``/``poe docs_serve`` the
same way as ``docs/_render_benchmark_summary.py`` and ``docs/_render_nist_tables.py``):

    uv run --group docs python docs/_render_model_formulas.py

COV-04 background. 34 model formulas were authored twice in independent LaTeX: once
as ``PeakModel.formula_latex`` in ``python/oracles/models.py`` (the numpy parity
oracle, numerically pinned against the Rust kernel by
``tests/unit/oracles/test_wheel_eval.py``), and again by hand in the Formula column
of this page. A 2026-08-21 audit found only 4 of 34 byte-identical; the rest had
drifted into differently-written-but-equivalent LaTeX, and two (``log_normal``,
``split_pearson7``) had drifted into genuinely wrong mathematics before being
hand-corrected. Nothing pinned the two sources together, unlike the adjacent
wire-string parity that ``tests/parity/test_schema_parity.py`` genuinely enforces.

Why not a whole-page regenerate (unlike the two sibling scripts above). Both
siblings render a page that is *entirely* generated data — a "GENERATED FILE, do
not hand-edit" banner up top is honest because every line comes from one artifact
read. This page is not that: it carries hand-written prose conventions, per-section
groupings, amplitude-exception paragraphs, footnotes, and machine-pinned structure
(``tests/meta/test_catalog_drift.py`` checks the wire-variant count, the shape-
factory roster, and parameter names against ``compose.CANONICAL_PARAMS`` elsewhere
on this same page). Regenerating the whole file would either have to reimplement
all of that prose here too (duplicating, not fixing, the two-source problem) or
silently discard it on every build.

**Mechanism: inline marker comments around the formula cell's math only.** Each
table row's Formula cell wraps just its LaTeX span in a paired HTML comment,
keyed by the registry's ``key``:

    | `gaussian` | <!-- formula:gaussian -->$A \\cdot \\exp\\!\\left(...\\right)$<!-- /formula --> | ... |

``render()`` replaces only the text between ``<!-- formula:KEY -->`` and
``<!-- /formula -->`` with ``f"${MODEL_REGISTRY[KEY].formula_latex}$"``; nothing
else on the page — row order, the Parameters/Python `ModelType`/NIST columns,
per-row prose annotations following the marker (e.g. "— $\\sigma$ is the
**HWHM**"), section headings, footnotes — is ever touched. That keeps the
generator's blast radius exactly as small as the thing it owns (COV-04 scoped it
to "formula strings ONLY"), and it is why cell-level markers were chosen over
wrapping whole tables or whole sections in ``<!-- BEGIN generated:formulas -->``
blocks: a table-level region would force this script to also own the Parameters/
NIST columns' hand-authored annotations (HWHM caveats, amplitude exceptions,
solver caveats) it has no data model for, reintroducing exactly the duplication
this module exists to remove. A ``--8<--`` snippet-include (the other documented
house option) does not fit either: pymdownx's snippet directive splices in whole
files/blocks on their own line, and a Formula cell's LaTeX has to live inside a
single markdown table row alongside hand-written cells it cannot own — there is
no way to ``--8<--`` a table-cell fragment without breaking the row.

**As of this script's introduction, the page carries zero ``formula:KEY``
markers** — migrating each table is a follow-up patch reviewed separately (see
the COV-04 report). Until that patch lands, every run of this script is a
documented no-op: it reads the page, finds no markers, writes nothing, and exits
0. This is not a bug to "fix" by having the script insert markers itself — this
script only ever fills in markers a human review has already placed; inventing
table structure is out of its scope, matching COV-04's "propose, do not apply"
constraint on this page.

**Never fails the docs build.** If ``oracles.models`` cannot be imported (missing
compiled ``spectrafit_core`` extension, missing ``scipy``, or any other
environment gap), or the target page is missing, this prints a diagnostic and
exits 0 without changing anything — a docs build must not depend on the Python
extension having been compiled first, mirroring the "no data yet" placeholder
convention of the two sibling scripts (the placeholder here is simply "leave the
page exactly as it already reads," since unlike those two scripts this page is
never wholly generated in the first place).

Deterministic: no timestamps, no wall-clock, no dict-ordering dependence — marker
keys are looked up directly (no iteration-order-sensitive traversal) and the
output is a straight string substitution over the existing file, so running this
twice on the same inputs produces byte-identical output.
"""

from __future__ import annotations

import re
from pathlib import Path

DOCS_DIR = Path(__file__).parent
REPO_ROOT = DOCS_DIR.parent
PAGE_PATH = DOCS_DIR / "reference" / "models" / "index.md"

# Matches `<!-- formula:KEY -->...body...<!-- /formula -->`. Keys are registry
# keys (``oracles.models.MODEL_REGISTRY``), always ``[a-z0-9_]+`` by convention
# (mirrors the wire-string alphabet) — see ``PeakModel.key`` in models.py.
_MARKER_RE = re.compile(
    r"<!-- formula:(?P<key>[a-z0-9_]+) -->(?P<body>.*?)<!-- /formula -->",
    re.DOTALL,
)


def _load_registry() -> dict[str, str] | None:
    """Return ``{key: formula_latex}`` from the live registry, or ``None`` if unavailable.

    Broad ``except Exception`` is deliberate: any failure here (missing compiled
    extension, missing optional dependency, an import-time error in a future
    registry entry) must degrade to "leave the page alone", never fail the build.
    """
    try:
        from oracles.models import MODEL_REGISTRY
    except Exception as exc:  # noqa: BLE001 - see docstring
        print(f"[model-formulas] oracles.models unavailable ({exc}); leaving page as-is")
        return None
    return {
        key: model.formula_latex for key, model in MODEL_REGISTRY.items() if model.formula_latex
    }


def render() -> None:
    """Rewrite every ``<!-- formula:KEY -->`` marker in the page from the live registry.

    Writes the file only when at least one marker's content actually changed, so
    a no-op run never touches the file's mtime or creates a spurious git diff.
    """
    if not PAGE_PATH.exists():
        print(f"[model-formulas] no page at {PAGE_PATH}; nothing to sync")
        return

    formulas = _load_registry()
    if formulas is None:
        return

    page = PAGE_PATH.read_text(encoding="utf-8")

    updated = 0
    unknown_keys: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        nonlocal updated
        key = match.group("key")
        latex = formulas.get(key)
        if latex is None:
            unknown_keys.append(key)
            return match.group(0)
        new_body = f"${latex}$"
        if new_body != match.group("body"):
            updated += 1
        return f"<!-- formula:{key} -->{new_body}<!-- /formula -->"

    new_page = _MARKER_RE.sub(_replace, page)

    if unknown_keys:
        print(
            f"[model-formulas] {len(unknown_keys)} marker(s) reference a key not in "
            f"MODEL_REGISTRY (left untouched): {sorted(set(unknown_keys))}",
        )

    marker_count = len(_MARKER_RE.findall(page))
    if marker_count == 0:
        print(
            "[model-formulas] 0 formula:KEY markers found in "
            f"{PAGE_PATH.relative_to(REPO_ROOT)} — nothing to sync yet "
            "(see the COV-04 migration patch proposal)",
        )
        return

    if new_page == page:
        print(f"[model-formulas] {marker_count} marker(s) found, already in sync")
        return

    PAGE_PATH.write_text(new_page, encoding="utf-8")
    print(f"[model-formulas] synced {updated}/{marker_count} formula marker(s) in {PAGE_PATH}")


def main() -> int:
    """Entry point: sync the page's formula markers and return an exit code (always 0)."""
    render()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
