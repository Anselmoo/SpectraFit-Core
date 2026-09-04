"""Hook conformance harness — point the verification machine at itself.

The project leans on a wall of Edit/Write hooks (CLAUDE.md calls the
conventions "load-bearing"). But a hook scoped to a path that no longer
exists is *silently inert*: it exits 0 on everything, and a green light
wired to nothing looks identical to a working guard.

This harness treats every hook as a subject under test, exactly the way
the oracles benchmark treats spectrafit:

  * a ``should_block`` oracle — a payload the hook MUST reject (exit 2),
  * a ``should_pass`` oracle — a payload the hook MUST allow (exit 0).

A guard scoped to a dead path (``python/benchmarkmark/``, ``frontend/``,
empty ``python/extras/`` …) physically cannot block its own should_block
fixture, so the moment a hook rots against the live tree this test goes
red. Findings F1–F6 of the 2026-06-26 audit would not have survived one
CI run with this in place.

Two kinds of hook live under ``.claude/hooks/`` and they need two
oracles, not one:

  * **PreToolUse content blockers** — Claude Code pipes ``{"tool_input": ...}``
    on stdin and reads the exit code; a violation is exit 2. ``mode="stdin"``.
  * **pre-commit / pre-push repo scanners** (the ``pre-merge-*`` gates wired in
    ``.pre-commit-config.yaml``) — no stdin at all. They scan the working tree
    and a violation is exit 1. Their ``should_block`` fixture is therefore a
    *tree* fixture: real content written into the live tree for the duration of
    one subprocess call, then restored byte-for-byte. ``mode="tree"``.

Registry-over-loop, pydantic-first: adding the next hook is one
``HookContract`` record, not new code. Run:

    uv run pytest tests/meta/test_hook_enforcement.py -q

Audit note (2026-08-21, GOV-15): this registry held 6 records against 28 hooks
and covered none of the five ``pre-merge-*`` gates CLAUDE.md names by title —
including ``pre-merge-schema-sync``, which reported "PASS: Schemas appear to be
in sync" while reading a re-export shim with zero struct definitions (GOV-02).
The gate it needed to be caught by was the one that stopped at 21%.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict

# Repo root = three levels up from tests/meta/<this file>.
REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"

# Block-mode env so hooks that default to warn (exit 0 + stderr) actually
# return exit 2 on a violation. Hooks ignore vars they don't read.
BLOCK_ENV = {
    "ENFORCE_PYDANTIC_MODE": "block",
    "PYDANTIC_NATIVE_MODE": "block",
    "ENFORCE_MATCH_DISPATCH_MODE": "block",
    "MATCH_DISPATCH_MODE": "block",
    "RENDER_BOUNDARY_MODE": "block",
    "FRONTEND_FREEZE_MODE": "block",
    "SOFT_FREEZE_MODE": "block",
}


class HookContract(BaseModel):
    """One hook's enforcement oracle: what it must block, what it must pass.

    ``payload`` shape mirrors the real Claude Code PreToolUse stdin contract
    every hook here parses: ``{"tool_input": {"file_path", "content"}}``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    hook: str  # filename under .claude/hooks/, sans .sh
    case: str = ""  # disambiguator when one hook needs several oracles
    reason: str  # why this guard exists — names the audit finding it pins
    should_block: dict  # tool_input that MUST exit 2 (lands on the LIVE tree)
    should_pass: dict  # tool_input that MUST exit 0
    # ``stdin`` = PreToolUse content blocker driven by the payloads above.
    # ``tree``  = pre-commit repo scanner; the payloads are inert and the
    #             should_block oracle is block_appends / block_replacements.
    mode: Literal["stdin", "tree"] = "stdin"
    # PreToolUse blocks with 2; a pre-commit gate fails with 1.
    block_exit_code: int = 2
    # Tree fixtures, applied only for the should_block run and reverted in a
    # ``finally``. appends: path -> text appended (file created if absent).
    # replacements: path -> (needle, replacement), applied once.
    block_appends: Mapping[str, str] = {}
    block_replacements: Mapping[str, tuple[str, str]] = {}
    # Extra env for the should_block run only (path overrides a gate exposes
    # so it can be aimed at a fixture instead of live source).
    block_env: Mapping[str, str] = {}
    # Skip honestly when the gate's own dependency is not installed, rather
    # than reporting a red that says nothing about the hook.
    requires_module: str | None = None
    timeout_s: int = 30
    # Stateless content-blockers (PreToolUse, scan tool_input["content"]) fit the
    # block/pass oracle directly. Stateful/reminder hooks do NOT: a Stop hook reads
    # `git diff` of the working tree, a soft-freeze diffs against on-disk exports,
    # and a PostToolUse reminder is non-blocking (stderr nudge, exit 0). Those need
    # a different harness (seeded git state / stderr assertion) — tracked as a
    # follow-up; skip the stateless oracle for them rather than assert a wrong one.
    stateless_blocker: bool = True


def _payload(file_path: str, content: str) -> dict:
    # tool_name="Write" is load-bearing: the hooks' proposed_text() only reads
    # tool_input["content"] when tool_name is Write/Edit. Omit it and the hook
    # falls through to reading the (nonexistent) on-disk file -> None -> exit 0,
    # a false green/red that hides whether the guard actually fires.
    return {
        "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": content},
    }


# --- Tree-fixture literals --------------------------------------------------
# Kept as named constants so the record below reads as a registry entry rather
# than as an escaped blob, and so each fixture's shape is reviewable on its own.

# Non-JSON return type across the PyO3 boundary.
PYO3_FIXTURE_RS = """
#[pyfunction]
fn hook_enforcement_fixture() -> Vec<f64> {
    vec![]
}
"""

# Back-edge: the DAG root crate taking a dependency on a downstream crate.
DAG_BACK_EDGE_TOML = "\nspectrafit-solver = { workspace = true }\n"

# A registration the grep-based binding audit sees but binding_audit_notes.toml
# does not list. A comment, so lib.rs stays compilable while the fixture is live.
BINDING_FIXTURE_RS = "\n// tests/meta fixture: wrap_pyfunction!(hook_enforcement_fixture, m)\n"


# --- The manifest -----------------------------------------------------------
# Every entry's should_block lands on the *live* tree (python/oracles/, web/).
# A hook still scoped to a dead path (the F1–F6 bug) cannot block these,
# so its should_block case fails loudly. This is the whole point.
HOOK_CONTRACTS: tuple[HookContract, ...] = (
    HookContract(
        hook="enforce-pydantic-native",
        reason="F3: dict-key contract access must be blocked on the LIVE engine "
        "(python/oracles/), not the empty python/extras/.",
        should_block=_payload(
            "python/oracles/contract.py",
            'import json\npayload = json.loads(raw)\nx = payload["featured"]\n',
        ),
        should_pass=_payload(
            "python/oracles/contract.py",
            "from pydantic import BaseModel\n\n\nclass R(BaseModel):\n    x: int\n",
        ),
    ),
    HookContract(
        hook="enforce-match-dispatch",
        reason="F4: if/elif <var>== chains must be blocked on python/oracles/ "
        "(backends/registry dispatch), not just tests/.",
        should_block=_payload(
            "python/oracles/backends/_dispatch.py",
            "def pick(k):\n"
            '    if k == "a":\n        return 1\n'
            '    elif k == "b":\n        return 2\n'
            '    elif k == "c":\n        return 3\n',
        ),
        should_pass=_payload(
            "python/oracles/backends/_dispatch.py",
            "def pick(k):\n    match k:\n"
            '        case "a":\n            return 1\n'
            "        case _:\n            return 0\n",
        ),
    ),
    HookContract(
        hook="enforce-render-boundary",
        reason="F1: template-engine imports in Python exporters must be blocked "
        "on python/oracles/ (live exporters), not python/benchmarkmark/.",
        should_block=_payload(
            "python/oracles/forensics.py",
            "import jinja2\n\nenv = jinja2.Environment()\n",
        ),
        should_pass=_payload(
            "python/oracles/forensics.py",
            "from pathlib import Path\n\n\ndef render(p: Path) -> None: ...\n",
        ),
    ),
    HookContract(
        hook="contract-sync-reminder",
        reason="F5: editing the canonical contract must nudge contract_regen; "
        "scope must be python/oracles/contract.py, not python/benchmark/.",
        should_block=_payload(  # non-blocking PostToolUse nudge: stderr, exit 0
            "python/oracles/contract.py",
            "class BenchReport(BaseModel):\n    new_field: int = 0\n",
        ),
        should_pass=_payload(
            "python/oracles/cases.py",
            "# unrelated edit, no contract change\nX = 1\n",
        ),
        stateless_blocker=False,  # reminder hook — needs a stderr oracle, not exit 2
    ),
    HookContract(
        hook="frontend-soft-freeze",
        reason="F6: deleting an exported symbol / table header must be blocked "
        "in web/ (the live dashboard), not the nonexistent frontend/.",
        should_block=_payload(
            "web/src/panels/registry.tsx",
            "// header row removed, exports stripped\nconst x = 1;\n",
        ),
        should_pass=_payload(
            "web/src/panels/registry.tsx",
            "export const PANELS = [];\nexport function renderPanels() {}\n",
        ),
        stateless_blocker=False,  # diffs against on-disk exports — needs seeded file state
    ),
    HookContract(
        hook="decisions-adr-reminder",
        reason="F2: edits to the live engine/dashboard must trip the ADR "
        "reminder; regex must cover python/oracles/ + web/, not the typo dirs.",
        should_block=_payload(  # Stop hook: reads `git diff`, not this payload
            "python/oracles/synth.py",
            "# architectural change to the live engine\n",
        ),
        should_pass=_payload(
            "README.md",
            "doc-only change, no architectural surface touched\n",
        ),
        stateless_blocker=False,  # Stop hook inspects working-tree git state, not payload
    ),
    # --- GOV-07 / GOV-14: new git pre-commit warn-only gates ------------------
    # Neither is a PreToolUse stdin content-blocker (mode="stdin" here is
    # nominal/unused) nor a pre-merge tree-fixture gate (mode="tree" expects
    # exit 1 on violation; these always exit 0 by design). Both scan
    # `git diff --cached`, which this harness's stdin/tree oracles don't
    # model, so real coverage lives in dedicated bash test scripts run
    # against an isolated synthetic repo — .claude/hooks/tests/test_warn_tag_residue.sh
    # for warn-tag-residue.sh — rather than here; this record exists for
    # registry completeness (the "every hook I add gets a record" rule) with
    # stateless_blocker=False so the generic should_block/should_pass
    # parametrization is honestly skipped instead of asserting a wrong shape.
    HookContract(
        hook="warn-match-dispatch",
        reason="GOV-07: pre-commit-side twin of enforce-match-dispatch.sh, "
        "closing the Bash-heredoc escape hatch CLAUDE.md itself documents for "
        "the PreToolUse hook. Shares detection logic via "
        ".claude/hooks/lib/match_dispatch_check.py — proven directly in this "
        "file's own PreToolUse-mode contract above (same regex/module), and "
        "against a live seeded git-diff fixture in the implementing session's "
        "verification transcript (not re-modeled here since this harness has "
        "no git-diff-cached oracle shape).",
        should_block={},
        should_pass={},
        stateless_blocker=False,
    ),
    HookContract(
        hook="warn-tag-residue",
        reason="GOV-14: no prior hook stopped internal tracking tags "
        "(EF-XX-NN / Cycle N / Plan X[N] / GNN) from reaching shipped source "
        "comments; two dedicated sweeps each closed their own enumerated list "
        "and 23 tags across 21 files still survived. Covered by "
        ".claude/hooks/tests/test_warn_tag_residue.sh (isolated synthetic "
        "git repo: fires on a seeded new tag of all four kinds, stays silent "
        "on held-out non-tag prose and on a clean staged diff).",
        should_block={},
        should_pass={},
        stateless_blocker=False,
    ),
    # --- the five pre-merge gates CLAUDE.md names by title -------------------
    # These are pre-commit/pre-push repo scanners (.pre-commit-config.yaml,
    # stages: [pre-commit, pre-push]), not PreToolUse blockers: no stdin,
    # violation = exit 1, and the should_block oracle is a tree fixture.
    HookContract(
        hook="pre-merge-schema-sync",
        case="serde-field-renamed-on-the-rust-side-only",
        reason="GOV-02: CLAUDE.md promises this gate blocks a serde struct "
        "field renamed without the matching Pydantic rename. Renaming "
        "FitResultSpec.reduced_chi2 in types.rs alone is exactly that defect: "
        "both languages still compile, both still pass their own tests, and "
        "the field silently vanishes from the JSON payload.",
        mode="tree",
        block_exit_code=1,
        block_replacements={
            "crates/spectrafit-types/src/types.rs": (
                "    pub reduced_chi2: f64,",
                "    pub reduced_chi_squared: f64,",
            ),
        },
        should_block={},  # inert: the tree fixture is the oracle
        should_pass={},  # pristine tree must exit 0 — no false positive
    ),
    HookContract(
        hook="pre-merge-schema-sync",
        case="aimed-at-a-file-with-no-struct-definitions",
        reason="GOV-02 verbatim: the gate used to read spectrafit-types/src/"
        "lib.rs, a 21-line re-export shim with zero struct or enum bodies, and "
        "reported PASS. Finding nothing to compare must FAIL — an inert gate "
        "that reports success is worse than no gate.",
        mode="tree",
        block_exit_code=1,
        block_env={"SCHEMA_SYNC_RUST_TYPES": "crates/spectrafit-types/src/lib.rs"},
        should_block={},
        should_pass={},
    ),
    HookContract(
        hook="pre-merge-pyO3",
        case="pyfunction-returning-a-non-json-type",
        reason="CLAUDE.md: 'every #[pyfunction] must return JSON strings only'. "
        "A pyfunction returning Vec<f64> crosses the PyO3 boundary with a "
        "native type instead of a JSON string — the exact violation this gate "
        "is named for.",
        mode="tree",
        block_exit_code=1,
        block_appends={
            # Dot-prefixed and outside every src/ dir, so cargo never sees it;
            # `find crates -name '*.rs'` (what the hook greps) does.
            "crates/.hook_enforcement_fixture.rs": PYO3_FIXTURE_RS,
        },
        should_block={},
        should_pass={},
    ),
    HookContract(
        hook="pre-merge-dag",
        case="back-edge-from-the-root-crate-to-the-solver",
        reason="CLAUDE.md: 'dependency direction is enforced by the pre-merge-dag "
        "hook — don't introduce a back-edge as a shortcut'. spectrafit-types is "
        "the DAG root and must depend on nothing internal; a spectrafit-solver "
        "edge on it is a literal back-edge.",
        mode="tree",
        block_exit_code=1,
        block_appends={
            "crates/spectrafit-types/Cargo.toml": DAG_BACK_EDGE_TOML,
        },
        should_block={},
        should_pass={},
    ),
    HookContract(
        hook="pre-merge-binding-audit",
        case="registered-pyfunction-with-no-notes-entry",
        reason="CLAUDE.md: 'every new #[pyfunction] registered in spectrafit-"
        "core/src/lib.rs needs a one-line entry in binding_audit_notes.toml'. "
        "The fixture is a wrap_pyfunction! registration with no TOML entry — "
        "written as a Rust comment so lib.rs still compiles while the grep-"
        "based audit (scripts/audit_bindings.py) still sees it.",
        mode="tree",
        block_exit_code=1,
        block_appends={
            "crates/spectrafit-core/src/lib.rs": BINDING_FIXTURE_RS,
        },
        should_block={},
        should_pass={},
    ),
    HookContract(
        hook="pre-merge-contract-golden",
        case="golden-openapi-description-drifted-from-live-schema",
        reason="CLAUDE.md: a Pydantic Field(description=...) serialized into "
        "BenchReport becomes OpenAPI description text byte-for-byte, so editing "
        "it IS a contract change. The fixture perturbs that text in the checked-"
        "in golden, which is indistinguishable — to the comparator — from "
        "editing the source and forgetting `poe contract_regen`. Mutating the "
        "golden rather than python/oracles/contract.py keeps a crashed test run "
        "from leaving live contract source in a broken state.",
        mode="tree",
        block_exit_code=1,
        block_replacements={
            "tests/audit/golden/openapi_normalised.json": (
                "Git branch name at benchmark run time.",
                "Git BRANCH name at benchmark run time.",
            ),
        },
        should_block={},
        should_pass={},
        requires_module="fastapi",  # the 'benchmark' extra; the hook shells to pytest
        timeout_s=180,
    ),
)

# pre-merge gates with no oracle yet, and why. Kept explicit so the ratchet in
# test_every_pre_merge_gate_has_a_contract still blocks a NEW uncovered gate.
UNFIXTURED_PRE_MERGE: frozenset[str] = frozenset(
    {
        # Regenerates docs/contributor-guide/architecture.md and .rrt/tree.lock.toml
        # in place via `rrt tree --snapshot`. Its should_pass run would rewrite two
        # tracked files as a side effect, so a fixture here needs a sandboxed
        # checkout, not a tree fixture. Follow-up.
        "pre-merge-arch-tree",
        # Decides from `git diff --cached` plus .claude/audit/ bypass state, so its
        # oracle is seeded git index state, not tree content — same follow-up
        # bucket as the Stop/soft-freeze hooks above.
        "pre-merge-perf-baseline",
    },
)


def _live_hooks() -> list[HookContract]:
    """Skip records whose hook .sh isn't on disk (keeps the suite honest
    without crashing if a hook is renamed before its contract is)."""
    out = []
    for c in HOOK_CONTRACTS:
        if (HOOKS_DIR / f"{c.hook}.sh").exists():
            out.append(c)
    return out


def _contract_id(contract: HookContract) -> str:
    return f"{contract.hook}-{contract.case}" if contract.case else contract.hook


def _run_hook(
    hook: str,
    payload: dict,
    *,
    extra_env: Mapping[str, str] = {},
    timeout_s: int = 30,
) -> int:
    """Pipe payload to the real hook on stdin; return its exit code.

    Mirrors how Claude Code invokes a PreToolUse hook: JSON on stdin,
    cwd = repo root (hooks resolve paths relative to it), decision = exit code.
    A ``mode="tree"`` gate ignores the stdin entirely; cwd = repo root is what
    matters there, since that is how pre-commit invokes it.
    """
    proc = subprocess.run(
        ["bash", str(HOOKS_DIR / f"{hook}.sh")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
        env={**_base_env(), **BLOCK_ENV, **extra_env},
        timeout=timeout_s,
    )
    return proc.returncode


def _base_env() -> dict:
    import os

    return dict(os.environ)


@contextmanager
def _tree_fixture(contract: HookContract) -> Iterator[None]:
    """Materialise a should_block fixture in the LIVE tree, then undo it.

    A repo scanner can only be proven to fire against real tree content, so
    the fixture is real — and every touched path is snapshotted as bytes first
    and rewritten verbatim in the ``finally``, whether the assertion passed,
    failed, or raised. Files the fixture created are unlinked.

    Each record touches paths no other record touches, so the fixtures stay
    independent if the suite is run under xdist.
    """
    saved: list[tuple[Path, bytes | None]] = []
    try:
        for rel, chunk in contract.block_appends.items():
            path = REPO_ROOT / rel
            saved.append((path, path.read_bytes() if path.exists() else None))
            with path.open("a", encoding="utf-8") as handle:
                handle.write(chunk)
        for rel, (needle, replacement) in contract.block_replacements.items():
            path = REPO_ROOT / rel
            original = path.read_bytes()
            saved.append((path, original))
            text = original.decode("utf-8")
            assert needle in text, (
                f"{_contract_id(contract)}: fixture needle {needle!r} is no longer "
                f"present in {rel}. The fixture has rotted — it can no longer "
                f"produce the violation it claims to, so the oracle is dead."
            )
            path.write_text(text.replace(needle, replacement, 1), encoding="utf-8")
        yield
    finally:
        for path, original in reversed(saved):
            match original:
                case None:
                    path.unlink(missing_ok=True)
                case _:
                    path.write_bytes(original)


def _skip_if_dependency_missing(contract: HookContract) -> None:
    match contract.requires_module:
        case None:
            return
        case name if importlib.util.find_spec(name) is None:
            pytest.skip(
                f"{_contract_id(contract)} shells out to a check that imports "
                f"{name!r}, which is not installed in this environment "
                f"(optional extra). Skipping beats a red that says nothing "
                f"about the hook.",
            )
        case _:
            return


def _exercise(contract: HookContract, *, blocking: bool) -> int:
    """Run the hook once under its should_block or should_pass oracle."""
    match (contract.mode, blocking):
        case ("tree", True):
            with _tree_fixture(contract):
                return _run_hook(
                    contract.hook,
                    contract.should_block,
                    extra_env=contract.block_env,
                    timeout_s=contract.timeout_s,
                )
        case ("tree", False):
            # Pristine tree: a repo scanner that fails on a clean checkout is
            # a broken gate just as surely as one that never fails.
            return _run_hook(
                contract.hook,
                contract.should_pass,
                timeout_s=contract.timeout_s,
            )
        case (_, True):
            return _run_hook(
                contract.hook,
                contract.should_block,
                extra_env=contract.block_env,
                timeout_s=contract.timeout_s,
            )
        case _:
            return _run_hook(
                contract.hook,
                contract.should_pass,
                timeout_s=contract.timeout_s,
            )


@pytest.mark.parametrize("contract", _live_hooks(), ids=_contract_id)
def test_hook_blocks_violation(contract: HookContract) -> None:
    """The hook MUST reject its should_block oracle.

    A guard scoped to a dead path cannot reach the live-tree violation, and a
    gate reading a file that defines none of what it claims to compare cannot
    reach one either. Both exit 0 here — the rot F1–F6 and GOV-02 documented.
    Fail loudly.
    """
    if not contract.stateless_blocker:
        pytest.skip(
            f"{contract.hook} is stateful/reminder — needs a dedicated oracle (follow-up)",
        )
    _skip_if_dependency_missing(contract)
    code = _exercise(contract, blocking=True)
    assert code == contract.block_exit_code, (
        f"{contract.hook}.sh did NOT block a known violation on the live "
        f"tree (exit {code}, expected {contract.block_exit_code}). The guard "
        f"is inert.\nWhy this matters: {contract.reason}"
    )


@pytest.mark.parametrize("contract", _live_hooks(), ids=_contract_id)
def test_hook_passes_clean(contract: HookContract) -> None:
    """The hook MUST allow its should_pass oracle (exit 0) — no false block."""
    if not contract.stateless_blocker:
        pytest.skip(
            f"{contract.hook} is stateful/reminder — needs a dedicated oracle (follow-up)",
        )
    _skip_if_dependency_missing(contract)
    code = _exercise(contract, blocking=False)
    assert code == 0, (
        f"{contract.hook}.sh blocked a CLEAN payload (exit {code}, "
        f"expected 0) — false positive.\nContext: {contract.reason}"
    )


def test_every_wired_hook_has_a_contract() -> None:
    """Coverage gate: every scope-guarded hook on disk is pinned by a
    contract above. New rot-prone hooks can't be added without an oracle.
    """
    scoped: set[str] = set()
    for sh in HOOKS_DIR.glob("*.sh"):
        text = sh.read_text(encoding="utf-8", errors="ignore")
        # Hooks that hardcode a path scope are the ones that can silently rot.
        if (
            'startswith("python/' in text
            or 'startswith("web/' in text
            or ('startswith("frontend/' in text or "grep -qE '^(" in text)
        ):
            scoped.add(sh.stem)

    covered = {c.hook for c in HOOK_CONTRACTS}
    uncovered = scoped - covered
    assert not uncovered, (
        "Scope-guarded hooks with no enforcement oracle (add a HookContract "
        f"so a path rename can't silently disable them): {sorted(uncovered)}"
    )


def test_every_pre_merge_gate_has_a_contract() -> None:
    """Ratchet: no NEW pre-merge-*.sh gate lands without a block/pass oracle.

    The pre-merge-* family is the set CLAUDE.md advertises by title as what
    keeps the polyglot boundaries honest, which makes an unproven one the most
    expensive kind of dead guard: contributors are told in writing that it
    blocks them. Two are grandfathered in UNFIXTURED_PRE_MERGE with a written
    reason; anything else must carry a contract.
    """
    gates = {sh.stem for sh in HOOKS_DIR.glob("pre-merge-*.sh")}
    covered = {c.hook for c in HOOK_CONTRACTS}
    uncovered = gates - covered - UNFIXTURED_PRE_MERGE
    assert not uncovered, (
        "pre-merge gate(s) with no HookContract oracle — CLAUDE.md tells "
        "contributors these block them, so an unproven one must not land: "
        f"{sorted(uncovered)}"
    )


def test_no_stale_entries_in_the_unfixtured_allowlist() -> None:
    """The grandfather list must not outlive the gates it excuses."""
    gates = {sh.stem for sh in HOOKS_DIR.glob("pre-merge-*.sh")}
    stale = (UNFIXTURED_PRE_MERGE - gates) | (
        UNFIXTURED_PRE_MERGE & {c.hook for c in HOOK_CONTRACTS}
    )
    assert not stale, (
        "UNFIXTURED_PRE_MERGE names gates that no longer exist or that now "
        f"have a contract — drop them from the allowlist: {sorted(stale)}"
    )
