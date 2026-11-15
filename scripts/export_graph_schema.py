#!/usr/bin/env python3
"""Write the JSON Schema of a fit graph to ``python/spectrafit_core/graph.schema.json`` (#93).

The schema is ``FitGraph.model_json_schema()``: the file a graph JSON written by
``FitGraph.model_dump_json()`` conforms to, so a second implementation (for example
``reproducibility/interop/graph_to_lmfit.py``) can read graphs without importing
SpectraFit-Core. ``tests/unit/spectrafit_core/test_graph_schema_file.py`` fails when the
committed file differs from what this script writes.

    uv run python scripts/export_graph_schema.py           # write the file
    uv run python scripts/export_graph_schema.py --check   # exit 1 when it is stale
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from spectrafit_core import FitGraph

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "python" / "spectrafit_core" / "graph.schema.json"


def _strict(value: object) -> object:
    r"""Replace non-finite floats by ``None``, the wire form of an open bound.

    ``Parameter.min`` / ``Parameter.max`` default to $\mp\infty$, which strict JSON
    cannot hold; the model writes them as ``null`` on the wire and reads ``null`` back as
    $\mp\infty$, so the schema states the same.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _strict(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_strict(v) for v in value]
    return value


def render() -> str:
    """Return the schema file's exact text."""
    schema = _strict(FitGraph.model_json_schema())
    return json.dumps(schema, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Write the schema file, or with ``--check`` report whether it is current."""
    ap = argparse.ArgumentParser(description="Export the FitGraph JSON Schema.")
    ap.add_argument("--check", action="store_true", help="exit 1 if the file is stale")
    ap.add_argument("--path", type=Path, default=SCHEMA_PATH, help="schema file to write/check")
    args = ap.parse_args(argv)
    text = render()
    if args.check:
        current = args.path.read_text(encoding="utf-8") if args.path.exists() else None
        if current != text:
            print(f"{args.path} is stale: run scripts/export_graph_schema.py", file=sys.stderr)
            return 1
        return 0
    args.path.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
