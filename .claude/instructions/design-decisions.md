> Applies to: **

# Design Decision Documentation

This project tracks architectural and technical decisions in `DECISIONS.md` at the repo root.

## Rules

- When you make, confirm, or discover a design decision, append it to `DECISIONS.md` **immediately** using the Edit or Create tool — do not wait until the end of the session.
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
- Read `DECISIONS.md` at the start of a session to avoid contradicting prior decisions.
- If a prior decision is superseded, add a `**Superseded by**: [date] title` line to the old entry instead of deleting it.

## Do not

- Do not defer writing decisions until "later" — context compaction or session end will lose them.
- Do not write vague entries like "use Rust for performance" — include the specific alternative that was rejected and why.
- Do not store decisions only in chat — the file is the persistent record.
