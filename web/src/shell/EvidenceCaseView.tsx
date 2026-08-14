/**
 * EvidenceCaseView — the single-case drill-down sub-view of the Evidence
 * destination. Extracted verbatim from EvidencePanel (no DOM/style change):
 * the back button, the case selector, the per-case verdict/scenario headers,
 * the sticky section rail, and the section-grouped panel bodies
 * (fit / perf / repro).
 */
import { Fragment } from "react";
import type { ReactElement } from "react";
import type { BenchReport } from "../contract";
import { analyzedById } from "../contract";
import type { PanelCtx } from "../panels/types";
import { renderPanels } from "./renderPanels";
import { CaseVerdict } from "./CaseVerdict";
import { CaseScenario } from "./CaseScenario";

export function EvidenceCaseView({
  report,
  ctx,
  selectedId,
  openCase,
  onBack,
}: {
  report: BenchReport;
  ctx: PanelCtx;
  selectedId: string;
  openCase: (id: string) => void;
  onBack: () => void;
}): ReactElement {
  const f = analyzedById(report, selectedId);

  return (
    <Fragment key="ev-case">
      {/* Back button */}
      <button
        onClick={onBack}
        aria-label="Back to All cases overview"
        style={{
          background: "none",
          border: "none",
          color: "var(--system-blue)",
          cursor: "pointer",
          fontFamily: "var(--font-mono)",
          fontSize: "0.85rem",
          padding: 0,
          marginBottom: "var(--space-3)",
          alignSelf: "flex-start",
        }}
      >
        ← All cases
      </button>

      {/* Case selector */}
      {report.analyzed?.length ? (
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
          <label
            htmlFor="case-selector"
            style={{ fontSize: "0.8rem", color: "var(--text-secondary)", fontFamily: "var(--font-mono)" }}
          >
            case
          </label>
          <select
            id="case-selector"
            value={selectedId}
            onChange={(e) => openCase(e.target.value)}
            style={{
              background: "var(--surface-raised)",
              border: "1px solid var(--border-subtle)",
              borderRadius: 6,
              color: "var(--text-primary)",
              fontFamily: "var(--font-mono)",
              fontSize: "0.82rem",
              padding: "3px 8px",
            }}
          >
            {report.analyzed.map((fc) => (
              <option key={fc.id} value={fc.id}>
                {fc.id} · {fc.category}
              </option>
            ))}
          </select>
        </div>
      ) : null}

      {f != null && (
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
          {f.id} · {f.category}
        </h2>
      )}

      {/* Per-case verdict headline — subject-blind, data-derived. */}
      <CaseVerdict report={report} caseId={selectedId} />

      {/* Model → scenario → constraints header (narrative order, above plots). */}
      <CaseScenario report={report} caseId={selectedId} />

      {/* Dye+Tog: sticky section rail — case view has 3 sections */}
      <nav className="ev-rail" aria-label="Case sections">
        <a href="#sec-fit">The fit</a>
        <a href="#sec-perf">Per-backend performance</a>
        <a href="#sec-repro">Reproducibility &amp; conditioning</a>
      </nav>

      {/* Dye+Jobs: section — "The fit" → Fit, Peak contributions, Parameter recovery, Pull calibration */}
      <section id="sec-fit">
        <h3 className="ev-section">The fit</h3>
        {renderPanels("evidence", report, ctx, "sec-fit")}
      </section>

      {/* Dye+Jobs: section — "Per-backend performance" → Convergence, Timing, Warmup, Scaling */}
      {f != null && (
        <section id="sec-perf">
          <h3 className="ev-section">Per-backend performance</h3>
          {renderPanels("evidence", report, ctx, "sec-perf")}
        </section>
      )}

      {/* Dye+Jobs: section — "Reproducibility & conditioning" → Reproducibility, Conditioning */}
      {f != null && (
        <section id="sec-repro">
          <h3 className="ev-section">Reproducibility &amp; conditioning</h3>
          {renderPanels("evidence", report, ctx, "sec-repro")}
        </section>
      )}
    </Fragment>
  );
}
