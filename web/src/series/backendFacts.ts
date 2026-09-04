/**
 * backendFacts — derive per-backend medians from suite[].m for the landing table.
 *
 * Only backends actually present in suite[].m are included (data-derived count,
 * not a hardcoded roster). Results are sorted alphabetically (order implies nothing).
 *
 * Returns one row per backend with:
 *   id          — solver id
 *   medMs       — median solve time in ms (median of per-case medMs values)
 *   medR2       — median r² across cases
 *   medSpeedup  — median speedup vs baseline across cases
 *   casesRun    — number of cases where this backend has a result
 *   successRate — fraction of cases where success === true (0–1)
 */
import type { BenchReport } from "../contract";

export interface BackendFact {
  id: string;
  medMs: number | null;
  medR2: number | null;
  medSpeedup: number | null;
  casesRun: number;
  successRate: number | null;
}

function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1
    ? sorted[mid]
    : (sorted[mid - 1] + sorted[mid]) / 2;
}

export function backendFacts(report: BenchReport): BackendFact[] {
  // Collect all backend ids actually present in suite[].m — never hardcoded.
  const idSet = new Set<string>();
  for (const c of report.suite ?? []) {
    for (const id of Object.keys(c.m ?? {})) {
      idSet.add(id);
    }
  }

  const rows: BackendFact[] = [];
  for (const id of Array.from(idSet).sort()) {
    const msMeasured: number[] = [];
    const r2Measured: number[] = [];
    const speedupMeasured: number[] = [];
    let casesRun = 0;
    let successCount = 0;
    let successTotal = 0;

    for (const c of report.suite ?? []) {
      const m = (c.m ?? {})[id];
      if (m == null) continue;
      casesRun++;
      if (typeof m.medMs === "number" && Number.isFinite(m.medMs)) msMeasured.push(m.medMs);
      if (typeof m.r2 === "number" && Number.isFinite(m.r2)) r2Measured.push(m.r2);
      if (typeof m.speedup === "number" && Number.isFinite(m.speedup)) speedupMeasured.push(m.speedup);
      if (typeof m.success === "boolean") {
        successTotal++;
        if (m.success) successCount++;
      }
    }

    rows.push({
      id,
      medMs: median(msMeasured),
      medR2: median(r2Measured),
      medSpeedup: median(speedupMeasured),
      casesRun,
      successRate: successTotal > 0 ? successCount / successTotal : null,
    });
  }

  return rows;
}
