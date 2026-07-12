// ---------------------------------------------------------------------------
// Information-criteria rows (ΔAIC / ΔBIC / MAE) per backend, for one case.
//
// summary.{dAIC,dBIC} are model-selection-grade deltas already computed per
// case (each backend's AIC/BIC minus the best across backends). Lower ΔAIC /
// ΔBIC = the preferred fit. MAE complements RMSE (mean absolute residual).
// Subject-blind: callers pass solverIds from solversOf(report).
// ---------------------------------------------------------------------------

export interface InfoCriteriaRow {
  backend: string;
  dAIC: number;
  dBIC: number;
  mae: number;
  /** True for the preferred model — the lowest ΔAIC across the listed backends. */
  best: boolean;
}

/**
 * Project per-backend info criteria into one row per solver that reports them.
 * A backend is included only if its summary carries a finite dAIC (so we never
 * fabricate a 0 for a backend that simply didn't report the criterion).
 */
export function infoCriteriaRows(f: any, solverIds: string[]): InfoCriteriaRow[] {
  const raw = solverIds
    .filter((id) => Number.isFinite(f?.profiles?.[id]?.summary?.dAIC))
    .map((id) => {
      const s = f.profiles[id].summary;
      return {
        backend: id,
        dAIC: s.dAIC as number,
        dBIC: Number.isFinite(s.dBIC) ? (s.dBIC as number) : NaN,
        mae: Number.isFinite(s.mae) ? (s.mae as number) : NaN,
        best: false,
      };
    });
  if (raw.length === 0) return [];
  const minDAIC = Math.min(...raw.map((r) => r.dAIC));
  return raw.map((r) => ({ ...r, best: r.dAIC === minDAIC }));
}
