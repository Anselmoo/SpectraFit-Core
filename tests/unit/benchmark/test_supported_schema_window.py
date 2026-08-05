"""Guard: the supported-schema window is single-sourced and cannot drift.

`oracles.bench_contract.SUPPORTED_SCHEMA` is the SINGLE SOURCE OF TRUTH for which
payload versions a current build renders. The web mirror
(`web/src/contract/index.ts` → ``export const SUPPORTED_SCHEMA = new Set([...])``)
is a hand-written literal kept *independently buildable* (the web tree never has
to run the Python app), but it is PINNED to the canonical window by this test —
so a schema bump that updates one side and forgets the other fails CI loudly
instead of merging as a latent red.

This is the named, non-bypassable guard the architecture-grilling tribunal
required for the schema single-source-of-truth (closing the SP-3-class defect
where the web gate silently lagged the 1.5→1.6 rename). It runs in the default
pytest suite — there is no ``--no-verify`` path around a failing test.
"""

from __future__ import annotations

import re
from pathlib import Path

from oracles.bench_contract import SCHEMA_VERSION, SUPPORTED_SCHEMA
from oracles.migrate import MIGRATIONS

_WEB_CONTRACT = (
    Path(__file__).resolve().parents[3] / "web" / "src" / "contract" / "index.ts"
)


def _web_supported_schema() -> set[str]:
    """Parse ``new Set([...])`` out of the web SUPPORTED_SCHEMA literal."""
    src = _WEB_CONTRACT.read_text(encoding="utf-8")
    m = re.search(
        r"export\s+const\s+SUPPORTED_SCHEMA\s*=\s*new\s+Set\(\[(?P<body>.*?)\]\)",
        src,
        re.DOTALL,
    )
    assert m is not None, (
        f"could not locate `export const SUPPORTED_SCHEMA = new Set([...])` in "
        f"{_WEB_CONTRACT} — the guard's parser is stale or the web mirror moved"
    )
    return set(re.findall(r'["\']([^"\']+)["\']', m.group("body")))


def test_web_mirror_matches_canonical_window() -> None:
    """The web SUPPORTED_SCHEMA set must equal the canonical Python window."""
    web = _web_supported_schema()
    canonical = set(SUPPORTED_SCHEMA)
    assert web == canonical, (
        "SUPPORTED_SCHEMA drift: the web mirror "
        f"({sorted(web)}) does not match the canonical window "
        f"({sorted(canonical)}) in oracles.bench_contract. Update "
        f"{_WEB_CONTRACT} so the two agree — they are single-sourced on purpose."
    )


def test_current_version_is_in_window() -> None:
    """A build must render its own current-version payloads."""
    assert SCHEMA_VERSION in SUPPORTED_SCHEMA, (
        f"SCHEMA_VERSION {SCHEMA_VERSION!r} is not in the supported window "
        f"{SUPPORTED_SCHEMA!r} — the current version must always be renderable"
    )


def test_every_windowed_version_can_migrate_to_current() -> None:
    """No windowed version may be un-migrate-able to ``SCHEMA_VERSION``.

    Reachability over the adjacent ``MIGRATIONS`` steps (e.g. 1.4→1.5→…→1.7).
    The current version trivially reaches itself.
    """
    # adjacency: from_v -> set(to_v)
    adj: dict[str, set[str]] = {}
    for from_v, to_v in MIGRATIONS:
        adj.setdefault(from_v, set()).add(to_v)

    def reaches_current(v: str) -> bool:
        seen: set[str] = set()
        stack = [v]
        while stack:
            cur = stack.pop()
            if cur == SCHEMA_VERSION:
                return True
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(adj.get(cur, ()))
        return False

    for v in SUPPORTED_SCHEMA:
        assert reaches_current(v), (
            f"windowed version {v!r} has no migration path to {SCHEMA_VERSION!r} "
            f"in oracles.migrate.MIGRATIONS — the window admits an "
            f"un-migrate-able version; add the migrator or drop it from the window"
        )
