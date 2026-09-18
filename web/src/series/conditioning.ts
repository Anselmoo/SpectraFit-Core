import type { Featured } from "../contract";

export interface KappaRow {
  backend: string;
  kappa: number | null;
  illPosed: boolean;
  absent: boolean;
}

export function kappaRows(f: Featured, solverIds: string[]): KappaRow[] {
  return solverIds
    .filter((b) => f.profiles?.[b])
    .map((b) => {
      const k = f.profiles[b].jacobianConditionNumber ?? null;
      return {
        backend: b,
        kappa: k,
        illPosed: k != null && k >= 1e6,
        absent: k == null,
      };
    });
}

export interface Coupling {
  pair: string;
  r: number;
}

export function topCouplings(f: Featured, k = 3): Coupling[] {
  const corr = f.corr;
  const names = f.paramNames;
  if (!corr || !names) return [];
  const out: Coupling[] = [];
  for (let i = 0; i < corr.length; i++) {
    for (let j = i + 1; j < corr.length; j++) {
      out.push({ pair: `${names[i]}·${names[j]}`, r: corr[i][j] });
    }
  }
  return out.sort((a, b) => Math.abs(b.r) - Math.abs(a.r)).slice(0, k);
}
