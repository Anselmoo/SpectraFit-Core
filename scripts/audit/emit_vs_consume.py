"""Discovery instrument (NOT a CI guard) for unreferenced contract fields.

Lists BenchReport contract leaves the Python contract emits whose camelCase name
is never referenced anywhere under web/src — dead-field / missing-plot
candidates. Heuristic; emits candidates.

Run from repo root:  uv run python scripts/audit/emit_vs_consume.py
"""

from __future__ import annotations

import re
from pathlib import Path

CONTRACT = Path("python/oracles/bench_contract.py")
WEB_SRC = Path("web/src")


def emitted_fields() -> set[str]:
    """Pydantic field names declared in contract.py (snake_case -> camelCase)."""
    text = CONTRACT.read_text()
    snake = set(re.findall(r"^\s{4}([a-z][a-z0-9_]*)\s*:", text, re.MULTILINE))
    out: set[str] = set()
    for s in snake:
        parts = s.split("_")
        out.add(parts[0] + "".join(p.title() for p in parts[1:]))
    return out


def web_references() -> str:
    """Concatenate all non-test web/src TypeScript source for substring lookup."""
    return "".join(
        p.read_text()
        for p in WEB_SRC.rglob("*.ts*")
        if "__tests__" not in str(p) and "node_modules" not in str(p)
    )


def main() -> None:
    """Print emitted contract fields that no web/src source references."""
    web = web_references()
    unref = sorted(f for f in emitted_fields() if len(f) >= 4 and f not in web)
    print(f"emitted-but-unreferenced contract fields: {len(unref)}")
    for f in unref:
        print(f"  {f}")


if __name__ == "__main__":
    main()
