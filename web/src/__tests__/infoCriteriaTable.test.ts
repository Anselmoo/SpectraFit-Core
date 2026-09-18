/**
 * R2: infoCriteria renders a TABLE (intentional, not a missing chart).
 *
 * The `infoCriteriaBody` at `panels/bodies/evidenceCase.tsx:412` was observed
 * to produce `svgCount:0` on `#case=EZ-005`. This is EXPECTED: the panel is a
 * ΔAIC/ΔBIC/MAE comparison TABLE, not a chart. This test pins that design
 * decision so a future "blank SVG" alarm knows this panel is table-by-design
 * and does not need a chart fix.
 */
import { describe, it, expect } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { infoCriteriaBody } from "../panels/bodies/evidenceCase";
import type { BenchReport } from "../contract";

// ---------------------------------------------------------------------------
// Minimal report fixture with a case that carries dAIC/dBIC/mae per backend
// ---------------------------------------------------------------------------

function makeReportWithInfoCriteria(): BenchReport {
  // `infoCriteriaBody` calls `selectedCase` → `analyzedById` which reads
  // `r.analyzed`, not `r.suite`. The case object needs `profiles[id].summary.dAIC`.
  const caseObj = {
    id: "EZ-005",
    profiles: {
      spectrafit: {
        summary: { r2: 0.999, dAIC: 0, dBIC: 0, mae: 1.2e-3 },
      },
      lmfit: {
        summary: { r2: 0.998, dAIC: 4.1, dBIC: 3.8, mae: 2.5e-3 },
      },
    },
  };
  return {
    solvers: [
      { id: "spectrafit", label: "spectrafit" },
      { id: "lmfit", label: "lmfit" },
    ],
    analyzed: [caseObj],
    suite: [],
  } as unknown as BenchReport;
}

function makeCtx() {
  return {
    selectedId: "EZ-005",
    view: "case" as const,
    solverIds: ["spectrafit", "lmfit"],
    colors: { spectrafit: "#0cf", lmfit: "#f80" },
  };
}

// ---------------------------------------------------------------------------
// R2: table renders with ΔAIC/ΔBIC rows — NO SVG, by design
// ---------------------------------------------------------------------------

describe("infoCriteria panel (R2) — table-by-design, not a missing chart", () => {
  it("renders a <table> element (no SVG — intentional)", () => {
    const report = makeReportWithInfoCriteria();
    const node = infoCriteriaBody(report, makeCtx());
    const html = renderToStaticMarkup(node as React.ReactElement);

    // Must render a table
    expect(html).toContain("<table");
    // Must NOT contain an SVG (it is a table, never a chart)
    expect(html).not.toContain("<svg");
  });

  it("renders ΔAIC column header", () => {
    const report = makeReportWithInfoCriteria();
    const node = infoCriteriaBody(report, makeCtx());
    const html = renderToStaticMarkup(node as React.ReactElement);
    expect(html).toContain("ΔAIC");
  });

  it("renders ΔBIC column header", () => {
    const report = makeReportWithInfoCriteria();
    const node = infoCriteriaBody(report, makeCtx());
    const html = renderToStaticMarkup(node as React.ReactElement);
    expect(html).toContain("ΔBIC");
  });

  it("renders one <tr> per backend that reports dAIC", () => {
    const report = makeReportWithInfoCriteria();
    const node = infoCriteriaBody(report, makeCtx());
    const html = renderToStaticMarkup(node as React.ReactElement);
    // Two backends in fixture → two data rows (plus the header row)
    // Count <tr> occurrences: header + 2 data = 3
    const trCount = (html.match(/<tr/g) ?? []).length;
    expect(trCount).toBeGreaterThanOrEqual(3);
  });

  it("preferred backend is marked with ★ preferred", () => {
    const report = makeReportWithInfoCriteria();
    const node = infoCriteriaBody(report, makeCtx());
    const html = renderToStaticMarkup(node as React.ReactElement);
    // spectrafit has dAIC=0 (lowest) → preferred
    expect(html).toContain("preferred");
  });

  it("renders the empty-state message when no backend has dAIC", () => {
    const report = {
      solvers: [{ id: "spectrafit", label: "spectrafit" }],
      analyzed: [
        {
          id: "EZ-005",
          profiles: { spectrafit: { summary: { r2: 0.999 } } }, // no dAIC
        },
      ],
      suite: [],
    } as unknown as BenchReport;
    const node = infoCriteriaBody(report, makeCtx());
    const html = renderToStaticMarkup(node as React.ReactElement);
    expect(html).toContain("No information criteria");
    expect(html).not.toContain("<table");
  });
});
