export interface ScalingLine {
  backend: string;
  rows: { n: number; ms: number; backend: string }[];
}

export function scalingLines(
  f: any,
  solverIds: string[]
): ScalingLine[] {
  return solverIds
    .filter((b) => f.profiles?.[b]?.scaling?.length)
    .map((b) => ({
      backend: b,
      rows: f.profiles[b].scaling.map((p: any) => ({
        n: p.x,
        ms: p.y,
        backend: b,
      })),
    }));
}
