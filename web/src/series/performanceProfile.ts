// ---------------------------------------------------------------------------
// Dolan-Moré performance profile — the standard solver-benchmark figure.
//
// For each case p and solver s, the performance ratio is
//     r_{p,s} = cost_{p,s} / min_s(cost_{p,s})
// where cost = suite[].m[s].medMs (median solve time). The profile is
//     ρ_s(τ) = (# cases with r_{p,s} ≤ τ) / N
// a non-decreasing step function of τ on a log axis from 1 upward.
//   ρ_s(1)   = fraction of cases where s is the fastest.
//   ρ_s(∞)   = fraction of cases s ever solved (the right plateau = robustness).
//
// Reference: Dolan & Moré, "Benchmarking optimization software with performance
// profiles", Math. Program. 91 (2002).
// ---------------------------------------------------------------------------

export interface ProfilePoint {
  tau: number;
  rho: number;
}
export interface ProfileSeries {
  backend: string;
  points: ProfilePoint[];
}

/**
 * Per-solver Dolan-Moré performance profile over the whole suite, by median
 * solve time (medMs). A case only contributes a ratio for a solver that
 * reported a finite cost on it; the divisor is the cheapest finite cost on that
 * case across the given solvers. The total N is the number of cases that have at
 * least one finite cost (so ρ is a fraction of comparable cases).
 */
export function performanceProfileSeries(report: any, solverIds: string[]): ProfileSeries[] {
  const suite: any[] = Array.isArray(report?.suite) ? report.suite : [];

  const cost = (c: any, b: string): number | null => {
    const v = c?.m?.[b]?.medMs;
    return Number.isFinite(v) && v > 0 ? (v as number) : null;
  };

  // Cases that any of the listed solvers could solve (have a finite cost).
  const comparable = suite.filter((c) => solverIds.some((b) => cost(c, b) != null));
  const N = comparable.length;

  // Per (case, solver) performance ratio r_{p,s}; null where the solver has no
  // finite cost (the case is "not solved" by s — it lives at τ = ∞, never counted).
  const ratios: Record<string, number[]> = Object.fromEntries(solverIds.map((b) => [b, []]));
  for (const c of comparable) {
    const costs = solverIds.map((b) => cost(c, b)).filter((v): v is number => v != null);
    const best = Math.min(...costs);
    for (const b of solverIds) {
      const cb = cost(c, b);
      if (cb != null) ratios[b].push(cb / best);
    }
  }

  return solverIds.map((backend) => {
    const rs = ratios[backend].slice().sort((a, b) => a - b);
    if (N === 0 || rs.length === 0) {
      // Nothing solved → flat profile pinned at ρ = 0 from τ = 1.
      return { backend, points: [{ tau: 1, rho: 0 }] };
    }
    // Build the step function: at each distinct ratio τ, ρ jumps to the fraction
    // of cases (over N) with r ≤ τ. Start the curve at τ = 1 (ρ = fraction at 1).
    const points: ProfilePoint[] = [];
    const pushStep = (tau: number) => {
      const count = rs.filter((r) => r <= tau + 1e-12).length;
      const rho = count / N;
      const last = points[points.length - 1];
      if (last && last.tau === tau) last.rho = rho;
      else points.push({ tau, rho });
    };
    pushStep(1); // ρ(1) = fastest-fraction
    for (const r of rs) if (r > 1 + 1e-12) pushStep(r);
    return { backend, points };
  });
}
