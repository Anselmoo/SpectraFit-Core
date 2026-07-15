export interface KappaRow {
  backend: string;
  kappa: number | null;
  illPosed: boolean;
  absent: boolean;
}

export function kappaRows(f: any, solverIds: string[]): KappaRow[] {
  return solverIds
    .filter((b) => f.profiles?.[b])
    .map((b) => {
      const k = f.profiles[b].jacobianConditionNumber;
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

export function topCouplings(f: any, k = 3): Coupling[] {
  const corr = f.corr as number[][] | undefined;
  const names = f.paramNames as string[] | undefined;
  if (!corr || !names) return [];
  const out: Coupling[] = [];
  for (let i = 0; i < corr.length; i++) {
    for (let j = i + 1; j < corr.length; j++) {
      out.push({ pair: `${names[i]}·${names[j]}`, r: corr[i][j] });
    }
  }
  return out.sort((a, b) => Math.abs(b.r) - Math.abs(a.r)).slice(0, k);
}
