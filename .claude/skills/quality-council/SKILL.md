---
name: quality-council
description: |
  Five-voice quality council — Jobs (reduction), Ive (craft), Dye
  (system hierarchy), Tog (usability), Kare (metaphor). Convened on
  stuck wires, design questions, and presentation polish. Absorbs
  one-more-thing, boring-to-brilliant, cupertino-council, and
  evolutionary-platform-thinking — their specialist content lives in
  references/. Use when the user says "it feels off", "design from
  first principles", "what's missing", "make it memorable", "elevate
  this", "Time Machine treatment", "Apple-style", "future-proof this",
  "Vista trap", or when a tri-stream cycle's stuck-mode escape hits
  rung 3. Composes with superpowers:brainstorming.
license: MIT
---

# quality-council

The polish + elevation conductor. Not used for routine coding — used
when the question is principled: *what should this feel like*, *what's
the one thing missing*, *will this design last*.

## When to convene

Trigger phrases (any of):

- "make this feel premium" / "design like Apple" / "cupertino"
- "boring", "just a utility", "elevate this", "Time Machine treatment"
- "one more thing", "surprise me", "what would make this unforgettable"
- "will this scale?", "future-proof", "Vista trap", "extensible?"
- Automatic: rung 3 of the andon-loop stuck-mode escape ladder.

## Anchors

**CLAUDE.md sections** (read before acting):
- *Running & previewing the dashboard (Claude Desktop / preview)* —
  the design discussions usually touch a render surface.

**Hooks**: none (this skill operates on principles, not code).

## Serena first?

`serena_first: false` — the council critiques ideas and surfaces, not
symbols. Code-touching follow-ups invoke a stream skill (which IS
serena-first).

## Decision: which voice / which sub-document?

The council convenes all five voices by default. The references give
each voice its own canon to lean on:

| Voice / mode | Reference |
|--------------|-----------|
| Jobs — reduction ("the one thing missing") | `references/one-more-thing.md` |
| Ive + Time Machine — transfigure the commodity into the loved | `references/brilliant.md` |
| Full 5-voice Apple critique (Jobs, Ive, Dye, Tog, Kare) | `references/cupertino.md` |
| Evolutionary fitness, Vista traps, Rosetta roadmaps | `references/evolutionary.md` |

A typical convening reads ALL four — each voice critiques the artifact,
then the council synthesizes (or escalates if the voices disagree).

## Output shape

For a routine convening:

1. **Per-voice findings** — 1 paragraph each.
2. **Tension table** — where the voices conflict (Jobs wants reduction;
   Tog wants more affordance; resolve in favor of the constraint).
3. **The one thing missing** (Jobs voice answer).
4. **Concrete next action** — a specific file/path or design move.

For a stuck-mode rung-3 convening: same shape PLUS:

- **Re-framing** — is the wire wrong? the contract at the wrong
  altitude? the proof checking the wrong thing?
- **Escalation flag** — if the council can't reach consensus, surface
  to the user with the tension table.

## Composes with

1. `superpowers:brainstorming` — for the design question form ("what
   should this feel like").
2. Whichever stream skill owns the artifact post-critique.
3. NOT a substitute for verification — RIGOR remains the
   `verification` skill's job.

## Three-pillar reporting

The council touches PRESENTATION primarily. Its output is one of:

- A redesign brief (carries forward into web-stream).
- A "missing one thing" recommendation (carries forward to a stream).
- An evolutionary fitness assessment (informs roadmap, not a single
  cycle).
