/** IA contract (spec §3b): each Evidence panel is "overall" (all cases) or
 *  "single" (the selected case). Overview renders OVERALL only; Case renders
 *  SINGLE only. A panel in the wrong list/view is a drift bug. */
export const OVERALL_PANELS = [
  "suite-table", "saturation", "delta-r2-ci", "speedup-ci", "winner-stability",
] as const;
export const SINGLE_PANELS = [
  "fit", "peaks", "recovery", "pulls", "convergence",
  "timing", "warmup", "scaling", "reproducibility", "conditioning",
] as const;
export const EVIDENCE_PANELS = [...OVERALL_PANELS, ...SINGLE_PANELS] as const;
export type EvidenceScope = "overall" | "single";
