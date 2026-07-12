"""BenchReport schema-version migration pipeline.

The contract evolves through additive minor bumps (a new optional field with a
default — Pydantic fills in the default for old payloads, no migrator needed)
and breaking major bumps (renames or removals — every consumer needs to upgrade
through a registered migrator). This module owns the second path: a tiny
``(from_v, to_v) -> Callable`` registry and a single dispatch entry point.

A migrator is registered with :func:`register_migration`:

    @register_migration("1.0", "1.1")
    def _upgrade_1_0_to_1_1(payload: dict) -> dict:
        # mutate or rebuild the dict and return it
        return payload

and called via :func:`migrate_report`:

    upgraded = migrate_report(payload, from_v=payload["schemaVersion"], to_v=SCHEMA_VERSION)

The dispatcher exists so adding a new path is **one decoration**, not a new
``if/elif`` arm inside the migrate function — registry-over-imperative is the
project's standing convention (see CLAUDE.md).
"""

from __future__ import annotations

import json

from collections.abc import Callable
from pathlib import Path

from oracles.bench_contract import SCHEMA_VERSION

Migration = Callable[[dict], dict]

# Public registry: `(from_v, to_v) -> migration fn`. Tests inspect this directly,
# so the dict is the source of truth for "which paths are registered" — never
# duplicated in a parallel ``if/elif`` chain.
MIGRATIONS: dict[tuple[str, str], Migration] = {}


def register_migration(from_v: str, to_v: str) -> Callable[[Migration], Migration]:
    """Register ``fn`` as the upgrader from ``from_v`` to ``to_v``.

    Decorator form:

        @register_migration("1.0", "1.1")
        def _upgrade_1_0_to_1_1(payload: dict) -> dict:
            ...
    """

    def deco(fn: Migration) -> Migration:
        MIGRATIONS[(from_v, to_v)] = fn
        return fn

    return deco


def migrate_report(payload: dict, *, from_v: str, to_v: str) -> dict:
    """Upgrade a deserialized BenchReport-shaped dict between schema versions.

    Returns the payload unchanged when ``from_v == to_v`` (identity, zero-cost
    happy path). Raises :class:`ValueError` when the requested ``(from_v, to_v)``
    pair is not registered — never silently passes an unmigrated payload through
    to Pydantic, where it would error downstream with a less actionable message.
    """
    if from_v == to_v:
        return payload
    key = (from_v, to_v)
    if key not in MIGRATIONS:
        raise ValueError(f"No migration path from {from_v} to {to_v}")
    return MIGRATIONS[key](payload)


# --------------------------------------------------------------------------- #
# Registered migrations
# --------------------------------------------------------------------------- #
@register_migration("1.0", "1.1")
def _upgrade_1_0_to_1_1(payload: dict) -> dict:
    """1.0 → 1.1: additive ``baseline_solver_id`` field.

    The field has a default of ``"lmfit"`` on the Pydantic side, so old payloads
    validate against the bumped schema without going through this migrator. This
    entry is registered for completeness so the pipeline is exercised end-to-end
    and so a future tool that *insists* on a complete migration chain doesn't
    fall through the gap. The migrator just updates ``schemaVersion``; the
    default fills in the missing field at validation time.
    """
    return {**payload, "schemaVersion": "1.1"}


@register_migration("1.1", "1.2")
def _upgrade_1_1_to_1_2(payload: dict) -> dict:
    """1.1 -> 1.2: additive ``manifest`` field (optional, default ``None``).

    Completeness entry (same pattern as 1.0 -> 1.1): the Pydantic default fills
    the field, this migrator only advances ``schemaVersion`` so the chain walked
    by :func:`migrate_payload_to_current` is gap-free from 1.0 onward.
    """
    return {**payload, "schemaVersion": "1.2"}


@register_migration("1.2", "1.3")
def _upgrade_1_2_to_1_3(payload: dict) -> dict:
    """1.2 -> 1.3: attach the panel registry.

    Unlike the pure-completeness 1.0 -> 1.1 entry, an empty ``panels`` list
    would render a BLANK Case page in the post-Plan-D web shell (the grid is
    driven entirely by panel specs). DEFAULT_PANELS is a static registry —
    the 1.2-era engine rendered exactly these hardcoded panels — so attaching
    it is the semantically faithful upgrade, not an invention.
    """
    from oracles.panels import default_panels

    return {
        **payload,
        "schemaVersion": "1.3",
        "panels": [p.model_dump(by_alias=True) for p in default_panels()],
    }


@register_migration("1.3", "1.4")
def _upgrade_1_3_to_1_4(payload: dict) -> dict:
    """1.3 -> 1.4: additive inference block + data_provenance fields.

    Pure completeness entry — every new field has a Pydantic default
    (inference=None, data_provenance="synthetic", speedup_ci=None), so old
    payloads validate without transformation; this only advances the stamp.
    """
    return {**payload, "schemaVersion": "1.4"}


@register_migration("1.4", "1.5")
def _upgrade_1_4_to_1_5(payload: dict) -> dict:
    """1.4 -> 1.5: additive ``BackendProfile.theta_distance`` series.

    The real convergence-to-truth metric. Pure completeness entry — the new field
    has a Pydantic default
    (``theta_distance=None``), so old payloads validate without transformation;
    this only advances the stamp.
    """
    return {**payload, "schemaVersion": "1.5"}


@register_migration("1.5", "1.6")
def _upgrade_1_5_to_1_6(payload: dict) -> dict:
    """1.5 -> 1.6: rename the misleading ``timeResolved`` field to ``globalFit``.

    The field was always a shared-model multi-spectrum joint global fit, not a
    time-specific feature (SP-3). Field rename → breaking, so this migrator
    rewrites the wire key (and its time-specific sub-keys ``times``/``t``/
    ``tLabel`` → ``datasetAxis``/``coord``/``axisLabel``) on every analyzed case.
    """
    out = {**payload, "schemaVersion": "1.6"}
    analyzed = out.get("analyzed")
    if isinstance(analyzed, list):
        new_analyzed = []
        for case in analyzed:
            if isinstance(case, dict) and "timeResolved" in case:
                case = {**case}
                tr = case.pop("timeResolved")
                if isinstance(tr, dict):
                    tr = {**tr}
                    if "times" in tr:
                        tr["datasetAxis"] = tr.pop("times")
                    if "tLabel" in tr:
                        tr["axisLabel"] = tr.pop("tLabel")
                    slices = tr.get("slices")
                    if isinstance(slices, list):
                        new_slices = []
                        for s in slices:
                            if isinstance(s, dict) and "t" in s:
                                t_val = s["t"]
                                s = {k: v for k, v in s.items() if k != "t"}
                                s["coord"] = t_val
                            new_slices.append(s)
                        tr["slices"] = new_slices
                case["globalFit"] = tr
            new_analyzed.append(case)
        out["analyzed"] = new_analyzed
    return out


@register_migration("1.6", "1.7")
def _upgrade_1_6_to_1_7(payload: dict) -> dict:
    """1.6 -> 1.7: ``multidim`` reshaped from a 2-D map to a genuine N-D fit (SP-2).

    The field was a 2-D-only ``gaussian2d`` map (``nx``/``ny`` + 2-D
    ``obs``/``model``/``resid`` grids + ``MultiDimPeak`` cx/cy/sx/sy); it is now a
    real ≥3-D ``gaussian_nd`` showcase (``nDims``/``shape``/``rSquared`` +
    ``NdPeak`` amplitude/center[]/sigma[]). The old 2-D instances cannot be mapped
    to the N-D shape and are synthetic + regenerated on every run, so they are
    dropped to ``None`` (the field is optional). New runs populate the N-D form.
    """
    out = {**payload, "schemaVersion": "1.7"}
    analyzed = out.get("analyzed")
    if isinstance(analyzed, list):
        out["analyzed"] = [
            {**case, "multidim": None}
            if isinstance(case, dict) and case.get("multidim") is not None
            else case
            for case in analyzed
        ]
    return out


# --------------------------------------------------------------------------- #
# Chain helpers: walk any legacy payload up to today's SCHEMA_VERSION
# --------------------------------------------------------------------------- #
def migrate_payload_to_current(payload: dict) -> dict:
    """Walk *payload* through registered single-step migrations to SCHEMA_VERSION.

    Identity (no copy) when the payload is already current. Each hop is looked
    up in :data:`MIGRATIONS` by the payload's current ``schemaVersion``; a
    missing hop raises :class:`ValueError` — never a silent pass-through of a
    stale payload (the no-silent-fallback rule). A migrator that fails to
    advance the version stamp is also a loud error, so a buggy entry cannot
    spin the walk forever.

    Once at least one hop runs, the fully-migrated payload is validated against
    today's :class:`~oracles.bench_contract.BenchReport`. The stamp-only migrators
    (1.3→1.4, 1.4→1.5) advance the version without transforming the payload, on
    the assumption that Pydantic defaults cover the new fields; this validation
    *proves* that assumption per payload, so a stamp-only migration that yields
    a structurally invalid dict raises a ``pydantic.ValidationError`` here
    instead of silently handing a broken payload downstream (EF-PY-10). The
    already-current identity path is left untouched (zero-cost, no validation).
    """
    current = payload.get("schemaVersion")
    if current is None:
        raise ValueError("payload has no schemaVersion field; cannot migrate")
    migrated = False
    while current != SCHEMA_VERSION:
        step = next(
            (fn for (f, _t), fn in MIGRATIONS.items() if f == current),
            None,
        )
        if step is None:
            raise ValueError(f"No migration path from {current} to {SCHEMA_VERSION}")
        payload = step(payload)
        migrated = True
        bumped = payload.get("schemaVersion")
        if bumped == current:
            raise ValueError(f"migration from {current} did not advance schemaVersion")
        current = bumped
    if migrated:
        from oracles.bench_contract import BenchReport

        BenchReport.model_validate(payload)
    return payload


def migrate_to_current(path: str | Path) -> str:
    """File-level shim for the offline-bundle path (``poe report_html``).

    Loads ``results.json`` at *path*; when already at SCHEMA_VERSION the
    original path is returned unchanged (zero-cost happy path). Otherwise the
    payload is chain-migrated and written next to the original as
    ``results.migrated.json``, and that new path is printed-friendly returned —
    the poe task feeds it to the web build as ``BENCH_JSON``.
    """
    src = Path(path)
    payload = json.loads(src.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") == SCHEMA_VERSION:
        return str(src)
    upgraded = migrate_payload_to_current(payload)
    dest = src.with_name("results.migrated.json")
    dest.write_text(json.dumps(upgraded), encoding="utf-8")
    return str(dest)
