/**
 * TDD: ProvenanceFooter — pinned-baseline label (G20) + sanitize disclosure (G5).
 *
 * Cases:
 *   1. The pinned runId is labeled "pinned baseline:" so it cannot be read as
 *      the rendered run's id (it is a different run — the masthead dates THIS run).
 *   2. manifest.sanitizedValuePaths non-empty → a suppression count line renders,
 *      with the paths in the title attribute.
 *   3. manifest.sanitizedValuePaths empty/absent → no suppression line (gated-on-present).
 *   4. No pinned runId → renders nothing (no placeholder).
 */
import { render, cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import React from "react";
import { ProvenanceFooter } from "../ProvenanceFooter";
import type { BenchReport } from "../../contract";

function reportWith(manifest: unknown): BenchReport {
  return { schemaVersion: "1.7", manifest } as unknown as BenchReport;
}

afterEach(cleanup);

describe("ProvenanceFooter", () => {
  it("labels the pinned run as 'pinned baseline' (G20)", () => {
    render(
      <ProvenanceFooter
        report={reportWith({ pinned: { runId: "2026-06-08_run_012" } })}
      />,
    );
    expect(screen.getByText(/pinned baseline: 2026-06-08_run_012/)).toBeTruthy();
  });

  it("renders the G5 suppression disclosure when sanitizedValuePaths is non-empty", () => {
    render(
      <ProvenanceFooter
        report={reportWith({
          pinned: { runId: "2026-06-08_run_012" },
          sanitizedValuePaths: ["$.suite[3].m.jax.r2", "$.analyzed[0].conv[7]"],
        })}
      />,
    );
    const line = screen.getByText(/2 non-finite values suppressed \(0\.0\)/);
    expect(line).toBeTruthy();
    expect(line.getAttribute("title")).toContain("$.suite[3].m.jax.r2");
  });

  it("uses the singular form for one suppressed value", () => {
    render(
      <ProvenanceFooter
        report={reportWith({
          pinned: { runId: "2026-06-08_run_012" },
          sanitizedValuePaths: ["$.suite[3].m.jax.r2"],
        })}
      />,
    );
    expect(screen.getByText(/1 non-finite value suppressed \(0\.0\)/)).toBeTruthy();
  });

  it("renders no suppression line when nothing was suppressed", () => {
    render(
      <ProvenanceFooter
        report={reportWith({
          pinned: { runId: "2026-06-08_run_012" },
          sanitizedValuePaths: [],
        })}
      />,
    );
    expect(screen.queryByText(/suppressed/)).toBeNull();
  });

  it("renders nothing without a pinned runId (no placeholder)", () => {
    const { container } = render(<ProvenanceFooter report={reportWith(null)} />);
    expect(container.innerHTML).toBe("");
  });
});
