import { render } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { CaseScenario } from "../CaseScenario";
import type { BenchReport } from "../../contract";

const base = {
  id: "FX-001", name: "single gaussian fixed/clean #1", category: "fixed",
  modelFormula: "A \\cdot x", noise: 0.02, Ngrid: [200], paramNames: ["p0.center"],
  peaks: [{ label: "p0", y: [] }],
  fixedParams: { p0: ["center"] }, exprEdges: [],
} as unknown;

function reportWith(an: unknown): BenchReport {
  return { analyzed: [an], suite: [] } as unknown as BenchReport;
}

describe("CaseScenario", () => {
  it("renders the formula as math and the fixed-param constraint", () => {
    const { container, getByText } = render(<CaseScenario report={reportWith(base)} caseId="FX-001" />);
    expect(container.querySelector(".katex")).not.toBeNull();
    expect(getByText(/center/i)).toBeTruthy();
  });
  it("renders an expr-edge tie when present", () => {
    const ti = { ...(base as Record<string, unknown>), id: "TI-001", fixedParams: {}, exprEdges: [{ targetNode: "p1", targetParam: "sigma", expression: "p0.sigma" }] };
    const { getByText } = render(<CaseScenario report={reportWith(ti)} caseId="TI-001" />);
    expect(getByText(/p1\.sigma\s*=\s*p0\.sigma/)).toBeTruthy();
  });
  it("returns null for an unknown case id", () => {
    const { container } = render(<CaseScenario report={reportWith(base)} caseId="ZZ-999" />);
    expect(container.firstChild).toBeNull();
  });
});
