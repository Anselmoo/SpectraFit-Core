/**
 * NIST StRD validation panel — vitest (A7 web half).
 *
 * Exercises `nistValidationBody` via direct import (the audit destination was
 * removed in Unit 5; the body function remains importable from bodies/methods
 * and is re-exported from the registry for claimEvidenceIntegrity.test.ts).
 */
import { render, cleanup, fireEvent } from "@testing-library/react";
import { afterEach, expect, test, describe } from "vitest";
import { nistValidationBody } from "./registry";
import type { BenchReport } from "../contract";
import React from "react";

afterEach(cleanup);

// ---------------------------------------------------------------------------
// Minimal stub BenchReport shapes for the NIST panel
// ---------------------------------------------------------------------------

function makeNistReport(nistValidation: unknown): BenchReport {
  return {
    trustBlock: {
      rung: 5,
      wires: [],
      nClaimsAudited: 8,
      nClaimsTotal: 9,
      nistValidation: nistValidation,
    },
    solvers: [],
    categories: [],
    suite: [],
    analyzed: [],
    manifest: null,
    panels: [],
    inference: null,
    baselineSolverId: "lmfit",
    schemaVersion: "0.1.0",
  } as unknown as BenchReport;
}

const SAMPLE_NIST: unknown = {
  thresholdSigFigs: 4.0,
  minSigFigs: 8.75,
  passed: true,
  datasets: [
    {
      name: "Gauss1",
      model: "b1·exp(-b2·x) + b3·exp(-(x-b4)²/b5²) + b6·exp(-(x-b7)²/b8²)",
      nParams: 8,
      minSigFigs: 10.58,
      passed: true,
      params: [
        { name: "b1", certified: 98.7782, fitted: 98.7782, sigFigsAgreed: 11.25 },
        { name: "b2", certified: 0.0104973, fitted: 0.0104973, sigFigsAgreed: 10.82 },
      ],
    },
    {
      name: "Lanczos1",
      model: "b1·exp(-b2·x) + b3·exp(-b4·x) + b5·exp(-b6·x)",
      nParams: 6,
      minSigFigs: 8.75,
      passed: true,
      params: [
        { name: "b1", certified: 0.0951, fitted: 0.0951, sigFigsAgreed: 8.75 },
      ],
    },
  ],
};

describe("nist-validation panel (body function — audit destination removed)", () => {
  test("is importable and callable directly (not through PANELS registry)", () => {
    expect(nistValidationBody).toBeDefined();
    expect(typeof nistValidationBody).toBe("function");
  });

  test("renders a visible heading", () => {
    const report = makeNistReport(SAMPLE_NIST);
    const node = nistValidationBody(report);
    const { container } = render(<>{node}</>);
    const h = container.querySelector("h2, h3");
    expect(h?.textContent ?? "").toMatch(/NIST/i);
  });

  test("renders dataset rows for each NistDataset (after expanding)", () => {
    const report = makeNistReport(SAMPLE_NIST);
    const node = nistValidationBody(report);
    const { container, getByText } = render(<>{node}</>);

    // Dataset table is behind progressive disclosure — click to expand.
    const expandBtn = container.querySelector("[data-nist-expand]") as HTMLButtonElement;
    expect(expandBtn).toBeTruthy();
    fireEvent.click(expandBtn);

    // Dataset names are rendered as row headers
    getByText("Gauss1");
    getByText("Lanczos1");

    // Per-param sub-rows via the ↳ prefix
    const paramLabels = container.querySelectorAll("td");
    const texts = Array.from(paramLabels).map((el) => el.textContent ?? "");
    expect(texts.some((t) => t.includes("b1"))).toBe(true);
    expect(texts.some((t) => t.includes("b2"))).toBe(true);
  });

  test("shows min sig figs for each dataset (after expanding)", () => {
    const report = makeNistReport(SAMPLE_NIST);
    const node = nistValidationBody(report);
    const { container, getAllByText } = render(<>{node}</>);

    const expandBtn = container.querySelector("[data-nist-expand]") as HTMLButtonElement;
    fireEvent.click(expandBtn);

    expect(getAllByText("10.58").length).toBeGreaterThanOrEqual(1);
    expect(getAllByText("8.75").length).toBeGreaterThanOrEqual(1);
  });

  test("shows aggregate threshold and overall min sig figs in summary line", () => {
    const report = makeNistReport(SAMPLE_NIST);
    const node = nistValidationBody(report);
    const { container } = render(<>{node}</>);

    const text = container.textContent ?? "";
    expect(text).toMatch(/threshold.*4.*sig figs/i);
    expect(text).toMatch(/worst case.*8\.75/i);
  });

  test("renders gracefully when nistValidation is null", () => {
    const report = makeNistReport(null);
    const node = nistValidationBody(report);
    const { container } = render(<>{node}</>);
    expect(container.textContent).toMatch(/no nist validation/i);
  });

  test("renders certified and fitted values in param sub-rows (after expanding)", () => {
    const report = makeNistReport(SAMPLE_NIST);
    const node = nistValidationBody(report);
    const { container } = render(<>{node}</>);

    const expandBtn = container.querySelector("[data-nist-expand]") as HTMLButtonElement;
    fireEvent.click(expandBtn);

    const text = container.textContent ?? "";
    expect(text).toMatch(/certified.*98\.7782/i);
    expect(text).toMatch(/fitted.*98\.7782/i);
  });

  test("expand button starts collapsed (aria-expanded=false) and toggles to true", () => {
    const report = makeNistReport(SAMPLE_NIST);
    const node = nistValidationBody(report);
    const { container } = render(<>{node}</>);

    const expandBtn = container.querySelector("[data-nist-expand]") as HTMLButtonElement;
    expect(expandBtn.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(expandBtn);
    expect(expandBtn.getAttribute("aria-expanded")).toBe("true");
  });
});
