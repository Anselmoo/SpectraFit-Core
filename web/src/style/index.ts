/** Token name constants — the CSS custom properties defined in tokens.css. */
export const TOKEN_NAMES = {
  bg: "--bg",
  surface: "--surface",
  surface2: "--surface-2",
  glassBlur: "--glass-blur",
  hairline: "--hairline",
  ink: "--ink",
  inkDim: "--ink-dim",
  inkFaint: "--ink-faint",
  accent: "--accent",
  provMeasured: "--prov-measured",
  provDerived: "--prov-derived",
  provReconstructed: "--prov-reconstructed",
  provAbsent: "--prov-absent",
  pass: "--pass",
  warn: "--warn",
  fail: "--fail",
  fontDisplay: "--font-display",
  fontBody: "--font-body",
  fontMono: "--font-mono",
  radius: "--radius",
  motion: "--motion",
} as const;

export type TokenName = (typeof TOKEN_NAMES)[keyof typeof TOKEN_NAMES];
