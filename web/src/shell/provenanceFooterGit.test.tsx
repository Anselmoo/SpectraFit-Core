/**
 * Wave B1 — ProvenanceFooter git-provenance extension tests.
 *
 * TDD red-first: verifies the footer shows gitCommit (short), gitBranch,
 * and a human-readable timestamp from runTimestampUnix, gated-on-present.
 */
import { render, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ProvenanceFooter } from "./ProvenanceFooter";
import type { BenchReport } from "../contract";

afterEach(cleanup);

function makeReport(overrides: {
  runId?: string | null;
  gitCommit?: string | null;
  gitBranch?: string | null;
  runTimestampUnix?: number | null;
} = {}): BenchReport {
  const { runId, gitCommit, gitBranch, runTimestampUnix } = overrides;
  return {
    schemaVersion: "1.5",
    baselineSolverId: "lmfit",
    solvers: [],
    categories: [],
    suite: [],
    analyzed: [],
    manifest: runId
      ? {
          geomeanSpeedupVsBaseline: 1.0,
          maxAbsDeltaR2: 0.0,
          spectrafitWinRate: 1.0,
          regressions: 0,
          gateState: "PASS",
          pinned: { runId },
        }
      : null,
    gitCommit: gitCommit ?? null,
    gitBranch: gitBranch ?? null,
    runTimestampUnix: runTimestampUnix ?? null,
    trustBlock: null,
    inference: null,
  } as unknown as BenchReport;
}

describe("ProvenanceFooter — git provenance extension", () => {
  it("shows gitCommit (short) when present", () => {
    const report = makeReport({
      runId: "2026-06-18_run_001",
      gitCommit: "abc1234",
      gitBranch: null,
      runTimestampUnix: null,
    });
    const { container } = render(<ProvenanceFooter report={report} />);
    const text = container.textContent ?? "";
    expect(text).toContain("abc1234");
  });

  it("shows gitBranch when present", () => {
    const report = makeReport({
      runId: "2026-06-18_run_001",
      gitCommit: null,
      gitBranch: "fix/dashboard-and-greenups",
      runTimestampUnix: null,
    });
    const { container } = render(<ProvenanceFooter report={report} />);
    const text = container.textContent ?? "";
    expect(text).toContain("fix/dashboard-and-greenups");
  });

  it("shows a human-readable timestamp when runTimestampUnix is present", () => {
    // Unix epoch 1750000000 → some deterministic date string
    const report = makeReport({
      runId: "2026-06-18_run_001",
      gitCommit: null,
      gitBranch: null,
      runTimestampUnix: 1750000000,
    });
    const { container } = render(<ProvenanceFooter report={report} />);
    const text = container.textContent ?? "";
    // Should show something date-like (year 2025 or similar)
    expect(text).toMatch(/202[0-9]/);
  });

  it("does not show git fields when they are absent (no leaked null)", () => {
    const report = makeReport({
      runId: "2026-06-18_run_001",
      gitCommit: null,
      gitBranch: null,
      runTimestampUnix: null,
    });
    const { container } = render(<ProvenanceFooter report={report} />);
    const text = container.textContent ?? "";
    expect(text).not.toContain("null");
    expect(text).not.toContain("undefined");
  });

  it("still renders null when runId is absent (existing contract)", () => {
    const report = makeReport({
      runId: null,
      gitCommit: "abc1234",
      gitBranch: "main",
      runTimestampUnix: 1750000000,
    });
    const { container } = render(<ProvenanceFooter report={report} />);
    // The existing gate: runId absent → render nothing
    expect(container.textContent).toBe("");
  });

  it("shows all three git fields when all are present", () => {
    const report = makeReport({
      runId: "2026-06-18_run_001",
      gitCommit: "deadbeef",
      gitBranch: "main",
      runTimestampUnix: 1750000000,
    });
    const { container } = render(<ProvenanceFooter report={report} />);
    const text = container.textContent ?? "";
    expect(text).toContain("deadbeef");
    expect(text).toContain("main");
    expect(text).toMatch(/202[0-9]/);
  });
});
