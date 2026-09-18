/**
 * X1: Axis-label presence test.
 *
 * Renders each plot factory with minimal data and checks that the resulting SVG
 * contains at least one non-empty <text> element that holds an axis label string.
 * The simplest structural check: Observable Plot writes axis labels as <text> nodes;
 * we assert the SVG's textContent contains each expected label string.
 *
 * This test guards against future regressions where `label: null` reappears on a
 * primary axis — it will fail if the axis label text is absent from the rendered SVG.
 */
// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { spectrumPlot, residualPlot } from "./spectrum";
import { timingBoxPlot } from "./timing";
import { winnerPlot } from "./winner";
import { recoveryPlot } from "./recovery";
import { saturationHeatmap } from "./saturation";
import { conditioningPlot } from "./conditioning";
import { recoveryErrorPlot } from "./recoveryError";
import { speedupDistPlot } from "./speedupDist";
import { iterationsPlot } from "./iterations";
import { ciIntervalPlot } from "./index";
import { PLOT_SPECS } from "./spec";

const colors = { lmfit: "#0cf" };

describe("axis labels — no null primary-axis labels", () => {
  it("spectrumPlot: x=energy (arb. units), y=intensity (arb. units)", () => {
    const s = {
      ref: [{ x: 0, y: 1 }],
      guess: [{ x: 0, y: 0.9 }],
      fits: [{ backend: "lmfit", rows: [{ x: 0, y: 1, backend: "lmfit" }] }],
    };
    const svg = spectrumPlot(s as any, { colors });
    const text = svg.textContent ?? "";
    expect(text).toContain("energy");
    expect(text).toContain("intensity");
  });

  it("residualPlot: x=energy (arb. units), y=residual", () => {
    const rows = [{ x: 0, y: 0.01, backend: "lmfit" }];
    const svg = residualPlot(rows as any, { colors });
    const text = svg.textContent ?? "";
    expect(text).toContain("energy");
    expect(text).toContain("residual");
  });

  it("timingBoxPlot: x=solve time (ms, log), y=solver", () => {
    const rows = [{ backend: "lmfit", p5: 1, p25: 2, median: 3, p75: 4, p95: 5 }];
    const svg = timingBoxPlot(rows as any, { colors });
    const text = svg.textContent ?? "";
    expect(text).toContain("solve time");
    expect(text).toContain("solver");
  });

  it("winnerPlot: x=win fraction (bootstrap), y=solver", () => {
    const bars = [{ backend: "lmfit", fraction: 0.8 }];
    const svg = winnerPlot(bars as any, { colors });
    const text = svg.textContent ?? "";
    expect(text).toContain("win fraction");
    expect(text).toContain("solver");
  });

  it("recoveryPlot: x=deviation from truth, y=parameter", () => {
    const rows = [
      { param: "amplitude", guess: 1, fit: 1.1, truth: 1.0, backend: "lmfit", scale: 1, guessDev: 0, fitDev: 0.1 },
    ];
    const svg = recoveryPlot(rows as any, { colors });
    const text = svg.textContent ?? "";
    expect(text).toContain("deviation from truth");
    expect(text).toContain("parameter");
  });

  it("saturationHeatmap: x=solver, y=category", () => {
    const rows = [{ category: "easy", backend: "lmfit", r2: 0.999 }];
    const svg = saturationHeatmap(rows as any, {});
    const text = svg.textContent ?? "";
    expect(text).toContain("solver");
    expect(text).toContain("category");
  });

  it("conditioningPlot: x=κ(J) (log), y=solver", () => {
    const rows = [{ backend: "lmfit", kappa: 10, absent: false }];
    const svg = conditioningPlot(rows as any, { colors });
    const text = svg.textContent ?? "";
    expect(text).toContain("κ");
    expect(text).toContain("solver");
  });

  it("recoveryErrorPlot: x=recovery error (%), y=solver", () => {
    const rows = [{ backend: "lmfit", values: [0.1, 0.2], p5: 0.05, p25: 0.1, median: 0.15, p75: 0.2, p95: 0.25 }];
    const svg = recoveryErrorPlot(rows as any, { colors });
    const text = svg.textContent ?? "";
    expect(text).toContain("recovery error");
    expect(text).toContain("solver");
  });

  it("speedupDistPlot: x=speedup × (log), y=solver", () => {
    const rows = [{ backend: "lmfit", p5: 0.5, p25: 0.8, median: 1, p75: 2, p95: 5 }];
    const svg = speedupDistPlot(rows as any, { colors });
    const text = svg.textContent ?? "";
    expect(text).toContain("speedup");
    expect(text).toContain("solver");
  });

  it("iterationsPlot: x=iterations, y=solver", () => {
    const rows = [{ backend: "lmfit", nIter: 20 }];
    const svg = iterationsPlot(rows as any, { colors });
    const text = svg.textContent ?? "";
    expect(text).toContain("iterations");
    expect(text).toContain("solver");
  });

  it("ciIntervalPlot: y=case (no null label)", () => {
    const rows = [{ caseId: "EZ-001", point: 1.5, lo: 1.0, hi: 2.0 }];
    const svg = ciIntervalPlot(rows as any, { spec: PLOT_SPECS["speedup-ci"] });
    const text = svg.textContent ?? "";
    expect(text).toContain("case");
    expect(text).toContain("speedup");
  });
});
