// ---------------------------------------------------------------------------
// Success / convergence rate per (category, backend).
//
// successFraction = mean over the category's cases of whether that backend
// reported a successful solve. The first robustness question a referee asks:
// "how often does it actually converge?"
// ---------------------------------------------------------------------------

export interface SuccessRow {
  category: string;
  backend: string;
  successFraction: number;
}

export function successRateSeries(report: any, solverIds: string[]): SuccessRow[] {
  const suite: any[] = Array.isArray(report?.suite) ? report.suite : [];
  const categories = [...new Set(suite.map((c) => c?.category).filter((c): c is string => typeof c === "string"))];

  const rows: SuccessRow[] = [];
  for (const category of categories) {
    const cases = suite.filter((c) => c?.category === category);
    for (const backend of solverIds) {
      const flags: number[] = cases.filter((c) => c?.m?.[backend] != null).map((c) => (c.m[backend].success ? 1 : 0));
      if (flags.length === 0) continue; // no measured cases → omit (don't fabricate 0)
      const successFraction = flags.reduce((a, b) => a + b, 0) / flags.length;
      rows.push({ category, backend, successFraction });
    }
  }
  return rows;
}
