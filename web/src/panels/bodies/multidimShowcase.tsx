/**
 * Multi-dimensional fit showcase body (G18, SP-2).
 *
 * Renders the `analyzed[].multidim` block from the first case that carries it
 * (the engine attaches the showcase to the featured case only): headline
 * stats (D, grid shape, points, r²) + per-peak recovered parameters + one
 * axis-pair projection heatmap per `Projection`.
 *
 * spec: multidim-projection (see plots/spec.ts — descriptive, no verdict).
 * Honest empty-state when the served run predates the showcase — the engine
 * capability exists; this run just didn't record it.
 */
import type { CSSProperties, ReactNode } from "react";
import type { BenchReport, MultiDim } from "../../contract";
import { PlotMount } from "../../plots/PlotMount";
import { multidimProjectionHeatmap } from "../../plots/multidim";

const MONO: CSSProperties = { fontFamily: "var(--font-mono)" };

function fmt(x: number): string {
  return Number.isInteger(x) ? String(x) : x.toFixed(3);
}

function StatsGrid({ md }: { md: MultiDim }): ReactNode {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "auto 1fr",
        gap: "var(--s1) var(--s4)",
        ...MONO,
        fontSize: "0.82rem",
        marginBottom: "var(--s4)",
      }}
    >
      <span style={{ color: "var(--ink-faint)" }}>Dimensions</span>
      <span style={{ color: "var(--ink)", fontWeight: 600 }}>{md.nDims}-D</span>
      <span style={{ color: "var(--ink-faint)" }}>Grid</span>
      <span>
        {md.shape.join(" × ")} ({md.nPoints.toLocaleString()} points)
      </span>
      <span style={{ color: "var(--ink-faint)" }}>r²</span>
      <span style={{ color: "var(--ink)", fontWeight: 600 }}>{md.rSquared.toFixed(4)}</span>
      {md.peaks.map((p, i) => (
        <span key={`peak-${i}`} style={{ display: "contents" }}>
          <span style={{ color: "var(--ink-faint)" }}>Peak {i} (A={fmt(p.amplitude)})</span>
          <span>
            center [{p.center.map(fmt).join(", ")}] · σ [{p.sigma.map(fmt).join(", ")}]
          </span>
        </span>
      ))}
    </div>
  );
}

export function multidimShowcaseBody(report: BenchReport): ReactNode {
  const md = report.analyzed?.find((f) => f.multidim != null)?.multidim ?? null;

  if (md == null) {
    return (
      <p
        style={{
          margin: 0,
          fontSize: "0.85rem",
          color: "var(--ink-faint)",
          ...MONO,
          lineHeight: 1.5,
        }}
      >
        The native N-D kernel (<code>gaussian_nd</code>, SP-2) is{" "}
        <strong>implemented</strong> but this served run did not record the
        showcase. Regenerate the benchmark to populate it; the panel then shows
        the fitted N-D surface's axis-pair projections and recovered peak
        parameters.
      </p>
    );
  }

  return (
    <>
      <StatsGrid md={md} />
      {md.projections.map((proj, i) => (
        <PlotMount
          key={`proj-${i}`}
          make={(w) => multidimProjectionHeatmap(proj, { width: w })}
          deps={[report, i]}
        />
      ))}
      <p style={{ margin: "var(--s3) 0 0", fontSize: "0.72rem", color: "var(--ink-faint)", ...MONO }}>
        Data provenance: {md.dataProvenance} — fitted by {md.source}'s native{" "}
        <code>gaussian_nd</code> kernel (the subject, not an oracle).
      </p>
    </>
  );
}
