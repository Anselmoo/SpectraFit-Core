/**
 * Standing — verdict header + render-truth + credibility rung.
 *
 * Thin destination over the panel registry: the three Standing records carry
 * their own bespoke .glass markup (heading inside the card), so they render
 * bare — wrapping them in a PanelCard would create a double h2.
 */
import { Fragment, isValidElement } from "react";
import type { ReactElement, ReactNode } from "react";
import type { BenchReport } from "../contract";
import { solversOf } from "../contract";
import { PANELS } from "../panels/registry";
import type { PanelCtx } from "../panels/types";
import { ProvenanceFooter } from "./ProvenanceFooter";

export function StandingPanel({ report }: { report: BenchReport }): ReactElement {
  const ctx: PanelCtx = {
    selectedId: null,
    view: "overview",
    solverIds: solversOf(report),
    colors: Object.fromEntries(report.solvers.map((s) => [s.id, s.color])),
  };
  const records = PANELS.filter((p) => p.dest === "standing");
  return (
    <>
      <div className="stagger" style={{ display: "flex", flexDirection: "column", gap: "var(--s4)" }}>
        {records.map((p) => {
          const node = p.make(report, ctx);
          // Standing records always return bespoke .glass ReactNode cards; guard
          // drops null/non-element bodies (raw SVGs never occur for this dest).
          if (node == null || !isValidElement(node)) return null;
          return <Fragment key={p.id}>{node as ReactNode}</Fragment>;
        })}
      </div>
      <ProvenanceFooter report={report} />
    </>
  );
}
