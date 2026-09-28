/**
 * Badge — small non-interactive status pill (version tags, gate pass/fail,
 * backend/solver labels). Ported from the DesignSync handbook's
 * components/core/Badge.jsx, adapted onto this repo's tokens.css names.
 *
 * Token mapping notes (handbook name -> tokens.css name):
 *   --surface-sunken -> --surface-page (neutral tone's recessed background)
 *   --accent / --accent-soft -> --system-blue / --system-blue-soft
 *   --accent-hover (accent tone's text color) -> derived color-mix, same
 *                    technique tokens.css uses for --blue-200/--blue-400
 *   --success / --success-soft -> --success / --system-green-soft
 *   --warning / --warning-soft -> --warning / --system-orange-soft
 *   --danger  -> --danger (var(--system-red)); no --system-red-soft exists in
 *                tokens.css, so danger's soft fill is derived locally with the
 *                same 16%-alpha convention the other *-soft tokens use.
 */
import type { ReactNode } from "react";

export interface BadgeProps {
  children: ReactNode;
  /** @default "neutral" */
  tone?: "neutral" | "accent" | "success" | "warning" | "danger";
  /** @default "md" */
  size?: "sm" | "md";
}

const ACCENT_TEXT = "color-mix(in srgb, var(--system-blue) 88%, black)";
const DANGER_SOFT = "color-mix(in srgb, var(--danger) 16%, transparent)";

const TONES: Record<NonNullable<BadgeProps["tone"]>, { background: string; color: string; border: string }> = {
  neutral: { background: "var(--surface-page)", color: "var(--text-secondary)", border: "var(--border-subtle)" },
  accent: { background: "var(--system-blue-soft)", color: ACCENT_TEXT, border: "transparent" },
  success: { background: "var(--system-green-soft)", color: "var(--success)", border: "transparent" },
  warning: { background: "var(--system-orange-soft)", color: "var(--warning)", border: "transparent" },
  danger: { background: DANGER_SOFT, color: "var(--danger)", border: "transparent" },
};

export function Badge({ children, tone = "neutral", size = "md" }: BadgeProps) {
  const t = TONES[tone];
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "5px",
        fontFamily: "var(--font-mono)",
        fontSize: size === "sm" ? "10.5px" : "11.5px",
        fontWeight: 600,
        letterSpacing: "0.03em",
        textTransform: "uppercase",
        padding: size === "sm" ? "2px 7px" : "3px 9px",
        borderRadius: "var(--radius-full)",
        background: t.background,
        color: t.color,
        border: `1px solid ${t.border}`,
      }}
    >
      {children}
    </span>
  );
}
