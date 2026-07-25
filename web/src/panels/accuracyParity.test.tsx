/**
 * Accuracy-parity-by-category card (Cycle 5, T5.1) — the cross-case editorial:
 * where the subject matches the baseline's accuracy and where it doesn't, one
 * row per category, derived from inference.equivalence (the FDR-controlled,
 * full-run TOST), joined to category labels. Names the baseline, never crowns
 * the subject.
 */
import { render, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import type { ReactElement } from "react";
import { PANELS } from "./registry";
import type { PanelCtx } from "./types";
import type { BenchReport } from "../contract";

afterEach(cleanup);

const ctx: PanelCtx = { selectedId: null, view: "overview", solverIds: [], colors: {} };

const report = {
  baselineSolverId: "lmfit",
  categories: [
    { id: "easy", label: "Easy", n: 20, hue: "var(--ok)" },
    { id: "optfn", label: "Optimization fns", n: 20, hue: "var(--c-guess)" },
    { id: "edge", label: "Edge / ill-conditioned", n: 20, hue: "var(--bad)" },
  ],
  inference: {
    config: { equivalenceMargin: 0.001, bootstrapB: 2000, seed: 1, fdrQ: 0.05 },
    equivalence: [
      { category: "easy", equivalent: true, margin: 0.001, diff: 2.7e-16 },
      { category: "edge", equivalent: true, margin: 0.001, diff: 2.6e-7 },
      { category: "optfn", equivalent: false, margin: 0.001, diff: 0.0282955 },
    ],
  },
} as unknown as BenchReport;

function renderPanel(id: string): string {
  const rec = PANELS.find((p) => p.id === id);
  expect(rec, `panel "${id}" registered`).toBeTruthy();
  const node = rec!.make(report, ctx);
  const { container } = render(node as ReactElement);
  return container.textContent ?? "";
}

describe("Accuracy parity by category (T5.1)", () => {
  test("takeaway counts the equivalent categories and names the baseline", () => {
    const text = renderPanel("accuracy-parity");
    // 2 of 3 categories are equivalent.
    expect(text).toMatch(/2\D+3/);
    // names the baseline, not the subject.
    expect(text).toContain("lmfit");
    expect(text.toLowerCase()).not.toContain("spectrafit");
  });

  test("surfaces the one category that is NOT at parity, by label", () => {
    const text = renderPanel("accuracy-parity");
    // optfn is the exception → its human label appears with its diff (exponential).
    expect(text).toContain("Optimization fns");
    expect(text).toMatch(/2\.83e-2/);
  });

  // EF-PANELS-09 — optfn/global are out of the Δr² accuracy gate by design;
  // calling them an accuracy "exception" or saying the subject and baseline
  // "genuinely differ" conflates gate scope with accuracy regression.
  test("optfn non-equivalence is framed as out-of-gate-scope, not as accuracy exception", () => {
    const text = renderPanel("accuracy-parity");
    // The card must NOT say "genuinely differ" for optfn — that framing implies
    // a Δr² accuracy regression, but optfn is excluded from the accuracy gate.
    expect(text).not.toContain("genuinely differ");
    // The card must NOT use the word "exception" to describe optfn non-equivalence
    // in context of "the subject and baseline" differ.
    expect(text).not.toMatch(/exception.*Optimization fns|Optimization fns.*exception/i);
  });
});
