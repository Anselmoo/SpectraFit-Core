/**
 * Task 4.6 render-level tests: nested-model adequacy panel body.
 *
 * RED-FIRST: these tests fail until the panel body is implemented.
 * W9 drift guard tests live in proseContractDrift.test.ts.
 */
import { describe, it, expect } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { NestedAdequacy } from "../series/nestedAdequacy";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const NESTED_ADEQUACY_FIXTURE: NestedAdequacy = {
  trueOrder: 3,
  reducedRejected: true,
  overNotPreferredAic: false,
  overNotPreferredBic: true,
  selectedOrderAic: 4,
  selectedOrderBic: 3,
  recoveredTrueOrderAic: false,
  recoveredTrueOrderBic: true,
  reducedVsTrue: { lrtStat: 18.5, lrtP: 0.0002, fStat: 16.2, fP: 0.0003, dAIC: -14.5, dBIC: -12.1 },
  trueVsOver:   { lrtStat:  3.1, lrtP:  0.079,  fStat:  2.8, fP: 0.098,  dAIC:  1.2,  dBIC:  3.8 },
};

function makeReportWithNestedAdequacy() {
  // nestedAdequacy lives on Featured (analyzed[] elements)
  return {
    analyzed: [
      {
        id: "tri-gaussian",
        category: "reality",
        nestedAdequacy: NESTED_ADEQUACY_FIXTURE,
      },
    ],
  } as unknown as import("../contract").BenchReport;
}

function makeReportWithoutNestedAdequacy() {
  return {
    analyzed: [
      {
        id: "easy-001",
        category: "easy",
        nestedAdequacy: null,
      },
    ],
  } as unknown as import("../contract").BenchReport;
}

// ---------------------------------------------------------------------------
// Render test: populated nestedAdequacy
// ---------------------------------------------------------------------------

describe("nestedAdequacyBody render — populated fixture (W9, BIC recovers, AIC over-selects)", () => {
  it("renders BIC recovery verdict with true order", async () => {
    const { nestedAdequacyBody } = await import("../panels/bodies/nestedAdequacy");
    const report = makeReportWithNestedAdequacy();
    const node = nestedAdequacyBody(report);
    const html = renderToStaticMarkup(node as React.ReactElement);
    expect(html).toContain("BIC");
    expect(html).toMatch(/3/);
    expect(html).toMatch(/recov/i);
  });

  it("renders the AIC nuance (over-selects order 4 in this fixture)", async () => {
    const { nestedAdequacyBody } = await import("../panels/bodies/nestedAdequacy");
    const report = makeReportWithNestedAdequacy();
    const node = nestedAdequacyBody(report);
    const html = renderToStaticMarkup(node as React.ReactElement);
    expect(html).toContain("AIC");
    expect(html).toMatch(/4/);
  });

  it("renders LRT / p-value evidence (reduced rejected)", async () => {
    const { nestedAdequacyBody } = await import("../panels/bodies/nestedAdequacy");
    const report = makeReportWithNestedAdequacy();
    const node = nestedAdequacyBody(report);
    const html = renderToStaticMarkup(node as React.ReactElement);
    expect(html).toMatch(/LRT|lrt|p\s*[=<]/i);
  });

  it("renders ΔAIC and ΔBIC values", async () => {
    const { nestedAdequacyBody } = await import("../panels/bodies/nestedAdequacy");
    const report = makeReportWithNestedAdequacy();
    const node = nestedAdequacyBody(report);
    const html = renderToStaticMarkup(node as React.ReactElement);
    expect(html).toMatch(/AIC|BIC/);
    // ΔAIC = -14.5 or ΔBIC = -12.1 should appear
    expect(html).toMatch(/-14|-12|1\.2|3\.8/);
  });

  it("does not crash or render a blank when nestedAdequacy is present", async () => {
    const { nestedAdequacyBody } = await import("../panels/bodies/nestedAdequacy");
    const report = makeReportWithNestedAdequacy();
    const node = nestedAdequacyBody(report);
    const html = renderToStaticMarkup(node as React.ReactElement);
    expect(html.length).toBeGreaterThan(50);
  });
});

// ---------------------------------------------------------------------------
// Render test: absent nestedAdequacy → "not exercised" note, no crash
// ---------------------------------------------------------------------------

describe("nestedAdequacyBody render — absent fixture (nestedAdequacy is null)", () => {
  it("renders 'not exercised' / 'W9' note when nestedAdequacy is null", async () => {
    const { nestedAdequacyBody } = await import("../panels/bodies/nestedAdequacy");
    const report = makeReportWithoutNestedAdequacy();
    const node = nestedAdequacyBody(report);
    const html = renderToStaticMarkup(node as React.ReactElement);
    expect(html).toMatch(/not exercised|W9.*not|not.*W9|oracle.*not run|not.*this report/i);
  });

  it("does not crash when nestedAdequacy is null", async () => {
    const { nestedAdequacyBody } = await import("../panels/bodies/nestedAdequacy");
    const report = makeReportWithoutNestedAdequacy();
    expect(() => {
      const node = nestedAdequacyBody(report);
      renderToStaticMarkup(node as React.ReactElement);
    }).not.toThrow();
  });

  it("absent state does not contain 'BIC recovers'", async () => {
    const { nestedAdequacyBody } = await import("../panels/bodies/nestedAdequacy");
    const report = makeReportWithoutNestedAdequacy();
    const node = nestedAdequacyBody(report);
    const html = renderToStaticMarkup(node as React.ReactElement);
    expect(html).not.toMatch(/BIC recovers/i);
  });
});
