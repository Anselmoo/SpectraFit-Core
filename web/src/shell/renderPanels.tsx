import { isValidElement, type ReactNode } from "react";
import { PANELS } from "../panels/registry";
import { PanelCard } from "../panels/chrome";
import { scopeMatches, type PanelCtx } from "../panels/types";
import type { BenchReport } from "../contract";
import type { DestId } from "./nav";

/**
 * Render every registry panel for `dest` that matches the current view.
 *
 * All panels return a ReactNode (charts are wrapped in PlotMount inside each
 * panel body). Panels whose make() returns null/undefined are dropped (no
 * empty card).
 */
export function renderPanels(
  dest: DestId,
  report: BenchReport,
  ctx: PanelCtx,
  sectionId?: string,
): ReactNode[] {
  return PANELS.filter(
    (p) =>
      p.dest === dest &&
      scopeMatches(p.scope, ctx.view) &&
      (sectionId === undefined || p.section === sectionId),
  ).map((p) => {
    const node = p.make(report, ctx);
    if (node === null || node === undefined) return null;
    if (isValidElement(node)) {
      const title = typeof p.title === "function" ? p.title(report) : p.title;
      const caption = typeof p.caption === "function" ? p.caption(report) : p.caption;
      return (
        <PanelCard key={p.id} title={title} caption={caption}>
          {node}
        </PanelCard>
      );
    }
    return null;
  });
}
