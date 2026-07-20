"""Wire W3 — results.json must round-trip through the Pydantic contract.

If parsing then re-emitting changes any value, the on-disk payload is not the
canonical form. Catches: silent NaN→0 conversion that isn't idempotent, alias
drift, default-value drift.

Each ``results.json`` is ~46 MB, so a sweep over every run on disk (26+) OOM-kills
the audit suite. The **default** test therefore round-trips only the newest few
runs (memory-safe). The **full-history** sweep is marked ``slow`` and excluded from
the default run (``addopts = -m 'not slow'`` in ``pyproject.toml``); run it
explicitly with ``pytest -m slow`` on a machine/CI with ample RAM.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oracles.bench_contract import SCHEMA_VERSION, BenchReport
from oracles.migrate import migrate_payload_to_current
from oracles.reports import REPORTS_ROOT

# How many of the newest runs the default (non-slow) test round-trips. Bounded so
# the audit suite stays memory-safe; the slow test below covers full history.
_DEFAULT_RECENT = 3


def _all_results() -> list[Path]:
    return sorted(REPORTS_ROOT.glob("benchmark/*/results.json"))


_ALL = _all_results()
_LATEST = _ALL[-_DEFAULT_RECENT:]


def _case_id(p: Path) -> str:
    return f"{p.parent.parent.name}/{p.parent.name}"


def _assert_canonical_roundtrip(path: Path) -> None:
    raw = json.loads(path.read_text())
    # Runs predating a later schema bump (e.g. SP-3's 1.5→1.6 time_resolved→
    # global_fit rename) are legitimately non-canonical on disk: migrate to the
    # current schema first. Migration *correctness* is pinned in test_migrate;
    # here we check the contract's parse→emit behaviour on the current form.
    payload = migrate_payload_to_current(raw)
    model = BenchReport.model_validate(payload)
    re_emitted = json.loads(model.model_dump_json(by_alias=True))

    if raw.get("schemaVersion") == SCHEMA_VERSION:
        # Current-schema run: the on-disk payload MUST already be byte-canonical
        # (catches silent NaN→0, alias drift, default-value drift on write).
        assert json.dumps(re_emitted, sort_keys=True) == json.dumps(
            raw, sort_keys=True
        ), (
            f"non-canonical results.json at {path}: parse→emit changed bytes; "
            "find the field that drifted via `deepdiff.DeepDiff(raw, re_emitted)`"
        )
    else:
        # Pre-bump run: assert parse→emit is IDEMPOTENT on the migrated form —
        # re-parsing the emitted payload and re-emitting must not drift.
        re_emitted_2 = json.loads(
            BenchReport.model_validate(re_emitted).model_dump_json(by_alias=True)
        )
        assert json.dumps(re_emitted, sort_keys=True) == json.dumps(
            re_emitted_2, sort_keys=True
        ), (
            f"non-idempotent contract round-trip at {path} (schema "
            f"{raw.get('schemaVersion')}→{SCHEMA_VERSION}): emit→parse→emit drifted; "
            "inspect via `deepdiff.DeepDiff(re_emitted, re_emitted_2)`"
        )


@pytest.mark.skipif(not _LATEST, reason="no benchmark run on disk yet")
@pytest.mark.parametrize("path", _LATEST, ids=_case_id)
def test_results_json_canonical_roundtrip(path: Path):
    """Default, memory-safe: round-trip the latest few runs."""
    _assert_canonical_roundtrip(path)


@pytest.mark.slow
@pytest.mark.skipif(not _ALL, reason="no benchmark run on disk yet")
@pytest.mark.parametrize("path", _ALL, ids=_case_id)
def test_results_json_canonical_roundtrip_full_history(path: Path):
    """Opt-in (``pytest -m slow``): round-trip every run on disk.

    Memory-heavy (~46 MB per run × all runs) — run only on an ample-RAM
    machine/CI, never in the default suite.
    """
    _assert_canonical_roundtrip(path)
