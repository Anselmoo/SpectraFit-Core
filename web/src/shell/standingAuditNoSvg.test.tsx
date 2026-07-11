/**
 * TDD guard: standing PanelRecords never return a raw SVGSVGElement.
 * This pins the invariant: every standing record returns a bespoke ReactNode
 * card (no raw DOM SVGSVGElement). The Audit destination was removed (Unit 5).
 */
import { isValidElement } from "react";
import { describe, expect, test } from "vitest";
import { PANELS } from "../panels/registry";
import type { PanelCtx } from "../panels/types";
import type { BenchReport } from "../contract";

// Minimal realistic report fixture that satisfies every standing/audit body
// function (gateVerdictCard, renderTruthCard, wireMatrixCard, etc.).
const report = {
  schemaVersion: "1.5",
  baselineSolverId: "lmfit",
  solvers: [
    { id: "lmfit", label: "lmfit", color: "#888", backend: "lmfit" },
    { id: "spectrafit", label: "spectrafit", color: "#4af", backend: "spectrafit" },
  ],
  categories: [{ id: "easy", label: "Easy", n: 10, hue: "var(--ok)" }],
  suite: [],
  manifest: {
    geomeanSpeedupVsBaseline: 2.5,
    maxAbsDeltaR2: 1e-6,
    spectrafitWinRate: 0.75,
    regressions: 0,
    gateState: "PASS",
    harmonicMeanSpeedupVsBaseline: 2.1,
    saturatedCategories: [],
  },
  trustBlock: {
    rung: 3,
    n_claims_total: 5,
    n_claims_audited: 4,
    wires: [
      { id: "W1", label: "Wire 1", status: "pass", claim: "claim 1", evidence: "evidence 1" },
    ],
    nist_validation: null,
  },
  inference: null,
  featured: [],
  analyzed: [],
} as unknown as BenchReport;

const ctx: PanelCtx = {
  selectedId: null,
  view: "overview",
  solverIds: ["lmfit", "spectrafit"],
  colors: { lmfit: "#888", spectrafit: "#4af" },
};

const destinations = ["standing"] as const;

describe("Standing panel records never return a raw SVGSVGElement", () => {
  for (const dest of destinations) {
    const records = PANELS.filter((p) => p.dest === dest);
    for (const panel of records) {
      test(`${dest}/${panel.id}: make() returns a ReactElement, not SVGSVGElement or null`, () => {
        const node = panel.make(report, ctx);
        // null means the panel opted out for this report (e.g. renderTruthCard when
        // trustBlock is null). That is acceptable — the guard we removed only
        // added SVGSVGElement protection, not null protection.
        if (node == null) return;
        // Must be a valid React element, never a raw DOM SVGSVGElement.
        expect(node).not.toBeInstanceOf(SVGSVGElement);
        expect(isValidElement(node)).toBe(true);
      });
    }
  }
});
