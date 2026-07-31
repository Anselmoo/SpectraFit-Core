/**
 * EvidenceOverview — the "across all cases" sub-view of the Evidence
 * destination. Extracted verbatim from EvidencePanel (no DOM/style change):
 * the headline, the sticky section rail, and the section-grouped panel
 * bodies (finding / compare / constrained / showcase).
 */
import { Fragment } from "react";
import type { ReactElement } from "react";
import type { BenchReport } from "../contract";
import type { PanelCtx } from "../panels/types";
import { renderPanels } from "./renderPanels";
import { EvidenceVerdict } from "./EvidenceVerdict";

export function EvidenceOverview({
  report,
  ctx,
}: {
  report: BenchReport;
  ctx: PanelCtx;
}): ReactElement {
  // Tog: only surface the constrained-fit section when the run actually carries
  // fixed/tied cases — no silent empty shell (a heading with no body).
  const hasConstrained = (report.analyzed ?? []).some(
    (c) => c.category === "fixed" || c.category === "tied",
  );

  return (
    <Fragment key="ev-overview">
      <h2
        style={{
          margin: 0,
          fontFamily: "var(--font-display)",
          fontWeight: 300,
          fontSize: "1.1rem",
          color: "var(--text-primary)",
          letterSpacing: "-0.01em",
        }}
      >
        Across all {report.suite.length} cases
      </h2>

      {/* The headline finding — a published report leads with the result. */}
      <EvidenceVerdict report={report} />

      {/* Dye+Tog: sticky section rail — overview sections */}
      <nav className="ev-rail" aria-label="Overview sections">
        <a href="#sec-finding">The finding</a>
        <a href="#sec-compare">Across all cases</a>
        {hasConstrained && <a href="#sec-constrained">Constrained fitting</a>}
        <a href="#sec-showcase">Native showcases</a>
      </nav>

      {/* Dye+Jobs: section — "The finding" → Saturation map */}
      <section id="sec-finding">
        <h3 className="ev-section">The finding</h3>
        {renderPanels("evidence", report, ctx, "sec-finding")}
      </section>

      {/* Dye+Jobs: section — "Across all cases" → suite table + CI charts + winner stability */}
      <section id="sec-compare">
        <h3 className="ev-section">Across all cases</h3>
        {renderPanels("evidence", report, ctx, "sec-compare")}
      </section>

      {/* Constrained-fit showcase (FX/TI) — gated-on-data: the whole section
          (heading included) is hidden when the run carries no fixed/tied
          cases, so there is never an empty heading (Tog). */}
      {hasConstrained && (
      <section id="sec-constrained">
        <h3 className="ev-section">Constrained fitting</h3>
        {renderPanels("evidence", report, ctx, "sec-constrained")}
      </section>
      )}

      {/* Native-kernel showcases (G18: SP-2 N-D fit + SP-3 global fit).
          NOT data-gated: the bodies render an honest "not recorded in this
          run" note when the served run predates the showcase, so the
          section is never an empty shell — and the capability is never
          silently invisible (the failure mode that kept SP-2/SP-3 cut). */}
      <section id="sec-showcase">
        <h3 className="ev-section">Native showcases</h3>
        {renderPanels("evidence", report, ctx, "sec-showcase")}
      </section>
    </Fragment>
  );
}
