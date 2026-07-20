/**
 * Shell — top-level neutral narrative chain.
 *
 * Two destinations: Standing (facts masthead + per-backend results table) and
 * Evidence (all cases, side by side). The Audit/Methods destination has been
 * removed; verification detail is available at GET /api/v1/trust.
 * Subject-blind: no backend is crowned. Hash permalink: #standing | #evidence.
 * #audit redirects to #evidence (handled in destinationFromHash).
 *
 * This is now a thin router: segmented-control nav + hash routing, switching
 * between the two destination components. Every panel body lives in the
 * declarative registry (`../panels/registry`); the destinations render it.
 */
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { DESTINATIONS, destinationFromHash, hashOf } from "./nav";
import type { DestId } from "./nav";
import type { BenchReport } from "../contract";
import { StandingPanel } from "./StandingPanel";
import { EvidencePanel } from "./EvidencePanel";
import { CompletenessBanner } from "./CompletenessBanner";
import { LivenessBanner } from "./LivenessBanner";

export function Shell({ report }: { report: BenchReport }): ReactElement {
  const [dest, setDest] = useState<DestId>(() => destinationFromHash(window.location.hash));

  // Keep in sync with browser back/forward and external hash changes
  useEffect(() => {
    function onHashChange() {
      setDest(destinationFromHash(window.location.hash));
    }
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  function navigate(id: DestId) {
    window.location.hash = hashOf(id);
    setDest(id);
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "var(--s5)",
        gap: "var(--s5)",
      }}
    >
      {/* Honest disclosure when the served run is partial (no timing / no θ). */}
      <CompletenessBanner report={report} />

      {/* Warn when the dev stack is unreachable or a newer run is available (G13). */}
      <LivenessBanner report={report} />

      {/* Glass segmented-control nav */}
      <nav
        className="glass"
        style={{
          display: "flex",
          gap: 2,
          padding: 4,
          width: "100%",
          maxWidth: "var(--layout-nav)",
        }}
        aria-label="Narrative navigation"
      >
        {DESTINATIONS.map((d) => {
          const active = d.id === dest;
          return (
            <button
              key={d.id}
              onClick={() => navigate(d.id)}
              style={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 2,
                padding: "var(--s2) var(--s3)",
                border: "none",
                borderRadius: "calc(var(--radius) - 4px)",
                background: active ? "var(--accent)" : "transparent",
                color: active ? "var(--bg)" : "var(--ink-dim)",
                cursor: "pointer",
                fontFamily: "var(--font-body)",
                fontSize: "0.9rem",
                fontWeight: active ? 600 : 400,
                transition: "background var(--motion), color var(--motion)",
              }}
              aria-current={active ? "page" : undefined}
            >
              <span style={{ fontWeight: 600 }}>{d.label}</span>
              <span
                style={{
                  fontSize: "0.72rem",
                  opacity: active ? 0.85 : 0.65,
                  color: active ? "var(--bg)" : "var(--ink-faint)",
                }}
              >
                {d.blurb}
              </span>
            </button>
          );
        })}
      </nav>

      {/* Active destination panel — per-destination max width */}
      <div style={{ width: "100%", flex: 1, display: "flex", flexDirection: "column" }}>
        <div
          style={{
            width: "100%",
            // Standing is now a data-table landing (the facts masthead + per-backend
            // table), so it needs the wide layout like Evidence — the narrow editorial
            // width clipped the table and tripped the R4 horizontal-overflow guard.
            maxWidth:
              dest === "evidence" || dest === "standing"
                ? "var(--layout-evidence)"
                : "var(--layout-editorial)",
            margin: "0 auto",
          }}
        >
          {dest === "standing" && <StandingPanel report={report} />}
          {dest === "evidence" && <EvidencePanel report={report} />}
        </div>
      </div>
    </div>
  );
}
