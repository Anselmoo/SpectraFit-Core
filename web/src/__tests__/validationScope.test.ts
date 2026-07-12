/**
 * C1.1 · I-SCOPE-HONEST — the Standing credibility card must NOT lead with a bare
 * rung self-score. It must disclose the validation SCOPE: what was tested AND the
 * load-bearing "what we did NOT test" gaps — no reduced/nested-model adequacy V&V,
 * no inferential hypothesis test behind the headline, a narrow NIST subset. The
 * numeric rung is demoted to a qualified subscript (a verification-completeness
 * score, not a trust guarantee), never the hero.
 *
 * This pins the user's concern: "examples with shrinked models is not yet tested
 * and also no hypothesis test, therefore the standing card is useless." A rung-5
 * report must still surface those gaps in the rendered card.
 */
import { describe, it, expect } from "vitest";
import type React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { BenchReport } from "../contract";

function makeRung5Report(): BenchReport {
  return {
    trustBlock: {
      rung: 5,
      n_claims_audited: 15,
      n_claims_total: 16,
      wires: [
        { wire_id: "W1", name: "Residual sanity", status: "pass", evidence: "residuals finite" },
        { wire_id: "W2c", name: "Jacobian conditioning", status: "gap", evidence: "κ(J) not exposed by lmfit/jax" },
        { wire_id: "W8", name: "NIST StRD external validation", status: "pass", evidence: "certified values reproduced" },
      ],
      nist_validation: {
        threshold_sig_figs: 4,
        total_available: 27,
        datasets: [
          { name: "Gauss1", model: "Three-term Gaussian", n_params: 8, params: [], min_sig_figs: 6, passed: true },
          { name: "BoxBOD", model: "Saturating exponential", n_params: 2, params: [], min_sig_figs: 5, passed: true },
        ],
        min_sig_figs: 5,
        passed: true,
      },
    },
  } as unknown as BenchReport;
}

describe("C1.1 validation-scope card (I-SCOPE-HONEST)", () => {
  it("discloses the load-bearing 'not tested' gaps for a rung-5 report", async () => {
    const { renderTruthCard } = await import("../panels/bodies/standing");
    const node = renderTruthCard(makeRung5Report());
    const html = renderToStaticMarkup(node as React.ReactElement).toLowerCase();

    // The honest "what we did NOT test" section must exist…
    expect(html).toContain("not tested");
    // …naming the two gaps the user flagged:
    expect(html).toMatch(/reduced|nested-model/); // "shrinked models"
    expect(html).toContain("hypothesis test"); // no inferential test behind the headline
    // …and the narrow NIST subset (derived from the data: N of 27).
    expect(html).toContain("of 27");

    // The rung must be contextualised, not presented as a bare trust guarantee.
    expect(html).toMatch(/not a (trust )?guarantee|verification-completeness|checklist/);
  });

  it("returns null when trustBlock is absent", async () => {
    const { renderTruthCard } = await import("../panels/bodies/standing");
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(renderTruthCard({} as any)).toBeNull();
  });
});
