export interface RecRow {
  param: string;
  backend: string;
  truth: number;
  guess: number;
  fit: number;
  /**
   * EF-PLOTS-07: per-parameter normalization so parameters of disparate
   * magnitude (a 10³ amplitude vs a 10⁻¹ width) share one fair, dimensionless
   * x-axis instead of collapsing on a single shared linear scale. `scale` is
   * `max(|truth|, |guess|, ε)` — backend-independent (truth/guess do not vary by
   * backend), so every backend's row for a parameter shares it and the rows stay
   * comparable. The deviations are signed and relative; truth maps to 0.
   */
  scale: number;
  guessDev: number;
  fitDev: number;
}

const ACS = ["a", "c", "s"] as const;
const EPS = 1e-12;

export function recoveryRows(f: any, solverIds: string[]): RecRow[] {
  const out: RecRow[] = [];
  (f.truth ?? []).forEach((t: any, i: number) => {
    for (const k of ACS) {
      const param = `${k}${i}`;
      const guess = f.guessParams?.[i]?.[k];
      // scale is computed from truth + guess only (both backend-independent) so a
      // wildly-off fit can honestly extend beyond ±1 rather than compressing the rest.
      const scale = Math.max(Math.abs(t[k]), Number.isFinite(guess) ? Math.abs(guess) : 0, EPS);
      for (const b of solverIds) {
        const fit = f.profiles?.[b]?.fit?.params?.[i]?.[k];
        if (fit == null) continue;
        out.push({
          param,
          backend: b,
          truth: t[k],
          guess,
          fit,
          scale,
          guessDev: ((Number.isFinite(guess) ? guess : t[k]) - t[k]) / scale,
          fitDev: (fit - t[k]) / scale,
        });
      }
    }
  });
  return out;
}
