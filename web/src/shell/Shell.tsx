/**
 * Shell — top-level neutral narrative chain.
 *
 * Two destinations: Standing (facts masthead + per-backend results table) and
 * Evidence (all cases, side by side). The Audit/Methods destination has been
 * removed; verification detail is available at GET /api/v1/trust.
 * Subject-blind: no backend is crowned. Hash permalink: #standing | #evidence.
 * #audit redirects to #evidence (handled in destinationFromHash).
 *
 * This is now a thin router: underline-tab nav (see ../ui/Tabs) + hash
 * routing, switching between the two destination components. Every panel
 * body lives in the declarative registry (`../panels/registry`); the
 * destinations render it.
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
import { Tabs, TabPanel } from "../ui/Tabs";

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
        padding: "var(--space-5)",
        gap: "var(--space-5)",
      }}
    >
      {/* Honest disclosure when the served run is partial (no timing / no θ). */}
      <CompletenessBanner report={report} />

      {/* Warn when the dev stack is unreachable or a newer run is available (G13). */}
      <LivenessBanner report={report} />

      {/* Underline-only destination nav — ported from the design handbook's
          navigation Tabs component (see web/src/ui/Tabs.tsx header for the
          full provenance note). Replaces the former filled-pill segmented
          control; nav.ts's DestId/hash-routing/destinationFromHash logic
          below is unchanged, only the control rendering it is new.

          Brand mark: the handbook's app-icon-core.svg (indigo/violet
          gear-ring + nested fitted-peak mark, documented in the handbook's
          llm/brand-assets.json as the spectrafit-core benchmark-dashboard
          header mark — distinct from the primary blue app-icon.svg used for
          the favicon/docs-site), inlined as JSX SVG matching the handbook's
          own embedding construction (ui_kits/benchmark-dashboard/Dashboard.jsx
          topbar), plus the short label from that same reference composition. */}
      <nav
        style={{
          width: "100%",
          maxWidth: "var(--layout-nav)",
          display: "flex",
          alignItems: "center",
          gap: "var(--space-3)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--space-2)",
            fontFamily: "var(--font-mono)",
            fontSize: "0.78rem",
            fontWeight: 600,
            letterSpacing: "0.02em",
            color: "var(--text-secondary)",
            whiteSpace: "nowrap",
          }}
        >
          <svg viewBox="0 0 64 64" width={26} height={26} aria-hidden="true">
            <defs>
              <linearGradient id="shellBrandBg" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#9F8CF5" />
                <stop offset="55%" stopColor="#5E5CE6" />
                <stop offset="100%" stopColor="#7D3FBF" />
              </linearGradient>
              <linearGradient id="shellBrandGlyph" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#FFFFFF" />
                <stop offset="100%" stopColor="#E4DBFF" />
              </linearGradient>
              <linearGradient id="shellBrandGloss" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#fff" stopOpacity={0.5} />
                <stop offset="45%" stopColor="#fff" stopOpacity={0.05} />
                <stop offset="100%" stopColor="#fff" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="shellBrandShade" x1="0" y1="0" x2="0" y2="1">
                <stop offset="55%" stopColor="#000000" stopOpacity={0} />
                <stop offset="100%" stopColor="#000000" stopOpacity={0.28} />
              </linearGradient>
              <clipPath id="shellBrandSquircle">
                <rect x={1} y={1} width={62} height={62} rx={14.3} />
              </clipPath>
            </defs>
            <g clipPath="url(#shellBrandSquircle)">
              <rect x={1} y={1} width={62} height={62} fill="url(#shellBrandBg)" />
              <g fill="#1D1240" fillOpacity={0.3}>
                {[0, 45, 90, 135, 180, 225, 270, 315].map((angle) => (
                  <rect
                    key={angle}
                    x={29.3}
                    y={7.5}
                    width={5.4}
                    height={7}
                    rx={1}
                    transform={`rotate(${angle} 32 32)`}
                  />
                ))}
              </g>
              <circle cx={32} cy={32} r={19} fill="none" stroke="#1D1240" strokeOpacity={0.3} strokeWidth={5.4} />
              <g fill="url(#shellBrandGlyph)">
                {[0, 45, 90, 135, 180, 225, 270, 315].map((angle) => (
                  <rect
                    key={angle}
                    x={29.3}
                    y={7.5}
                    width={5.4}
                    height={7}
                    rx={1}
                    transform={`rotate(${angle} 32 32)`}
                  />
                ))}
              </g>
              <circle cx={32} cy={32} r={19} fill="none" stroke="url(#shellBrandGlyph)" strokeWidth={4.2} />
              <path
                d="M21.15 43.2C23.95 43.2 26.75 22.2 29.55 20.8C32.35 19.4 30.95 25 32.35 26.4C33.75 27.8 33.05 25.7 35.85 23.6C39.35 20.8 40.05 43.2 42.85 43.2"
                fill="none"
                stroke="#1D1240"
                strokeOpacity={0.3}
                strokeLinecap="round"
                strokeWidth={4.8}
              />
              <path
                d="M21.15 43.2C23.95 43.2 26.75 22.2 29.55 20.8C32.35 19.4 30.95 25 32.35 26.4C33.75 27.8 33.05 25.7 35.85 23.6C39.35 20.8 40.05 43.2 42.85 43.2"
                fill="none"
                stroke="url(#shellBrandGlyph)"
                strokeLinecap="round"
                strokeWidth={3.6}
              />
              <rect x={1} y={1} width={62} height={62} fill="url(#shellBrandShade)" />
              <rect x={1} y={1} width={62} height={26} fill="url(#shellBrandGloss)" />
            </g>
          </svg>
          <span>spectrafit-core · benchmark</span>
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <Tabs
            tabs={DESTINATIONS}
            activeId={dest}
            onChange={navigate}
            aria-label="Narrative navigation"
            idBase="destination"
          />
        </div>
      </nav>

      {/* Active destination panel — per-destination max width */}
      <div style={{ width: "100%", flex: 1, display: "flex", flexDirection: "column" }}>
        <TabPanel
          id={dest}
          idBase="destination"
          style={{
            width: "100%",
            flex: 1,
            // Standing is now a data-table landing (the facts masthead + per-backend
            // table), so it needs the wide layout like Evidence — the narrow editorial
            // width clipped the table and tripped the R4 horizontal-overflow guard.
            maxWidth:
              dest === "evidence" || dest === "standing"
                ? "var(--layout-content)"
                : "var(--layout-prose)",
            margin: "0 auto",
          }}
        >
          {dest === "standing" && <StandingPanel report={report} />}
          {dest === "evidence" && <EvidencePanel report={report} />}
        </TabPanel>
      </div>
    </div>
  );
}
