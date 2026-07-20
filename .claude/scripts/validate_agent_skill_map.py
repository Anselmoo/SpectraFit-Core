#!/usr/bin/env python3
"""Validate .claude/AGENT_SKILL_MAP.md against .claude/agents and skill folders.

Usage: python3 .claude/scripts/validate_agent_skill_map.py

Exits with code 0 when all mappings are valid. Exits 1 when any agent is
missing from the map or when any mapped skill path is absent.
"""

from pathlib import Path
import re
import sys


def parse_mapping(md_path: Path):
    """Parse the agent->skill markdown table into a ``{agent: skill}`` mapping."""
    mapping = {}
    if not md_path.exists():
        print(f"✗ Mapping file not found: {md_path}")
        return mapping

    table_row_re = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|.*$")

    with md_path.open("r", encoding="utf-8") as f:
        for line in f:
            m = table_row_re.match(line)
            if not m:
                continue
            left = m.group(1).strip()
            right = m.group(2).strip()
            # skip header separator line like '|---|---:|' or pure-dash columns
            if re.fullmatch(r"-+", left) or re.fullmatch(r"-+", right):
                continue
            # skip header row where left contains 'Agent' and right contains 'Skill'
            if left.lower().startswith('agent') and 'skill' in right.lower():
                continue
            mapping[left] = right

    return mapping


def main():
    """Validate the agent->skill map against on-disk agents and skill paths."""
    repo_root = Path(__file__).resolve().parents[2]
    claude_agents_dir = repo_root / '.claude' / 'agents'
    mapping_md = repo_root / '.claude' / 'AGENT_SKILL_MAP.md'

    agents = []
    if claude_agents_dir.exists():
        for p in sorted(claude_agents_dir.glob('*.agent.md')):
            agents.append(p.stem.replace('.agent', '') if p.stem.endswith('.agent') else p.stem)
    else:
        print(f"✗ .claude/agents directory not found: {claude_agents_dir}")
        sys.exit(1)

    mapping = parse_mapping(mapping_md)

    missing_mapping = []
    for a in sorted(agents):
        if a not in mapping:
            missing_mapping.append(a)

    missing_skill_paths = []
    for agent_name, skill_path in mapping.items():
        # normalize path like `.github/skills/foo/` to repo relative path
        p = skill_path.strip().strip('`').strip()
        # remove leading ./ if present
        if p.startswith('./'):
            p = p[2:]
        skill_dir = repo_root / p.lstrip('/')
        if not skill_dir.exists():
            missing_skill_paths.append((agent_name, p))

    ok = True
    if missing_mapping:
        ok = False
        print('\nMissing mapping entries for the following .claude agents:')
        for a in missing_mapping:
            print(f"  - {a}")

    if missing_skill_paths:
        ok = False
        print('\nMapping entries that point to missing skill paths:')
        for a, p in missing_skill_paths:
            print(f"  - {a} -> {p} (not found)")

    # also warn about mapping entries that don't correspond to agents
    unmapped = [m for m in mapping.keys() if m not in agents]
    if unmapped:
        print('\nWarning: mapping contains entries for agents not present in .claude/agents:')
        for m in unmapped:
            print(f"  - {m}")

    if ok:
        print('\n✓ Agent → Skill mapping is consistent')
        return 0
    else:
        print('\n✗ Agent → Skill mapping validation failed')
        return 1


if __name__ == '__main__':
    sys.exit(main())
