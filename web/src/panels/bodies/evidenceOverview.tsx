/**
 * Evidence-overview destination body functions (dest: "evidence", scope: "overview").
 */
import type { ReactNode } from "react";
import type { BenchReport } from "../../contract";
import type { PanelCtx } from "../types";
import { ciRows } from "../../series";
import { saturationGrid } from "../../series/saturation";
import { ciIntervalPlot } from "../../plots";
import { PLOT_SPECS } from "../../plots/spec";
import { saturationHeatmap } from "../../plots/saturation";
import { winnerPlot } from "../../plots/winner";
import { winnerBars } from "../../series/winner";
import { SuiteTable, toCsv } from "../../chrome/table";
import { paretoSeries } from "../../series/pareto";
import { paretoPlot } from "../../plots/pareto";
import { performanceProfileSeries } from "../../series/performanceProfile";
import { performanceProfilePlot } from "../../plots/performanceProfile";
import { successRateSeries } from "../../series/successRate";
import { successRatePlot } from "../../plots/successRate";
import { recoveryErrorSeries } from "../../series/recoveryError";
import { recoveryErrorPlot } from "../../plots/recoveryError";
import { speedupDistSeries } from "../../series/speedupDist";
import { speedupDistPlot } from "../../plots/speedupDist";
import { PlotMount } from "../../plots/PlotMount";
import { AnyCase } from "./shared";

// ===========================================================================
// Evidence — overview panels (composite ReactNode bodies)
// ===========================================================================

export function saturationBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  const equivalence = report.inference?.equivalence ?? [];
  const margin = report.inference?.config?.equivalenceMargin;
  if (!report.suite?.length) {
    return (
      <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--ink-faint)", fontFamily: "var(--font-mono)" }}>
        No suite data in this report.
      </p>
    );
  }
  const categoryCounts = Object.fromEntries(
    (report.categories ?? []).map((c: { id: string; n: number }) => [c.id, c.n])
  );
  return (
    <>
      <PlotMount
        make={(w) => saturationHeatmap(saturationGrid(report.suite as AnyCase), {
          width: w,
          categoryCounts: Object.keys(categoryCounts).length > 0 ? categoryCounts : undefined,
        })}
        deps={[report, ctx.view]}
      />
      <div
        style={{
          marginTop: "var(--s4)",
          display: "flex",
          flexWrap: "wrap",
          gap: "var(--s2)",
          alignItems: "center",
        }}
      >
        {margin != null && (
          <span
            style={{
              fontSize: "0.76rem",
              color: "var(--ink-faint)",
              fontFamily: "var(--font-mono)",
              marginRight: "var(--s2)",
            }}
          >
            equivalence margin {margin.toExponential(0)}
          </span>
        )}
        {equivalence.map((eq) => (
          <span
            key={eq.category}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              padding: "2px 8px",
              borderRadius: 4,
              fontSize: "0.76rem",
              fontFamily: "var(--font-mono)",
              border: `1px solid ${eq.equivalent ? "var(--pass)" : "var(--hairline)"}`,
              color: eq.equivalent ? "var(--pass)" : "var(--ink-dim)",
              background: "transparent",
            }}
          >
            {eq.category} {eq.equivalent ? "✓ equivalent" : "✗ distinguishes"}
            {margin != null && eq.equivalent && ` (Δ≤${margin.toExponential(0)})`}
          </span>
        ))}
        {equivalence.length === 0 && (
          <span style={{ fontSize: "0.8rem", color: "var(--ink-faint)", fontFamily: "var(--font-mono)" }}>
            No TOST results in this report.
          </span>
        )}
      </div>
      {(report.manifest?.saturatedCategories?.length ?? 0) > 0 && (
        <div
          aria-label="saturated categories"
          style={{
            marginTop: "var(--s3)",
            display: "flex",
            flexWrap: "wrap",
            gap: "var(--s2)",
            alignItems: "center",
          }}
        >
          <span
            style={{
              fontSize: "0.74rem",
              color: "var(--ink-faint)",
              fontFamily: "var(--font-mono)",
              marginRight: "var(--s1)",
            }}
          >
            saturated:
          </span>
          {report.manifest!.saturatedCategories!.map((id) => (
            <span
              key={id}
              aria-label="saturated category"
              style={{
                display: "inline-flex",
                alignItems: "center",
                padding: "2px 8px",
                borderRadius: 999,
                border: "1px solid var(--hairline)",
                background: "color-mix(in srgb, var(--warn) 12%, transparent)",
                color: "var(--warn)",
                fontSize: "0.74rem",
                fontFamily: "var(--font-mono)",
                fontWeight: 600,
                whiteSpace: "nowrap",
              }}
            >
              {report.categories?.find((c) => c.id === id)?.label ?? id}
            </span>
          ))}
        </div>
      )}
    </>
  );
}

// Categories excluded from the Δr² accuracy gate by design (per CLAUDE.md).
// Non-equivalence here is expected and out of scope — not an accuracy regression.
const OUT_OF_GATE_CATEGORIES = new Set(["optfn", "global"]);

/**
 * Accuracy parity by category (T5.1, cross-case editorial). Reads the
 * FDR-controlled per-category equivalence test (inference.equivalence) and joins
 * it to the category labels — one row per category, showing where the subject
 * matches the baseline's accuracy within the margin and where it does not.
 *
 * Categories excluded from the Δr² accuracy gate (optfn, global) are listed as
 * "out of accuracy-gate scope" rather than accuracy exceptions — calling them
 * exceptions would conflate gate scope with accuracy regressions. The baseline
 * is named; the subject is never crowned.
 */
export function accuracyParityBody(report: BenchReport): ReactNode {
  const equiv = report.inference?.equivalence ?? [];
  if (equiv.length === 0) {
    return (
      <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--ink-faint)", fontFamily: "var(--font-mono)" }}>
        No per-category equivalence data in this report.
      </p>
    );
  }
  const margin = report.inference?.config?.equivalenceMargin;
  const baseline = report.baselineSolverId;
  const labelOf = (id: string) => report.categories?.find((c) => c.id === id)?.label ?? id;

  // Split: in-gate categories (subject to the Δr² accuracy gate) vs out-of-gate.
  const inGate = equiv.filter((e) => !OUT_OF_GATE_CATEGORIES.has(e.category));
  const outOfGate = equiv.filter((e) => OUT_OF_GATE_CATEGORIES.has(e.category));

  const nEquiv = equiv.filter((e) => e.equivalent).length;
  // In-gate non-equivalence is a genuine accuracy difference worth flagging.
  const inGateNonEquiv = inGate.filter((e) => !e.equivalent);

  // Evidence panel — PanelCard supplies the card chrome + title + caption, so the
  // body returns content only (no self-wrapping .glass, no duplicate heading).
  return (
    <>
      <p style={{ margin: "0 0 var(--s4)", fontSize: "0.82rem", color: "var(--ink-dim)", fontFamily: "var(--font-mono)", lineHeight: 1.5 }}>
        <strong style={{ color: "var(--ink)" }}>
          {nEquiv} of {equiv.length}
        </strong>{" "}
        categories sit within the {margin != null ? margin.toExponential(0) : "equivalence"} margin vs{" "}
        <strong style={{ color: "var(--ink)" }}>{baseline}</strong> —{" "}
        {inGateNonEquiv.length === 0 ? (
          <>accuracy parity holds across the board for in-gate categories.</>
        ) : (
          <>
            in-gate{" "}{inGateNonEquiv.length === 1 ? "category" : "categories"} outside the margin:{" "}
            {inGateNonEquiv.map((e, i) => (
              <span key={e.category}>
                {i > 0 ? ", " : ""}
                <strong style={{ color: "var(--warn)" }}>{labelOf(e.category)}</strong> (Δ{" "}
                {e.diff.toExponential(2)})
              </span>
            ))}
          </>
        )}
        {outOfGate.length > 0 && (
          <>
            {" "}·{" "}
            {outOfGate.map((e, i) => (
              <span key={e.category}>
                {i > 0 ? ", " : ""}
                <strong style={{ color: "var(--ink-dim)" }}>{labelOf(e.category)}</strong>
              </span>
            ))}{" "}
            {outOfGate.length === 1 ? "is" : "are"} out of accuracy-gate scope (Δr² gate excludes these categories by design).
          </>
        )}
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: "2px", fontFamily: "var(--font-mono)", fontSize: "0.8rem" }}>
        {equiv.map((e) => {
          const outOfScope = OUT_OF_GATE_CATEGORIES.has(e.category);
          return (
            <div
              key={e.category}
              style={{
                display: "flex",
                alignItems: "baseline",
                gap: "var(--s3)",
                padding: "3px 0",
                borderBottom: "1px solid color-mix(in srgb, var(--hairline) 50%, transparent)",
              }}
            >
              <span style={{ minWidth: "11rem", color: "var(--ink-dim)" }}>{labelOf(e.category)}</span>
              <span
                style={{
                  color: e.equivalent ? "var(--pass)" : outOfScope ? "var(--ink-faint)" : "var(--warn)",
                  fontWeight: 600,
                  minWidth: "5.5rem",
                }}
              >
                {e.equivalent ? "✓ at parity" : outOfScope ? "— out of gate scope" : "✗ differs"}
              </span>
              <span style={{ color: "var(--ink-faint)" }}>Δ {e.diff.toExponential(2)}</span>
            </div>
          );
        })}
      </div>
    </>
  );
}

export function suiteTableBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  if (!report.suite?.length) {
    return (
      <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--ink-faint)", fontFamily: "var(--font-mono)" }}>
        No suite data in this report.
      </p>
    );
  }
  const onSelect = ctx.openCase;
  return (
    <>
      <div style={{ maxHeight: 360, overflow: "auto" }}>
        <SuiteTable suite={report.suite as AnyCase} solverIds={ctx.solverIds} onSelect={onSelect} />
      </div>
      <div style={{ marginTop: "var(--s3)" }}>
        <button
          style={{
            background: "var(--surface-2)",
            border: "1px solid var(--hairline)",
            borderRadius: 6,
            color: "var(--ink-dim)",
            fontFamily: "var(--font-mono)",
            fontSize: "0.8rem",
            padding: "4px 12px",
            cursor: "pointer",
          }}
          onClick={() => {
            const blob = new Blob([toCsv(report.suite as AnyCase, ctx.solverIds)], { type: "text/csv" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "suite.csv";
            a.click();
            URL.revokeObjectURL(url);
          }}
        >
          Export CSV
        </button>
      </div>
    </>
  );
}

export function deltaR2CiBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  if (report.inference == null) {
    return (
      <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--ink-faint)", fontFamily: "var(--font-mono)" }}>
        No inference block in this report.
      </p>
    );
  }
  const n = report.inference.cases.length;
  return (
    <>
      <div style={{ maxHeight: 420, overflowY: "auto" }}>
        <PlotMount
          make={(w) =>
            report.inference
              ? ciIntervalPlot(
                  ciRows(report.inference.cases as AnyCase, "deltaR2Ci").sort(
                    (a, b) => Math.abs(b.point) - Math.abs(a.point),
                  ),
                  {
                    spec: PLOT_SPECS["delta-r2-ci"],
                    width: w,
                  },
                )
              : null
          }
          deps={[report, ctx.view]}
        />
      </div>
      <p
        style={{
          margin: "var(--s3) 0 0",
          fontSize: "0.76rem",
          color: "var(--ink-faint)",
          fontFamily: "var(--font-mono)",
        }}
      >
        All {n} cases, sorted by |Δr²| — overlap with 0 means statistically indistinguishable accuracy; gate band ±1e-3.
      </p>
    </>
  );
}

export function speedupCiBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  if (report.inference == null) {
    return (
      <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--ink-faint)", fontFamily: "var(--font-mono)" }}>
        No inference block in this report.
      </p>
    );
  }
  const n = report.inference.cases.length;
  return (
    <>
      <div style={{ maxHeight: 420, overflowY: "auto" }}>
        <PlotMount
          make={(w) =>
            report.inference
              ? ciIntervalPlot(
                  ciRows(report.inference.cases as AnyCase, "speedupCi").sort(
                    (a, b) => Math.abs(b.point - 1) - Math.abs(a.point - 1),
                  ),
                  {
                    spec: PLOT_SPECS["speedup-ci"],
                    width: w,
                  },
                )
              : null
          }
          deps={[report, ctx.view]}
        />
      </div>
      <p
        style={{
          margin: "var(--s3) 0 0",
          fontSize: "0.76rem",
          color: "var(--ink-faint)",
          fontFamily: "var(--font-mono)",
        }}
      >
        All {n} cases, sorted by speedup magnitude — anything to the right of 1× is faster than the baseline.
      </p>
    </>
  );
}

export function winnerStabilityBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  if (report.inference == null) {
    return (
      <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--ink-faint)", fontFamily: "var(--font-mono)" }}>
        No inference block in this report.
      </p>
    );
  }
  const winnerSummary = winnerBars(report.inference.winnerStability ?? {});
  return (
    <>
      <PlotMount
        make={(w) =>
          report.inference
            ? winnerPlot(winnerBars(report.inference.winnerStability ?? {}).bars, { colors: ctx.colors, width: w })
            : null
        }
        deps={[report, ctx.view]}
      />
      {winnerSummary.noRobustWinner && (
        <p
          style={{
            margin: "var(--s3) 0 0",
            fontSize: "0.76rem",
            color: "var(--ink-faint)",
            fontFamily: "var(--font-mono)",
          }}
        >
          no robust winner — the leader wins &lt; 60% of resamples
        </p>
      )}
    </>
  );
}

export function paretoBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  if (!report.suite?.length) {
    return (
      <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--ink-faint)", fontFamily: "var(--font-mono)" }}>
        No suite data in this report.
      </p>
    );
  }
  return (
    <PlotMount
      make={(w) => paretoPlot(paretoSeries(report, ctx.solverIds), { colors: ctx.colors, width: w })}
      deps={[report, ctx.view]}
    />
  );
}

export function perfProfileBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  if (!report.suite?.length) {
    return (
      <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--ink-faint)", fontFamily: "var(--font-mono)" }}>
        No suite data in this report.
      </p>
    );
  }
  return (
    <PlotMount
      make={(w) => performanceProfilePlot(performanceProfileSeries(report, ctx.solverIds), { colors: ctx.colors, width: w })}
      deps={[report, ctx.view]}
    />
  );
}

export function successRateBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  if (!report.suite?.length) {
    return (
      <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--ink-faint)", fontFamily: "var(--font-mono)" }}>
        No suite data in this report.
      </p>
    );
  }
  return (
    <PlotMount
      make={(w) => successRatePlot(successRateSeries(report, ctx.solverIds), { colors: ctx.colors, width: w })}
      deps={[report, ctx.view]}
    />
  );
}

export function recoveryErrorBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  if (!report.suite?.length) {
    return (
      <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--ink-faint)", fontFamily: "var(--font-mono)" }}>
        No suite data in this report.
      </p>
    );
  }
  return (
    <PlotMount
      make={(w) => recoveryErrorPlot(recoveryErrorSeries(report, ctx.solverIds), { colors: ctx.colors, width: w })}
      deps={[report, ctx.view]}
    />
  );
}

export function speedupDistBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  if (!report.suite?.length) {
    return (
      <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--ink-faint)", fontFamily: "var(--font-mono)" }}>
        No suite data in this report.
      </p>
    );
  }
  return (
    <PlotMount
      make={(w) => speedupDistPlot(speedupDistSeries(report, ctx.solverIds), { colors: ctx.colors, width: w })}
      deps={[report, ctx.view]}
    />
  );
}
