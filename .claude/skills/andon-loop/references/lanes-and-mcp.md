# Lanes, parallelization, and MCP leverage

Two of your observations — "Playwright is slow / only works in the first cycle"
and "the bottleneck is lack of MCP usage" — are the same problem: an expensive
proof sitting on the critical path of every cycle. The fix is structural, not
heroic.

## Visible vs non-visible lanes

Split every wire's proof into two lanes:

- **Fast / non-visible lane** — provable from bytes: ABI returns, import
  contracts, JSON schema, HTTP response shape. Cheap, deterministic, runs **every
  cycle**, on the critical path.
- **Slow / visible lane** — needs a rendered surface: Playwright, screenshots,
  visual diff. Expensive, flaky-prone, runs **on a cadence** (every *N* cycles)
  or **in parallel**, off the critical path.

The key insight: a web stage usually has *both* a fast data contract (the JSON it
fetches) and a slow render contract (what the user sees). Prove the data contract
every cycle; prove the render only periodically. Most front-end regressions are
data-shape regressions and get caught in the fast lane — so "Playwright is slow"
stops mattering because Playwright is no longer on the hot path.

### Why Playwright "only worked in the first cycle"

That is the classic symptom of an E2E check doing work a contract test should do:
it is re-validating data shape *through the browser* every time, so it is slow
and brittle. Move the data-shape assertion down to the fast lane (assert the JSON
the app fetches), and let Playwright assert only what genuinely needs pixels
(does the chart render, is the control visible). The visible lane shrinks to the
few things only a browser can confirm.

## Parallelization patterns

Once lanes are split, two forms of parallelism open up:

1. **Lane parallelism** — run the slow/visible lane in a background job while the
   fast loop keeps walking the stream. The fast loop never waits on the browser;
   it only consults the slow lane's last result from the ledger.
2. **Sub-stream parallelism** — if the stream forks (e.g. `bench → json` and
   `bench → web` are independent consumers of `bench`), the two branches can be
   hardened in parallel after their shared upstream wire is green. Detect forks
   in stream detection: a stage with two outgoing wires whose downstreams don't
   depend on each other.

Do not parallelize before the fast lane is reliably green — parallelism
multiplies the cost of a flaky gate.

## MCP leverage points

Treat MCPs as **constraint elevators** (Theory of Constraints step 4): bring one
in precisely when it removes the current bottleneck, not speculatively.

| Constraint | MCP that elevates it | What it buys |
|------------|----------------------|--------------|
| Slow/visible lane on the hot path | a Playwright / browser MCP | drives the rendered check directly, so the visible lane is cheap enough to run more often |
| Manual PR / merge gating | a GitHub MCP | the loop can open the PR and read CI status, closing the cycle without a context switch |
| Data-contract drift against a live DB | a database MCP | the wired test can query real schema instead of a fixture |
| Re-reading docs/specs each cycle | a docs MCP (e.g. Context7) | the gap scan checks behavior against current API docs automatically |

Record candidates in the ledger's `mcp_candidates` as you map the stream
(Phase 0c), then **promote** one in Phase 6 only when it would remove the
*current* constraint. An MCP that automates a step which isn't the bottleneck is
exactly the local optimization TOC warns against — it feels productive and
changes nothing.

## A concrete reshaping of your case

Before: every cycle ran Playwright to confirm the web app worked → slow, so it
only really ran in cycle 1.

After:
- **Every cycle (fast):** `bench → json` schema check + `json → web` fetch-shape
  check. Catches the overwhelming majority of breakage in seconds.
- **Every 3rd cycle, or in parallel (slow):** one Playwright check that the chart
  actually renders the JSON — driven by a Playwright MCP so it costs a tool call,
  not a hand-rolled harness.
- **Constraint, recomputed each cycle:** once the visible lane is off the hot
  path, the bottleneck likely moves to wherever bugs reopen most — which is now
  visible in the ledger history instead of hidden behind a slow test.

## The acceleration contract (fix mode)

The loop's own bottleneck is serial, un-delegated work: proving the slow lane
inline blocks the fast loop, and hand-rolling what an MCP already does wastes the
cycle. So in `fix` mode acceleration is a **commitment, not a suggestion** —
wherever the platform offers it, the loop must take it.

| Trigger | Required action in `fix` mode | Records in step `via` |
|---------|-------------------------------|------------------------|
| A slow / visible wire needs proving | Run it in a **subagent**, in the background, off the critical path; the fast loop reads its last result from the ledger | `subagent` |
| The stream **forks** (a stage with independent downstreams) | Harden the branches in **parallel subagents** once their shared upstream wire is green | `subagent` |
| An MCP elevates the current constraint | **Use it** — Playwright/browser MCP for the visible lane, GitHub MCP for PR gating, DB MCP for data contracts — instead of writing a one-off harness | `mcp:<name>` |
| A scan or doc-check repeats every pass | Delegate to a subagent or a docs MCP rather than re-doing it inline | `subagent` / `mcp:<name>` |

**Platform gates.** Subagents exist in Claude Code, not in the plain chat
interface; MCPs must be connected. The acceleration block degrades gracefully:
`required` means "use it where available." On a platform without subagents, the
slow lane falls back to cadence (every *N* passes) and the loop says so in the
cycle report rather than pretending it parallelized.

**Why mandate it.** Theory of Constraints again: once the visible lane is off the
hot path and the right MCP is doing the expensive proof, the constraint moves to
real engineering work instead of loop overhead. Acceleration is how the loop
stops being its own bottleneck — which was the original complaint that started
this skill.
