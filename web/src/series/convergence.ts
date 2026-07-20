import { historyMode } from "../provenance";
export interface ConvLine { backend:string; mode:"line"|"endpoints"; rows:{iter:number;cost:number;backend:string}[]; }
export function convSeries(f:any, solverIds:string[]):ConvLine[] {
  return solverIds.filter(b=>f.profiles?.[b]?.conv).map(b=>({
    backend:b, mode:historyMode(f.profiles[b].historySource),
    rows:f.profiles[b].conv.map((c:number,i:number)=>({iter:i,cost:c,backend:b})) }));
}

// ---------------------------------------------------------------------------
// Convergence to the KNOWN ground truth — the REAL metric (Invariant V, Phase 4).
//
// spectrafit's faer LM driver now records the free-parameter vector θ at every
// accepted iteration (FitResult.params_history), so the benchmark engine computes
// the scale-normalized distance to the known synthetic truth per iteration:
//
//   dₖ = ‖(θₖ − θ_true) / s‖₂,   sᵢ = max(|θ_true,ᵢ|, 1)
//
// carried as the contract field `thetaDistance` on the subject's profile. This
// is the actual distance of the iterates to the true parameters — NOT the χ²-floor
// proxy it replaced. Only spectrafit records a parameter trajectory; oracle
// backends expose no per-iteration θ, so the metric is spectrafit-only.
// ---------------------------------------------------------------------------

/** Tiny positive floor so a log y-axis never receives a value ≤ 0. */
export const FLOOR_EPS = 1e-12;

export interface ThetaDistance {
  /** The backend that recorded the θ trajectory (found by data, not hardcoded). */
  backend: string;
  /** Visual reference line: the scale-normalized recovery tolerance. */
  recoveryTol: number;
  rows: { iter: number; dist: number }[];
}

/**
 * The REAL convergence-to-truth series. Subject-blind: the trajectory is found
 * by which backend actually carries a ``thetaDistance`` array (only the subject
 * solver records per-iteration θ), never by a hardcoded backend id. Returns
 * ``null`` when no backend has the field (non-synthetic case / no trajectory) —
 * never a fabricated series.
 */
export function thetaDistanceSeries(f: any): ThetaDistance | null {
  const profiles: Record<string, any> = f?.profiles ?? {};
  const hit = Object.entries(profiles).find(
    ([, p]) => Array.isArray(p?.thetaDistance) && p.thetaDistance.length > 0,
  );
  if (!hit) return null;
  const [backend, prof] = hit;
  return {
    backend,
    recoveryTol: 1e-2,
    rows: (prof.thetaDistance as number[]).map((d, i) => ({
      iter: i,
      dist: Math.max(d, FLOOR_EPS),
    })),
  };
}
