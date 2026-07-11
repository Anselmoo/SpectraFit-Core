"""TDD red phase: the migrate scaffold the contract-evolution policy needs.

These tests fail to import / fail their assertions until
``python/extras/bench/migrate.py`` exists. They pin four properties:

1. Identity when ``from_v == to_v`` — the zero-cost happy path.
2. Unknown ``(from, to)`` pairs raise a clear ``ValueError`` — never silently
   pass an unmigrated payload through to Pydantic where it would error
   downstream with a less actionable message.
3. The Pydantic-canonical additive-bump pattern: an old payload (without a
   future field) validates as the current BenchReport via the field's default.
4. The migration registry is the exclusive source of truth — adding a path is
   one ``@register_migration`` decoration, not an ``if/elif`` chain inside the
   migrate function.

Closes Top-10 #3 (registry-driven round-trip coverage):
the registry-driven round-trip block at the bottom of this file actually exercises
every registered ``(from_v, to_v)`` migrator end-to-end, so the first breaking
schema bump cannot discover the dispatcher missing an arm at 2 a.m.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from oracles.bench_contract import SCHEMA_VERSION, BenchReport
from oracles.migrate import (
    MIGRATIONS,
    migrate_payload_to_current,
    migrate_report,
    migrate_to_current,
    register_migration,
)
from oracles.panels import DEFAULT_PANELS
from oracles.reports import latest_results
from oracles.synth import build_report


def test_identity_when_versions_equal() -> None:
    """``from_v == to_v`` returns the payload unchanged (no copy required)."""
    payload = {"schemaVersion": "1.0", "x": 1}
    assert migrate_report(payload, from_v="1.0", to_v="1.0") == payload


def test_unknown_pair_raises_with_actionable_message() -> None:
    """A missing migration registration is a loud ``ValueError`` — not a silent pass."""
    with pytest.raises(ValueError, match="No migration path from 2.0 to 3.0"):
        migrate_report({}, from_v="2.0", to_v="3.0")


def test_pydantic_accepts_old_payload_via_default() -> None:
    """An on-disk results.json validates as the current BenchReport (after migration).

    Pins that the chain migration + Pydantic validation path works end-to-end for
    any results.json on disk. Payloads already at SCHEMA_VERSION pass through as
    identity (zero-cost); older payloads are chain-migrated first. Breaking schema
    bumps (like 1.5→1.6, which renamed ``timeResolved``→``globalFit``) require a
    registered migrator — additive-only bumps need only a Pydantic default.
    """
    latest = latest_results("benchmark")
    if latest is None:
        pytest.skip("no benchmark run on disk to migrate")
    raw = json.loads(latest.read_text(encoding="utf-8"))
    migrated = migrate_payload_to_current(raw)
    BenchReport.model_validate(migrated)  # must not raise


def test_migrations_registry_is_extensible_via_decorator() -> None:
    """Registering a new path is one ``@register_migration`` call.

    The dispatcher reads the registry; there is no ``if/elif`` chain inside
    ``migrate_report``. Anti-regression for someone who would later add a
    new path by editing the function body instead of adding a registration.
    """

    @register_migration("9.9", "9.10")
    def _upgrade(payload: dict) -> dict:
        return {**payload, "upgraded": True}

    try:
        out = migrate_report({"x": 1}, from_v="9.9", to_v="9.10")
        assert out["upgraded"] is True
        assert ("9.9", "9.10") in MIGRATIONS
    finally:
        MIGRATIONS.pop(("9.9", "9.10"), None)


# --------------------------------------------------------------------------- #
# Registered-path round-trip (Top-10 #3): every migrator runs end-to-end.
#
# The tests above pin the *shape* of the registry; the block below pins that
# every entry actually produces a payload that survives Pydantic validation.
# A migrator that compiles but trashes a required field would otherwise only
# be discovered the first time someone tries to read a legacy results.json.
# --------------------------------------------------------------------------- #


@pytest.fixture
def current_payload_dict() -> dict:
    """A canonical current-schema BenchReport, serialized as a dict (camelCase aliases)."""
    return json.loads(build_report().model_dump_json(by_alias=True))


def test_registry_is_nonempty() -> None:
    """A registry that never gets exercised is not Rosetta — it's wishful thinking.

    Drops to zero only if the project removes every breaking-major path. In that
    case this guard reminds the author to delete this whole block and re-add it
    when the next breaking bump lands.
    """
    assert MIGRATIONS, (
        "MIGRATIONS registry is empty — at least one path must remain to keep the "
        "dispatcher exercised against a real payload."
    )


def _stamp_schema_version(payload: dict, version: str) -> dict:
    """Seed ``payload`` with a single ``schemaVersion`` key (camelCase wire form).

    ``BenchReport`` is an ``extra="forbid"`` model with ``alias_generator=to_camel``.
    Pydantic accepts the camelCase alias OR the snake_case field name — but never
    BOTH in the same dict (the duplicate is treated as an unknown extra and fails
    validation). The serialized form ``model_dump_json(by_alias=True)`` produces
    camelCase, which is what archived ``results.json`` files on disk carry, so the
    tests below seed only that form.
    """
    payload.pop("schema_version", None)
    payload["schemaVersion"] = version
    return payload


def test_every_registered_migrator_stamps_target_schema_version(
    current_payload_dict: dict,
) -> None:
    """Every registered ``(from_v, to_v)`` migrator stamps ``to_v`` on the result.

    A migrator that returns the payload without bumping the version is the most
    common silent-fail mode (the dispatcher succeeds, Pydantic accepts the old
    version, downstream tools think the migration didn't run). The contract is:
    after migration, the schemaVersion key reads ``to_v``.
    """
    for (from_v, to_v), migrator in MIGRATIONS.items():
        legacy = _stamp_schema_version(deepcopy(current_payload_dict), from_v)
        upgraded = migrator(legacy)
        assert "schemaVersion" in upgraded, (
            f"migrator {from_v} → {to_v} dropped the schemaVersion field entirely"
        )
        assert upgraded["schemaVersion"] == to_v, (
            f"migrator {from_v} → {to_v} produced {upgraded['schemaVersion']!r} instead of {to_v!r}"
        )


def test_every_registered_migrator_produces_a_payload_pydantic_accepts(
    current_payload_dict: dict,
) -> None:
    """End-to-end: migrate output validates as today's BenchReport.

    This is the Rosetta property the registry is supposed to enforce. A migrator
    that bumps the version but trashes a required field would slip through every
    test above and only show up the first time someone tries to read a legacy
    results.json — typically the day before publication.
    """
    for (from_v, _to_v), migrator in MIGRATIONS.items():
        legacy = _stamp_schema_version(deepcopy(current_payload_dict), from_v)
        upgraded = migrator(legacy)
        # Defaults on additive fields fill in for anything the migrator left implicit.
        BenchReport.model_validate(upgraded)


def test_built_in_1_0_to_1_1_upgrade_round_trips_end_to_end(
    current_payload_dict: dict,
) -> None:
    """Concrete instance: the registered 1.0 → 1.1 path round-trips a real shape.

    1.0 → 1.1 added ``baseline_solver_id`` (default ``"lmfit"``). A pre-1.1
    payload would lack the field entirely; the migrator stamps the version, and
    Pydantic's default fills the missing field at validation time. This pins
    that the additive-bump contract works in practice, not just in policy.
    """
    pre_1_1 = deepcopy(current_payload_dict)
    pre_1_1.pop("baselineSolverId", None)  # camelCase alias — _Base serializes this way
    pre_1_1.pop("baseline_solver_id", None)
    _stamp_schema_version(pre_1_1, "1.0")

    upgraded = migrate_report(pre_1_1, from_v="1.0", to_v="1.1")
    report = BenchReport.model_validate(upgraded)
    assert report.schema_version == "1.1"
    assert report.baseline_solver_id == "lmfit", "Pydantic default did not fill the missing field"


def test_additive_minor_bump_validates_without_going_through_migrate(
    current_payload_dict: dict,
) -> None:
    """1.1 → 1.2 is an additive minor bump (``manifest`` optional with default).

    Per the SCHEMA_VERSION evolution policy (DECISIONS.md 2026-06-06), additive
    minor bumps must NOT need a migrator: Pydantic's default-on-optional handles
    them at validation time. This test pins the policy by skipping migrate.py
    entirely and asserting the older payload still validates as today's schema.
    """
    pre_1_2 = deepcopy(current_payload_dict)
    pre_1_2.pop("manifest", None)
    _stamp_schema_version(pre_1_2, "1.1")
    # No migrate_report call — additive-minor contract says Pydantic covers it.
    report = BenchReport.model_validate(pre_1_2)
    assert report.manifest is None
    # Pydantic accepts the legacy schemaVersion verbatim; the additive-bump
    # contract is about *field shape* compatibility, not about silently rewriting
    # the version stamp on disk.
    assert report.schema_version in {"1.1", SCHEMA_VERSION}


def test_migrate_1_2_to_1_3_attaches_nonempty_default_panels(
    current_payload_dict: dict,
) -> None:
    """1.2 → 1.3 attaches the real DEFAULT_PANELS registry — NOT an empty list.

    An empty ``panels`` list renders a BLANK Case page in the post-Plan-D web
    shell (the grid is driven entirely by panel specs), so the migrator must
    attach the static DEFAULT_PANELS the 1.2-era engine rendered hardcoded.
    """
    pre_1_3 = deepcopy(current_payload_dict)
    pre_1_3.pop("panels", None)
    _stamp_schema_version(pre_1_3, "1.2")

    migrated = migrate_report(pre_1_3, from_v="1.2", to_v="1.3")
    assert migrated["schemaVersion"] == "1.3"
    report = BenchReport.model_validate(migrated)
    assert len(report.panels) >= 20, "1.2 → 1.3 must attach a NON-empty panel registry"
    assert len(report.panels) == len(DEFAULT_PANELS)
    assert [p.id for p in report.panels] == [p.id for p in DEFAULT_PANELS]


def test_migrate_payload_to_current_chains_from_1_0(
    current_payload_dict: dict,
) -> None:
    """A 1.0 payload chain-walks 1.0 → 1.1 → 1.2 → 1.3 in one call.

    This is the API/bundle chokepoint contract: any archived results.json,
    however old, comes out stamped SCHEMA_VERSION with a non-empty panel
    registry — no gap in the registered chain.
    """
    legacy = deepcopy(current_payload_dict)
    legacy.pop("panels", None)
    legacy.pop("manifest", None)
    legacy.pop("baselineSolverId", None)
    legacy.pop("baseline_solver_id", None)
    _stamp_schema_version(legacy, "1.0")

    upgraded = migrate_payload_to_current(legacy)
    assert upgraded["schemaVersion"] == SCHEMA_VERSION
    report = BenchReport.model_validate(upgraded)
    assert report.baseline_solver_id == "lmfit"
    assert len(report.panels) >= 20


def test_migrate_payload_to_current_is_identity_when_current(
    current_payload_dict: dict,
) -> None:
    """An already-current payload passes through unchanged (zero-cost path)."""
    payload = deepcopy(current_payload_dict)
    _stamp_schema_version(payload, SCHEMA_VERSION)
    assert migrate_payload_to_current(payload) is payload


def test_migrate_payload_to_current_raises_on_unknown_version() -> None:
    """An unregistered version is a loud ValueError, never a silent pass."""
    with pytest.raises(ValueError, match="No migration path from 0.9"):
        migrate_payload_to_current({"schemaVersion": "0.9"})
    with pytest.raises(ValueError, match="no schemaVersion"):
        migrate_payload_to_current({})


def test_chain_migration_validates_final_payload(
    current_payload_dict: dict,
) -> None:
    """EF-PY-10: a stamp-only migration that yields an INVALID payload must raise.

    The 1.3→1.4 / 1.4→1.5 migrators only advance the version stamp ("Pydantic
    defaults fill the new fields"). Nothing proved the *stamped* payload still
    validates against today's contract. If an archived payload is structurally
    corrupt (here: a required field set to the wrong type), the chain walk must
    fail loudly with a validation error — not silently hand a broken dict back.
    """
    import pydantic

    corrupt = deepcopy(current_payload_dict)
    # `suite` is a required list field; a string is structurally invalid.
    corrupt["suite"] = "not-a-list"
    _stamp_schema_version(corrupt, "1.4")  # stamp-only hop 1.4 → 1.5

    with pytest.raises(pydantic.ValidationError):
        migrate_payload_to_current(corrupt)


def test_chain_migration_lets_valid_payload_round_trip(
    current_payload_dict: dict,
) -> None:
    """EF-PY-10 anti-regression: a structurally VALID legacy payload still passes.

    The post-migration validation must not reject good payloads — a 1.4 payload
    (missing only the additive 1.5 ``theta_distance`` field) chain-migrates and
    validates clean.
    """
    legacy = deepcopy(current_payload_dict)
    _stamp_schema_version(legacy, "1.4")
    upgraded = migrate_payload_to_current(legacy)
    assert upgraded["schemaVersion"] == SCHEMA_VERSION
    BenchReport.model_validate(upgraded)  # must not raise


def test_migrate_to_current_file_shim(
    current_payload_dict: dict, tmp_path: Path
) -> None:
    """The bundle-path shim writes ``results.migrated.json`` for old payloads.

    Current payloads return the original path unchanged; pre-current payloads
    get a sibling ``results.migrated.json`` whose content is chain-migrated —
    the ``poe report_html`` task feeds that file to the web build as BENCH_JSON.
    """
    # Already-current → original path back, no sibling written.
    current = deepcopy(current_payload_dict)
    _stamp_schema_version(current, SCHEMA_VERSION)
    src_current = tmp_path / "current" / "results.json"
    src_current.parent.mkdir(parents=True)
    src_current.write_text(json.dumps(current), encoding="utf-8")
    assert migrate_to_current(src_current) == str(src_current)
    assert not (src_current.parent / "results.migrated.json").exists()

    # 1.2 payload → sibling results.migrated.json with non-empty panels.
    legacy = deepcopy(current_payload_dict)
    legacy.pop("panels", None)
    _stamp_schema_version(legacy, "1.2")
    src_legacy = tmp_path / "legacy" / "results.json"
    src_legacy.parent.mkdir(parents=True)
    src_legacy.write_text(json.dumps(legacy), encoding="utf-8")
    migrated_path = Path(migrate_to_current(src_legacy))
    assert migrated_path.name == "results.migrated.json"
    payload = json.loads(migrated_path.read_text(encoding="utf-8"))
    assert payload["schemaVersion"] == SCHEMA_VERSION
    assert len(payload["panels"]) >= 20


def test_1_2_to_1_3_additive_bump_validates_without_migrator(
    current_payload_dict: dict,
) -> None:
    """1.2 -> 1.3 is an additive minor bump (``panels`` optional, default []).

    Per the SCHEMA_VERSION evolution policy (DECISIONS.md 2026-06-06), additive
    minor bumps must NOT need a migrator: Pydantic's default-on-optional handles
    them at validation time. This test pins the policy by skipping migrate.py
    entirely and asserting the older payload still validates as today's schema.
    """
    pre_1_3 = deepcopy(current_payload_dict)
    pre_1_3.pop("panels", None)
    _stamp_schema_version(pre_1_3, "1.2")
    # No migrate_report call — additive-minor contract says Pydantic covers it.
    report = BenchReport.model_validate(pre_1_3)
    assert report.panels == []
    # Pydantic accepts the legacy schemaVersion verbatim; the additive-bump
    # contract is about *field shape* compatibility, not about silently rewriting
    # the version stamp on disk.
    assert report.schema_version in {"1.2", SCHEMA_VERSION}


def test_migrate_1_5_to_1_6_renames_time_resolved_to_global_fit() -> None:
    """1.5 → 1.6: the misleading ``timeResolved`` field is renamed to ``globalFit``.

    The field was always a shared-model multi-spectrum joint global fit, not a
    time-specific feature (SP-3). The migrator also rewrites the time-specific
    sub-keys (``times``→``datasetAxis``, ``tLabel``→``axisLabel``, per-slice
    ``t``→``coord``) so the wire is fully axis-neutral after migration.
    """
    payload = {
        "schemaVersion": "1.5",
        "analyzed": [
            {
                "timeResolved": {
                    "x": [0.0, 1.0],
                    "times": [0.0, 0.5],
                    "tLabel": "time",
                    "slices": [
                        {"t": 0.0, "obs": [1.0], "model": [1.0]},
                        {"t": 0.5, "obs": [2.0], "model": [2.0]},
                    ],
                    "traces": [],
                }
            }
        ],
    }
    out = migrate_report(payload, from_v="1.5", to_v="1.6")

    assert out["schemaVersion"] == "1.6"
    case = out["analyzed"][0]
    assert "timeResolved" not in case
    assert "globalFit" in case
    gf = case["globalFit"]
    # top-level sub-key renames
    assert "times" not in gf and gf["datasetAxis"] == [0.0, 0.5]
    assert "tLabel" not in gf and gf["axisLabel"] == "time"
    # per-slice rename
    assert all("t" not in s and "coord" in s for s in gf["slices"])
    assert [s["coord"] for s in gf["slices"]] == [0.0, 0.5]


def test_migrate_1_6_to_1_7_drops_legacy_multidim() -> None:
    """1.6 → 1.7: the 2-D-only ``multidim`` is reshaped to a genuine N-D fit (SP-2).

    Old 2-D map instances (nx/ny + 2-D grids + cx/cy/sx/sy peaks) cannot be mapped
    to the N-D shape and are synthetic + regenerated each run, so the migrator
    drops them to ``None``; new runs populate the N-D form.
    """
    payload = {
        "schemaVersion": "1.6",
        "analyzed": [
            {"multidim": {"nx": 2, "ny": 2, "obs": [[1.0]], "peaks": []}},
            {"multidim": None},
        ],
    }
    out = migrate_report(payload, from_v="1.6", to_v="1.7")

    assert out["schemaVersion"] == "1.7"
    assert out["analyzed"][0]["multidim"] is None
    assert out["analyzed"][1]["multidim"] is None
