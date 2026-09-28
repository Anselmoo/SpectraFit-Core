// ---------------------------------------------------------------------------
// Nested-model adequacy series helpers.
//
// Derives human-readable verdict and delta-table rows from `NestedAdequacy`
// (from `Featured.nestedAdequacy`). All values come from the contract; nothing
// is hardcoded.
// ---------------------------------------------------------------------------
import type { components } from "../openapi.gen";

export type NestedAdequacy = components["schemas"]["NestedAdequacy"];
export type SelectionStats = components["schemas"]["SelectionStats"];

/**
 * High-level verdict derived from the NestedAdequacy block.
 *
 * The W9 wire is BIC-governed: recovery is assessed by `recoveredTrueOrderBic`.
 * AIC's disagreement (when present) is surfaced honestly rather than suppressed.
 */
export interface NestedVerdict {
  trueOrder: number;
  /** BIC-governed recovery (the W9 criterion). */
  bicRecovered: boolean;
  selectedOrderBic: number;
  /** AIC result (may differ from BIC). */
  aicRecovered: boolean;
  selectedOrderAic: number;
  /** True when AIC and BIC agree on the selected order. */
  aicBicAgree: boolean;
  /** Whether the reduced (m*-1) model is statistically rejected (LRT). */
  reducedRejected: boolean;
  lrtPReducedVsTrue: number;
  dAICReducedVsTrue: number;
  dBICReducedVsTrue: number;
  dAICTrueVsOver: number;
  dBICTrueVsOver: number;
}

/**
 * Project the `NestedAdequacy` contract block into a `NestedVerdict`.
 * Returns `null` when called with a nullish value — callers gate on null.
 */
export function nestedVerdict(na: NestedAdequacy | null | undefined): NestedVerdict | null {
  if (na == null) return null;
  return {
    trueOrder: na.trueOrder,
    bicRecovered: na.recoveredTrueOrderBic,
    selectedOrderBic: na.selectedOrderBic,
    aicRecovered: na.recoveredTrueOrderAic,
    selectedOrderAic: na.selectedOrderAic,
    aicBicAgree: na.selectedOrderAic === na.selectedOrderBic,
    reducedRejected: na.reducedRejected,
    lrtPReducedVsTrue: na.reducedVsTrue.lrtP,
    dAICReducedVsTrue: na.reducedVsTrue.dAIC,
    dBICReducedVsTrue: na.reducedVsTrue.dBIC,
    dAICTrueVsOver: na.trueVsOver.dAIC,
    dBICTrueVsOver: na.trueVsOver.dBIC,
  };
}

/**
 * One row in the delta-criteria table (one nested comparison).
 */
export interface DeltaRow {
  label: string;
  lrtP: number;
  fP: number;
  dAIC: number;
  dBIC: number;
}

/**
 * Project both nested comparisons into table rows.
 * Comparison orientation: full − reduced, so negative ΔAIC/ΔBIC = full preferred.
 */
export function deltaRows(na: NestedAdequacy | null | undefined): DeltaRow[] {
  if (na == null) return [];
  return [
    {
      label: `true (m*=${na.trueOrder}) vs reduced (m*−1=${na.trueOrder - 1})`,
      lrtP: na.reducedVsTrue.lrtP,
      fP: na.reducedVsTrue.fP,
      dAIC: na.reducedVsTrue.dAIC,
      dBIC: na.reducedVsTrue.dBIC,
    },
    {
      label: `over-fitted (m*+1=${na.trueOrder + 1}) vs true (m*=${na.trueOrder})`,
      lrtP: na.trueVsOver.lrtP,
      fP: na.trueVsOver.fP,
      dAIC: na.trueVsOver.dAIC,
      dBIC: na.trueVsOver.dBIC,
    },
  ];
}
