/**
 * Pinned-baseline comparison card — renders pinned vs current geomean speedup
 * and their delta, gated on manifest.pinned != null.
 *
 * TDD: red tests written before implementation exists.
 */
import { render, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import type { ReactElement } from "react";
import { pinnedBaselineCard } from "./methods";
import type { BenchReport } from "../../contract";

afterEach(cleanup);

const reportWithPinned = {
  schemaVersion: 1.5,
  baselineSolverId: "lmfit",
  manifest: {
    geomeanSpeedupVsBaseline: 14.5,
    pinned: {
      runId: "2026-06-08_run_018",
      recordedAt: "2026-06-08T16:48:54+00:00",
      geomeanSpeedupVsBaseline: 12.36,
      nCases: 139,
    },
  },
} as unknown as BenchReport;

const reportNoPinned = {
  schemaVersion: 1.5,
  baselineSolverId: "lmfit",
  manifest: {
    geomeanSpeedupVsBaseline: 14.5,
    pinned: null,
  },
} as unknown as BenchReport;

const reportNullManifest = {
  schemaVersion: 1.5,
  baselineSolverId: "lmfit",
  manifest: null,
} as unknown as BenchReport;

describe("pinnedBaselineCard — gated-on-data", () => {
  test("returns null when manifest.pinned is null", () => {
    const result = pinnedBaselineCard(reportNoPinned);
    expect(result).toBeNull();
  });

  test("returns null when manifest is null", () => {
    const result = pinnedBaselineCard(reportNullManifest);
    expect(result).toBeNull();
  });
});

describe("pinnedBaselineCard — renders comparison", () => {
  test("renders the pinned run id", () => {
    const node = pinnedBaselineCard(reportWithPinned);
    const { container } = render(node as ReactElement);
    expect(container.textContent).toContain("2026-06-08_run_018");
  });

  test("renders pinned geomean speedup value", () => {
    const node = pinnedBaselineCard(reportWithPinned);
    const { container } = render(node as ReactElement);
    // 12.36 formatted via toFixed(2)
    expect(container.textContent).toContain("12.36");
  });

  test("renders current geomean speedup value", () => {
    const node = pinnedBaselineCard(reportWithPinned);
    const { container } = render(node as ReactElement);
    // 14.5 formatted via toFixed(2) → "14.50"
    expect(container.textContent).toMatch(/14\.5/);
  });

  test("renders the delta (current − pinned)", () => {
    // delta = 14.5 − 12.36 = 2.14
    const node = pinnedBaselineCard(reportWithPinned);
    const { container } = render(node as ReactElement);
    expect(container.textContent).toMatch(/2\.1[0-9]/);
  });

  test("is subject-blind — does not hardcode a backend name", () => {
    const node = pinnedBaselineCard(reportWithPinned);
    const { container } = render(node as ReactElement);
    // Subject-blind: no hardcoded "spectrafit" or "lmfit" in the card body
    expect(container.textContent?.toLowerCase()).not.toContain("spectrafit");
  });

  test("renders an up/down/flat indicator for positive delta", () => {
    // delta > 0 → up indicator (▲ or ↑ or "+")
    const node = pinnedBaselineCard(reportWithPinned);
    const { container } = render(node as ReactElement);
    // Some directional token must be present
    const text = container.textContent ?? "";
    const hasDirection = text.includes("▲") || text.includes("↑") || text.includes("+");
    expect(hasDirection).toBe(true);
  });
});
