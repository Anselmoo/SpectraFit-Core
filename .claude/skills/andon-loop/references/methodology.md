# Methodology: where this loop comes from

This skill is not a new invention; it is four well-tested disciplines wired
together and pointed at a codebase. Knowing the source of each phase tells you
when to bend it.

## The lineage

### Toyota Production System — Jidoka and Andon (the enforcement)
Jidoka means "automation with a human touch": build quality *in* rather than
inspecting it *out*. Its visible artifact is the **andon cord** — any worker can
halt the entire line the moment a defect appears, because a defect that flows to
the next station is far more expensive to fix there than here. This is Phase 4's
hard stop: **a red wire halts the loop.** The instinct you described — "check if
it is connected before going next" — is Jidoka.

TPS adds one more idea this skill leans on: **standardized work** — once an
improvement is proven, you capture it as the new standard so it is never
re-derived by hand. In a software loop, a proven, thrice-repeated fix or closure
ritual gets *extracted into a skill* (the Phase 6 kaizen step). The loop's highest
output is not the patched code; it is the standard it leaves behind.

### Deming — PDCA (the loop shape)
Plan → Do → Check → Act, repeated. Plan = pick one gap (Phase 3). Do =
implement. Check = unit + wired test (Phase 4). Act = advance, or stop and
re-plan. Each cycle (Phase 5) is one full turn of the wheel; Phase 6 is the
"Act" that re-plans the *next* turn. PDCA is why this is a *loop* and not a
checklist.

### Goldratt — Theory of Constraints (the prioritization)
A system's throughput is set by its single biggest bottleneck; improving
anything else is waste until that constraint moves. The Five Focusing Steps —
identify the constraint, exploit it, subordinate everything to it, elevate it,
then repeat because it has now moved — are exactly Phases 2, 3, and 6. You
already did the first step instinctively when you named MCP-usage and Playwright
as your bottlenecks. The skill makes "attack the constraint first" a rule rather
than a hunch.

### Google SRE — error budgets (the bug-vs-feature call)
SRE's key move is to *quantify* acceptable unreliability. Inside budget, ship
features; over budget, stop and harden. This resolves your "evaluate between bugs
and missing features" question with a rule instead of vibes: wires green + bugs
within tolerance → a feature step is legitimate (Phase 3's error-budget
override). Over budget → no features until you are back in the black.

## What Apple actually contributes (and what it doesn't)

Apple has no published *hardening loop* — its engineering process is private,
and the popular "Apple uses design thinking" framing is a retrofit. Apple does
not describe itself in IDEO/d.school terms; the account written by Apple
University's own dean (Podolny & Hansen, *How Apple Is Organized for
Innovation*, HBR 2020) describes something different and more useful here: a
functional organization that **aligns expertise with decision rights** — experts
leading experts, not general managers hitting targets. Three of its principles
are baked into this skill:

- **Zero artifacts** (the green-wire bar). The article's camera team refused to
  ship a feature that failed on a rare corner case — photographing a face behind
  chicken wire — because sidestepping corner cases would violate a strict quality
  standard. A wire here is green only when its contract holds on the edge cases,
  not just the happy path. This is the single best articulation of the gate.
- **Separating "how right" from "how hard"** (the andon rule, as a principle).
  Apple leaders are expected not to let the difficulty of executing a decision
  determine whether it is chosen. Translated: you do not skip a red wire because
  greening it is hard.
- **Immersion in the details** (scan rigor). Leaders are expected to know their
  area several levels down and to drill into the actual test result or line of
  code, not a summary. The gap scan inspects real artifacts, not vibes.

The one thing the third-party "design thinking" pieces get right is **radical
focus** — Jobs cutting the product line from fifteen to three on his return.
That is the loop's "one item per step." But focus and a quality bar are Apple's
contribution; the *loop mechanics* come from Toyota, Deming, and Goldratt above.
That is why this skill is named for the andon cord, not for Cupertino.

## "Wired test" is contract testing

The term you coined has an established name: **contract testing** (often
consumer-driven contracts, popularized by tools like Pact). The idea is identical
— prove that a producer satisfies exactly what a consumer needs across a
boundary, without standing up the whole system. Keep saying "wired test" if you
like it; just know that:

- A **unit test** proves a stage is correct *in isolation*.
- A **wired test / contract test** proves the **handoff** — that A's output is
  something B can actually consume. This is the test that turns a wire green.
- An **E2E test** proves the whole stream end to end. Expensive; this is the
  slow/visible lane, run on cadence, not every step.

The whole point of the wire abstraction is that you usually do *not* need the
expensive E2E run to know a handoff works — a cheap contract test on the data
shape catches most breakage in the fast lane.

## Passes, cycles, and sub-cycles

The three time scales map cleanly onto the lineage. A **pass** is one turn of
Deming's PDCA wheel applied to the whole stream. A **cycle** is convergence —
you keep turning the wheel until a pass produces no new defects, which is just
PDCA's "repeat until stable." A **sub-cycle** is Jidoka pointed the other way:
the andon rule stops a defect flowing *downstream*, and the sub-cycle catches a
fix that disturbs something *upstream*, re-proving the shaken contract before
moving on. None of this is new theory; it is the same three disciplines applied
at the granularity each problem actually occurs.

## The one rule that matters most

If you remember nothing else: **never advance past a red wire to make the loop
feel productive.** Apparent progress bought by skipping the gate is the single
failure mode that turns a hardening loop into a debt generator. The andon cord
exists to make stopping the *normal*, expected thing — not a defeat.
