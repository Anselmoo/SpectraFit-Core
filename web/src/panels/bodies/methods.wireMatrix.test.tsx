/**
 * Wave B2 — wireMatrixCard verification-tree + orientation tests.
 *
 * Covers:
 *   - Dye: wires grouped under [data-claim-group] containers matching CLAIM_GROUPS
 *   - Tog: [data-audit-orientation] orientation line is rendered
 *   - W5 honest CI disclosure: skipped wire shows "CI" not a bare dash
 */
import { render, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import type { ReactElement } from "react";
import type { BenchReport } from "../../contract";
import { wireMatrixCard } from "./methods";

afterEach(cleanup);

function makeReport(wires: object[] = []): BenchReport {
  return {
    trustBlock: {
      rung: 5,
      nClaimsAudited: 10,
      nClaimsTotal: 16,
      wires,
      nistValidation: null,
    },
  } as unknown as BenchReport;
}

const SAMPLE_WIRES = [
  { wireId: "W1", name: "Synth invariants", status: "pass", evidence: "all pass" },
  { wireId: "W2a", name: "Metric formulas", status: "pass", evidence: "r² recomputed" },
  { wireId: "W2c", name: "κ(J) conditioning", status: "gap", evidence: "lmfit does not expose κ(J)" },
  { wireId: "W3", name: "Contract roundtrip", status: "pass", evidence: "JSON roundtrip clean" },
  { wireId: "W5", name: "Render fidelity", status: "skipped", evidence: "Playwright JSON-vs-render (CI only)" },
  { wireId: "W6", name: "Gate values", status: "pass", evidence: "geomean speedup ≥ 1×" },
  { wireId: "W8", name: "NIST StRD", status: "pass", evidence: "certified values reproduced" },
];

describe("wireMatrixCard — Wave B2 tree structure (Dye)", () => {
  test("renders [data-claim-group] containers when wires are present", () => {
    const node = wireMatrixCard(makeReport(SAMPLE_WIRES));
    const { container } = render(node as ReactElement);
    const groups = container.querySelectorAll("[data-claim-group]");
    expect(groups.length).toBeGreaterThanOrEqual(2);
  });

  test("W1 and W2a appear in the Accuracy group", () => {
    const node = wireMatrixCard(makeReport(SAMPLE_WIRES));
    const { container } = render(node as ReactElement);
    const accuracyGroup = Array.from(container.querySelectorAll("[data-claim-group]")).find((el) =>
      el.getAttribute("data-claim-group")?.toLowerCase().includes("accuracy"),
    );
    expect(accuracyGroup).toBeTruthy();
    expect(accuracyGroup?.textContent).toContain("W1");
    expect(accuracyGroup?.textContent).toContain("W2a");
  });

  test("W8 appears in the External validation group", () => {
    const node = wireMatrixCard(makeReport(SAMPLE_WIRES));
    const { container } = render(node as ReactElement);
    const externalGroup = Array.from(container.querySelectorAll("[data-claim-group]")).find((el) =>
      el.getAttribute("data-claim-group")?.toLowerCase().includes("external"),
    );
    expect(externalGroup).toBeTruthy();
    expect(externalGroup?.textContent).toContain("W8");
  });

  test("W5 appears in the Render fidelity group", () => {
    const node = wireMatrixCard(makeReport(SAMPLE_WIRES));
    const { container } = render(node as ReactElement);
    const renderGroup = Array.from(container.querySelectorAll("[data-claim-group]")).find((el) =>
      el.getAttribute("data-claim-group")?.toLowerCase().includes("render"),
    );
    expect(renderGroup).toBeTruthy();
    expect(renderGroup?.textContent).toContain("W5");
  });
});

describe("wireMatrixCard — Tog orientation header", () => {
  test("renders [data-audit-orientation] with a link to Standing", () => {
    const node = wireMatrixCard(makeReport(SAMPLE_WIRES));
    const { container } = render(node as ReactElement);
    const orient = container.querySelector("[data-audit-orientation]");
    expect(orient).toBeTruthy();
    expect(orient?.textContent?.toLowerCase()).toMatch(/standing|verdict/);
  });

  test("orientation is also rendered when trustBlock is null", () => {
    const report = { trustBlock: null } as unknown as BenchReport;
    const node = wireMatrixCard(report);
    const { container } = render(node as ReactElement);
    const orient = container.querySelector("[data-audit-orientation]");
    expect(orient).toBeTruthy();
  });
});

describe("wireMatrixCard — W5 honest CI disclosure", () => {
  test("skipped W5 wire shows CI-related text (not just a bare dash)", () => {
    const node = wireMatrixCard(makeReport(SAMPLE_WIRES));
    const { container } = render(node as ReactElement);
    // Find the wire-row for W5
    const w5Row = Array.from(container.querySelectorAll(".wire-row")).find(
      (el) => el.textContent?.includes("W5"),
    );
    expect(w5Row).toBeTruthy();
    const evidenceSpan = w5Row?.querySelector(".wire-evidence");
    // Must contain CI disclosure, not a bare dash sentinel
    expect(evidenceSpan?.textContent?.toLowerCase()).toMatch(/ci|verified/);
  });

  test("skipped W5 dot has aria-label 'verified in CI' (not bare 'skipped')", () => {
    const node = wireMatrixCard(makeReport(SAMPLE_WIRES));
    const { container } = render(node as ReactElement);
    const w5Row = Array.from(container.querySelectorAll(".wire-row")).find(
      (el) => el.textContent?.includes("W5"),
    );
    const dot = w5Row?.querySelector(".wire-dot");
    const ariaLabel = dot?.getAttribute("aria-label") ?? "";
    expect(ariaLabel.toLowerCase()).toMatch(/verified|ci/);
  });
});

describe("wireMatrixCard — null trustBlock", () => {
  test("returns a card (not null) when trustBlock is absent", () => {
    const report = { trustBlock: null } as unknown as BenchReport;
    const node = wireMatrixCard(report);
    expect(node).not.toBeNull();
    const { container } = render(node as ReactElement);
    expect(container.textContent?.toLowerCase()).toMatch(/no verification wires/);
  });
});
