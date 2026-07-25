// ---------------------------------------------------------------------------
// Shared display-formatting helpers used across series/ and panels/bodies/.
// ---------------------------------------------------------------------------

/** Below this threshold a p-value is shown as "< 0.0001" rather than rounded to 0.0000. */
export const MIN_DISPLAYABLE_P = 0.0001;

/** Format a p-value: "< 0.0001" below the display floor, else 4 decimal places. */
export function fmtP(x: number): string {
  if (x < MIN_DISPLAYABLE_P) return "< 0.0001";
  return x.toFixed(4);
}
