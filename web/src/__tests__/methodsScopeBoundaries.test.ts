/**
 * C1.2 · Methods honest block (2): "what we did NOT test".
 *
 * The Methods (audit) destination must carry the scope boundaries in detail — not
 * just the positive rigor story. scopeBoundariesCard enumerates the untested axes:
 * no reduced/nested-model adequacy V&V, no inferential hypothesis test behind the
 * rung, the narrow NIST subset, and the κ(J) oracle gap. Gated on trustBlock.
 */
import { describe, it, expect } from "vitest";
import type React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { BenchReport } from "../contract";

function makeReport(): BenchReport {
  return {
    trustBlock: {
      rung: 5,
      n_claims_audited: 15,
      n_claims_total: 16,
      wires: [
        { wire_id: "W2c", name: "Jacobian conditioning", status: "gap", evidence: "κ(J) not exposed by lmfit/jax" },
        { wire_id: "W5", name: "Render fidelity", status: "skipped", evidence: "CI only" },
        { wire_id: "W8", name: "NIST StRD", status: "pass", evidence: "certified values reproduced" },
      ],
      nist_validation: {
        threshold_sig_figs: 4,
        total_available: 27,
        datasets: [
          { name: "Gauss1", model: "Three-term Gaussian", n_params: 8, params: [], min_sig_figs: 6, passed: true },
        ],
        min_sig_figs: 6,
        passed: true,
      },
    },
  } as unknown as BenchReport;
}

describe("C1.2 scopeBoundariesCard (Methods 'not tested' block)", () => {
  it("enumerates the untested axes for a report with a trustBlock", async () => {
    const { scopeBoundariesCard } = await import("../panels/bodies/methods");
    const node = scopeBoundariesCard(makeReport());
    const html = renderToStaticMarkup(node as React.ReactElement).toLowerCase();

    /* R5: heading trimmed to "Scope & boundaries" (Kare — redundant subtitle removed);
       the honest "not tested" intent lives in the intro para ("unmeasured and disclosed")
       and in the list items ("not exercised") — test the body phrase, not the heading. */
    expect(html).toMatch(/unmeasured|not exercised|did not test/);
    expect(html).toMatch(/reduced|nested-model/);
    expect(html).toContain("hypothesis test");
    expect(html).toContain("of 27");
  });

  it("returns null when trustBlock is absent", async () => {
    const { scopeBoundariesCard } = await import("../panels/bodies/methods");
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(scopeBoundariesCard({} as any)).toBeNull();
  });
});
