/**
 * Evidence — overview (all-cases) ↔ case (single-case drill-down).
 *
 * Thin destination over the panel registry. This component keeps the e2e-critical
 * DOM verbatim from the old inline EvidencePanel: the overview/case sub-view state,
 * the `#case=` hash effect, the ev-rail section nav, the `<section id=…>` grouping
 * with `<h3 className="ev-section">` headings, the suite-table row → openCase wiring
 * (via ctx.openCase), and the /All cases/ back button. The panels themselves are
 * rendered from the registry through renderPanels(), grouped by section.
 */
import { Fragment, useEffect, useState } from "react";
import type { ReactElement } from "react";
import type { BenchReport } from "../contract";
import { solversOf, analyzedById, defaultCaseId } from "../contract";
import type { PanelCtx } from "../panels/types";
import { renderPanels } from "./renderPanels";
import { EvidenceVerdict } from "./EvidenceVerdict";
import { CaseVerdict } from "./CaseVerdict";
import { CaseScenario } from "./CaseScenario";

export function EvidencePanel({ report }: { report: BenchReport }): ReactElement {
  // Case selector state — default to the most discriminating case (largest r²
  // spread across backends), not the saturated analyzed[0].
  const [selectedId, setSelectedId] = useState<string>(() => defaultCaseId(report));

  // Sub-view state: "overview" (all-cases) vs "case" (single-case drill-down)
  const initialHashCase = (() => {
    const m = /^#case=(.+)$/.exec(window.location.hash);
    return m ? decodeURIComponent(m[1]) : null;
  })();
  // Only open case view on mount when the permalink id resolves to a real
  // analyzed case; an unresolved #case=<missing-id> must start on overview, not
  // a half-rendered dead page (UX-01).
  const [view, setView] = useState<"overview" | "case">(
    initialHashCase && analyzedById(report, initialHashCase) ? "case" : "overview",
  );
  useEffect(() => {
    if (initialHashCase && analyzedById(report, initialHashCase)) {
      setSelectedId(initialHashCase);
      setView("case");
    }
    const onHash = () => {
      const m = /^#case=(.+)$/.exec(window.location.hash);
      if (m) {
        const id = decodeURIComponent(m[1]);
        // Guard parity with the mount effect above: only enter case view when
        // the id resolves to a real analyzed case. A stale / shared
        // #case=<missing-id> permalink otherwise lands on a self-contradictory
        // dead page (controlled-select value with no matching option, "No
        // analyzed cases" body while the selector is full). Fall back to
        // overview instead.
        if (analyzedById(report, id)) {
          setSelectedId(id);
          setView("case");
        } else {
          setView("overview");
        }
      } else if (window.location.hash === "#evidence" || window.location.hash === "") {
        setView("overview");
      }
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const openCase = (id: string) => {
    setSelectedId(id);
    setView("case");
    window.location.hash = `#case=${encodeURIComponent(id)}`;
  };
  const backToOverview = () => {
    setView("overview");
    window.location.hash = "#evidence";
  };

  // Escape key returns to overview when in case view
  useEffect(() => {
    if (view !== "case") return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") backToOverview();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view]);

  // Derive helpers — subject-blind
  const solverIds = solversOf(report);
  const colors = Object.fromEntries(report.solvers.map((s) => [s.id, s.color]));
  const f = analyzedById(report, selectedId);

  const ctx: PanelCtx = {
    selectedId,
    view,
    solverIds,
    colors,
    openCase,
  };

  // Tog: only surface the constrained-fit section when the run actually carries
  // fixed/tied cases — no silent empty shell (a heading with no body).
  const hasConstrained = (report.analyzed ?? []).some(
    (c) => c.category === "fixed" || c.category === "tied",
  );

  return (
    <div className="stagger" style={{ display: "flex", flexDirection: "column", gap: "var(--s4)" }}>
      {view === "overview" ? (
        <Fragment key="ev-overview">
          <h2
            style={{
              margin: 0,
              fontFamily: "var(--font-display)",
              fontWeight: 300,
              fontSize: "1.1rem",
              color: "var(--ink)",
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
      ) : (
        <Fragment key="ev-case">
          {/* Back button */}
          <button
            onClick={backToOverview}
            aria-label="Back to All cases overview"
            style={{
              background: "none",
              border: "none",
              color: "var(--accent)",
              cursor: "pointer",
              fontFamily: "var(--font-mono)",
              fontSize: "0.85rem",
              padding: 0,
              marginBottom: "var(--s3)",
              alignSelf: "flex-start",
            }}
          >
            ← All cases
          </button>

          {/* Case selector */}
          {report.analyzed?.length ? (
            <div style={{ display: "flex", alignItems: "center", gap: "var(--s3)" }}>
              <label
                htmlFor="case-selector"
                style={{ fontSize: "0.8rem", color: "var(--ink-faint)", fontFamily: "var(--font-mono)" }}
              >
                case
              </label>
              <select
                id="case-selector"
                value={selectedId}
                onChange={(e) => openCase(e.target.value)}
                style={{
                  background: "var(--surface-2)",
                  border: "1px solid var(--hairline)",
                  borderRadius: 6,
                  color: "var(--ink)",
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
                color: "var(--ink)",
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
      )}
    </div>
  );
}
