export interface GridCell { category: string; backend: string; r2: number; failed: boolean; }

/** r² below this threshold is considered a failed / divergent fit. */
export const SATURATION_FAIL_THRESHOLD = 0.9;

export function saturationGrid(
  suite: Array<{ category: string; m: Record<string, { r2: number }> }>,
): GridCell[] {
  const acc = new Map<string, { sum: number; n: number }>();
  for (const c of suite) {
    for (const [backend, met] of Object.entries(c.m)) {
      const k = `${c.category}\x00${backend}`;
      const a = acc.get(k) ?? { sum: 0, n: 0 };
      a.sum += met.r2; a.n += 1; acc.set(k, a);
    }
  }
  return [...acc].map(([k, a]) => {
    const sep = k.indexOf("\x00");
    const category = k.slice(0, sep);
    const backend = k.slice(sep + 1);
    const r2 = a.sum / a.n;
    return { category, backend, r2, failed: r2 < SATURATION_FAIL_THRESHOLD };
  });
}
