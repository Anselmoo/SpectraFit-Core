/**
 * EvidenceVerdict — the headline finding atop the results destination.
 * Subject-blind, reads the manifest gate fields; renders nothing without a manifest.
 */
import { render, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { EvidenceVerdict } from "./EvidenceVerdict";
import type { BenchReport } from "../contract";

afterEach(cleanup);

const withManifest = {
  baselineSolverId: "lmfit",
  manifest: {
    gateState: "pass",
    geomeanSpeedupVsBaseline: 12.28,
    harmonicMeanSpeedupVsBaseline: 11.25,
    maxAbsDeltaR2: 8.97e-10,
    spectrafitWinRate: 0.867,
    regressions: 0,
  },
} as unknown as BenchReport;

describe("EvidenceVerdict", () => {
  test("leads with the finding: geomean, baseline, accuracy, win rate — subject-blind", () => {
    const { container } = render(<EvidenceVerdict report={withManifest} />);
    const text = container.textContent ?? "";
    expect(text).toMatch(/12\.28×/);
    expect(text).toMatch(/lmfit/); // vs baseline, not a crowned subject
    expect(text).toMatch(/8\.97e-10/);
    expect(text).toMatch(/86\.7%/);
    expect(text.toLowerCase()).toContain("pass");
    // subject-blind: never names spectrafit as the winner
    expect(text.toLowerCase()).not.toContain("spectrafit");
  });

  test("renders nothing when the manifest is absent", () => {
    const noManifest = { baselineSolverId: "lmfit", manifest: null } as unknown as BenchReport;
    const { container } = render(<EvidenceVerdict report={noManifest} />);
    expect(container.textContent).toBe("");
  });
});
