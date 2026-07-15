export type StabMetric = "r2" | "rmse" | "redChi2" | "iters";

export interface StabBand {
  backend: string;
  rows: {
    n: number;
    mean: number;
    lo: number;
    hi: number;
    backend: string;
  }[];
}

export function stabilityBand(
  f: any,
  solverIds: string[],
  metric: StabMetric
): StabBand[] {
  return solverIds
    .filter((b) => f.profiles?.[b]?.stability?.[metric])
    .map((b) => ({
      backend: b,
      rows: f.profiles[b].stability[metric].map((p: any) => ({
        n: p.n,
        mean: p.mean,
        lo: p.mean - p.sd,
        hi: p.mean + p.sd,
        backend: b,
      })),
    }));
}
