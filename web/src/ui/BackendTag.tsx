/**
 * BackendTag — colored-dot identity chip for a solver/backend.
 *
 * Ported from the DesignSync handbook (components/data/BackendTag.jsx). The
 * handbook's own `dotHue` backend-name map is intentionally NOT reproduced
 * here: spectrafit-core's real backend colors come from
 * python/oracles/cases.py's SOLVER_META list, flow through the OpenAPI
 * contract as report.solvers[].color/.soft, and reach this component via the
 * `color` prop — the PRIMARY integration point. This component supplies
 * markup + accessibility structure only, never backend-color policy.
 *
 * Static, non-interactive — same rule as Badge. If a backend chip needs to be
 * clickable (e.g. to filter a table by backend), wrap it in a ghost button
 * rather than adding click handling here.
 *
 * Accessibility: the dot is decorative reinforcement only — `label` (or the
 * `backend` fallback) is real text carrying the identity, so color-blind
 * users and screen readers get the same information sighted users do from
 * the dot.
 */
import type { ReactElement } from "react";

export interface BackendTagProps {
  /** Backend identity key (e.g. "spectrafit", "lmfit"). Used as the label fallback. */
  backend?: string;
  /** Display text; defaults to `backend`. */
  label?: string;
  /** Dot color (CSS color value) — sourced from the contract's report.solvers[].color/.soft, never a local map. */
  color?: string;
}

export function BackendTag({ backend, label, color }: BackendTagProps): ReactElement {
  const dot = color ?? "var(--text-tertiary)";
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "6px",
        fontFamily: "var(--font-mono)",
        fontSize: "11.5px",
        color: "var(--text-secondary)",
        // --surface-sunken (handbook token) does not exist in this project's tokens.css;
        // --surface-raised is the closest equivalent already defined here.
        background: "var(--surface-raised)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-full)",
        padding: "3px 10px 3px 8px",
      }}
    >
      <span
        aria-hidden
        style={{
          width: "8px",
          height: "8px",
          borderRadius: "50%",
          background: dot,
          flexShrink: 0,
        }}
      />
      {label ?? backend}
    </span>
  );
}
