/**
 * Button — standard action button (form submits, dialog confirms, toolbar
 * actions, CLI-style "run" triggers). Ported from the DesignSync handbook's
 * components/core/Button.jsx, adapted onto this repo's tokens.css names.
 *
 * Token mapping notes (handbook name -> tokens.css name):
 *   --accent            -> --system-blue
 *   --accent-soft       -> --system-blue-soft   (focus ring)
 *   --accent-hover /
 *   --accent-active     -> no dedicated ramp step exists in tokens.css yet;
 *                          derived locally with color-mix(), the same technique
 *                          tokens.css itself uses for --blue-200/--blue-400.
 *   --text-on-accent    -> --text-primary (this dashboard is dark-only and
 *                          --text-primary is #FFFFFF, which is what accent-filled
 *                          buttons need for contrast).
 *   --surface-sunken    -> --surface-page (the darkest/most-recessed surface
 *                          this dashboard has).
 */
import { useState } from "react";
import type { ReactNode, CSSProperties } from "react";

export interface ButtonProps {
  /** Button label / content. */
  children: ReactNode;
  /** @default "primary" */
  variant?: "primary" | "secondary" | "ghost" | "danger";
  /** @default "md" */
  size?: "sm" | "md" | "lg";
  disabled?: boolean;
  /** Optional leading icon node. */
  icon?: ReactNode;
  onClick?: () => void;
  type?: "button" | "submit";
}

const ACCENT_HOVER = "color-mix(in srgb, var(--system-blue) 88%, black)";
const ACCENT_ACTIVE = "color-mix(in srgb, var(--system-blue) 72%, black)";
const DANGER_HOVER = "color-mix(in srgb, var(--danger) 90%, black)";

const PAD: Record<NonNullable<ButtonProps["size"]>, string> = {
  sm: "6px 12px",
  md: "9px 16px",
  lg: "12px 22px",
};
const FONT_SIZE: Record<NonNullable<ButtonProps["size"]>, string> = {
  sm: "12.5px",
  md: "13.5px",
  lg: "15px",
};

export function Button({
  children,
  variant = "primary",
  size = "md",
  disabled = false,
  icon = null,
  onClick,
  type = "button",
}: ButtonProps) {
  const [hover, setHover] = useState(false);
  const [pressed, setPressed] = useState(false);

  const base: CSSProperties = {
    fontFamily: "var(--font-body)",
    fontWeight: 600,
    fontSize: FONT_SIZE[size],
    padding: PAD[size],
    borderRadius: "var(--radius-md)",
    border: "1px solid transparent",
    cursor: disabled ? "not-allowed" : "pointer",
    display: "inline-flex",
    alignItems: "center",
    gap: "8px",
    transition:
      "background var(--motion-fast) var(--ease-standard), border-color var(--motion-fast), color var(--motion-fast)",
    opacity: disabled ? 0.5 : 1,
    lineHeight: 1.2,
    boxShadow: hover && !disabled ? "0 0 0 3px var(--system-blue-soft)" : "none",
  };

  // Hover/press = a darker step on the same brand ramp (accent -> hover -> active),
  // never an opacity fade — matches the ramp-step convention used across this system.
  const variants: Record<NonNullable<ButtonProps["variant"]>, CSSProperties> = {
    primary: {
      background: pressed ? ACCENT_ACTIVE : hover ? ACCENT_HOVER : "var(--system-blue)",
      color: "var(--text-primary)",
      borderColor: pressed ? ACCENT_ACTIVE : hover ? ACCENT_HOVER : "var(--system-blue)",
    },
    secondary: {
      background: hover ? "var(--surface-page)" : "var(--surface-card)",
      color: "var(--text-primary)",
      borderColor: "var(--border-strong)",
    },
    ghost: {
      background: hover ? "var(--system-blue-soft)" : "transparent",
      color: "var(--system-blue)",
      borderColor: "transparent",
    },
    danger: {
      background: hover ? DANGER_HOVER : "var(--danger)",
      color: "var(--text-primary)",
      borderColor: "var(--danger)",
    },
  };

  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => {
        setHover(false);
        setPressed(false);
      }}
      onFocus={() => setHover(true)}
      onBlur={() => setHover(false)}
      onMouseDown={() => setPressed(true)}
      onMouseUp={() => setPressed(false)}
      style={{ ...base, ...variants[variant] }}
    >
      {icon}
      {children}
    </button>
  );
}
