/**
 * Card — general-purpose content container (dashboard metric tiles, docs
 * content blocks, settings groups).
 *
 * Ported from the design handbook's components/core/Card.jsx (+ Card.d.ts):
 * an optional title/subtitle header, a body slot, and an optional footer
 * separated by a hairline — never more than these three regions. `padding`
 * scales all three uniformly.
 *
 * EXTENSION over the handbook source: forwards `ref` to the body wrapper div.
 * The handbook's own Card.jsx does not forward refs at all — this repo needs
 * it because web/src/panels/chrome.tsx's PanelCard hands that ref straight to
 * ExportButton's `containerRef`, which `querySelector("svg")`s inside it to
 * find a chart to export. The ref intentionally targets the *body* div, not
 * the outer card shell, so the query stays scoped to rendered content.
 */
import { forwardRef } from "react";
import type { ReactNode } from "react";

export interface CardProps {
  children?: ReactNode;
  title?: string;
  subtitle?: string;
  footer?: ReactNode;
  /** @default "md" */
  padding?: "sm" | "md" | "lg";
}

const PAD: Record<NonNullable<CardProps["padding"]>, string> = {
  sm: "14px",
  md: "20px",
  lg: "28px",
};

export const Card = forwardRef<HTMLDivElement, CardProps>(function Card(
  { children, title, subtitle, footer, padding = "md" },
  ref,
) {
  return (
    <div
      style={{
        background: "var(--surface-card)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-lg)",
        boxShadow: "var(--shadow-sm)",
        padding: PAD[padding],
        display: "flex",
        flexDirection: "column",
        gap: "10px",
      }}
    >
      {(title || subtitle) && (
        <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
          {title && (
            <h3
              style={{
                margin: 0,
                fontFamily: "var(--font-display)",
                fontSize: "1rem",
                fontWeight: 600,
                color: "var(--text-primary)",
              }}
            >
              {title}
            </h3>
          )}
          {subtitle && (
            <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--text-secondary)" }}>{subtitle}</p>
          )}
        </div>
      )}
      <div ref={ref} style={{ color: "var(--text-primary)", fontSize: "0.85rem" }}>
        {children}
      </div>
      {footer && (
        <div
          style={{
            borderTop: "1px solid var(--border-subtle)",
            paddingTop: "10px",
            display: "flex",
            gap: "8px",
          }}
        >
          {footer}
        </div>
      )}
    </div>
  );
});
