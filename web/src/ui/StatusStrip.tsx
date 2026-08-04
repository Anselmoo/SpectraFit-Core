/**
 * StatusStrip — flat, non-blurred disclosure strip for persistent status
 * banners (preview-run completeness, dev-stack liveness).
 *
 * Not one of the design handbook's 9 named core components — built directly
 * from its guidelines/patterns-status-disclosure.card.html sample, which
 * documents the brand's "state your own limitations" voice rule as a
 * persistent UI strip: flat --surface-sunken background, 1px --border-subtle
 * border, --radius-md corners, no blur, a leading tone-pill + body text. Per
 * the handbook's explicit retirement of the left-border-accent admonition
 * pattern, there is deliberately NO borderLeft accent stripe here — the pill
 * carries the warning signal instead.
 *
 * EXTENSION over the sample: an optional `action` slot for a trailing
 * control. The handbook's own pattern sample has no action slot — this is a
 * documented spectrafit-core-specific extension, not a silent departure:
 * LivenessBanner's "stale" state needs to offer a manual reload inline with
 * the message rather than bolting an ad hoc button on next to a shared
 * component.
 */
import type { CSSProperties, ReactNode } from "react";

export interface StatusStripProps {
  /** Leading tone-pill text, e.g. "Preview run", "Dev stack unreachable". */
  pillLabel: string;
  /** Body copy for the strip. */
  children: ReactNode;
  /** Trailing action, e.g. a Reload button. See file-level doc above. */
  action?: ReactNode;
  /** @default "status" */
  role?: string;
  ariaLabel?: string;
  /** Escape hatch for caller-side layout concerns (e.g. maxWidth). */
  style?: CSSProperties;
}

export function StatusStrip({ pillLabel, children, action, role = "status", ariaLabel, style }: StatusStripProps) {
  return (
    <div
      role={role}
      aria-label={ariaLabel}
      style={{
        width: "100%",
        display: "flex",
        alignItems: "center",
        gap: "var(--space-3)",
        background: "var(--surface-sunken)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-md)",
        padding: "10px 14px",
        ...style,
      }}
    >
      <span
        style={{
          flexShrink: 0,
          fontFamily: "var(--font-mono)",
          fontSize: "10px",
          fontWeight: 700,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          padding: "4px 9px",
          borderRadius: "var(--radius-full)",
          background: "var(--warning-soft)",
          color: "var(--warning)",
        }}
      >
        {pillLabel}
      </span>
      <span style={{ flex: 1, fontSize: "0.8rem", color: "var(--text-secondary)", lineHeight: 1.4 }}>
        {children}
      </span>
      {action}
    </div>
  );
}
