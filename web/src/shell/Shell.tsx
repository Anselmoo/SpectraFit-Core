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
import faviconSvgRaw from "../../public/favicon.svg?raw";

// The shared brand SVG has no intrinsic size (viewBox only) — inject an
// explicit width/height so it renders at this header's 26x26 footprint
// without needing wrapper CSS. See the brand-mark comment below for why
// this is a `?raw` import rather than a plain <img src>.
const BRAND_MARK_SVG = faviconSvgRaw.replace(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">',
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="26" height="26">',
);

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

          Brand mark (2026-08-03 icon unification, cupertino-council pass):
          previously an indigo/violet gear-ring mark hand-drawn inline here
          (the design handbook's app-icon-core.svg, documented as distinct
          from the blue docs-site favicon by design) and a separate blue
          wave-only mark for docs — now ONE shared glyph (gear-ring + wave,
          blue-glass rendering) used everywhere, imported raw from
          public/favicon.svg rather than hand-duplicated a third time, so
          there is exactly one file to ever edit. `?raw` (not a plain <img
          src="/favicon.svg">) because the standalone offline report.html
          bundle (vite-plugin-singlefile) does not copy sibling static
          assets — a raw string import gets inlined into the JS bundle
          itself, so this resolves in every build mode. width/height are
          injected into the imported markup below since the shared SVG has
          no intrinsic size (only a viewBox), matching this mark's original
          26x26 footprint in the header. */}
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
          <span
            aria-hidden="true"
            style={{ display: "inline-flex", width: 26, height: 26 }}
            dangerouslySetInnerHTML={{ __html: BRAND_MARK_SVG }}
          />
          <span>SpectraFit-Core · Benchmark</span>
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
