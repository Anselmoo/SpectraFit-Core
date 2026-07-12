/**
 * Global-fit showcase body (G18, SP-3).
 *
 * Renders the `analyzed[].globalFit` block from the first case that carries it:
 * the joint multi-dataset fit (one shared model — shared peak centers/widths —
 * across every slice of the series) + the per-peak amplitude kinetics the
 * joint fit recovers along the dataset axis.
 *
 * spec: global-fit-slices, global-fit-kinetics (plots/spec.ts — descriptive).
 * Honest empty-state when the served run predates the showcase.
 */
import type { CSSProperties, ReactNode } from "react";
import type { BenchReport } from "../../contract";
import { PlotMount } from "../../plots/PlotMount";
import { globalFitKineticsPlot, globalFitSlicesPlot } from "../../plots/globalFit";

const MONO: CSSProperties = { fontFamily: "var(--font-mono)" };

export function globalFitShowcaseBody(report: BenchReport): ReactNode {
  const gf = report.analyzed?.find((f) => f.globalFit != null)?.globalFit ?? null;

  if (gf == null) {
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
        The shared-model joint fit (<code>GlobalFitGraph</code>, SP-3) is{" "}
        <strong>implemented</strong> but this served run did not record the
        showcase. Regenerate the benchmark to populate it; the panel then shows
        every slice fitted by one joint model plus the recovered per-peak
        amplitude kinetics.
      </p>
    );
  }

  return (
    <>
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
        <span style={{ color: "var(--ink-faint)" }}>Series</span>
        <span style={{ color: "var(--ink)", fontWeight: 600 }}>
          {gf.slices.length} slices along {gf.axisLabel}
        </span>
        <span style={{ color: "var(--ink-faint)" }}>Shared peaks</span>
        <span>
          {gf.traces
            .map((t) => `${t.label} (c=${t.center.toFixed(2)}, σ=${t.sigma.toFixed(2)})`)
            .join(" · ")}
        </span>
      </div>
      <PlotMount make={(w) => globalFitSlicesPlot(gf, { width: w })} deps={[report]} />
      <PlotMount make={(w) => globalFitKineticsPlot(gf, { width: w })} deps={[report]} />
      <p style={{ margin: "var(--s3) 0 0", fontSize: "0.72rem", color: "var(--ink-faint)", ...MONO }}>
        Data provenance: {gf.dataProvenance} — one <code>GlobalFitGraph</code> joint fit by{" "}
        {gf.source}; peak centers and widths are shared across slices, amplitudes vary per slice.
      </p>
    </>
  );
}
