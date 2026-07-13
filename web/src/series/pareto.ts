// ---------------------------------------------------------------------------
// Runtime-vs-accuracy Pareto frontier over the whole suite.
//
// Each (case × backend) is a point at (medMs, r²). The non-dominated envelope
// is the set of points that nothing beats on BOTH axes (lower median time AND
// higher r²) — the ideal speed/accuracy trade-off referees look for.
// ---------------------------------------------------------------------------

export interface ParetoPoint { x: number; y: number; caseId: string; backend: string }
export interface ParetoBackend { backend: string; points: ParetoPoint[] }

/** An array of per-backend series, with the computed frontier attached. */
export type ParetoSeries = ParetoBackend[] & { envelope: ParetoPoint[] };

function envelopeOf(all: ParetoPoint[]): ParetoPoint[] {
  // A point is on the frontier if no other point has x ≤ and y ≥ (one strict).
  const frontier = all.filter(
    (p) => !all.some((q) => q !== p && q.x <= p.x && q.y >= p.y && (q.x < p.x || q.y > p.y)),
  );
  // Sort by ascending x; drop ties that don't improve y so the line is monotone.
  frontier.sort((a, b) => a.x - b.x || b.y - a.y);
  const out: ParetoPoint[] = [];
  for (const p of frontier) {
    if (out.length === 0 || p.y > out[out.length - 1].y) out.push(p);
  }
  return out;
}

export function paretoSeries(report: any, solverIds: string[]): ParetoSeries {
  const suite: any[] = Array.isArray(report?.suite) ? report.suite : [];
  const backends: ParetoBackend[] = solverIds.map((b) => ({
    backend: b,
    points: suite
      .filter((c) => c?.m?.[b] && Number.isFinite(c.m[b].medMs) && Number.isFinite(c.m[b].r2))
      .map((c) => ({ x: c.m[b].medMs as number, y: c.m[b].r2 as number, caseId: c.id as string, backend: b })),
  }));
  const all = backends.flatMap((s) => s.points);
  const result = backends as ParetoSeries;
  result.envelope = envelopeOf(all);
  return result;
}
