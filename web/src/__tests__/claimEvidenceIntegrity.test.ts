/**
 * L3 render-level claim-evidence integrity (I5).
 *
 * I5: a rung-5 report MUST NOT show the "No NIST validation data" empty fallback
 * in the nist-validation panel.  A populated trustBlock.nist_validation must
 * produce at least one dataset name in the rendered output.
 *
 * Also includes a lightweight source-scan assertion that the NIST claim's
 * evidence root (`trustBlock.nist_validation`) is referenced in registry.tsx —
 * mirroring the noHardcodedBackend pattern but for the claim-path contract.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

// ---------------------------------------------------------------------------
// Fixture helpers
// ---------------------------------------------------------------------------

function makeRung5Report() {
  // Minimal BenchReport-shaped object with a rung-5 trustBlock + nist_validation.
  // Only fields consumed by nistValidationBody need to be present.
  return {
    trustBlock: {
      rung: 5,
      nist_validation: {
        threshold_sig_figs: 4.0,
        datasets: [
          {
            name: "Gauss1",
            model: "Three-term Gaussian",
            n_params: 8,
            params: [
              { name: "b1", certified: 98.0, fitted: 98.01, sig_figs_agreed: 6.0 },
            ],
            min_sig_figs: 6.0,
            passed: true,
          },
        ],
        min_sig_figs: 6.0,
        passed: true,
      },
    },
  } as unknown as import("../contract").BenchReport;
}

function makeReportWithNoNist() {
  return {
    trustBlock: {
      rung: 4,
      nist_validation: null,
    },
  } as unknown as import("../contract").BenchReport;
}

// ---------------------------------------------------------------------------
// I5: populated rung-5 trustBlock must not show the empty fallback
// ---------------------------------------------------------------------------

describe("L3 render-level claim-evidence integrity (I5)", () => {
  it("rung-5 report with nist_validation renders dataset name, not the empty fallback", async () => {
    // Dynamically import after happy-dom is set up
    const { nistValidationBody } = await import("../panels/registry");

    const report = makeRung5Report();
    const node = nistValidationBody(report);

    // Render to static markup for string inspection
    const html = renderToStaticMarkup(node as React.ReactElement);

    expect(html).not.toContain("No NIST validation data in this report.");
    expect(html).toContain("Gauss1");
  });

  it("report without nist_validation renders the empty fallback (guard for the negative case)", async () => {
    const { nistValidationBody } = await import("../panels/registry");

    const report = makeReportWithNoNist();
    const node = nistValidationBody(report);

    const html = renderToStaticMarkup(node as React.ReactElement);
    expect(html).toContain("No NIST validation data in this report.");
    expect(html).not.toContain("Gauss1");
  });
});

// ---------------------------------------------------------------------------
// Source-scan: trustBlock.nist_validation (snake_case) must appear in the panel
// RENDER code — registry.tsx AND the bodies/ modules. The bodies were split out
// of registry.tsx (the 1891→359 refactor), moving nistValidationBody's real
// access (`report.trustBlock?.nist_validation`) into bodies/methods.tsx; scanning
// registry.tsx alone matched only a comment, making this guard vacuous and unable
// to catch a wrong `trustBlock.nistValidation` access in a body.
// ---------------------------------------------------------------------------

const PANEL_DIR = join(import.meta.dirname, "..", "panels");
const PANEL_SOURCE = [
  join(PANEL_DIR, "registry.tsx"),
  join(PANEL_DIR, "bodies", "standing.tsx"),
  join(PANEL_DIR, "bodies", "methods.tsx"),
  join(PANEL_DIR, "bodies", "evidenceOverview.tsx"),
  join(PANEL_DIR, "bodies", "evidenceCase.tsx"),
  join(PANEL_DIR, "bodies", "shared.tsx"),
]
  .map((p) => readFileSync(p, "utf-8"))
  .join("\n");

describe("L3 source-scan: claim evidence path referenced in the panel render code", () => {
  it("the panels access trustBlock.nist_validation (snake_case, not nistValidation)", () => {
    // The NIST claim source_field root — must be present as a real ACCESS, not just
    // a comment. nistValidationBody reads `report.trustBlock?.nist_validation`.
    expect(PANEL_SOURCE).toMatch(/trustBlock\??\.\s*nist_validation/);
    // The old (wrong) camelCase must NOT be the access key anywhere in the panels.
    expect(PANEL_SOURCE).not.toMatch(/trustBlock\??\.\s*nistValidation/);
  });
});
