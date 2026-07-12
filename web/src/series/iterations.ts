// ---------------------------------------------------------------------------
// Iterations to converge — per backend for a single analyzed case.
//
// Reads profiles[backend].summary.nIter for each solver and returns a flat
// array of { backend, nIter } records for bar plotting.
// ---------------------------------------------------------------------------

export interface IterationEntry {
  backend: string;
  nIter: number;
}

/**
 * Build per-backend iteration counts for the selected analyzed case.
 *
 * Falls back to the first analyzed case when caseId is not found.
 * Backends with no summary or a non-finite nIter are omitted.
 */
export function iterationsSeries(report: any, caseId: string, solverIds: string[]): IterationEntry[] {
  const analyzed: any[] = Array.isArray(report?.analyzed) ? report.analyzed : [];
  const f = analyzed.find((c) => c?.id === caseId) ?? analyzed[0];
  if (f == null) return [];

  return solverIds
    .map((backend) => {
      const nIter: unknown = f?.profiles?.[backend]?.summary?.nIter;
      if (typeof nIter !== "number" || !Number.isFinite(nIter) || nIter < 0) return null;
      return { backend, nIter: Math.round(nIter) };
    })
    .filter((e): e is IterationEntry => e !== null);
}
