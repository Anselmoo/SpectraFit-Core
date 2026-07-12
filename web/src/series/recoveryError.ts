// ---------------------------------------------------------------------------
// Suite-wide parameter-recovery error distribution.
//
// Per backend, the spread of m[backend].paramErr across every case — how far
// fitted parameters land from the known truth. Summarised as a 5-number box
// (p5, p25, median, p75, p95). Tighter and lower is more accurate.
// ---------------------------------------------------------------------------

/** Linear-interpolated quantile of an ASCENDING-sorted array (q in [0,1]). */
export function quantileSorted(sorted: number[], q: number): number {
  const n = sorted.length;
  if (n === 0) return NaN;
  if (n === 1) return sorted[0];
  const pos = (n - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  if (lo === hi) return sorted[lo];
  const frac = pos - lo;
  return sorted[lo] * (1 - frac) + sorted[hi] * frac;
}

export interface RecoveryBox {
  backend: string;
  values: number[];
  p5: number;
  p25: number;
  median: number;
  p75: number;
  p95: number;
}

export function recoveryErrorSeries(report: any, solverIds: string[]): RecoveryBox[] {
  const suite: any[] = Array.isArray(report?.suite) ? report.suite : [];
  const out: RecoveryBox[] = [];
  for (const backend of solverIds) {
    const values = suite
      .map((c) => c?.m?.[backend]?.paramErr)
      .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
    if (values.length === 0) continue; // omit backends with no recovery-error data
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
