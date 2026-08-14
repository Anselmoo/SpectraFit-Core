// ---------------------------------------------------------------------------
// harmonicMeanSpeedup — client-side harmonic mean helper for the Standing panel.
//
// The harmonic mean (N / Σ(1/xᵢ)) is the correct aggregate for equal-time
// speedup comparisons (Eeckhout 2024 "R.I.P. Geomean Speedup") and is always
// ≤ the geometric mean for positively-skewed speedup distributions.
//
// Usage
// -----
// 1. Preferred: read `manifest.harmonicMeanSpeedupVsBaseline` directly when
//    the served results.json includes the field.
// 2. Fallback: call `harmonicMeanFromSuite(suite, subjectId)` to compute it
//    client-side from the per-case speedup values already in the report.
//    This covers runs whose results.json predates the field addition.
// ---------------------------------------------------------------------------

/**
 * Harmonic mean of a list of positive numbers: N / Σ(1/xᵢ).
 *
 * Returns `null` when the input is empty or all values are non-finite /
 * non-positive (same sentinel-by-null convention as the Python `_harmonic_mean`).
 */
export function harmonicMean(values: number[]): number | null {
  const valid = values.filter((v) => Number.isFinite(v) && v > 0);
  if (valid.length === 0) return null;
  const sumReciprocals = valid.reduce((acc, v) => acc + 1 / v, 0);
  return valid.length / sumReciprocals;
}

/**
 * Compute the harmonic mean of the per-case speedup values for *subjectId*
 * across all suite cases that report a finite positive speedup for that solver.
 *
 * This is the client-side fallback when `manifest.harmonicMeanSpeedupVsBaseline`
 * is null/absent (i.e. results.json predates the field).
 */
export function harmonicMeanFromSuite(
  suite: Array<{ m: Record<string, { speedup: number }> }>,
  subjectId: string,
): number | null {
  const speedups = suite
    .map((c) => c?.m?.[subjectId]?.speedup)
    .filter((v): v is number => typeof v === "number" && Number.isFinite(v) && v > 0);
  return harmonicMean(speedups);
}
