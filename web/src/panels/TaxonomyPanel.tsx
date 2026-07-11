/**
 * Failure-mode taxonomy — the dashboard's falsification record.
 *
 * Six catches (2 Track-0 engine self-catches + 4 render-defect catches) from the
 * audit pipeline running against the engine itself and the Playwright render-audit.
 * This is a BESPOKE .glass card (matching the wire-matrix card pattern) — AuditPanel
 * renders audit records bare, so this card carries its own single <h2> heading.
 *
 * Wave B2: Track-0 self-catches elevated as warm signpost (Kare), render-defects
 * collapsed behind progressive disclosure (Jobs).
 */
import { useState } from "react";
import { FAILURE_MODES } from "./taxonomy";
import type { FailureMode } from "./taxonomy";

export function TaxonomyPanel() {
  const [expanded, setExpanded] = useState(false);

  // Track-0 catches (category="track0") are always visible — they're the heart of the story.
  // Render-defect catches (category="render") are collapsed by default (Jobs — reduction).
  const alwaysVisible = FAILURE_MODES.filter((m) => m.category === "track0");
  const collapsible = FAILURE_MODES.filter((m) => m.category === "render");

  const renderRow = (m: FailureMode) => (
    <li
      key={m.bug}
      data-failure-row
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: "var(--s3)",
        padding: "var(--s3)",
        borderRadius: 8,
        background: "var(--surface-2)",
      }}
    >
      <div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "0.84rem", color: "var(--ink)" }}>{m.bug}</div>
        <div style={{ fontSize: "0.8rem", color: "var(--fail)", marginTop: "var(--s1)" }}>before · {m.before}</div>
      </div>
      <div>
        <div style={{ fontSize: "0.8rem", color: "var(--pass)" }}>fix · {m.fix}</div>
        <div
          style={{
            fontSize: "0.76rem",
            color: "var(--ink-faint)",
            fontFamily: "var(--font-mono)",
            marginTop: "var(--s1)",
          }}
        >
          guard · {m.guard}
        </div>
      </div>
    </li>
  );

  return (
    <div className="glass" style={{ padding: "var(--s6)" }}>
      {/* Kare — warm signpost: name the story, not just the list */}
      <h2
        style={{
          margin: "0 0 var(--s2)",
          fontFamily: "var(--font-display)",
          fontWeight: 300,
          fontSize: "1.1rem",
          color: "var(--ink)",
          letterSpacing: "-0.01em",
        }}
      >
        What we caught in ourselves
      </h2>
      <p
        data-taxonomy-lead
        style={{ margin: "0 0 var(--s4)", fontSize: "0.8rem", color: "var(--ink-faint)", lineHeight: 1.6 }}
      >
        A benchmark that can{"’"}t catch its own mistakes isn{"’"}t trustworthy. The two catches below
        came from the audit pipeline running against the engine itself — not a reviewer, not a user — before we
        published the rung. The render-defect catches below them came from the Playwright audit that checks the
        dashboard as it actually renders.
      </p>

      {/* Always-visible: Track-0 self-catches */}
      {alwaysVisible.length > 0 && (
        <>
          <div
            style={{
              fontSize: "0.72rem",
              fontFamily: "var(--font-mono)",
              fontWeight: 600,
              letterSpacing: "0.05em",
              textTransform: "uppercase",
              color: "var(--ink-faint)",
              margin: "0 0 var(--s2)",
            }}
          >
            Engine self-catches (Track 0)
          </div>
          <ul
            style={{
              listStyle: "none",
              margin: "0 0 var(--s4)",
              padding: 0,
              display: "flex",
              flexDirection: "column",
              gap: "var(--s2)",
            }}
          >
            {alwaysVisible.map(renderRow)}
          </ul>
        </>
      )}

      {/* Progressive disclosure: render-defect catches (Jobs — collapse the wall) */}
      {collapsible.length > 0 && (
        <>
          <button
            data-taxonomy-expand
            onClick={() => setExpanded((v) => !v)}
            style={{
              background: "none",
              border: "1px solid var(--hairline)",
              borderRadius: 4,
              color: "var(--accent)",
              cursor: "pointer",
              fontFamily: "var(--font-mono)",
              fontSize: "0.75rem",
              padding: "var(--s1) var(--s3)",
              marginBottom: "var(--s3)",
            }}
            aria-expanded={expanded}
          >
            {expanded ? "▴ Hide render-defect catches" : "▾ Show render-defect catches"}
            {" "}({collapsible.length})
          </button>
          {expanded && (
            <ul
              style={{
                listStyle: "none",
                margin: 0,
                padding: 0,
                display: "flex",
                flexDirection: "column",
                gap: "var(--s2)",
              }}
            >
              {collapsible.map(renderRow)}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
