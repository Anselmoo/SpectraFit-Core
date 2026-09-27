> Applies to: **

# Design Decision Documentation

Architectural and technical decisions are recorded in a decision log that is kept outside this repository. Do not create the decision log here.

## Rules

- When you make, confirm, or discover a design decision, record it **immediately** in the MR description (and hand it to the maintainer for the decision log) — do not wait until the end of the session.
- A "design decision" is any choice where alternatives existed: library selection, algorithm choice, API shape, data format, performance trade-off, crate layout, inter-layer boundary.
- Use this ADR format for each entry:

```
## [YYYY-MM-DD] <short imperative title, e.g. "Use JSON strings across PyO3 boundary">
**Context**: why the decision was needed
**Decision**: what was decided
**Rationale**: why this approach over the alternatives
**Trade-offs**: known downsides or constraints accepted
```

- Mark decisions inline in your response with `> **[DECISION]**` so they are easy to spot and grep.
- Ask the maintainer for relevant prior decisions when a change touches an established design.
- If a prior decision is superseded, add a `**Superseded by**: [date] title` line to the old entry instead of deleting it.

## Do not

- Do not defer writing decisions until "later" — context compaction or session end will lose them.
- Do not write vague entries like "use Rust for performance" — include the specific alternative that was rejected and why.
- Do not store decisions only in chat — the MR description is the reviewable record.
