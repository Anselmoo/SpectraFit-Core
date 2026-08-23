# Skill-gen reference — scaffold a new skill directory

Self-contained essentials. Historical content under
`.claude/skills/skill-generator/` is in git history.

## When to add a new skill

Only when an artifact has a **distinct trigger language** that no
existing consolidated skill claims. Default answer is: extend an
existing skill's `references/` directory instead.

## Skill shape (this repo's convention)

```
.claude/skills/<name>/
├── SKILL.md          (frontmatter: name, description, license)
├── references/       (sub-documents, one per subject)
└── scripts/          (optional: helper scripts)
```

`SKILL.md` frontmatter MUST carry: `name`, `description` (markdown
trigger language), `license`. Body MUST carry: anchor list (CLAUDE.md
sections, hooks), serena-first declaration, decision table for
sub-documents, composes_with list, three-pillar reporting note.

## Anchored to INDEX.yaml

A new skill MUST register in `.claude/skills/INDEX.yaml` with full
metadata (stream, anchors, composes_with, serena_first, absorbs=[]).
The validator (`scripts/validate_index.py`) refuses to merge a skill
that isn't indexed.

## Stuck-mode entry

A skill that reopens (the trigger language matches another skill, the
anchors are wrong) usually means the skill should have been a reference
inside an existing skill. Curiosity sub-cycle: re-read INDEX.yaml's
existing entries and ask whether the new skill's purpose is genuinely
distinct.
