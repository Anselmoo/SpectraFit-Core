/**
 * Shared helpers and constants used by 2+ panels/bodies modules.
 * Nothing here imports from registry.tsx — no import cycles.
 */
import type { BenchReport } from "../../contract";
import { analyzedById, defaultCaseId } from "../../contract";
import type { PanelCtx } from "../types";

// ---------------------------------------------------------------------------
// Gate badge — status → CSS variable mapping (was inline in Shell)
// ---------------------------------------------------------------------------

export const GATE_COLOR: Record<string, string> = {
  pass: "var(--pass)",
  warn: "var(--warn)",
  fail: "var(--fail)",
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type AnyCase = any;

/** Resolve the selected case (or first analyzed) for the single-case panels. */
export function selectedCase(report: BenchReport, ctx: PanelCtx): AnyCase | undefined {
  // ctx.selectedId is driven by EvidencePanel (which also seeds it from
  // defaultCaseId); the fallback here mirrors that choice — the discriminating
  // case, not the saturated analyzed[0] — so any panel reached without a
  // selection still opens on a case where backends visibly diverge.
  const id = ctx.selectedId ?? defaultCaseId(report);
  return analyzedById(report, id);
}

export function solverLabelMap(report: BenchReport): Record<string, string> {
  return Object.fromEntries(report.solvers.map((s) => [s.id, s.label]));
}

/**
 * Derive human-readable constraint lines from a case's fixedParams + exprEdges.
 * Returns an array of strings, e.g.:
 *   ["p0.center held fixed", "p1.sigma = p0.sigma"]
 * Used by CaseScenario and constrainedFitBody so constraint rendering is DRY.
 */
export function constraintLines(f: {
  fixedParams?: Record<string, string[]>;
  exprEdges?: Array<{ targetNode: string; targetParam: string; expression: string }>;
}): string[] {
  const fixed: string[] = [];
  for (const [node, params] of Object.entries(f.fixedParams ?? {})) {
    for (const param of params) {
      fixed.push(`${node}.${param} held fixed`);
    }
  }
  const ties: string[] = (f.exprEdges ?? []).map(
    ({ targetNode, targetParam, expression }) => `${targetNode}.${targetParam} = ${expression}`,
  );
  return [...fixed, ...ties];
}
