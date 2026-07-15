/**
 * Task 5.7 render-level tests: inferential-headline panels (W10 + W11).
 *
 * RED-FIRST: these tests fail until the panel body is implemented.
 * W10/W11 drift guard tests live in proseContractDrift.test.ts.
 */
import { describe, it, expect } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { components } from "../openapi.gen";

type CalibrationResult = components["schemas"]["CalibrationResult"];
type SpeedInferenceResult = components["schemas"]["SpeedInferenceResult"];

// ---------------------------------------------------------------------------
// Series tests — inferentialHeadline.ts
// ---------------------------------------------------------------------------

const CAL_PASS: CalibrationResult = {
  n: 120,
  coverage: 0.692,
  coverageCiLo: 0.608,
  coverageCiHi: 0.769,
  nominal: 0.6827,
  binomialP: 0.14,
  ksStat: 0.048,
  ksP: 0.52,
  alpha: 0.025,
  passed: true,
  skipped: false,
};

const CAL_FAIL: CalibrationResult = {
  n: 60,
  coverage: 0.55,
  coverageCiLo: 0.42,
  coverageCiHi: 0.68,
  nominal: 0.6827,
  binomialP: 0.005,
  ksStat: 0.12,
  ksP: 0.08,
  alpha: 0.025,
  passed: false,
  skipped: false,
};

const SPEED_PASS: SpeedInferenceResult = {
  geomeanSpeedup: 3.8,
  ciLo: 2.1,
  ciHi: 5.9,
  excludesOne: true,
  signP: 0.002,
  wilcoxonP: 0.003,
  alpha: 0.025,
  passed: true,
  skipped: false,
};

const SPEED_FAIL: SpeedInferenceResult = {
  geomeanSpeedup: 1.05,
  ciLo: 0.9,
  ciHi: 1.25,
  excludesOne: false,
  signP: 0.6,
  wilcoxonP: 0.55,
  alpha: 0.025,
  passed: false,
  skipped: false,
};

// ---------------------------------------------------------------------------
// Skipped fixtures: skipped=true, passed=false (engine emits these when
// insufficient data — < minPulls for W10, < 2 speedups for W11). These must
// render as "not exercised", NOT as a fail badge. (I1 regression guard)
// ---------------------------------------------------------------------------

const CAL_SKIPPED: CalibrationResult = {
  n: 5,
  coverage: 0.0,
  coverageCiLo: 0.0,
  coverageCiHi: 0.0,
  nominal: 0.6827,
  binomialP: 1.0,
  ksStat: 0.0,
  ksP: 1.0,
  alpha: 0.025,
  passed: false,
  skipped: true,
};

const SPEED_SKIPPED: SpeedInferenceResult = {
  geomeanSpeedup: 0.0,
  ciLo: 0.0,
  ciHi: 0.0,
  excludesOne: false,
  signP: 1.0,
  wilcoxonP: 1.0,
  alpha: 0.025,
  passed: false,
  skipped: true,
};

describe("inferentialHeadline series — calibrationRows", () => {
  it("returns a verdict row with pass=true when calibration passes", async () => {
    const { calibrationRows } = await import("../series/inferentialHeadline");
    const rows = calibrationRows(CAL_PASS);
    expect(rows).not.toBeNull();
    expect(rows!.some((r) => r.label.match(/coverage|binomial/i))).toBe(true);
    expect(rows!.some((r) => r.pass === true)).toBe(true);
  });

  it("returns rows with fail=false when calibration fails", async () => {
    const { calibrationRows } = await import("../series/inferentialHeadline");
    const rows = calibrationRows(CAL_FAIL);
    expect(rows).not.toBeNull();
    expect(rows!.some((r) => r.pass === false)).toBe(true);
  });

  it("returns null for null input", async () => {
    const { calibrationRows } = await import("../series/inferentialHeadline");
    expect(calibrationRows(null)).toBeNull();
  });
});

describe("inferentialHeadline series — speedRows", () => {
  it("returns verdict rows including the geomean speedup and CI", async () => {
    const { speedRows } = await import("../series/inferentialHeadline");
    const rows = speedRows(SPEED_PASS);
    expect(rows).not.toBeNull();
    expect(rows!.some((r) => r.label.match(/geomean|speedup/i))).toBe(true);
    expect(rows!.some((r) => r.label.match(/CI|ci|interval/i))).toBe(true);
  });

  it("returns a pass row for passed speed inference", async () => {
    const { speedRows } = await import("../series/inferentialHeadline");
    const rows = speedRows(SPEED_PASS);
    expect(rows!.some((r) => r.pass === true)).toBe(true);
  });

  it("returns a fail row for failing speed inference", async () => {
    const { speedRows } = await import("../series/inferentialHeadline");
    const rows = speedRows(SPEED_FAIL);
    expect(rows!.some((r) => r.pass === false)).toBe(true);
  });

  it("returns null for null input", async () => {
    const { speedRows } = await import("../series/inferentialHeadline");
    expect(speedRows(null)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Panel render tests — inferentialHeadline.tsx
// ---------------------------------------------------------------------------

function makeReportWithInference() {
  return {
    inference: {
      config: {
        equivalenceMargin: 0.01,
        bootstrapB: 5000,
        seed: 42,
        fdrQ: 0.05,
        alphaCalibration: 0.025,
        alphaSpeed: 0.025,
        coverageNominal: 0.6827,
        minPulls: 20,
      },
      cases: [],
      equivalence: [],
      winnerStability: {},
      calibration: CAL_PASS,
      speedInference: SPEED_PASS,
    },
  } as unknown as import("../contract").BenchReport;
}

function makeReportWithoutInference() {
  return {
    inference: {
      config: {
        equivalenceMargin: 0.01,
        bootstrapB: 5000,
        seed: 42,
        fdrQ: 0.05,
        alphaCalibration: 0.025,
        alphaSpeed: 0.025,
        coverageNominal: 0.6827,
        minPulls: 20,
      },
      cases: [],
      equivalence: [],
      winnerStability: {},
      calibration: null,
      speedInference: null,
    },
  } as unknown as import("../contract").BenchReport;
}

function makeReportNoInferenceBlock() {
  return {
    inference: undefined,
  } as unknown as import("../contract").BenchReport;
}

describe("inferentialHeadlineBody render — W10 calibration present (pass)", () => {
  it("renders the coverage point estimate", async () => {
    const { calibrationBody } = await import("../panels/bodies/inferentialHeadline");
    const report = makeReportWithInference();
    const node = calibrationBody(report);
    const html = renderToStaticMarkup(node as React.ReactElement);
    // Should show coverage value (69.2%)
    expect(html).toMatch(/69\.2|0\.692/);
  });

  it("renders the binomial p-value (primary verdict)", async () => {
    const { calibrationBody } = await import("../panels/bodies/inferentialHeadline");
    const report = makeReportWithInference();
    const node = calibrationBody(report);
    const html = renderToStaticMarkup(node as React.ReactElement);
    expect(html).toMatch(/binomial|W10/i);
    expect(html).toMatch(/0\.14|0\.1400/);
  });

  it("renders the KS secondary diagnostic", async () => {
    const { calibrationBody } = await import("../panels/bodies/inferentialHeadline");
    const report = makeReportWithInference();
    const node = calibrationBody(report);
    const html = renderToStaticMarkup(node as React.ReactElement);
    expect(html).toMatch(/KS|ks/i);
  });

  it("does not crash and is non-empty", async () => {
    const { calibrationBody } = await import("../panels/bodies/inferentialHeadline");
    const report = makeReportWithInference();
    const node = calibrationBody(report);
    const html = renderToStaticMarkup(node as React.ReactElement);
    expect(html.length).toBeGreaterThan(50);
  });
});

describe("inferentialHeadlineBody render — W10 calibration absent → qualified note", () => {
  it("renders the honest 'implemented (W10) but not exercised' note", async () => {
    const { calibrationBody } = await import("../panels/bodies/inferentialHeadline");
    const report = makeReportWithoutInference();
    const node = calibrationBody(report);
    const html = renderToStaticMarkup(node as React.ReactElement);
    expect(html).toMatch(/implemented.*W10|W10.*implemented/i);
    expect(html).toMatch(/not exercised/i);
  });

  it("does not crash when calibration is null", async () => {
    const { calibrationBody } = await import("../panels/bodies/inferentialHeadline");
    const report = makeReportWithoutInference();
    expect(() => {
      const node = calibrationBody(report);
      renderToStaticMarkup(node as React.ReactElement);
    }).not.toThrow();
  });

  it("absent state does not render a pass/fail verdict badge", async () => {
    const { calibrationBody } = await import("../panels/bodies/inferentialHeadline");
    const report = makeReportWithoutInference();
    const node = calibrationBody(report);
    const html = renderToStaticMarkup(node as React.ReactElement);
    // Should not show the specific coverage value
    expect(html).not.toMatch(/69\.2|0\.692/);
  });

  it("handles missing inference block gracefully", async () => {
    const { calibrationBody } = await import("../panels/bodies/inferentialHeadline");
    const report = makeReportNoInferenceBlock();
    expect(() => {
      const node = calibrationBody(report);
      renderToStaticMarkup(node as React.ReactElement);
    }).not.toThrow();
  });
});

describe("inferentialHeadlineBody render — W11 speed inference present (pass)", () => {
  it("renders the geomean speedup value", async () => {
    const { speedBody } = await import("../panels/bodies/inferentialHeadline");
    const report = makeReportWithInference();
    const node = speedBody(report);
    const html = renderToStaticMarkup(node as React.ReactElement);
    expect(html).toMatch(/3\.8|3\.80/);
  });

  it("renders CI bounds", async () => {
    const { speedBody } = await import("../panels/bodies/inferentialHeadline");
    const report = makeReportWithInference();
    const node = speedBody(report);
    const html = renderToStaticMarkup(node as React.ReactElement);
    // ciLo=2.1 or ciHi=5.9 should appear
    expect(html).toMatch(/2\.1|5\.9/);
  });

  it("renders sign-test or Wilcoxon p-value (secondary diagnostic)", async () => {
    const { speedBody } = await import("../panels/bodies/inferentialHeadline");
    const report = makeReportWithInference();
    const node = speedBody(report);
    const html = renderToStaticMarkup(node as React.ReactElement);
    expect(html).toMatch(/sign|wilcoxon|W11/i);
  });

  it("does not crash and is non-empty", async () => {
    const { speedBody } = await import("../panels/bodies/inferentialHeadline");
    const report = makeReportWithInference();
    const node = speedBody(report);
    const html = renderToStaticMarkup(node as React.ReactElement);
    expect(html.length).toBeGreaterThan(50);
  });
});

describe("inferentialHeadlineBody render — W11 speed inference absent → qualified note", () => {
  it("renders the honest 'implemented (W11) but not exercised' note", async () => {
    const { speedBody } = await import("../panels/bodies/inferentialHeadline");
    const report = makeReportWithoutInference();
    const node = speedBody(report);
    const html = renderToStaticMarkup(node as React.ReactElement);
    expect(html).toMatch(/implemented.*W11|W11.*implemented/i);
    expect(html).toMatch(/not exercised/i);
  });

  it("does not crash when speedInference is null", async () => {
    const { speedBody } = await import("../panels/bodies/inferentialHeadline");
    const report = makeReportWithoutInference();
    expect(() => {
      const node = speedBody(report);
      renderToStaticMarkup(node as React.ReactElement);
    }).not.toThrow();
  });

  it("absent state does not render the 3.8× geomean value", async () => {
    const { speedBody } = await import("../panels/bodies/inferentialHeadline");
    const report = makeReportWithoutInference();
    const node = speedBody(report);
    const html = renderToStaticMarkup(node as React.ReactElement);
    expect(html).not.toMatch(/3\.8/);
  });

  it("handles missing inference block gracefully", async () => {
    const { speedBody } = await import("../panels/bodies/inferentialHeadline");
    const report = makeReportNoInferenceBlock();
    expect(() => {
      const node = speedBody(report);
      renderToStaticMarkup(node as React.ReactElement);
    }).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// I1 regression guard: skipped=true, passed=false must render as "not exercised",
// NOT as a fail badge. The engine emits populated records (non-null) with
// skipped=true when data is insufficient — the web must not render them as fails.
// ---------------------------------------------------------------------------

function makeReportWithSkippedInference() {
  return {
    inference: {
      config: {
        equivalenceMargin: 0.01,
        bootstrapB: 5000,
        seed: 42,
        fdrQ: 0.05,
        alphaCalibration: 0.025,
        alphaSpeed: 0.025,
        coverageNominal: 0.6827,
        minPulls: 20,
      },
      cases: [],
      equivalence: [],
      winnerStability: {},
      calibration: CAL_SKIPPED,
      speedInference: SPEED_SKIPPED,
    },
  } as unknown as import("../contract").BenchReport;
}

describe("inferentialHeadline series — calibrationRows skipped", () => {
  it("returns null for a skipped record (skipped=true, passed=false)", async () => {
    const { calibrationRows } = await import("../series/inferentialHeadline");
    expect(calibrationRows(CAL_SKIPPED)).toBeNull();
  });
});

describe("inferentialHeadline series — speedRows skipped", () => {
  it("returns null for a skipped record (skipped=true, passed=false)", async () => {
    const { speedRows } = await import("../series/inferentialHeadline");
    expect(speedRows(SPEED_SKIPPED)).toBeNull();
  });
});

describe("inferentialHeadlineBody render — W10 calibration SKIPPED → 'not exercised' (I1)", () => {
  it("renders the 'not exercised' note for a skipped calibration record", async () => {
    const { calibrationBody } = await import("../panels/bodies/inferentialHeadline");
    const report = makeReportWithSkippedInference();
    const node = calibrationBody(report);
    const html = renderToStaticMarkup(node as React.ReactElement);
    expect(html).toMatch(/not exercised/i);
  });

  it("does NOT render a fail badge (✗) for a skipped calibration record", async () => {
    const { calibrationBody } = await import("../panels/bodies/inferentialHeadline");
    const report = makeReportWithSkippedInference();
    const node = calibrationBody(report);
    const html = renderToStaticMarkup(node as React.ReactElement);
    // The fail badge renders ✗ — skipped must not show this
    expect(html).not.toMatch(/✗/);
  });

  it("does NOT render the zero coverage value (0.0%) for a skipped record", async () => {
    const { calibrationBody } = await import("../panels/bodies/inferentialHeadline");
    const report = makeReportWithSkippedInference();
    const node = calibrationBody(report);
    const html = renderToStaticMarkup(node as React.ReactElement);
    // coverage=0.0 would appear as '0.0%' if rendered as a verdict row
    expect(html).not.toMatch(/binomial p/i);
  });
});

describe("inferentialHeadlineBody render — W11 speed inference SKIPPED → 'not exercised' (I1)", () => {
  it("renders the 'not exercised' note for a skipped speed inference record", async () => {
    const { speedBody } = await import("../panels/bodies/inferentialHeadline");
    const report = makeReportWithSkippedInference();
    const node = speedBody(report);
    const html = renderToStaticMarkup(node as React.ReactElement);
    expect(html).toMatch(/not exercised/i);
  });

  it("does NOT render a fail badge (✗) for a skipped speed inference record", async () => {
    const { speedBody } = await import("../panels/bodies/inferentialHeadline");
    const report = makeReportWithSkippedInference();
    const node = speedBody(report);
    const html = renderToStaticMarkup(node as React.ReactElement);
    expect(html).not.toMatch(/✗/);
  });

  it("does NOT render the geomean=0.0× verdict row for a skipped record", async () => {
    const { speedBody } = await import("../panels/bodies/inferentialHeadline");
    const report = makeReportWithSkippedInference();
    const node = speedBody(report);
    const html = renderToStaticMarkup(node as React.ReactElement);
    // geomean=0.00× would appear in a verdict row if skipped was mishandled
    expect(html).not.toMatch(/geomean speedup.*primary/i);
  });
});
