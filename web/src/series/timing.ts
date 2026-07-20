export interface TimingBox {
  backend: string;
  p5: number;
  p25: number;
  median: number;
  p75: number;
  p95: number;
}

export function timingBoxes(
  f: any,
  solverIds: string[]
): TimingBox[] {
  return solverIds
    .filter((b) => f.profiles?.[b]?.timing)
    .map((b) => {
      const t = f.profiles[b].timing;
      return {
        backend: b,
        p5: t.p5,
        p25: t.p25,
        median: t.median,
        p75: t.p75,
        p95: t.p95,
      };
    });
}
