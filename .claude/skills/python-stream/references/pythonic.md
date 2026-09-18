# Pythonic reference — PEP 20/8 code-review clinic

Distilled from the `pythonic-evaluator` standalone skill. Use when the user
pastes Python and asks "is this Pythonic?", "review this", or "how can I
improve this?" — even a single function. Historical/fuller content lives in
git history under `.claude/skills/pythonic-evaluator/`.

## Evaluation rubric (score 1–5 per dimension; produce a finding for ≤ 3)

| Dimension        | What to examine                                                        |
|------------------|------------------------------------------------------------------------|
| **Readability**  | Names, line length, visual noise, redundant comments                   |
| **Explicitness** | Magic numbers, ambiguous names, implicit behavior, missing type hints  |
| **Structure**    | Function focus, abstraction level, nesting depth, early returns        |
| **Data Modeling**| dict vs dataclass vs Pydantic vs TypedDict vs NamedTuple — right tool? |
| **Error Handling**| Bare except, swallowed exceptions, fail-fast, validation at boundary  |

## Output format (every evaluation uses this structure)

1. **Quick Verdict** — one or two sentences: dominant strength + biggest gap.
2. **Scorecard** — bar-chart text block (`[N/5] ████░`), summed to `/25`.
3. **Findings** — for each dimension ≤ 3: canonical principle name, severity
   emoji (🔴 correctness, 🟡 maintainability, 🟢 style), one-line "what's
   wrong", `# Before` / `# After — Pythonic` pair, one-line "why this is better."
   Lead with 🔴 regardless of dimension.
4. **What's Already Good** — one or two genuine strengths; skip if none.
5. **Next Snippet** — close every evaluation with an invitation to submit the next.

## Canonical principle names (use consistently)

| Anti-pattern                                 | Principle name                  |
|----------------------------------------------|---------------------------------|
| Plain dict for structured data               | "Reach for dataclass"           |
| `except:` or `except Exception:`             | "Specific exceptions only"      |
| Nested if/else instead of early return       | "Flatten with early return"     |
| Bare integer / string literal                | "Named constants"               |
| No type hints on function signature          | "Annotate the boundary"         |
| `for i in range(len(x))`                     | "Enumerate, don't index"        |
| Mutable default argument (`def f(x=[])`)     | "Immutable defaults"            |
| `x == True` / `x is True`                   | "Truthiness, not equality"      |
| `except: pass` / returning None on error     | "Errors must not pass silently" |
| Function doing more than one thing           | "Single responsibility"         |
| Pydantic v1 syntax (`@validator`, `.dict()`) | "Pydantic v2 always"            |
| `isinstance` check instead of duck typing    | "Prefer duck typing"            |
| Long comprehension harder to read than loop  | "Clarity over cleverness"       |

## Codebase alignment

In spectrafit-core the following conventions are *additional* constraints on
top of plain PEP 8/20 — call them out explicitly if violated:

- **Pydantic `BaseModel` over `@dataclass`** (enforced by `enforce-pydantic-native.sh`).
- **`match`/`case` over `if/elif ==` chains** on a discriminator (enforced by
  `enforce-match-dispatch.sh`).
- **Registry over per-call maps** — new shapes go into `MODEL_REGISTRY` / `MIGRATIONS`,
  not a fresh dict literal.

When a "reach for dataclass" finding fires on a contract model, redirect to
"reach for Pydantic BaseModel with `extra='forbid'`" — the codebase convention
wins over vanilla PEP advice.

## Session loop behaviour

- **Revised code:** re-score only changed dimensions; show delta (`Error Handling 1/5 → 4/5 ✓`).
- **"What should I fix first?":** point to 🔴 only; if none, lowest 🟡.
- **Score ≥ 22/25:** declare Pythonic, offer one optional stretch goal.
- **Snippet > 100 lines:** top three structural issues only; note public API surface first.
