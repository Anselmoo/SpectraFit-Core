"""Tests for scripts/self_heal_automation.py."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path


def _run_self_heal(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    script = Path(__file__).resolve().parents[2] / "scripts" / "self_heal_automation.py"
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )


def _latest_report_dir(base: Path) -> Path:
    runs = sorted([entry for entry in base.iterdir() if entry.is_dir()])
    assert runs, "expected at least one self-heal run directory"
    return runs[-1]


def test_fix_safe_makes_hook_executable_and_emits_report(tmp_path: Path) -> None:
    """Fix-safe mode should chmod hook scripts and record the applied fix."""
    hooks_dir = tmp_path / ".claude/hooks"
    hooks_dir.mkdir(parents=True)
    hook_path = hooks_dir / "pre-merge-pyO3.sh"
    hook_path.write_text("#!/bin/bash\necho ok\n", encoding="utf-8")
    hook_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    settings_path = tmp_path / ".claude/settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "hooks": [
                    {
                        "event": "PreToolUse",
                        "matcher": "Bash",
                        "type": "command",
                        "command": "bash .claude/hooks/pre-merge-pyO3.sh",
                    },
                ],
            },
        ),
        encoding="utf-8",
    )

    result = _run_self_heal(
        tmp_path,
        "--mode",
        "fix-safe",
        ".claude/hooks/pre-merge-pyO3.sh",
        ".claude/settings.json",
    )

    assert result.returncode == 1
    assert os.access(hook_path, os.X_OK)

    report_root = tmp_path / ".spectrafit_reports" / "self-heal"
    run_dir = _latest_report_dir(report_root)
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["fixed_count"] == 1
    assert summary["remaining_error_count"] == 0


def test_check_mode_fails_when_hook_reference_missing(tmp_path: Path) -> None:
    """Check mode should fail when settings reference a missing hook script."""
    (tmp_path / ".claude").mkdir()
    settings_path = tmp_path / ".claude/settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "hooks": [
                    {
                        "event": "PreToolUse",
                        "matcher": "Bash",
                        "type": "command",
                        "command": "bash .claude/hooks/missing.sh",
                    },
                ],
            },
        ),
        encoding="utf-8",
    )

    result = _run_self_heal(tmp_path, "--mode", "check", ".claude/settings.json")
    assert result.returncode == 1

    report_root = tmp_path / ".spectrafit_reports" / "self-heal"
    run_dir = _latest_report_dir(report_root)
    remaining = json.loads(
        (run_dir / "remaining_violations.json").read_text(encoding="utf-8"),
    )
    assert any(item["code"] == "hook_reference_missing" for item in remaining)


def test_instruction_dead_applies_to_glob_is_warning(tmp_path: Path) -> None:
    """An 'Applies to:' glob matching no real path should surface as a warning.

    Instruction files live at `.claude/instructions/*.md` (not the retired
    `.github/instructions/*.instructions.md`) and declare scope via a
    `> Applies to: <glob>` blockquote line, not YAML frontmatter — see
    GOV-03/GOV-05. A dead glob segment (the repo path it names was moved or
    renamed) is a warning, not a hard error, so it doesn't block commits.
    """
    inst_dir = tmp_path / ".claude/instructions"
    inst_dir.mkdir(parents=True)
    inst_file = inst_dir / "demo.md"
    inst_file.write_text(
        "> Applies to: python/does-not-exist/**/*.py\n\n# Demo\n",
        encoding="utf-8",
    )
    (tmp_path / ".claude/settings.json").write_text('{"hooks": []}', encoding="utf-8")
    (tmp_path / ".claude/hooks").mkdir()

    result = _run_self_heal(
        tmp_path,
        "--mode",
        "check",
        ".claude/instructions/demo.md",
    )
    assert result.returncode == 0

    report_root = tmp_path / ".spectrafit_reports" / "self-heal"
    run_dir = _latest_report_dir(report_root)
    remaining = json.loads(
        (run_dir / "remaining_violations.json").read_text(encoding="utf-8"),
    )
    assert any(item["code"] == "instruction_dead_applies_to_glob" for item in remaining)


def test_instruction_missing_applies_to_line_is_warning(tmp_path: Path) -> None:
    """An instruction file with no 'Applies to:' first line should warn, not error."""
    inst_dir = tmp_path / ".claude/instructions"
    inst_dir.mkdir(parents=True)
    inst_file = inst_dir / "demo.md"
    inst_file.write_text("# Demo\n\nNo applies-to line here.\n", encoding="utf-8")
    (tmp_path / ".claude/settings.json").write_text('{"hooks": []}', encoding="utf-8")
    (tmp_path / ".claude/hooks").mkdir()

    result = _run_self_heal(
        tmp_path,
        "--mode",
        "check",
        ".claude/instructions/demo.md",
    )
    assert result.returncode == 0

    report_root = tmp_path / ".spectrafit_reports" / "self-heal"
    run_dir = _latest_report_dir(report_root)
    remaining = json.loads(
        (run_dir / "remaining_violations.json").read_text(encoding="utf-8"),
    )
    assert any(item["code"] == "instruction_missing_applies_to" for item in remaining)


def test_skill_discovery_targets_claude_skills_not_github(tmp_path: Path) -> None:
    """Discovery/dispatch must target `.claude/skills/`, not the retired `.github/skills/`.

    Regression guard for GOV-03: the guard was blind to `.claude/skills/` and
    `.claude/instructions/` because TARGET_PREFIXES/discovery/dispatch all
    still pointed at `.github/skills/` and `.github/instructions/`, which were
    deleted in the 2026-07 `.github` -> `.claude` migration.
    """
    skill_dir = tmp_path / ".claude/skills/demo-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Demo skill\n\nNo required sections.\n", encoding="utf-8")
    (tmp_path / ".claude/settings.json").write_text('{"hooks": []}', encoding="utf-8")
    (tmp_path / ".claude/hooks").mkdir()

    result = _run_self_heal(tmp_path, "--mode", "check")
    assert result.returncode == 0

    report_root = tmp_path / ".spectrafit_reports" / "self-heal"
    run_dir = _latest_report_dir(report_root)
    remaining = json.loads(
        (run_dir / "remaining_violations.json").read_text(encoding="utf-8"),
    )
    assert any(
        item["surface"] == "skills" and item["code"] == "skill_section_missing"
        for item in remaining
    )
