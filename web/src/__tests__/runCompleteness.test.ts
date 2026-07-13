/**
 * runCompleteness derives what a served run contains from presence checks only —
 * never a hardcoded denominator. A run missing timing / convergence-to-truth is
 * disclosed (the CompletenessBanner shows it); a full run discloses nothing.
 */
import { describe, it, expect } from "vitest";
import { runCompleteness } from "../contract";
import type { BenchReport } from "../contract";

// Minimal stubs exercising only the fields runCompleteness reads.
const partial = {
  suite: [{ m: { spectrafit: { r2: 0.99, medMs: null } } }],
  analyzed: [{ profiles: { spectrafit: { thetaDistance: null } } }],
} as unknown as BenchReport;

const full = {
  suite: [{ m: { spectrafit: { r2: 0.99, medMs: 1.2 } } }],
  analyzed: [{ profiles: { spectrafit: { thetaDistance: [1.0, 0.4, 0.05] } } }],
} as unknown as BenchReport;

describe("runCompleteness", () => {
  it("flags a partial run (no timing, no θ) — presence-derived, no denominator", () => {
    const c = runCompleteness(partial);
    expect(c.nCases).toBe(1);
    expect(c.hasSuiteTiming).toBe(false);
    expect(c.hasConvergenceTruth).toBe(false);
    expect(c.missing).toEqual(["timing", "convergence-to-truth"]);
  });

  it("discloses nothing when the run carries timing and θ", () => {
    const c = runCompleteness(full);
    expect(c.hasSuiteTiming).toBe(true);
    expect(c.hasConvergenceTruth).toBe(true);
    expect(c.missing).toEqual([]);
  });

  it("flags only the missing dimension (timing present, θ absent)", () => {
    const mixed = {
      suite: [{ m: { spectrafit: { r2: 0.99, medMs: 2.0 } } }],
      analyzed: [{ profiles: { spectrafit: { thetaDistance: [] } } }],
    } as unknown as BenchReport;
    expect(runCompleteness(mixed).missing).toEqual(["convergence-to-truth"]);
  });
});
