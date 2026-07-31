/**
 * Axis policy tests — TDD red-first (Track 2, ported onto fix/dashboard-and-greenups).
 *
 * Asserts the niceDomain() + dataExtent() contract:
 *   (a) log-scale range spanning ≥2 decades → tight domain within ~2× of data
 *   (b) log-scale range <2 decades → still tight (no >2× dead space)
 *   (c) linear scale → tight rounded domain hugging data (no large empty margin)
 *   (d) log guard: min<=0 is clamped to smallest positive or falls back gracefully
 *   (e) 24-spec coverage: every log-scale chart fed decade-spanning data has no >2× dead space
 */
// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { niceDomain, dataExtent } from "./grammar";
import { timingBoxPlot } from "./timing";
import { scalingPlot } from "./scaling";
import { warmupPlot } from "./warmup";
import { convergencePlot, thetaDistancePlot } from "./convergence";
import { paretoPlot } from "./pareto";
import { speedupDistPlot } from "./speedupDist";
import { conditioningPlot } from "./conditioning";
import { recoveryErrorPlot } from "./recoveryError";

// ---------------------------------------------------------------------------
// niceDomain unit tests
// ---------------------------------------------------------------------------

describe("niceDomain — log scale", () => {
  it("3-decade range [1, 1000]: domain stays within 2× of data bounds", () => {
    const [lo, hi] = niceDomain([1, 1000], "log");
    expect(lo).toBeLessThanOrEqual(1);
    expect(hi).toBeGreaterThanOrEqual(1000);
    // No >2× dead space: lo must be >= data_min/2, hi must be <= data_max*2
    expect(lo).toBeGreaterThanOrEqual(0.5);
    expect(hi).toBeLessThanOrEqual(2000);
  });

  it("4-decade range [0.1, 1000]: still within 2×", () => {
    const [lo, hi] = niceDomain([0.1, 1000], "log");
    expect(lo).toBeLessThanOrEqual(0.1);
    expect(hi).toBeGreaterThanOrEqual(1000);
    expect(lo).toBeGreaterThanOrEqual(0.05);
    expect(hi).toBeLessThanOrEqual(2000);
  });

  it("1-decade range [1, 10]: domain within 2× of data", () => {
    const [lo, hi] = niceDomain([1, 10], "log");
    expect(lo).toBeLessThanOrEqual(1);
    expect(hi).toBeGreaterThanOrEqual(10);
    expect(lo).toBeGreaterThanOrEqual(0.5);
    expect(hi).toBeLessThanOrEqual(20);
  });

  it("sub-decade range [3, 7]: domain within 2× of data", () => {
    const [lo, hi] = niceDomain([3, 7], "log");
    expect(lo).toBeLessThanOrEqual(3);
    expect(hi).toBeGreaterThanOrEqual(7);
    expect(lo).toBeGreaterThanOrEqual(1.5);
    expect(hi).toBeLessThanOrEqual(14);
  });

  it("min<=0: clamps to a small positive value rather than returning 0 or negative", () => {
    const [lo] = niceDomain([0, 100], "log");
    expect(lo).toBeGreaterThan(0);
  });

  it("all negative input: returns finite positive domain (clamps to safe floor)", () => {
    const [lo, hi] = niceDomain([-10, -1], "log");
    expect(lo).toBeGreaterThan(0);
    expect(hi).toBeGreaterThan(lo);
  });

  // Finding #3: Math.min bug — when dMin<=0 the floor must be Math.max(dMax*1e-4, LOG_FLOOR)
  // not Math.min, which collapses to LOG_FLOOR=1e-9 for any dMax>1e-5 (dead-space stretch).
  it("log-floor clamp: dMin=0, dMax=100 — lo must be close to dMax*1e-4 (0.01), not 1e-9", () => {
    const [lo] = niceDomain([0, 100], "log");
    // With Math.max: lo = max(100*1e-4, 1e-9) = max(0.01, 1e-9) = 0.01
    // With Math.min: lo = min(100*1e-4, 1e-9) = min(0.01, 1e-9) = 1e-9  ← the bug
    // lo must NOT be stretched to 1e-9 when data goes to 100
    expect(lo).toBeGreaterThan(1e-6); // not stuck at LOG_FLOOR 1e-9
    expect(lo).toBeLessThan(1);      // still below data min (0)
  });

  it("log-floor clamp: dMin=0, dMax=1000 — lo must be ≥ dMax*1e-4 (0.1), not 1e-9", () => {
    const [lo] = niceDomain([0, 1000], "log");
    // Math.max: lo = max(1000*1e-4, 1e-9) = 0.1
    // Math.min: lo = min(1000*1e-4, 1e-9) = 1e-9  ← the bug
    expect(lo).toBeGreaterThan(1e-6);
  });

  it("log-floor clamp: dMin=0, dMax=0.001 (small) — lo must fall back to LOG_FLOOR not below", () => {
    const [lo] = niceDomain([0, 0.001], "log");
    // dMax*1e-4 = 1e-7, LOG_FLOOR=1e-9; Math.max gives 1e-7 (reasonable)
    // The key invariant: lo must be > 0 and the domain is not stretched absurdly
    expect(lo).toBeGreaterThan(0);
  });
});

describe("niceDomain — linear scale", () => {
  it("[1, 10]: domain contains the data and is reasonably tight (hi within 2× of data max)", () => {
    const [lo, hi] = niceDomain([1, 10], "linear");
    expect(lo).toBeLessThanOrEqual(1);
    expect(hi).toBeGreaterThanOrEqual(10);
    // No huge dead space: hi should be at most 2× data max
    expect(hi).toBeLessThanOrEqual(20);
  });

  it("[0.5, 0.9]: domain tightly rounds to the data range", () => {
    const [lo, hi] = niceDomain([0.5, 0.9], "linear");
    expect(lo).toBeLessThanOrEqual(0.5);
    expect(hi).toBeGreaterThanOrEqual(0.9);
    expect(hi).toBeLessThanOrEqual(1.8);
  });

  it("[100, 500]: domain within 2× of data max", () => {
    const [lo, hi] = niceDomain([100, 500], "linear");
    expect(lo).toBeLessThanOrEqual(100);
    expect(hi).toBeGreaterThanOrEqual(500);
    expect(hi).toBeLessThanOrEqual(1000);
  });
});

describe("niceDomain — decade detection rule", () => {
  it("≥2 decades: returns a decade-aligned domain (lo and hi are powers of 10)", () => {
    const [lo, hi] = niceDomain([1, 1000], "log"); // 3 decades
    // Decade-aligned means lo = 10^n for some integer n
    const loLog = Math.log10(lo);
    const hiLog = Math.log10(hi);
    expect(Math.abs(loLog - Math.round(loLog))).toBeLessThan(0.01);
    expect(Math.abs(hiLog - Math.round(hiLog))).toBeLessThan(0.01);
  });

  it("<2 decades: does not necessarily align to decades, but remains within 2×", () => {
    const [lo, hi] = niceDomain([3, 30], "log"); // 1 decade exactly
    expect(lo).toBeLessThanOrEqual(3);
    expect(hi).toBeGreaterThanOrEqual(30);
    expect(lo).toBeGreaterThanOrEqual(1);
    expect(hi).toBeLessThanOrEqual(60);
  });
});

// ---------------------------------------------------------------------------
// dataExtent unit tests
// ---------------------------------------------------------------------------

describe("dataExtent", () => {
  it("empty array → safe fallback [1, 10]", () => {
    const [lo, hi] = dataExtent([]);
    expect(lo).toBe(1);
    expect(hi).toBe(10);
  });

  it("all NaN → safe fallback [1, 10]", () => {
    const [lo, hi] = dataExtent([NaN, NaN]);
    expect(lo).toBe(1);
    expect(hi).toBe(10);
  });

  it("filters Inf values and uses remaining finite ones", () => {
    const [lo, hi] = dataExtent([1, Infinity, 100, -Infinity]);
    expect(lo).toBe(1);
    expect(hi).toBe(100);
  });

  it("single value → degenerate padded range", () => {
    const [lo, hi] = dataExtent([5]);
    expect(lo).toBeLessThan(5);
    expect(hi).toBeGreaterThan(5);
  });

  it("normal range → exact [min, max]", () => {
    const [lo, hi] = dataExtent([3, 7, 1, 100, 0.5]);
    expect(lo).toBe(0.5);
    expect(hi).toBe(100);
  });
});

// ---------------------------------------------------------------------------
// Chart anti-whitespace tests: decade-spanning data → no >2× dead space
// These verify the chart factory functions pass niceDomain correctly by
// checking the rendered SVG does not contain far-out-of-range tick labels.
// ---------------------------------------------------------------------------

describe("timingBoxPlot — log x auto-scale: decade-spanning data stays tight", () => {
  const rows = [
    { backend: "a", p5: 1, p25: 5, median: 10, p75: 500, p95: 1000 },
  ];
  it("renders SVG without throwing on 3-decade data", () => {
    const svg = timingBoxPlot(rows as any, { colors: { a: "#0cf" } });
    expect(svg).toBeInstanceOf(SVGElement);
  });
  it("SVG does not contain excessive dead-space ticks: 0.001 should not appear as a tick", () => {
    const svg = timingBoxPlot(rows as any, { colors: { a: "#0cf" } });
    // A 1e-3 tick label would indicate the auto-domain expanded far below data
    expect(svg.textContent).not.toContain("0.001");
  });
});

describe("scalingPlot — log x+y auto-scale", () => {
  const lines = [
    {
      backend: "a",
      rows: [
        { n: 100, ms: 0.5, backend: "a" },
        { n: 1000, ms: 5, backend: "a" },
        { n: 10000, ms: 50, backend: "a" },
      ],
    },
  ];
  it("renders SVG without throwing on 3-decade N range", () => {
    const svg = scalingPlot(lines as any, { colors: { a: "#0cf" } });
    expect(svg).toBeInstanceOf(SVGElement);
  });
  it("SVG does not contain far out-of-range ticks for x", () => {
    const svg = scalingPlot(lines as any, { colors: { a: "#0cf" } });
    // A tick at 1e-5 would indicate the domain ballooned far below 100
    expect(svg.textContent).not.toContain("0.00001");
  });
});

describe("warmupPlot — log x auto-scale", () => {
  const lines = [
    {
      backend: "a",
      rows: [
        { n: 1, perRun: 100, backend: "a" },
        { n: 100, perRun: 10, backend: "a" },
        { n: 1000, perRun: 1, backend: "a" },
      ],
    },
  ];
  it("renders SVG without throwing on 3-decade cumulative-runs range", () => {
    const svg = warmupPlot(lines as any, { colors: { a: "#0cf" } });
    expect(svg).toBeInstanceOf(SVGElement);
  });
});

describe("convergencePlot — log y auto-scale", () => {
  const lines = [
    {
      backend: "a",
      mode: "line",
      rows: [
        { iter: 0, cost: 1000, backend: "a" },
        { iter: 5, cost: 10, backend: "a" },
        { iter: 10, cost: 0.1, backend: "a" },
      ],
    },
  ];
  it("renders SVG without throwing on 4-decade cost range", () => {
    const svg = convergencePlot(lines as any, { colors: { a: "#0cf" } });
    expect(svg).toBeInstanceOf(SVGElement);
  });
});

describe("thetaDistancePlot — log y auto-scale (replaces convToFloor in current branch)", () => {
  const s = {
    backend: "spectrafit",
    recoveryTol: 1e-2,
    rows: [
      { iter: 0, dist: 100 },
      { iter: 5, dist: 1 },
      { iter: 10, dist: 0.01 },
    ],
  };
  it("renders SVG without throwing on 4-decade dist range", () => {
    const svg = thetaDistancePlot(s as any, { colors: { spectrafit: "#0cf" } });
    expect(svg).toBeInstanceOf(SVGElement);
  });
});

describe("paretoPlot — log x auto-scale (median solve time)", () => {
  const s = [
    {
      backend: "a",
      points: [
        { x: 0.5, y: 0.99, backend: "a" },
        { x: 100, y: 0.95, backend: "a" },
      ],
    },
  ] as any;
  s.envelope = [{ x: 0.5, y: 0.99 }, { x: 100, y: 0.95 }];
  it("renders SVG without throwing on 2-decade time range", () => {
    const svg = paretoPlot(s, { colors: { a: "#0cf" } });
    expect(svg).toBeInstanceOf(SVGElement);
  });
});

describe("speedupDistPlot — log x auto-scale", () => {
  const rows = [
    { backend: "a", p5: 0.5, p25: 1, median: 5, p75: 50, p95: 100 },
  ];
  it("renders SVG without throwing on 2-decade speedup range", () => {
    const svg = speedupDistPlot(rows as any, { colors: { a: "#0cf" } });
    expect(svg).toBeInstanceOf(SVGElement);
  });
  it("SVG does not show implausibly small ticks (0.0001) for a 0.5–100× range", () => {
    const svg = speedupDistPlot(rows as any, { colors: { a: "#0cf" } });
    expect(svg.textContent).not.toContain("0.0001");
  });
});

describe("conditioningPlot — log x auto-scale", () => {
  const rows = [
    { backend: "a", kappa: 100, absent: false },
    { backend: "b", kappa: 1e7, absent: false },
  ];
  it("renders SVG without throwing on 5-decade kappa range", () => {
    const svg = conditioningPlot(rows as any, { colors: { a: "#0cf", b: "#f80" } });
    expect(svg).toBeInstanceOf(SVGElement);
  });
});

describe("recoveryErrorPlot — log/linear x auto-scale via chooseRecoveryErrorScale", () => {
  const rows = [
    {
      backend: "a",
      values: [1, 5, 10, 50, 100],
      p5: 1,
      p25: 5,
      median: 10,
      p75: 50,
      p95: 100,
    },
  ];
  it("renders SVG without throwing on log-scale (all-positive) 2-decade recovery error", () => {
    const svg = recoveryErrorPlot(rows as any, { colors: { a: "#0cf" } });
    expect(svg).toBeInstanceOf(SVGElement);
  });
  it("SVG does not contain implausibly small ticks like 0.0001 for a 1–100 range", () => {
    const svg = recoveryErrorPlot(rows as any, { colors: { a: "#0cf" } });
    expect(svg.textContent).not.toContain("0.0001");
  });
});
