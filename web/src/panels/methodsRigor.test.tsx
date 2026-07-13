/**
 * Methods rigor cards — the "we don't cherry-pick" story + reproduce affordance.
 *
 * The audit destination was removed (Unit 5). These body functions remain
 * importable from bodies/methods; they're tested directly here.
 */
import { render, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import type { ReactElement } from "react";
import { cherryPickCard, reproduceCard } from "./bodies/methods";
import type { BenchReport } from "../contract";
import React from "react";

afterEach(cleanup);

const report = {
  schemaVersion: 1.5,
  baselineSolverId: "lmfit",
  solvers: [
    { id: "spectrafit", color: "#1" },
    { id: "lmfit", color: "#2" },
  ],
  suite: new Array(139).fill(null).map((_, i) => ({ id: `C-${i}` })),
  manifest: {
    pinned: {
      runId: "2026-06-08_run_018",
      recordedAt: "2026-06-08T16:48:54+00:00",
      geomeanSpeedupVsBaseline: 12.363531944725663,
      nCases: 139,
    },
  },
  inference: {
    config: { equivalenceMargin: 0.001, bootstrapB: 2000, seed: 20260612, fdrQ: 0.05 },
    equivalence: [
      { category: "easy", diff: 1e-9, equivalent: true, margin: 0.001 },
      { category: "edge", diff: 2e-9, equivalent: true, margin: 0.001 },
    ],
  },
  trustBlock: { n_claims_audited: 15, n_claims_total: 21, rung: 5, wires: [] },
} as unknown as BenchReport;

describe("Methods rigor — we don't cherry-pick (body function direct import)", () => {
  test("composes the resampling / interval / disclosed-gaps figures from the contract", () => {
    const node = cherryPickCard(report);
    const { container } = render(node as ReactElement);
    const text = container.textContent ?? "";
    // Resampling: bootstrap B from inference.config (localized — "2,000").
    expect(text).toMatch(/2,?000/);
    // Disclosed gaps: claims audited from trustBlock.
    expect(text).toMatch(/15\D+21/);
    // Intervals: the equivalence margin (FDR-controlled).
    expect(text).toMatch(/0\.001/);
    // Subject-blind: does not crown spectrafit.
    expect(text.toLowerCase()).not.toContain("spectrafit");
  });
});

describe("Methods rigor — reproduce affordance (body function direct import)", () => {
  test("shows the spc-bench command and the pinned run provenance", () => {
    const node = reproduceCard(report);
    const { container } = render(node as ReactElement);
    const text = container.textContent ?? "";
    expect(text).toContain("spc-bench");
    // Pinned provenance — all data-derived.
    expect(text).toContain("2026-06-08_run_018");
    expect(text).toContain("139");
    expect(text).toContain("lmfit"); // baseline solver id
  });
});
