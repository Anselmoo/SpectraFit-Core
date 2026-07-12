# Trunk Ledger — <trunk-slug> — <YYYY-MM-DD>
**Branch:** <git-branch>   **Status:** open

## Trunk
<one sentence — the goal>

## Definition of Done   (each item VERIFIABLE — a command/observable, not "looks good")
- [ ] <criterion + how to verify, e.g. `cargo test -p spectrafit-solver` green>
- [ ] <CI pipeline green on commit <sha>>
- [ ] <merged to main>

## Invariants in play
- Invariant <X>: <what must hold>

## Branch log
| # | find | invariant violated | kind | on-trunk? | verdict | status |
|---|------|--------------------|------|-----------|---------|--------|
| 1 | <find> | <invariant or —> | instance | branch (blocks merge) | fix-now | open |
