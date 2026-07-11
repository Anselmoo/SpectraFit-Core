# Stuck-mode escape ladder

> When a wire reopens or the same gap recurs, the loop is **stuck**. The
> existing thrash guard escalates after 3 reopens. This file specifies
> what "escalation" means at each rung — creativity-on-demand, not
> indefinite linear retry.

The escape ladder is **tiered** because cheap exploration beats expensive
re-framing, and re-framing beats council-by-default. We climb only as far
as we have to.

| Reopen # | Rung | Cost | What it does |
|----------|------|------|--------------|
| 1 | **Curiosity sub-cycle** | low | Map neighbors of the stuck wire via serena; surface surprises |
| 2 | **Reframe + spike** | medium | Time-boxed 60 min: name the defended assumption, implement the cheapest alternative as a throwaway |
| 3 | **Quality-council convene** | high | Invoke `quality-council` skill — five-voice critique re-frames or escalates to user |

After rung 3, the loop **must** stop and surface a decision to the user.
"Stuck three times" is the unambiguous signal that linear iteration is
the wrong mode — the answer is either elsewhere or a level up.

---

## Rung 1 — Curiosity sub-cycle

**Trigger**: a wire that was 🟢 has gone 🔴 once before, or a gap that
was closed has re-opened once.

**Action**: spawn an Explore subagent with this brief:

> The wire `<from> → <to>` (contract: `<contract>`) just reopened. Map
> its neighborhood:
> 1. `mcp__serena__find_symbol` on the symbol(s) the contract names.
> 2. `mcp__serena__find_referencing_symbols` on each — list every caller
>    and every consumer, with the file path and line.
> 3. For each, check `git log --since="14 days ago" -- <path>` — surface
>    recent commits that touched it.
> 4. Grep `DECISIONS.md` for ADRs that mention the contract.
> 5. Return: (a) the neighborhood map, (b) **surprises** — anything you
>    didn't expect (a new caller, an ADR that contradicts the contract,
>    a test that doesn't match its name).

The loop then re-picks the gap with the surprises in hand. The
hypothesis: most stucks are stuck because of an unseen neighbor.

Cost budget: ≤ 5 min wall-clock, ≤ 10 k tokens.

---

## Rung 2 — Reframe + spike

**Trigger**: the wire reopens a second time (now reopen #2).

**Action**: 60-minute time-box, two halves.

**Half 1 — Reframe (15 min)**. Write down explicitly:

1. **The defended assumption**: "We're holding `<X>` constant because
   `<reason>`."
2. **The cheapest violation**: "What if `<X>` weren't constant — what
   would `<contract>` look like?"
3. **The test of the violation**: "If we changed `<X>` to `<Y>`, what
   would we measure to know it worked?"

**Half 2 — Spike (45 min)**. Implement the violation as a throwaway
branch. Do not aim for production quality — aim for a measurement on the
test from step 3. If the spike succeeds, the loop now has a candidate
re-framing. If it fails, the loop has measured the cost of the
re-framing and can rule it out with evidence.

Either way, append an ADR-style entry to the andon ledger's `history`:

```json
{
  "type": "reframe_spike",
  "cycle": N,
  "pass": M,
  "wire": "<from> → <to>",
  "assumption": "...",
  "spike_branch": "spike/<topic>",
  "outcome": "succeeded" | "ruled_out" | "inconclusive",
  "next_action": "..."
}
```

Cost budget: 60 min wall-clock + spike implementation tokens.

---

## Rung 3 — Quality-council convene

**Trigger**: the wire reopens a third time.

**Action**: invoke the consolidated `quality-council` skill (which
absorbs `cupertino-council`, `one-more-thing`, `boring-to-brilliant`,
`evolutionary-platform-thinking`) with the stuck wire as input. The
council convenes five voices:

1. **Jobs (reduction)** — "What single thing should this wire actually
   do? Are we defending complexity that shouldn't exist?"
2. **Ive (craft)** — "Where in this wire is craftsmanship lacking? What
   detail is wrong that we've stopped seeing?"
3. **Dye (system hierarchy)** — "Where does this wire sit in the system?
   Is it at the wrong altitude?"
4. **Tog (usability)** — "Who consumes the proof of this wire? Is the
   proof understandable to them?"
5. **Kare (metaphor)** — "Is the metaphor we're using to talk about this
   wire actually wrong? Would a different name make the gap obvious?"

The council either:

- **Re-frames** the problem (the wire is the wrong wire; the contract
  is at the wrong level; the proof is checking the wrong thing). The
  loop accepts the re-framing, updates the ledger, and resumes from
  Phase 2 with the new wire definition.
- **Escalates to the user** (the council can't agree, or the resolution
  is a product decision). The loop stops; the user owns the next move.

Cost budget: as long as the council needs. Reaching rung 3 means the
prior rungs already failed — additional cost here is cheaper than
shipping a defect downstream or burning more cycles.

---

## Why this escape ladder, and not just "ask the user"

Asking the user is rung 3's escape valve, not the default. Three reasons:

1. **The user gave you 28 skills' worth of context for a reason.**
   Curiosity (rung 1) and reframe (rung 2) often surface answers that
   were already in the codebase, just not in the sub-loop's view.
2. **Three escalations are calibration data.** When the council
   convenes, the user has *evidence* that the wire is genuinely hard
   — not "you got stuck once." That evidence is worth the rung-1 + rung-2
   spend.
3. **The ledger preserves the journey.** Each rung writes to ledger
   `history`, so the council (and the user) can see what was tried.
   "Stuck" without a journey is opaque; with a journey it is diagnostic.

This is the "creativity and curiosity when stuck" the user specified —
formalized as a finite, terminating, evidence-producing escape ladder.
