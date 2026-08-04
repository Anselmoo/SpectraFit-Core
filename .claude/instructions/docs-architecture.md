> Applies to: ARCHITECTURE.md

# Documentation & architecture maintenance

Keep the canonical architecture documents current. Small design changes must update `ARCHITECTURE.md` or add an ADR.

## Rules

- When changing public interfaces (Python API or Rust crate surface), update `ARCHITECTURE.md` with the rationale and the migration notes.

- Major design decisions should be recorded as an ADR (architecture decision record) in `docs/adr/` with a short summary in `ARCHITECTURE.md`.

- Add or update examples and minimal diagrams when the shape of data (e.g., FitGraph, FitResult) or dataflow changes.

## Do not

- Do not leave architecture drift unrecorded — every PR that modifies interfaces must reference the corresponding doc change or ADR.
