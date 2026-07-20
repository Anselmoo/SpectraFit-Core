/**
 * Spectrum series builders — pure data transforms; no DOM, no colors.
 * Subject-blind: callers pass solverIds from solversOf(report).
 */

export interface XY { x: number; y: number; }
export interface FitLine { backend: string; rows: Array<XY & { backend: string }>; }
export interface SpectrumSeries { ref: XY[]; guess: XY[]; fits: FitLine[]; }

const zip = (x: number[], y: number[]): XY[] => x.map((xi, i) => ({ x: xi, y: y[i] }));

/**
 * Build ref markers, guess line, and one fit line per solver id.
 * Backends missing from f.profiles are silently skipped (no ghost entries).
 */
export function spectrumSeries(f: any, solverIds: string[]): SpectrumSeries {
  return {
    ref: zip(f.x, f.ref),
    guess: zip(f.x, f.guess),
    fits: solverIds
      .filter((id) => f.profiles?.[id]?.fit?.curve)
      .map((id) => ({
        backend: id,
        rows: f.x.map((xi: number, i: number) => ({ x: xi, y: f.profiles[id].fit.curve[i], backend: id })),
      })),
  };
}

export interface MetricRow {
  backend: string;
  r2: number;
  redChi2: number;
  rmse: number;
  speedup: number;
  nIter: number;
}

/**
 * Project per-backend summary metrics into a flat row per solver.
 * Backends missing from f.profiles are skipped.
 */
export function metricRows(f: any, solverIds: string[]): MetricRow[] {
  return solverIds
    .filter((id) => f.profiles?.[id]?.summary)
    .map((id) => {
      const s = f.profiles[id].summary;
      return { backend: id, r2: s.r2, redChi2: s.redChi2, rmse: s.rmse, speedup: s.speedup, nIter: s.nIter };
    });
}

/**
 * Flatten all backend residuals into a single array of tagged rows, normalized
 * to ONE sign convention (obs − fit) regardless of how each backend stored it.
 *
 * Backends disagree on residual sign: spectrafit/lmfit/jax store `obs − fit`
 * while the scipy-ls family stores `fit − obs`, so a raw plot of the stored
 * `resid` draws the scipy-ls lines as a mirror image (same magnitude, opposite
 * sign). We fix this in the web by RECOMPUTING `ref − fit.curve` whenever both
 * the reference spectrum and the fit curve are present — the convention is then
 * web-controlled and identical for every backend, no backend ids hardcoded.
 * Only when a curve is missing do we fall back to the stored `resid`.
 *
 * Backends with neither a fit curve nor a stored resid are skipped.
 */
export function residualRows(f: any, solverIds: string[]): Array<XY & { backend: string }> {
  return solverIds.flatMap((id) => {
    const fit = f.profiles?.[id]?.fit;
    if (!fit) return [];
    const curve = fit.curve as number[] | undefined;
    const stored = fit.resid as number[] | undefined;
    if (curve && f.ref) {
      // Web-controlled convention: obs − fit, recomputed from data.
      return f.x.map((xi: number, i: number) => ({ x: xi, y: f.ref[i] - curve[i], backend: id }));
    }
    if (stored) {
      return f.x.map((xi: number, i: number) => ({ x: xi, y: stored[i], backend: id }));
    }
    return [];
  });
}
