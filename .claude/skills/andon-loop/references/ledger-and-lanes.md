# Ledger: the resumable, enforceable state file

The ledger lives at `.andon/ledger.json` in the project root. It is what makes
the loop **auto-enforcing**: any session (or a CI hook) can read it and check the
andon rule without a human in the loop. Commit it — its `history` *is* the
hardening record of the project, step by step.

## Schema (v2)

```json
{
  "version": 2,
  "cycle": 1,                               // converged-run counter
  "pass": 4,                                // traversal counter within this cycle
  "cursor": {"stage": "web", "pass": 4},    // where the loop is right now
  "mode": "fix",                            // propose | fix  (operating switch)
  "intent": "harden",                       // harden | feature | split (what the cycle is for)
  "acceleration": {"subagents": "required", "mcp": "required"},
  "stages": ["crate", "core", "bench", "json", "web", "render"],
  "wires": [
    {
      "from": "crate", "to": "core",
      "lane": "fast",
      "status": "green",                    // green | red | unknown
      "contract": "ABI / pyo3",
      "wired_test": "tests/contract/test_crate_core.py",
      "last_proven_pass": 4
    },
    {
      "from": "web", "to": "render",
      "lane": "slow",
      "status": "red",
      "contract": "Playwright",
      "wired_test": "e2e/render.spec.ts",
      "last_proven_pass": 1,
      "cadence": 3                          // prove every 3 passes (slow lane)
    }
  ],
  "constraint": {"kind": "wire", "ref": "web→render", "note": "visible lane is the slowest gate"},
  "gaps": [
    {"id": "g14", "stage": "bench", "kind": "bug", "on_constraint": false,
     "note": "NaN in residuals leaks into JSON", "status": "open", "reopened": 0}
  ],
  "mcp_candidates": [
    {"wire": "web→render", "mcp": "playwright", "would_remove": "slow-lane cost"},
    {"wire": "*", "mcp": "github", "would_remove": "manual PR gating"}
  ],
  "history": [
    {"step": 1, "kind": "pass", "pass": 1, "cycle": 1,
     "cursor": {"stage": "crate"}, "constraint": {"ref": "crate→core"},
     "closed_bugs": 2, "closed_features": 0, "via": [],
     "wires": [{"from": "crate", "to": "core", "status": "red"}]},
    {"step": 2, "kind": "subcycle", "pass": 2, "cycle": 1,
     "from_stage": "bench", "back_to": "crate", "note": "fix touched the ABI contract",
     "constraint": {"ref": "crate→core"}, "via": [],
     "wires": [{"from": "crate", "to": "core", "status": "green"}]},
    {"step": 9, "kind": "pass", "pass": 4, "cycle": 1, "converged": true,
     "cursor": {"stage": "render"}, "constraint": {"ref": "web→render"},
     "closed_bugs": 0, "closed_features": 1, "via": ["subagent", "mcp:playwright"],
     "wires": [{"from": "web", "to": "render", "status": "green"}]}
  ]
}
```

## Field rules

- **status** transitions are the heart of enforcement. A wire goes `green` only
  after its `wired_test` passes in the current session, on the edge cases too
  (the zero-artifacts bar). It drops to `red` the moment that test fails.
  `unknown` means "no proof yet" and is treated as *not advanceable* — identical
  to `red` for the andon rule.
- **pass vs cycle**: `pass` counts traversals; `cycle` counts converged runs. A
  cycle increments only when a pass converges (zero new gaps, all wires green).
- **cursor** records position so a resumed session and the board both know where
  the loop stopped, and so a sub-cycle backtrack has somewhere to return *from*.
- **lane: slow** wires carry a `cadence`: prove them every *N* passes, not every
  step. Between proofs their status is `green` only if `last_proven_pass` is
  within `cadence` of the current pass; otherwise treat as `unknown`.
- **acceleration** is honored only in `fix` mode and only where the platform
  offers it (subagents in Claude Code, MCPs that are connected). `required` means
  the loop must use them rather than run the slow lane inline or hand-roll a
  browser harness; `off` disables. See `lanes-and-mcp.md`.
- **gaps** persist across sessions; `reopened` counts how often a gap came back.
  At `reopened >= 3` the gap's wire becomes the constraint (sub-cycle thrash
  guard) instead of being backtracked again.
- **history** is a list of **steps**, each a `pass` or a `subcycle`. A pass step
  records the cursor and a wires snapshot; a subcycle step records `from_stage`
  and `back_to` so the excursion can be drawn. `via` lists the accelerators used
  (`subagent`, `mcp:<name>`).

## Resuming

On entry, if the ledger exists:

1. Report cycle/pass, mode, the cursor, and a one-line wire status row (`🟢🟢🟢🟢⚪`).
2. Recheck any `slow`-lane wire whose `last_proven_pass` is stale → set `unknown`.
3. Resume at the cursor, or at the first non-green wire, or at the `constraint`
   if all are green.

## Rendering the board

The ledger is a time-series, not just state. Render it as a self-contained HTML
board — the stream drawn as a lit pipeline with a step scrubber:

```bash
python scripts/andon_board.py .andon/ledger.json   # → andon-board.html
```

Zero dependencies, opens in any browser. Two layouts share one step scrubber:
**linear** (default) draws the stream left to right; **wheel** (`--layout wheel`)
draws it as a ring where render wraps back to crate as a "↺ next pass" arc, with
the cycle/pass count in the hub — the PDCA wheel made literal, and the clearest
way to see that repeated traversals are passes of one cycle, not new cycles.
Each `history` step becomes a frame: dragging the scrubber walks the andon lamp,
as backtrack arcs (N→N−2 and back), badges accelerated steps (`⚡` subagent,
`◆` MCP), and marks the converged pass. Without snapshots it still renders the
current state. Generate it at each cycle close and drop the screenshot in the PR
or standup.

## Using it as a CI gate (optional, powerful)

A tiny script can read the ledger and exit non-zero if any fast-lane wire is not
green — turning the andon rule into a merge gate. This is the bridge from
"a loop I run" to "a rule the repo enforces on everyone." Suggest it in Phase 6
once the loop is stable; do not impose it early.
