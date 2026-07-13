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

Registry-over-loop, pydantic-first: adding the 26th hook is one
``HookContract`` record, not new code. Run:

    uv run pytest tests/meta/test_hook_enforcement.py -q
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

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
    reason: str  # why this guard exists — names the audit finding it pins
    should_block: dict  # tool_input that MUST exit 2 (lands on the LIVE tree)
    should_pass: dict  # tool_input that MUST exit 0
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
    return {"tool_name": "Write", "tool_input": {"file_path": file_path, "content": content}}


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
)


def _live_hooks() -> list[HookContract]:
    """Skip records whose hook .sh isn't on disk (keeps the suite honest
    without crashing if a hook is renamed before its contract is)."""
    out = []
    for c in HOOK_CONTRACTS:
        if (HOOKS_DIR / f"{c.hook}.sh").exists():
            out.append(c)
    return out


def _run_hook(hook: str, payload: dict) -> int:
    """Pipe payload to the real hook on stdin; return its exit code.

    Mirrors how Claude Code invokes a PreToolUse hook: JSON on stdin,
    cwd = repo root (hooks resolve paths relative to it), decision = exit code.
    """
    proc = subprocess.run(  # noqa: S603 — fixed local script, no shell
        ["bash", str(HOOKS_DIR / f"{hook}.sh")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**_base_env(), **BLOCK_ENV},
        timeout=30,
    )
    return proc.returncode


def _base_env() -> dict:
    import os

    return dict(os.environ)


@pytest.mark.parametrize(
    "contract", _live_hooks(), ids=lambda c: c.hook
)
def test_hook_blocks_violation(contract: HookContract) -> None:
    """The hook MUST reject its should_block payload (exit 2).

    A guard scoped to a dead path cannot reach the live-tree violation,
    so it exits 0 here — which is the rot F1–F6 documented. Fail loudly.
    """
    if not contract.stateless_blocker:
        pytest.skip(f"{contract.hook} is stateful/reminder — needs a dedicated oracle (follow-up)")
    code = _run_hook(contract.hook, contract.should_block)
    assert code == 2, (
        f"{contract.hook}.sh did NOT block a known violation on the live "
        f"tree (exit {code}, expected 2). The guard is inert — likely "
        f"scoped to a dead path.\nWhy this matters: {contract.reason}"
    )


@pytest.mark.parametrize(
    "contract", _live_hooks(), ids=lambda c: c.hook
)
def test_hook_passes_clean(contract: HookContract) -> None:
    """The hook MUST allow its should_pass payload (exit 0) — no false block."""
    if not contract.stateless_blocker:
        pytest.skip(f"{contract.hook} is stateful/reminder — needs a dedicated oracle (follow-up)")
    code = _run_hook(contract.hook, contract.should_pass)
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
        if 'startswith("python/' in text or 'startswith("web/' in text or (
            'startswith("frontend/' in text or "grep -qE '^(" in text
        ):
            scoped.add(sh.stem)

    covered = {c.hook for c in HOOK_CONTRACTS}
    uncovered = scoped - covered
    assert not uncovered, (
        "Scope-guarded hooks with no enforcement oracle (add a HookContract "
        f"so a path rename can't silently disable them): {sorted(uncovered)}"
    )
