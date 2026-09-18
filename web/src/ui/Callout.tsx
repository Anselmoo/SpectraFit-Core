/**
 * Callout — admonition block for docs/inline notices (the zensical/mkdocs
 * equivalent of `!!! note`): a symbol-in-circle + full soft-tint card, never
 * a left-border stripe. Ported from the DesignSync handbook's
 * components/feedback/Callout.jsx, adapted onto this repo's tokens.css names.
 *
 * Token mapping notes (handbook name -> tokens.css name):
 *   --accent / --accent-soft -> --system-blue / --system-blue-soft
 *   --text-on-accent -> --text-primary (dark-only dashboard, already #FFFFFF)
 *   --success / --success-soft -> --success / --system-green-soft
 *   --warning / --warning-soft -> --warning / --system-orange-soft
 *   --danger -> --danger; no --system-red-soft exists in tokens.css, so
 *               danger's soft fill is derived locally with the same
 *               16%-alpha convention the other *-soft tokens use.
 *   --text-xs / --text-sm / --leading-normal -> no named type-scale tokens
 *               exist in tokens.css (call sites there hardcode rem sizes
 *               directly, e.g. .rung-cap at 0.8rem) — sized in kind here.
 */
import type { ReactNode } from "react";

export interface CalloutProps {
  children: ReactNode;
  /** @default "note" */
  kind?: "note" | "tip" | "warning" | "danger";
  /** Overrides the default kind label. */
  title?: string;
}

const DANGER_SOFT = "color-mix(in srgb, var(--danger) 16%, transparent)";

interface KindSpec {
  solid: string;
  soft: string;
  label: string;
  glyph: string;
  iconColor: string;
}

function kindSpecs(title: string | undefined): Record<NonNullable<CalloutProps["kind"]>, KindSpec> {
  return {
    note: { solid: "var(--system-blue)", soft: "var(--system-blue-soft)", label: title ?? "Note", glyph: "i", iconColor: "var(--text-primary)" },
    tip: { solid: "var(--success)", soft: "var(--system-green-soft)", label: title ?? "Tip", glyph: "✓", iconColor: "var(--text-primary)" },
    warning: { solid: "var(--warning)", soft: "var(--system-orange-soft)", label: title ?? "Warning", glyph: "!", iconColor: "var(--text-primary)" },
    danger: { solid: "var(--danger)", soft: DANGER_SOFT, label: title ?? "Caution", glyph: "✕", iconColor: "#fff" },
  };
}

export function Callout({ children, kind = "note", title }: CalloutProps) {
  const k = kindSpecs(title)[kind];
  // Apple-style inline banner: a symbol in a solid tinted circle + full soft-tint card —
  // no left-border stripe (that's a generic admonition pattern, not one Apple itself uses).
  return (
    <div
      style={{
        background: k.soft,
        borderRadius: "var(--radius-lg)",
        padding: "14px 16px",
        display: "flex",
        gap: "12px",
        alignItems: "flex-start",
        fontFamily: "var(--font-body)",
      }}
    >
      <span
        aria-hidden="true"
        style={{
          flexShrink: 0,
          width: "22px",
          height: "22px",
          borderRadius: "50%",
          background: k.solid,
          color: k.iconColor,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: "12px",
          fontWeight: 700,
          marginTop: "1px",
        }}
      >
        {k.glyph}
      </span>
      <div style={{ display: "flex", flexDirection: "column", gap: "4px", minWidth: 0 }}>
        <span
          style={{
            fontSize: "0.72rem",
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: "0.06em",
            color: k.solid,
          }}
        >
          {k.label}
        </span>
        {/* Body copy stays at --text-primary (not the tinted kind color) so contrast
            never drops with the softer background — handbook accessibility note. */}
        <div style={{ fontSize: "0.88rem", color: "var(--text-primary)", lineHeight: 1.5 }}>{children}</div>
      </div>
    </div>
  );
}
