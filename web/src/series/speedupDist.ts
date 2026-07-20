// ---------------------------------------------------------------------------
// Suite-wide speedup distribution — per backend.
//
// For each backend, collect suite[].m[backend].speedup across all cases and
// summarise as a 5-number box (p5, p25, median, p75, p95). The raw values
// are also preserved so the plot can optionally draw a strip or violin.
// ---------------------------------------------------------------------------

import { quantileSorted } from "./recoveryError";

export interface SpeedupBox {
  backend: string;
  values: number[];
  p5: number;
  p25: number;
  median: number;
  p75: number;
  p95: number;
}

export function speedupDistSeries(report: any, solverIds: string[]): SpeedupBox[] {
  const suite: any[] = Array.isArray(report?.suite) ? report.suite : [];
  const out: SpeedupBox[] = [];

  for (const backend of solverIds) {
    const values = suite
      .map((c) => c?.m?.[backend]?.speedup)
      .filter((v): v is number => typeof v === "number" && Number.isFinite(v) && v > 0);

    if (values.length === 0) continue; // omit backends with no speedup data

    const sorted = [...values].sort((a, b) => a - b);
    out.push({
      backend,
      values,
      p5: quantileSorted(sorted, 0.05),
      p25: quantileSorted(sorted, 0.25),
      median: quantileSorted(sorted, 0.5),
      p75: quantileSorted(sorted, 0.75),
      p95: quantileSorted(sorted, 0.95),
    });
  }

  return out;
}
