"""DEFAULT_PANELS registry invariants + engine attachment."""

from __future__ import annotations

import json
from pathlib import Path

from oracles.bench_contract import PanelSpec
from oracles.panels import DEFAULT_PANELS, default_panels, write_fixture


def test_panel_ids_unique() -> None:
    ids = [p.id for p in DEFAULT_PANELS]
    assert len(ids) == len(set(ids)), f"duplicate panel ids: {ids}"


def test_every_panel_is_a_valid_panelspec() -> None:
    for p in DEFAULT_PANELS:
        assert isinstance(p, PanelSpec)
        assert p.source, f"panel {p.id} has empty source"


def test_default_panels_returns_fresh_list() -> None:
    a = default_panels()
    b = default_panels()
    assert a == list(DEFAULT_PANELS)
    assert a is not b


def test_fixture_matches_registry() -> None:
    """The checked-in web fixture must be regenerated when the registry changes."""
    fixture = (
        Path(__file__).resolve().parents[3]
        / "web"
        / "src"
        / "fixtures"
        / "default_panels.json"
    )
    assert fixture.exists(), (
        "web/src/fixtures/default_panels.json missing - run "
        "`uv run python -m oracles.panels` to regenerate"
    )
    on_disk = json.loads(fixture.read_text(encoding="utf-8"))
    current = json.loads(
        json.dumps([p.model_dump(by_alias=True) for p in DEFAULT_PANELS])
    )
    assert on_disk == current, (
        "default_panels.json is stale - run `uv run python -m oracles.panels`"
    )


def test_write_fixture_round_trips(tmp_path: Path) -> None:
    out = tmp_path / "default_panels.json"
    write_fixture(out)
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert [p["id"] for p in loaded] == [p.id for p in DEFAULT_PANELS]
