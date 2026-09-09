/**
 * useEvidenceRouting — hash-routing + Escape-key behavior for the Evidence
 * destination's overview ↔ case sub-view.
 *
 * Extracted verbatim from EvidencePanel (no behavior change): owns the
 * selected-case id, the overview/case view state, the `#case=<id>` permalink
 * read-on-mount + `hashchange` listener (falls back to overview when the id
 * does not resolve to a real analyzed case — UX-01), the `#evidence` /
 * empty-hash → overview mapping, and an Escape-key listener (case → overview
 * only, while in case view).
 */
import { useEffect, useState } from "react";
import type { BenchReport } from "../contract";
import { analyzedById, defaultCaseId } from "../contract";
import type { EvidenceView } from "../panels/types";

interface EvidenceRouting {
  selectedId: string;
  view: EvidenceView;
  openCase: (id: string) => void;
  backToOverview: () => void;
}

export function useEvidenceRouting(report: BenchReport): EvidenceRouting {
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
  const [view, setView] = useState<EvidenceView>(
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

  return { selectedId, view, openCase, backToOverview };
}
