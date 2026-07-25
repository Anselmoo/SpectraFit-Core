---
type: gap
title: "[Medium] docs-drift: cases.py category enumeration missing convex_baseline/diagonal_quadratic (FALSE POSITIVE)"
description: "python/oracles/cases.py category enumeration lists only easy/complex/reality/optfn/scaling/edge/lineshapes/fixed/tied — claimed missing convex_baseline/diagonal_quadratic"
tags: ["kind:bug", "status:closed", "domain:docs-drift", "severity:medium"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/unattributed]]
- On constraint: false
- Location: `python/oracles/cases.py` (category enumeration, `CATEGORY_REGISTRY`)
- Finding domain: docs-drift
- Suggested fix / explanation: add the missing `convex_baseline`/`diagonal_quadratic` categories
  to the enumeration.
- Resolved by: [[evidence/unattributed-methodology-ev1]]
- Proposal: **Deliberate no-change — the finding's premise is false.** Confirmed via a dedicated
  research pass: the live `CATEGORY_REGISTRY` in `cases.py` (9 `CategoryDef` records at lines
  1308-1407: easy/complex/reality/optfn/scaling/edge/lineshapes/fixed/tied) is complete —
  `convex_baseline`/`diagonal_quadratic` do not exist as live category values ANYWHERE in the
  current Python tree (grepped the whole tree, zero matches in `.py` files). They only appear as
  (a) descriptive prose in `MODELS.md:67,69` explaining what the `Quadratic` kernel conceptually
  "backs," and (b) historical `DECISIONS.md` entries (`[2026-05-31]`, `[2026-06-01]`-ish) about a
  `super_benchmark.py` catalog file that does not exist in the current tree
  (`find . -iname "super_benchmark*"` → no results) — a design that was apparently superseded or
  never merged. There is no live category to be "missing" from the enumeration; the audit item is
  chasing a ghost from an earlier, since-abandoned catalog design. No fix applied to `cases.py`.
  MODELS.md:67,69's present-tense phrasing ("backs the `convex_baseline` family") is mildly loose
  given no such family currently exists in the live catalog — flagged as a judgment call, left
  untouched (out of scope; a wording nitpick, not a factual error, since `Quadratic` genuinely can
  compose into a convex-bowl objective, it's just not wired as a named case family). Strategy: e
  (structural/connectivity — verified the negative: exhaustive grep across the Python tree).
  Blast radius: none (no change made).
