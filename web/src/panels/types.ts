import type { ReactNode } from "react";
import type { BenchReport } from "../contract";
import type { DestId } from "../shell/nav";

export type PanelScope = "overview" | "case" | "static";
export type EvidenceView = "overview" | "case";

export interface PanelCtx {
  selectedId: string | null;
  view: EvidenceView;
  solverIds: string[];
  colors: Record<string, string>;
  /** Navigate to a single-case drill-down (wired by EvidencePanel; the
   *  suite-table rows call this). Optional so static/case panels can omit it. */
  openCase?: (id: string) => void;
}

/** Machine-declared proxy marker (Invariant V, V5: no silent proxy).
 *  A panel that renders a *proxy* metric — a stand-in for a quantity not yet
 *  computed for real at the source — MUST declare it here, not only in prose.
 *  The `proxyRegister` vitest fails if a declared proxy is not also disclosed in
 *  LIMITATIONS.md, and pins the known proxy so it cannot be silently dropped. */
export interface ProxyDeclaration {
  /** Why this is a proxy (the real quantity that is missing). */
  reason: string;
  /** Tracked task that implements the real metric. */
  task: string;
}

export interface PanelRecord {
  id: string;
  dest: DestId;
  scope: PanelScope;
  /** Static title string, or a function that derives the title from the report
   *  (used when the title depends on dynamic contract data, e.g. baselineSolverId). */
  title: string | ((report: BenchReport) => string);
  /** Static caption, or a function deriving it from the report — so factual
   *  claims in a caption (case counts, dataset names) come from the data, never
   *  a hardcoded string that can drift from the served run. */
  caption?: string | ((report: BenchReport) => string);
  section?: string;
  /** Set when this panel renders a proxy metric (V5). Machine-declared, checked
   *  by the proxyRegister vitest against LIMITATIONS.md. */
  proxy?: ProxyDeclaration;
  /** Returns a ReactNode (null means no panel rendered). */
  make: (report: BenchReport, ctx: PanelCtx) => ReactNode;
}

export function scopeMatches(scope: PanelScope, view: EvidenceView): boolean {
  return scope === "static" || scope === view;
}
