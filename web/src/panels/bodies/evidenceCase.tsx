/**
 * Evidence-case destination body functions (dest: "evidence", scope: "case").
 */
import type { ReactNode } from "react";
import type { BenchReport } from "../../contract";
import type { PanelCtx } from "../types";
import { spectrumSeries, metricRows, residualRows } from "../../series/spectrum";
import { spectrumPlot, residualPlot } from "../../plots/spectrum";
import { peakRows } from "../../series/peaks";
import { peaksPlot } from "../../plots/peaks";
import { recoveryRows } from "../../series/recovery";
import { recoveryPlot } from "../../plots/recovery";
import { pullSeries } from "../../series/pulls";
import { pullsPlot } from "../../plots/pulls";
import { convSeries, thetaDistanceSeries } from "../../series/convergence";
import { convergencePlot, thetaDistancePlot } from "../../plots/convergence";
import { timingBoxes } from "../../series/timing";
import { timingBoxPlot } from "../../plots/timing";
import { warmupLines } from "../../series/warmup";
import { warmupPlot } from "../../plots/warmup";
import { scalingLines } from "../../series/scaling";
import { scalingPlot } from "../../plots/scaling";
import { stabilityBand } from "../../series/stability";
import { stabilityPlot } from "../../plots/stability";
import { kappaRows, topCouplings } from "../../series/conditioning";
import { conditioningPlot } from "../../plots/conditioning";
import { accuracyBoxes } from "../../series/accuracy";
import { accuracyBoxPlot } from "../../plots/accuracyBox";
import { infoCriteriaRows } from "../../series/infoCriteria";
import { residualQQSeries } from "../../series/residualQQ";
import { residualQQPlot } from "../../plots/residualQQ";
import { iterationsSeries } from "../../series/iterations";
import { iterationsPlot } from "../../plots/iterations";
import { PlotMount } from "../../plots/PlotMount";
import { AnyCase, selectedCase, solverLabelMap } from "./shared";

// ===========================================================================
// Evidence — single-case panels (composite ReactNode bodies)
// ===========================================================================

export function fitBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  const f = selectedCase(report, ctx);
  const solverIds = ctx.solverIds;
  const colors = ctx.colors;
  const solverLabel = solverLabelMap(report);
  if (f == null) {
    return (
      <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--ink-faint)", fontFamily: "var(--font-mono)" }}>
        No analyzed cases in this report.
      </p>
    );
  }
  const metrics = metricRows(f as AnyCase, solverIds);
  return (
    <>
      {/* HTML legend — swatch + label per backend */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--s3)", marginBottom: "var(--s3)" }}>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 5,
            fontSize: "0.76rem",
            color: "var(--ink-dim)",
            fontFamily: "var(--font-mono)",
          }}
        >
          <span
            style={{
              display: "inline-block",
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: "var(--ink-dim)",
              opacity: 0.55,
            }}
          />
          reference
        </span>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 5,
            fontSize: "0.76rem",
            color: "var(--ink-dim)",
            fontFamily: "var(--font-mono)",
          }}
        >
          <span
            style={{
              display: "inline-block",
              width: 14,
              height: 2,
              background: "var(--prov-derived)",
              borderBottom: "2px dashed var(--prov-derived)",
            }}
          />
          initial guess
        </span>
        {solverIds.map((id) =>
          f.profiles?.[id] ? (
            <span
              key={id}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 5,
                fontSize: "0.76rem",
                color: "var(--ink-dim)",
                fontFamily: "var(--font-mono)",
              }}
            >
              <span
                style={{
                  display: "inline-block",
                  width: 14,
                  height: 2,
                  background: colors[id] ?? "var(--accent)",
                }}
              />
              {solverLabel[id] ?? id}
            </span>
          ) : null,
        )}
      </div>

      {/* Spectrum overlay */}
      <PlotMount
        make={(w) => spectrumPlot(spectrumSeries(f as AnyCase, solverIds), { colors, width: w })}
        deps={[report, ctx.selectedId, ctx.view]}
      />
      {/* Residuals strip */}
      <PlotMount
        make={(w) => residualPlot(residualRows(f as AnyCase, solverIds), { colors, width: w })}
        deps={[report, ctx.selectedId, ctx.view]}
      />

      {/* Per-backend metrics table */}
      {metrics.length > 0 && (
        <div style={{ marginTop: "var(--s4)", overflowX: "auto" }}>
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontFamily: "var(--font-mono)",
              fontSize: "0.8rem",
              color: "var(--ink-dim)",
            }}
          >
            <thead>
              <tr>
                {["backend", "r²", "χ²_red", "RMSE", "speedup", "iters"].map((h) => (
                  <th
                    key={h}
                    style={{
                      textAlign: h === "backend" ? "left" : "right",
                      padding: "4px 8px",
                      borderBottom: "1px solid var(--hairline)",
                      color: "var(--ink-faint)",
                      fontWeight: 400,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {metrics.map((row) => (
                <tr key={row.backend}>
                  <td style={{ padding: "4px 8px", borderBottom: "1px solid var(--hairline)" }}>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                      <span
                        style={{
                          display: "inline-block",
                          width: 8,
                          height: 8,
                          borderRadius: "50%",
                          background: colors[row.backend] ?? "var(--accent)",
                          flexShrink: 0,
                        }}
                      />
                      {solverLabel[row.backend] ?? row.backend}
                    </span>
                  </td>
                  <td style={{ textAlign: "right", padding: "4px 8px", borderBottom: "1px solid var(--hairline)" }}>
                    {row.r2.toFixed(4)}
                  </td>
                  <td style={{ textAlign: "right", padding: "4px 8px", borderBottom: "1px solid var(--hairline)" }}>
                    {row.redChi2.toFixed(4)}
                  </td>
                  <td style={{ textAlign: "right", padding: "4px 8px", borderBottom: "1px solid var(--hairline)" }}>
                    {row.rmse.toExponential(2)}
                  </td>
                  <td style={{ textAlign: "right", padding: "4px 8px", borderBottom: "1px solid var(--hairline)" }}>
                    {row.speedup.toFixed(2)}×
                  </td>
                  <td style={{ textAlign: "right", padding: "4px 8px", borderBottom: "1px solid var(--hairline)" }}>
                    {row.nIter}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

export function peaksBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  const f = selectedCase(report, ctx);
  if (f == null) return null;
  return (
    <PlotMount
      make={(w) => peaksPlot(peakRows(f as AnyCase), w)}
      deps={[report, ctx.selectedId, ctx.view]}
    />
  );
}

export function recoveryBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  const f = selectedCase(report, ctx);
  if (f == null) return null;
  return (
    <>
      <PlotMount
        make={(w) => recoveryPlot(recoveryRows(f as AnyCase, ctx.solverIds), { colors: ctx.colors, width: w })}
        deps={[report, ctx.selectedId, ctx.view]}
      />
      <p
        style={{
          margin: "var(--s3) 0 0",
          fontSize: "0.76rem",
          color: "var(--ink-faint)",
          fontFamily: "var(--font-mono)",
        }}
      >
        amplitude / center / σ recoverable; other shape params unverifiable
      </p>
    </>
  );
}

export function pullsBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  const f = selectedCase(report, ctx);
  if (f == null) return null;
  const solverLabel = solverLabelMap(report);
  const pullEntries = pullSeries(f as AnyCase, ctx.solverIds);
  return (
    <>
      <PlotMount
        make={(w) => pullsPlot(pullSeries(f as AnyCase, ctx.solverIds), { colors: ctx.colors, width: w })}
        deps={[report, ctx.selectedId, ctx.view]}
      />
      <div
        style={{
          marginTop: "var(--s3)",
          fontSize: "0.76rem",
          color: "var(--ink-faint)",
          fontFamily: "var(--font-mono)",
          display: "flex",
          flexWrap: "wrap",
          gap: "var(--s2)",
        }}
      >
        {pullEntries
          .filter((p) => !p.absent)
          .map((p) => (
            <span key={p.backend}>
              {solverLabel[p.backend] ?? p.backend} {(p.coverage ?? 0).toFixed(2)}
            </span>
          ))}
        {pullEntries.filter((p) => p.absent).length > 0 && (
          <span>
            — absent (no σ):{" "}
            {pullEntries
              .filter((p) => p.absent)
              .map((p) => solverLabel[p.backend] ?? p.backend)
              .join(", ")}
          </span>
        )}
      </div>
    </>
  );
}

export function convergenceBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  const f = selectedCase(report, ctx);
  if (f == null) return null;
  // Derive which backends have reconstructed histories for this case (EF-PLOTS-08:
  // never hardcode backend ids — derive from the data so captions stay accurate
  // as the solver roster evolves).
  const series = convSeries(f as AnyCase, ctx.solverIds);
  const reconstructedBackends = series
    .filter((s) => s.mode === "endpoints")
    .map((s) => {
      const labelMap = solverLabelMap(report);
      return labelMap[s.backend] ?? s.backend;
    });
  return (
    <>
      <PlotMount
        make={(w) => convergencePlot(series, { colors: ctx.colors, width: w })}
        deps={[report, ctx.selectedId, ctx.view]}
      />
      {reconstructedBackends.length > 0 && (
        <div className="absent-note" style={{ marginTop: "var(--s3)" }}>
          <span aria-hidden style={{ fontFamily: "var(--font-mono)", flexShrink: 0 }}>~</span>
          <span>
            {reconstructedBackends.join("/")} {reconstructedBackends.length === 1 ? "history is a" : "histories are"} reconstructed{" "}
            {reconstructedBackends.length === 1 ? "proxy" : "proxies"} — endpoints are measured, the interior is
            interpolated. Shown as endpoints, not lines.
          </span>
        </div>
      )}
    </>
  );
}

export function convergenceTruthBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  const f = selectedCase(report, ctx);
  if (f == null) return null;
  const td = thetaDistanceSeries(f as AnyCase);
  if (td == null) return null; // non-synthetic case / no θ trajectory
  return (
    <PlotMount
      make={(w) => thetaDistancePlot(td, { colors: ctx.colors, width: w })}
      deps={[report, ctx.selectedId, ctx.view]}
    />
  );
}

export function timingBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  const f = selectedCase(report, ctx);
  if (f == null) return null;
  return (
    <PlotMount
      make={(w) => timingBoxPlot(timingBoxes(f as AnyCase, ctx.solverIds), { colors: ctx.colors, width: w })}
      deps={[report, ctx.selectedId, ctx.view]}
    />
  );
}

export function warmupBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  const f = selectedCase(report, ctx);
  if (f == null) return null;
  return (
    <PlotMount
      make={(w) => warmupPlot(warmupLines(f as AnyCase, ctx.solverIds), { colors: ctx.colors, width: w })}
      deps={[report, ctx.selectedId, ctx.view]}
    />
  );
}

export function scalingBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  const f = selectedCase(report, ctx);
  if (f == null) return null;
  return (
    <PlotMount
      make={(w) =>
        scalingPlot(scalingLines(f as AnyCase, ctx.solverIds), {
          colors: ctx.colors,
          crossN: (f as AnyCase).crossN,
          width: w,
        })
      }
      deps={[report, ctx.selectedId, ctx.view]}
    />
  );
}

export function reproducibilityBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  const f = selectedCase(report, ctx);
  if (f == null) return null;
  return (
    <PlotMount
      make={(w) => stabilityPlot(stabilityBand(f as AnyCase, ctx.solverIds, "iters"), { colors: ctx.colors, width: w, metric: "iters" })}
      deps={[report, ctx.selectedId, ctx.view]}
    />
  );
}

export function residualQQBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  const f = selectedCase(report, ctx);
  if (f == null) return null;
  return (
    <PlotMount
      make={(w) =>
        residualQQPlot(residualQQSeries(report, f.id as string, ctx.solverIds), { colors: ctx.colors, width: w })
      }
      deps={[report, ctx.selectedId, ctx.view]}
    />
  );
}

export function iterationsBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  const f = selectedCase(report, ctx);
  if (f == null) return null;
  return (
    <PlotMount
      make={(w) =>
        iterationsPlot(iterationsSeries(report, f.id as string, ctx.solverIds), { colors: ctx.colors, width: w })
      }
      deps={[report, ctx.selectedId, ctx.view]}
    />
  );
}

export function infoCriteriaBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  const f = selectedCase(report, ctx);
  if (f == null) return null;
  const rows = infoCriteriaRows(f as AnyCase, ctx.solverIds);
  if (rows.length === 0) {
    return (
      <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--ink-faint)", fontFamily: "var(--font-mono)" }}>
        No information criteria reported for this case.
      </p>
    );
  }
  const colors = ctx.colors;
  const solverLabel = solverLabelMap(report);
  const cell = {
    textAlign: "right" as const,
    padding: "4px 8px",
    borderBottom: "1px solid var(--hairline)",
  };
  return (
    <div style={{ overflowX: "auto" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontFamily: "var(--font-mono)",
          fontSize: "0.8rem",
          color: "var(--ink-dim)",
        }}
      >
        <thead>
          <tr>
            {["backend", "ΔAIC", "ΔBIC", "MAE"].map((h) => (
              <th
                key={h}
                style={{
                  textAlign: h === "backend" ? "left" : "right",
                  padding: "4px 8px",
                  borderBottom: "1px solid var(--hairline)",
                  color: "var(--ink-faint)",
                  fontWeight: 400,
                  whiteSpace: "nowrap",
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.backend}>
              <td style={{ padding: "4px 8px", borderBottom: "1px solid var(--hairline)" }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <span
                    style={{
                      display: "inline-block",
                      width: 8,
                      height: 8,
                      borderRadius: "50%",
                      background: colors[row.backend] ?? "var(--accent)",
                      flexShrink: 0,
                    }}
                  />
                  {solverLabel[row.backend] ?? row.backend}
                  {row.best && (
                    <span style={{ color: "var(--pass)", fontSize: "0.72rem" }} title="preferred model (lowest ΔAIC)">
                      ★ preferred
                    </span>
                  )}
                </span>
              </td>
              <td style={{ ...cell, color: row.best ? "var(--pass)" : "var(--ink-dim)" }}>
                {Number.isFinite(row.dAIC) ? row.dAIC.toFixed(2) : "—"}
              </td>
              <td style={cell}>{Number.isFinite(row.dBIC) ? row.dBIC.toFixed(2) : "—"}</td>
              <td style={cell}>{Number.isFinite(row.mae) ? row.mae.toExponential(2) : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function accuracyBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  const f = selectedCase(report, ctx);
  if (f == null) return null;
  const boxes = accuracyBoxes(f as AnyCase, ctx.solverIds);
  if (boxes.length === 0) {
    return (
      <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--ink-faint)", fontFamily: "var(--font-mono)" }}>
        No accuracy data for this case.
      </p>
    );
  }
  return (
    <>
      <PlotMount
        make={(w) => accuracyBoxPlot(boxes, { colors: ctx.colors, width: w })}
        deps={[report, ctx.selectedId, ctx.view]}
      />
      <p
        style={{
          margin: "var(--s3) 0 0",
          fontSize: "0.76rem",
          color: "var(--ink-faint)",
          fontFamily: "var(--font-mono)",
        }}
      >
        reduced χ² ≈ 1 is the target; dashed line marks 1. Distribution over repetitions (p5–p75, IQR box, median tick).
      </p>
    </>
  );
}

export function conditioningBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  const f = selectedCase(report, ctx);
  if (f == null) return null;
  const kappaRowsData = kappaRows(f as AnyCase, ctx.solverIds);
  const topCouplingsData = topCouplings(f as AnyCase, 3);
  const absentKappaBackends = kappaRowsData.filter((r) => r.absent).map((r) => r.backend);
  return (
    <>
      <PlotMount
        make={(w) => {
          const rows = kappaRows(f as AnyCase, ctx.solverIds);
          // Every backend gets a lane: those that expose κ(J) as a dot on the log
          // axis, those that don't as an explicit greyed "not exposed" lane. Only
          // a truly empty roster renders nothing.
          return rows.length ? conditioningPlot(rows, { colors: ctx.colors, width: w }) : null;
        }}
        deps={[report, ctx.selectedId, ctx.view]}
      />
      {absentKappaBackends.length > 0 && (
        <div className="absent-note" style={{ marginTop: "var(--s3)" }}>
          <span aria-hidden style={{ fontFamily: "var(--font-mono)", flexShrink: 0 }}>κ(J)</span>
          <span>
            {absentKappaBackends.join(" & ")} do not expose a Jacobian condition number.
            spectrafit (the subject) and scipy-ls report κ(J); lmfit and jax do not — a disclosed
            per-backend oracle limitation, not a subject capability gap. Their lanes above are
            greyed &ldquo;not exposed&rdquo;.
          </span>
        </div>
      )}
      {topCouplingsData.length > 0 && (
        <p
          style={{
            margin: "var(--s2) 0 0",
            fontSize: "0.76rem",
            color: "var(--ink-faint)",
            fontFamily: "var(--font-mono)",
          }}
        >
          top couplings: {topCouplingsData.map((c) => `${c.pair} ${c.r.toFixed(2)}`).join(" · ")}
        </p>
      )}
    </>
  );
}
