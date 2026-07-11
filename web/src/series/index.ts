import { format } from "d3-format";

export type Scale = "linear" | "log";

/** Labels for a tick set such that no two ADJACENT labels are identical.
 *  Increases precision until adjacent ties break (kills tick-collapse). */
export function tickLabels(ticks: number[], scale: Scale): string[] {
  for (let p = 0; p <= 12; p++) {
    const f = format(scale === "log" ? `.${p}~g` : `.${p}~f`);
    const labels = ticks.map((t) => f(t));
    let collapsed = false;
    for (let i = 1; i < labels.length; i++) {
      if (labels[i] === labels[i - 1]) { collapsed = true; break; }
    }
    if (!collapsed) return labels;
  }
  return ticks.map((t) => String(t)); // fallback: raw
}

export interface CIRow { caseId: string; lo: number; point: number; hi: number; }

/** Pure: project a list of inference cases onto one CI field as typed rows.
 *  Cases where `c[field]` is undefined are silently skipped — no TypeError. */
export function ciRows(
  cases: Array<{ caseId: string } & Record<string, { lo: number; point: number; hi: number }>>,
  field: string,
): CIRow[] {
  return cases
    .map((c) => {
      const ci = c[field];
      if (ci == null) return null;
      return { caseId: c.caseId, lo: ci.lo, point: ci.point, hi: ci.hi };
    })
    .filter((row): row is CIRow => row !== null);
}

// Legacy stub export preserved for any existing consumers
export type SeriesPoint = { x: number; y: number };

export function emptySeries(): SeriesPoint[] {
  return [];
}
