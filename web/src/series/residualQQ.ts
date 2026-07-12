// ---------------------------------------------------------------------------
// Residual normality QQ series — per backend.
//
// For each backend, we take the residuals from profiles[b].fit.resid (or
// fall back to the ecdfResid point cloud), standardise them (subtract mean,
// divide by sd), sort ascending, and pair each z_(k) with the theoretical
// normal quantile Φ⁻¹((k − 0.5) / n) via Acklam's rational approximation.
//
// A diagonal QQ plot confirms Gaussian-noise assumption; deviation reveals
// heavy tails or systematic structure.
// ---------------------------------------------------------------------------

/** Acklam's rational approximation to the inverse normal CDF.
 *  Accuracy: |error| < 4.5e-4 over the whole (0,1) interval.
 *  Reference: Peter J. Acklam, "An algorithm for computing the inverse normal
 *  cumulative distribution function", 2003.
 */
export function invNormalCdf(p: number): number {
  if (p <= 0) return -Infinity;
  if (p >= 1) return Infinity;

  // Coefficients for rational approximation
  const a = [
    -3.969683028665376e1,
    2.209460984245205e2,
    -2.759285104469687e2,
    1.38357751867269e2,
    -3.066479806614716e1,
    2.506628277459239,
  ] as const;

  const b = [
    -5.447609879822406e1,
    1.615858368580409e2,
    -1.556989798598866e2,
    6.680131188771972e1,
    -1.328068155288572e1,
  ] as const;

  const c = [
    -7.784894002430293e-3,
    -3.223964580411365e-1,
    -2.400758277161838,
    -2.549732539343734,
    4.374664141464968,
    2.938163982698783,
  ] as const;

  const d = [
    7.784695709041462e-3,
    3.224671290700398e-1,
    2.445134137142996,
    3.754408661907416,
  ] as const;

  const pLow = 0.02425;
  const pHigh = 1 - pLow;

  let q: number;
  let r: number;

  if (p < pLow) {
    // Lower tail
    q = Math.sqrt(-2 * Math.log(p));
    return (
      (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) /
      ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    );
  } else if (p <= pHigh) {
    // Central region
    q = p - 0.5;
    r = q * q;
    return (
      ((((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q) /
      (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    );
  } else {
    // Upper tail
    q = Math.sqrt(-2 * Math.log(1 - p));
    return -(
      (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) /
      ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    );
  }
}

export interface QQPoint {
  theoretical: number;
  sample: number;
}

export interface QQBackend {
  backend: string;
  points: QQPoint[];
}

/**
 * Extract residuals for a backend. Prefers fit.resid; falls back to
 * ecdfResid point cloud (y values), which holds the sorted residual ECDF.
 */
function residualsFor(f: any, backend: string): number[] {
  const resid: unknown = f?.profiles?.[backend]?.fit?.resid;
  if (Array.isArray(resid) && resid.length > 0) {
    return resid as number[];
  }
  // Fallback: ecdfResid is a list of {x,y} points; use the x values (residuals)
  const ecdf: unknown = f?.profiles?.[backend]?.ecdfResid;
  if (Array.isArray(ecdf) && ecdf.length > 0) {
    return (ecdf as Array<{ x: number; y: number }>).map((pt) => pt.x);
  }
  return [];
}

/**
 * Build per-backend QQ series for a single analyzed case.
 *
 * Standardises residuals (zero mean, unit sd), sorts ascending, and pairs
 * each sorted value z_(k) with the theoretical quantile Φ⁻¹((k−0.5)/n).
 */
export function residualQQSeries(report: any, caseId: string, solverIds: string[]): QQBackend[] {
  // Locate the analyzed case
  const analyzed: any[] = Array.isArray(report?.analyzed) ? report.analyzed : [];
  const f = analyzed.find((c) => c?.id === caseId) ?? analyzed[0];
  if (f == null) return [];

  return solverIds
    .map((backend) => {
      const raw = residualsFor(f, backend);
      if (raw.length === 0) return null;

      const n = raw.length;
      const mean = raw.reduce((s, v) => s + v, 0) / n;
      const variance = raw.reduce((s, v) => s + (v - mean) ** 2, 0) / n;
      const sd = Math.sqrt(variance);

      // Standardise; if sd≈0 (constant residuals), keep as-is
      const standardised = sd > 0 ? raw.map((v) => (v - mean) / sd) : raw.map(() => 0);

      // Sort ascending
      const sorted = [...standardised].sort((a, b) => a - b);

      // Pair with theoretical quantiles
      const points: QQPoint[] = sorted.map((z, k) => ({
        theoretical: invNormalCdf((k + 0.5) / n),
        sample: z,
      }));

      return { backend, points };
    })
    .filter((s): s is QQBackend => s !== null);
}
