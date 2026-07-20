import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "vitest";
import { FAILURE_MODES } from "./taxonomy";

test("each failure mode has before/fix/guard text", () => {
  // Wave B2: 2 Track-0 self-catches + 4 render-defect catches = 6 total.
  expect(FAILURE_MODES.length).toBe(6);
  for (const m of FAILURE_MODES) {
    expect(m.before.length).toBeGreaterThan(0);
    expect(m.fix.length).toBeGreaterThan(0);
    expect(m.guard.length).toBeGreaterThan(0);
  }
});

test("every claimed guard maps to a real e2e assertion (no vapor guards)", () => {
  const spec = readFileSync(resolve(__dirname, "../../tests/e2e/dashboard-render-audit.spec.ts"), "utf8");
  for (const m of FAILURE_MODES)
    expect(spec, `guard "${m.guardId}" not found in e2e spec`).toContain(m.guardId);
});
