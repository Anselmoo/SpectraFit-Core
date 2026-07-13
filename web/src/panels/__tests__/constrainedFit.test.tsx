import { render } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { constrainedFitBody } from "../bodies/constrainedFit";
import type { BenchReport } from "../../contract";
import type { PanelCtx } from "../types";

const ctx: PanelCtx = {
  selectedId: null,
  view: "overview",
  solverIds: ["spectrafit", "lmfit", "jax"],
  colors: {},
  openCase: () => {},
};

function reportWith(analyzed: unknown[], suite: unknown[], solvers: unknown[]): BenchReport {
  return { analyzed, suite, solvers } as unknown as BenchReport;
}

describe("constrainedFitBody", () => {
  it("lists fixed + tied cases with their constraint summaries", () => {
    const report = reportWith(
      [
        { id: "FX-001", name: "single gaussian · center-fixed", category: "fixed", fixedParams: { p0: ["center"] }, exprEdges: [] },
        { id: "TI-001", name: "2×gaussian shared σ", category: "tied", fixedParams: {}, exprEdges: [{ targetNode: "p1", targetParam: "sigma", expression: "p0.sigma" }] },
        { id: "EZ-001", name: "single gaussian", category: "easy", fixedParams: {}, exprEdges: [] },
      ],
      [
        { id: "FX-001", m: { spectrafit: {}, lmfit: {} } },
        { id: "TI-001", m: { spectrafit: {}, lmfit: {} } },
      ],
      [{ id: "spectrafit", label: "spectrafit" }, { id: "lmfit", label: "lmfit" }, { id: "jax", label: "jax" }],
    );
    const node = constrainedFitBody(report, ctx);
    const { getByText, queryByText } = render(node as React.ReactElement);
    expect(getByText("FX-001")).toBeTruthy();
    expect(getByText("TI-001")).toBeTruthy();
    expect(getByText(/center held fixed/)).toBeTruthy();
    expect(getByText(/p1\.sigma\s*=\s*p0\.sigma/)).toBeTruthy();
    // The unconstrained easy case must NOT appear in the showcase.
    expect(queryByText("EZ-001")).toBeNull();
  });

  it("discloses tie-unsupported backends derived from data (jax absent from tied .m)", () => {
    const report = reportWith(
      [{ id: "TI-001", name: "2×gaussian shared σ", category: "tied", fixedParams: {}, exprEdges: [{ targetNode: "p1", targetParam: "sigma", expression: "p0.sigma" }] }],
      [{ id: "TI-001", m: { spectrafit: {}, lmfit: {} } }],
      [{ id: "spectrafit", label: "spectrafit" }, { id: "lmfit", label: "lmfit" }, { id: "jax", label: "jax" }],
    );
    const { container } = render(constrainedFitBody(report, ctx) as React.ReactElement);
    // The disclosure text spans multiple text nodes (backend id + static copy);
    // assert on the element's combined textContent.
    const note = container.querySelector(".absent-note");
    expect(note?.textContent).toMatch(/jax\s+cannot express parameter ties/);
  });

  it("returns null when no fixed/tied cases exist", () => {
    const report = reportWith(
      [{ id: "EZ-001", name: "single gaussian", category: "easy", fixedParams: {}, exprEdges: [] }],
      [{ id: "EZ-001", m: {} }],
      [{ id: "spectrafit", label: "spectrafit" }],
    );
    expect(constrainedFitBody(report, ctx)).toBeNull();
  });
});
