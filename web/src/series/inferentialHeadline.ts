// ---------------------------------------------------------------------------
// Inferential-headline series helpers (W10 + W11).
//
// Derives human-readable verdict rows from `CalibrationResult` (W10) and
// `SpeedInferenceResult` (W11). All values come from the contract; nothing
// is hardcoded. Subject-blind: no reference to solver ids.
// ---------------------------------------------------------------------------
import type { components } from "../openapi.gen";

export type CalibrationResult = components["schemas"]["CalibrationResult"];
export type SpeedInferenceResult = components["schemas"]["SpeedInferenceResult"];

/**
 * One row in a verdict table.
 *
 *  - `label`   : human-readable row name
 *  - `value`   : formatted value string
 *  - `pass`    : verdict (true = pass, false = fail, null = informational)
 */
export interface VerdictRow {
  label: string;
  value: string;
  pass: boolean | null;
}

function fmtP(x: number): string {
  if (x < 0.0001) return "< 0.0001";
  return x.toFixed(4);
}

function fmtPct(x: number): string {
  return (x * 100).toFixed(1) + "%";
}

function fmtX(x: number): string {
  return x.toFixed(2) + "×";
}

/**
 * Project a `CalibrationResult` into verdict rows for display.
 * Returns `null` when called with a nullish value OR when the record is
 * marked `skipped === true` (insufficient pulls — callers should render the
 * "not exercised" note, not a fail badge).
 *
 * Primary verdict: binomial p against alpha (pass = coverage is consistent
 * with the nominal 1σ band).
 * Secondary diagnostic: KS test (distribution shape, not just the mean).
 */
export function calibrationRows(cal: CalibrationResult | null | undefined): VerdictRow[] | null {
  if (cal == null || cal.skipped) return null;

  const ciStr = `[${fmtPct(cal.coverageCiLo)}, ${fmtPct(cal.coverageCiHi)}]`;

  return [
    {
      label: "coverage (nominal 1σ = 68.27%)",
      value: `${fmtPct(cal.coverage)} 95% CI ${ciStr}`,
      pass: null, // informational — verdict is binomial p below
    },
    {
      label: "binomial p (primary, W10)",
      value: fmtP(cal.binomialP),
      pass: cal.passed,
    },
    {
      label: "KS p (secondary diagnostic)",
      value: fmtP(cal.ksP),
      pass: null, // informational — KS is a secondary check, not the W10 gate
    },
  ];
}

/**
 * Project a `SpeedInferenceResult` into verdict rows for display.
 * Returns `null` when called with a nullish value OR when the record is
 * marked `skipped === true` (fewer than 2 valid speedups — callers should
 * render the "not exercised" note, not a fail badge).
 *
 * Primary verdict: geomean speedup CI excludes 1 and passes sign-test / Wilcoxon.
 * Secondary diagnostic: sign-test and Wilcoxon p-values.
 */
export function speedRows(speed: SpeedInferenceResult | null | undefined): VerdictRow[] | null {
  if (speed == null || speed.skipped) return null;

  const ciStr = `[${fmtX(speed.ciLo)}, ${fmtX(speed.ciHi)}]`;

  return [
    {
      label: "geomean speedup (primary, W11)",
      value: `${fmtX(speed.geomeanSpeedup)} 95% CI ${ciStr}`,
      pass: speed.passed,
    },
    {
      label: "CI excludes 1×",
      value: speed.excludesOne ? "yes" : "no",
      pass: speed.excludesOne,
    },
    {
      label: "sign-test p (secondary)",
      value: fmtP(speed.signP),
      pass: null, // informational
    },
    {
      label: "Wilcoxon p (secondary)",
      value: fmtP(speed.wilcoxonP),
      pass: null, // informational
    },
  ];
}
