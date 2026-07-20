import type { components } from "../openapi.gen";

export type BenchReport = components["schemas"]["BenchReport"];
export type Featured = components["schemas"]["Featured"];
export type BackendProfile = components["schemas"]["BackendProfile"];
// Showcase types (G18): the N-D fit + shared-model global fit carried on
// analyzed[] and rendered by the sec-showcase Evidence panels.
export type MultiDim = components["schemas"]["MultiDim"];
export type Projection = components["schemas"]["Projection"];
export type NdPeak = components["schemas"]["NdPeak"];
export type GlobalFit = components["schemas"]["GlobalFit"];
export type GlobalFitSlice = components["schemas"]["GlobalFitSlice"];
export type PeakTrace = components["schemas"]["PeakTrace"];
export type TrustBlock = components["schemas"]["TrustBlock"];
export type WireResult = components["schemas"]["WireResult"];

/** The set of schema versions this build understands. 1.5 adds the additive
 *  `BackendProfile.theta_distance` (real convergence-to-truth metric); 1.4
 *  payloads still render (the field is optional). 1.6 renames the unrendered
 *  `time_resolved` field to `global_fit`. 1.7 reshapes the unrendered `multidim`
 *  field from a 2-D map to a genuine N-D fit; older payloads still render.
 *
 *  SINGLE-SOURCED: this literal MIRRORS the canonical window
 *  `benchmark.contract.SUPPORTED_SCHEMA` (Python). It is a hand-written literal
 *  so the web tree stays independently buildable, but it is PINNED to the
 *  canonical window by `tests/unit/benchmark/test_supported_schema_window.py`,
 *  which fails CI if the two drift. Edit BOTH together (canonical first). */
export const SUPPORTED_SCHEMA = new Set(["1.4", "1.5", "1.6", "1.7"]);

/**
 * Throws an explicit error if the report's schemaVersion is not in
 * SUPPORTED_SCHEMA. This ensures the app NEVER renders blank on an
 * unrecognised payload — it always surfaces the version mismatch.
 */
export function assertSupported(r: BenchReport): void {
  if (!SUPPORTED_SCHEMA.has(r.schemaVersion)) {
    throw new Error(`unsupported schema: ${r.schemaVersion}`);
  }
}

/**
 * Return the ordered list of solver ids from the data.
 * NO hardcoded ids — enumerated from r.solvers.
 */
export function solversOf(r: BenchReport): string[] {
  return r.solvers.map((s) => s.id);
}

/**
 * Find a Featured case by id. Returns undefined when not found.
 * NO silent PRIMARY fallback — undefined is the explicit signal
 * that the requested case is missing.
 */
export function analyzedById(r: BenchReport, id: string): Featured | undefined {
  return r.analyzed.find((f) => f.id === id);
}

/**
 * The case to open by default in the single-case drill-down.
 *
 * The historical default — `analyzed[0]` (EZ-001) — is a saturated easy case
 * where every backend lands on the identical global minimum, so the Fit and
 * residual panels show no divergence at all: a misleading first impression.
 * Instead we pick the case with the LARGEST r² spread across backends (computed
 * from the suite, data-driven so it survives re-runs), restricted to cases that
 * actually exist in `analyzed` (so the drill-down can render it). This surfaces a
 * genuinely discriminating case — typically an optfn multimodal trap — on mount.
 * Falls back to `analyzed[0]` when the suite carries no usable r² spread.
 */
export function defaultCaseId(r: BenchReport): string {
  const fallback = r.analyzed?.[0]?.id ?? "";
  const analyzedIds = new Set(r.analyzed?.map((f) => f.id) ?? []);
  let best = fallback;
  let bestSpread = -1;
  for (const c of r.suite ?? []) {
    if (!analyzedIds.has(c.id)) continue;
    const r2s = Object.values(c.m)
      .map((m) => m.r2)
      .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
    if (r2s.length < 2) continue;
    const spread = Math.max(...r2s) - Math.min(...r2s);
    if (spread > bestSpread) {
      bestSpread = spread;
      best = c.id;
    }
  }
  return best;
}

/**
 * Return the BackendProfile for the given solverId within a Featured case,
 * or undefined if that solver has no entry.
 */
export function profOf(f: Featured, solverId: string): BackendProfile | undefined {
  return f.profiles?.[solverId];
}

/**
 * What this served run actually contains — derived purely from presence checks,
 * never a hardcoded denominator (a "15 of 139" would itself drift). The dashboard
 * describes speed and convergence-to-truth in its panels; if the run didn't
 * record them, that is disclosed rather than rendered as confident-but-empty.
 */
export interface RunCompleteness {
  nCases: number;
  hasSuiteTiming: boolean;
  hasConvergenceTruth: boolean;
  /** Dimensions the report's panels describe but this run did not record. */
  missing: string[];
}

export function runCompleteness(r: BenchReport): RunCompleteness {
  const nCases = r.suite?.length ?? 0;
  const hasSuiteTiming = (r.suite ?? []).some((c) =>
    Object.values(c.m).some((m) => typeof m.medMs === "number" && Number.isFinite(m.medMs)),
  );
  const hasConvergenceTruth = (r.analyzed ?? []).some((f) =>
    Object.values(f.profiles ?? {}).some(
      (p) => Array.isArray(p?.thetaDistance) && p.thetaDistance.length > 0,
    ),
  );
  const missing: string[] = [];
  if (!hasSuiteTiming) missing.push("timing");
  if (!hasConvergenceTruth) missing.push("convergence-to-truth");
  return { nCases, hasSuiteTiming, hasConvergenceTruth, missing };
}

/**
 * Fetch the latest BenchReport from the API.
 * Throws on non-ok HTTP status.
 * Calls assertSupported so an unrecognised schemaVersion always throws
 * rather than silently rendering stale/corrupt data.
 */
export async function loadReport(): Promise<BenchReport> {
  const res = await fetch("/api/report");
  if (!res.ok) throw new Error(`/api/report ${res.status}`);
  const parsed = (await res.json()) as BenchReport;
  assertSupported(parsed);
  return parsed;
}
