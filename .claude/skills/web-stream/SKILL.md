---
name: web-stream
description: |
  Conductor for the web/ stream — the Vite + React dashboard that renders
  the BenchReport contract. Owns panels, render-truth surfaces, and the
  four-step verify cycle (vitest → bench → gate → playwright). Absorbs
  spectrafit-devboard and spectrafit-benchmark (web side); their
  specialist content lives in references/. Use when a task touches
  web/src/, panel registries, plot mounts, screenshots, dashboard export,
  or the manuscript-review gate. Composes with
  superpowers:test-driven-development and cupertino-council. Serena-first.
license: MIT
---

# web-stream

The single entry point for any Web-side work in spectrafit-core. Reads
`.claude/skills/INDEX.yaml § web-stream` for its anchor slice, then
dispatches to a `references/` sub-document.

## Anchors

**CLAUDE.md sections** (read before acting):
- *Running & previewing the dashboard (Claude Desktop / preview)* —
  detached server discipline, preview tool usage, contract regen flow.
- *Benchmark Engine (`oracles`) + Report* — the 3 destinations (Standing,
  Audit, Evidence), the PanelRecord registry as single source of truth.

**Hooks that will fire:**
- `enforce-render-boundary.sh` — block Python/template engines in TSX,
  block Pydantic in web files.
- `frontend-soft-freeze.sh` — block exported-symbol deletions and table-
  header removals on Edit; additive changes allowed.

## Serena first

The first action on any code-touching task **MUST** be a serena MCP call:

```
mcp__serena__get_symbols_overview    → orient a TSX file
mcp__serena__find_symbol PanelRecord → locate a panel definition
mcp__serena__find_referencing_symbols → who consumes this prop / type
```

`enforce-serena-first.sh` will warn on `Grep` patterns like
`class \w`, `def \w` from inside web/.

## Preview discipline (anchored to CLAUDE.md)

Two named servers live in `.claude/launch.json`:

| Name | Port | What | CLI fallback (detached) |
|------|------|------|--------------------------|
| `api` | 8000 | FastAPI `/api/report` | `nohup uv run poe serve &>/dev/null & disown` |
| `web` | 5173 | Vite, proxies `/api` → :8000 | `nohup npm --prefix web run dev &>/dev/null & disown` |

Start `api` before `web`. Use `preview_start <name>` in Claude Desktop —
it handles detachment. Inspect the live page with `preview_screenshot`,
`preview_snapshot`, `preview_eval`, `preview_inspect`, `preview_console_logs`,
`preview_network` — these are faster than re-screenshotting.

Port-conflict recovery:
`kill $(lsof -tiTCP:8000 -sTCP:LISTEN) 2>/dev/null || true`.

## The four-step verify loop (anchored to docs/methodology.md §3)

After any web edit:

1. `cd web && npm run test` — vitest / happy-dom, no browser.
2. `uv run poe benchmark` (or skip if no contract change).
3. `uv run spc-bench gate` — geomean speedup + max |Δr²| gate.
4. `uv run poe web_e2e` — Playwright `dashboard-render-audit`.
   **Needs both servers up**; auto-starts Vite but **not** the API.

Step 4 is the slow lane — in `tri-stream` mode it runs in a parallel
subagent, never blocks the fast loop.

## Decision: which sub-document?

| Subject | Reference |
|---------|-----------|
| Dashboard report panels, devboard HTML export, OKLCH dark mode, visx plot mounts | `references/devboard.md` |
| BenchReport contract on the web side, openapi.gen.ts regen, panel registry consumption | `references/benchmark-web.md` |

## Composes with

1. **Before**: `superpowers:test-driven-development` — a failing vitest
   first (or a `noHardcodedBackend.test.ts` source-scan, or a
   `contractCoverage.test.ts` assertion).
2. **While**: this skill's reference for the subject, serena-driven.
3. **Design questions**: `cupertino-council` (now part of
   `quality-council`) — Apple-style 5-voice critique on panel design.
4. **After**: the four-step verify cycle.
5. **If stuck**: `andon-loop/references/stuck-mode.md`.

## Three-pillar reporting

- **PERF**: panel render time, plot mount cost (visx + ResizeObserver).
- **RIGOR**: `noHardcodedBackend.test.ts` + `contractCoverage.test.ts`
  green; every backend enumerated via `solversOf(report)`.
- **PRESENTATION**: this is the stream's primary pillar — the
  render-truth panel snapshot, the Audit W1–W7 status, the manuscript-
  review gate.
