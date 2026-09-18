/** Token name constants — the CSS custom properties defined in tokens.css.
 *
 *  SpectraFit Design System v3.2 adoption (2026-07-28): every key below was
 *  renamed or newly added to track tokens.css's real handbook-derived names.
 *  `find_referencing_symbols` on the pre-adoption `TOKEN_NAMES` confirmed it
 *  had zero consumers anywhere else in web/src (only its own file used it, to
 *  derive the `TokenName` type) — so the old string keys (bg, surface,
 *  surface2, hairline, ink, inkDim, inkFaint, accent, pass, warn, fail,
 *  radius, motion) were dropped outright rather than kept as deprecated
 *  aliases; there was nothing depending on them to preserve. */
export const TOKEN_NAMES = {
  surfacePage: "--surface-page",
  surfaceCard: "--surface-card",
  surfaceRaised: "--surface-raised",
  glassBlur: "--glass-blur",
  borderSubtle: "--border-subtle",
  borderStrong: "--border-strong",
  textPrimary: "--text-primary",
  textSecondary: "--text-secondary",
  textTertiary: "--text-tertiary",
  systemBlue: "--system-blue",
  systemIndigo: "--system-indigo",
  provMeasured: "--prov-measured",
  provDerived: "--prov-derived",
  provReconstructed: "--prov-reconstructed",
  provAbsent: "--prov-absent",
  absentText: "--absent-text",
  success: "--success",
  warning: "--warning",
  danger: "--danger",
  fontDisplay: "--font-display",
  fontBody: "--font-body",
  fontMono: "--font-mono",
  space1: "--space-1",
  space2: "--space-2",
  space3: "--space-3",
  space4: "--space-4",
  space5: "--space-5",
  space6: "--space-6",
  space7: "--space-7",
  space8: "--space-8",
  space9: "--space-9",
  radiusSm: "--radius-sm",
  radiusMd: "--radius-md",
  radiusLg: "--radius-lg",
  radiusXl: "--radius-xl",
  radiusFull: "--radius-full",
  motionFast: "--motion-fast",
  motionBase: "--motion-base",
  motionSlow: "--motion-slow",
  layoutProse: "--layout-prose",
  layoutContent: "--layout-content",
  layoutNav: "--layout-nav",
} as const;

export type TokenName = (typeof TOKEN_NAMES)[keyof typeof TOKEN_NAMES];
