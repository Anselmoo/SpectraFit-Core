/**
 * Evidence — overview (all-cases) ↔ case (single-case drill-down).
 *
 * Thin destination over the panel registry. This component keeps the e2e-critical
 * DOM verbatim from the old inline EvidencePanel: the overview/case sub-view state,
 * the `#case=` hash effect, the ev-rail section nav, the `<section id=…>` grouping
 * with `<h3 className="ev-section">` headings, the suite-table row → openCase wiring
 * (via ctx.openCase), and the /All cases/ back button. The panels themselves are
 * rendered from the registry through renderPanels(), grouped by section.
 *
 * Structure: `useEvidenceRouting` (co-located hook) owns the sub-view state, the
 * `#case=` hash-routing effects, and the Escape-key effect. The two sub-view JSX
 * trees live in `EvidenceOverview` and `EvidenceCaseView` — this component is just
 * the routing glue + ctx assembly between them.
 */
import type { ReactElement } from "react";
import type { BenchReport } from "../contract";
import { solversOf } from "../contract";
import type { PanelCtx } from "../panels/types";
import { useEvidenceRouting } from "./useEvidenceRouting";
import { EvidenceOverview } from "./EvidenceOverview";
import { EvidenceCaseView } from "./EvidenceCaseView";

export function EvidencePanel({ report }: { report: BenchReport }): ReactElement {
  const { selectedId, view, openCase, backToOverview } = useEvidenceRouting(report);

  // Derive helpers — subject-blind
  const solverIds = solversOf(report);
  const colors = Object.fromEntries(report.solvers.map((s) => [s.id, s.color]));

  const ctx: PanelCtx = {
    selectedId,
    view,
    solverIds,
    colors,
    openCase,
  };

  return (
    <div className="stagger" style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
      {view === "overview" ? (
        <EvidenceOverview report={report} ctx={ctx} />
      ) : (
        <EvidenceCaseView
          report={report}
          ctx={ctx}
          selectedId={selectedId}
          openCase={openCase}
          onBack={backToOverview}
        />
      )}
    </div>
  );
}
