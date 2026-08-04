// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { recoveryPlot } from "./recovery";

const rows = [{ param: "a0", backend: "lmfit", truth: 5, guess: 4, fit: 5.01 }];

describe("recoveryPlot", () => {
  it("renders SVG", () => {
    expect(
      recoveryPlot(rows as any, { colors: { lmfit: "#0cf" } })
    ).toBeInstanceOf(SVGElement);
  });

  it("empty-safe", () => {
    expect(recoveryPlot([], { colors: {} })).toBeInstanceOf(SVGElement);
  });

  it("honors an explicit width", () => {
    const svg = recoveryPlot(rows as any, { colors: { lmfit: "#0cf" }, width: 500 });
    expect(svg.getAttribute("width")).toBe("500");
  });
});
