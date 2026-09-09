/**
 * TypeScript half of the cross-language guard on the per-backend median
 * reduction.
 *
 * `backendFacts()` here and `_backend_facts` in python/oracles/reports.py are
 * two implementations of one statistic. The dashboard computes it in the
 * browser; the docs performance page cannot (results.json is ~49 MB and
 * hook-blocked), so Python caches the same reduction into manifest.json. Both
 * outputs are published on the same Pages host under the same run id.
 *
 * Both sides assert against the SAME fixture, tests/parity/fixtures/
 * backend_facts_golden.json, so either implementation drifting fails its own
 * suite without needing a cross-language runner in CI. The Python half is
 * tests/parity/test_backend_facts_parity.py.
 *
 * If you change the reduction, update the golden AND both implementations
 * together — they are one statistic, not two.
 */
import { describe, expect, it } from "vitest";
import golden from "../../../../tests/parity/fixtures/backend_facts_golden.json";
import { backendFacts } from "../backendFacts";
import type { BenchReport } from "../../contract";

/** Golden cases use snake_case (the manifest's convention); the wire is camelCase. */
function toReport(g: typeof golden): BenchReport {
  return {
    suite: g.suite.map((c) => ({
      id: c.id,
      m: Object.fromEntries(
        Object.entries(c.m).map(([id, m]) => [
          id,
          { medMs: m.med_ms, r2: m.r2, speedup: m.speedup, success: m.success },
        ]),
      ),
    })),
  } as unknown as BenchReport;
}

describe("backendFacts matches the shared cross-language golden", () => {
  const rows = backendFacts(toReport(golden));
  const by = Object.fromEntries(rows.map((r) => [r.id, r]));

  it.each(["alpha", "beta"])("%s reproduces the golden exactly", (id) => {
    const want = (golden.expected as Record<string, Record<string, number>>)[id];
    const got = by[id];
    expect(got, `${id} missing from backendFacts output`).toBeDefined();
    expect(got.medMs).toBeCloseTo(want.med_ms, 10);
    expect(got.medR2).toBeCloseTo(want.med_r2, 10);
    expect(got.medSpeedup).toBeCloseTo(want.med_speedup, 10);
    expect(got.casesRun).toBe(want.cases_run);
    expect(got.successRate).toBeCloseTo(want.success_rate, 10);
  });

  it("does not count a case where the backend is absent", () => {
    // The branch most likely to diverge between the two ports: `beta` is in 3
    // of 4 golden cases, mirroring jax's 58-of-151 in the real suite.
    expect(by.beta.casesRun).toBe(3);
    expect(by.alpha.casesRun).toBe(4);
  });
});
