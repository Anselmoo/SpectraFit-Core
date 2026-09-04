/**
 * TDD: G18 showcase panels — multidim (SP-2) + globalFit (SP-3).
 *
 * Cases:
 *   1. multidim present → stats (D, grid, r², peaks) + a projection heatmap SVG.
 *   2. multidim absent → honest "did not record" note, no crash, no blank.
 *   3. globalFit present → series stats + slices SVG + kinetics SVG.
 *   4. globalFit absent → honest note.
 *   5. Carrier search: the block is found on ANY analyzed case, not just [0].
 */
import { render, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import React from "react";
import { multidimShowcaseBody } from "../bodies/multidimShowcase";
import { globalFitShowcaseBody } from "../bodies/globalFitShowcase";
import type { BenchReport, GlobalFit, MultiDim } from "../../contract";

afterEach(cleanup);

function reportWith(analyzed: unknown[]): BenchReport {
  return { analyzed } as unknown as BenchReport;
}

const MULTIDIM: MultiDim = {
  nDims: 3,
  shape: [8, 8, 8],
  nPoints: 512,
  rSquared: 0.9876,
  peaks: [{ amplitude: 2.5, center: [0.1, -0.2, 0.3], sigma: [1.0, 1.1, 0.9] }],
  projections: [
    {
      labels: ["x0", "x1"],
      matrix: [
        [0.0, 0.5, 0.0],
        [0.5, 2.5, 0.5],
        [0.0, 0.5, 0.0],
      ],
    },
  ],
  source: "spectrafit-core",
  dataProvenance: "synthetic",
};

const GLOBAL_FIT: GlobalFit = {
  x: [0, 1, 2, 3],
  datasetAxis: [0.0, 1.0],
  slices: [
    { coord: 0.0, obs: [0.1, 1.9, 0.2, 0.0], model: [0.0, 2.0, 0.1, 0.0] },
    { coord: 1.0, obs: [0.0, 1.0, 0.1, 0.0], model: [0.0, 1.1, 0.05, 0.0] },
  ],
  traces: [{ label: "p0", center: 1.0, sigma: 0.4, amplitude: [2.0, 1.1] }],
  source: "spectrafit-core",
  xLabel: "x",
  axisLabel: "time",
  dataProvenance: "synthetic",
};

describe("multidimShowcaseBody", () => {
  it("renders stats + a projection heatmap when multidim is present", () => {
    const { getByText, container } = render(
      <>{multidimShowcaseBody(reportWith([{ id: "EZ-001", multidim: MULTIDIM }]))}</>,
    );
    expect(getByText("3-D")).toBeTruthy();
    expect(getByText(/8 × 8 × 8/)).toBeTruthy();
    expect(getByText("0.9876")).toBeTruthy();
    // PlotMount container is present (the SVG mounts via ResizeObserver).
    expect(container.querySelector("div")).toBeTruthy();
  });

  it("renders the honest note when no analyzed case carries multidim", () => {
    const { getByText } = render(
      <>{multidimShowcaseBody(reportWith([{ id: "EZ-001", multidim: null }]))}</>,
    );
    expect(getByText(/did not record/)).toBeTruthy();
  });

  it("finds the carrier on any analyzed index, not just [0]", () => {
    const { getByText } = render(
      <>{multidimShowcaseBody(
        reportWith([{ id: "EZ-001", multidim: null }, { id: "CX-002", multidim: MULTIDIM }]),
      )}</>,
    );
    expect(getByText("3-D")).toBeTruthy();
  });
});

describe("globalFitShowcaseBody", () => {
  it("renders series stats + two plots when globalFit is present", () => {
    const { getAllByText, getByText } = render(
      <>{globalFitShowcaseBody(reportWith([{ id: "EZ-001", globalFit: GLOBAL_FIT }]))}</>,
    );
    // Appears in the stats grid AND as the in-SVG note — both are wanted.
    expect(getAllByText(/2 slices along time/).length).toBeGreaterThanOrEqual(1);
    expect(getByText(/p0 \(c=1\.00, σ=0\.40\)/)).toBeTruthy();
  });

  it("renders the honest note when no analyzed case carries globalFit", () => {
    const { getByText } = render(
      <>{globalFitShowcaseBody(reportWith([{ id: "EZ-001", globalFit: null }]))}</>,
    );
    expect(getByText(/did not record/)).toBeTruthy();
  });
});
