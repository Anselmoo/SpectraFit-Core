/**
 * Series transform for per-backend reduced-χ² distribution (AccuracyDist).
 *
 * AccuracyDist shape: { raw, median, p5, p25, p75 }
 * — a 4-quantile summary (no p95), mirroring TimingDist minus the p95.
 * Rendered as a horizontal box plot per backend.
 */

export interface AccuracyBox {
  backend: string;
  p5: number;
  p25: number;
  median: number;
  p75: number;
}

export function accuracyBoxes(
  f: any,
  solverIds: string[]
): AccuracyBox[] {
  return solverIds
    .filter((b) => {
      const acc = f.profiles?.[b]?.accuracy;
      return (
        acc != null &&
        typeof acc.median === "number" &&
        isFinite(acc.median)
      );
    })
    .map((b) => {
      const a = f.profiles[b].accuracy;
      return {
        backend: b,
        p5: a.p5,
        p25: a.p25,
        median: a.median,
        p75: a.p75,
      };
    });
}
