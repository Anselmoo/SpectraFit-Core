/**
 * Invariant P — scientific-plot methodology enforcement.
 *
 * Derives from the `PLOT_SPECS` registry (the single source of truth):
 *  - every chart plot fn used in the panel registry maps to ≥1 spec (no plot
 *    without a declared scientific question + grammar — the drift guard);
 *  - assertive plots carry a criterion AND a provenance id (a real value);
 *  - descriptive plots make no verdict (provenanceId null);
 *  - the ONE grammar holds (log axes labelled "(log)", every axis has a unit).
 *
 * This is the visualization analog of the value-provenance parity suite.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { axisLabel } from "../plots/grammar";
import { PLOT_SPECS, type PlotSpec } from "../plots/spec";

// The panel registry (record ids + titles) plus the body modules where the plot
// fns are actually CALLED. The bodies were split out of registry.tsx (the 1891→359
// refactor); scanning registry.tsx alone made the drift guard below vacuous (zero
// `*Plot(` calls remained there). Concatenate both so the guard stays live.
const PANELS_DIR = join(import.meta.dirname, "..", "panels");
const REGISTRY = [
  join(PANELS_DIR, "registry.tsx"),
  join(PANELS_DIR, "bodies", "standing.tsx"),
  join(PANELS_DIR, "bodies", "methods.tsx"),
  join(PANELS_DIR, "bodies", "evidenceOverview.tsx"),
  join(PANELS_DIR, "bodies", "evidenceCase.tsx"),
  join(PANELS_DIR, "bodies", "shared.tsx"),
  join(PANELS_DIR, "bodies", "multidimShowcase.tsx"),
  join(PANELS_DIR, "bodies", "globalFitShowcase.tsx"),
]
  .map((p) => readFileSync(p, "utf-8"))
  .join("\n");

const specs = Object.values(PLOT_SPECS);

// Each chart plot fn used in the panel registry → the spec id(s) it renders.
// The drift guard below fails if registry.tsx uses a `*Plot(` fn absent here.
const PLOT_FN_SPECS: Record<string, string[]> = {
  ciIntervalPlot: ["delta-r2-ci", "speedup-ci"],
  winnerPlot: ["winner-stability"],
  paretoPlot: ["pareto"],
  performanceProfilePlot: ["perf-profile"],
  successRatePlot: ["success-rate"],
  recoveryErrorPlot: ["recovery-error-suite"],
  spectrumPlot: ["spectrum"],
  residualPlot: ["residual"],
  peaksPlot: ["peaks"],
  recoveryPlot: ["recovery"],
  pullsPlot: ["pulls"],
  convergencePlot: ["convergence"],
  thetaDistancePlot: ["convergence-truth"],
  timingBoxPlot: ["timing"],
  warmupPlot: ["warmup"],
  scalingPlot: ["scaling"],
  stabilityPlot: ["reproducibility"],
  residualQQPlot: ["residual-qq"],
  speedupDistPlot: ["speedup-dist"],
  iterationsPlot: ["iterations"],
  conditioningPlot: ["conditioning"],
  saturationHeatmap: ["saturation"],
  infoCriteriaPlot: ["info-criteria"],
  accuracyBoxPlot: ["accuracy-dist"],
  multidimProjectionHeatmap: ["multidim-projection"],
  globalFitSlicesPlot: ["global-fit-slices"],
  globalFitKineticsPlot: ["global-fit-kinetics"],
};

describe("PlotSpec — Invariant P", () => {
  it("every spec id is unique and kebab-case", () => {
    for (const s of specs) {
      expect(s.id, `${s.id} kebab`).toMatch(/^[a-z][a-z0-9-]*$/);
    }
    expect(new Set(specs.map((s) => s.id)).size).toBe(specs.length);
  });

  it("assertive plots carry a criterion AND a provenance id", () => {
    const bad = specs
      .filter((s) => s.kind === "assertive")
      .filter((s) => !s.criterion || !s.provenanceId || !s.provenanceId.includes("."))
      .map((s) => s.id);
    expect(bad, `assertive plots missing criterion/provenanceId: ${bad}`).toEqual([]);
  });

  it("descriptive plots make no verdict (no provenance claim)", () => {
    const bad = specs
      .filter((s) => s.kind === "descriptive")
      .filter((s) => s.criterion !== null || s.provenanceId !== null)
      .map((s) => s.id);
    expect(bad, `descriptive plots must not assert criterion/provenanceId: ${bad}`).toEqual([]);
  });

  it("the one grammar holds (via the shared composer): direction, (log), units", () => {
    const violations: string[] = [];
    const check = (s: PlotSpec, dir: "x" | "y") => {
      const a = s[dir];
      if (!a.unit || a.unit.trim() === "") {
        violations.push(`${s.id}.${dir}: empty unit field (use "—" if dimensionless)`);
        return;
      }
      const rendered = axisLabel(a, dir); // the ONE composed label all plots use
      if (!rendered.includes(dir === "x" ? "→" : "↑")) {
        violations.push(`${s.id}.${dir}: composed label lacks the direction affordance — "${rendered}"`);
      }
      // Composed annotation is "(log)" alone or "(unit, log)" → both end "log)".
      if (a.scale === "log" && !rendered.includes("log)")) {
        violations.push(`${s.id}.${dir}: log scale but composed label lacks the log marker — "${rendered}"`);
      }
      if (a.unit !== "—" && !rendered.includes(a.unit)) {
        violations.push(`${s.id}.${dir}: unit "${a.unit}" not shown in "${rendered}"`);
      }
    };
    for (const s of specs) {
      check(s, "x");
      check(s, "y");
    }
    expect(violations, violations.join("\n")).toEqual([]);
  });

  it("no orphan specs — every spec id is referenced in registry.tsx", () => {
    const orphans = specs
      .filter((s) => !REGISTRY.includes(s.id))
      .map((s) => s.id);
    expect(orphans, `specs not referenced by any panel: ${orphans}`).toEqual([]);
  });

  it("drift guard — every chart plot fn in registry.tsx has a spec mapping", () => {
    // Plot fns follow the `<name>Plot(` / `<name>Heatmap(` convention.
    const used = new Set<string>();
    for (const m of REGISTRY.matchAll(/\b([a-z][A-Za-z0-9]*(?:Plot|Heatmap))\(/g)) {
      used.add(m[1]);
    }
    const unmapped = [...used].filter((fn) => !PLOT_FN_SPECS[fn]);
    expect(
      unmapped,
      `plot fn(s) used in registry without a PLOT_SPECS mapping (add a spec): ${unmapped}`,
    ).toEqual([]);
    // And every mapped spec id must exist in the registry.
    for (const ids of Object.values(PLOT_FN_SPECS)) {
      for (const id of ids) expect(PLOT_SPECS[id], `mapped spec ${id} exists`).toBeTruthy();
    }
  });

  /**
   * EF-PLOTS-03 — provenance:true is ENFORCED, not decorative.
   *
   * A spec with `provenance: true` claims "this plot distinguishes real vs
   * reconstructed/proxy data". The claim is only honest when the plot file
   * sources the shared provenance affordance (`provStyle`, `RECON_OPACITY`,
   * or `historyMode` from `../provenance`). If the file does not import or
   * reference those tokens the flag is a dead claim and must be set to false.
   *
   * How the check works:
   *   1. Find every spec where provenance === true.
   *   2. Reverse-look-up the plot fn(s) for that spec via PLOT_FN_SPECS.
   *   3. Derive the plot file name from the fn name (camelCase stem → kebab-case
   *      .ts file in web/src/plots/), then read its source.
   *   4. Assert the source contains at least one provenance-affordance token.
   */
  it("provenance:true plots must source the real/reconstructed affordance (EF-PLOTS-03)", () => {
    const PLOTS_DIR = join(import.meta.dirname, "..", "plots");
    // Affordance tokens that prove the plot visually distinguishes real vs proxy.
    const AFFORDANCE = /\b(provStyle|RECON_OPACITY|historyMode)\b/;

    // Build reverse map: spec id → plot fn names
    const specToFns: Record<string, string[]> = {};
    for (const [fn, ids] of Object.entries(PLOT_FN_SPECS)) {
      for (const id of ids) {
        (specToFns[id] ??= []).push(fn);
      }
    }

    // Derive file path from fn name: strip trailing "Plot"/"Heatmap", then
    // convert camelCase stem to kebab-case and append ".ts".
    function fnToFile(fn: string): string {
      const stem = fn.replace(/(?:Plot|Heatmap)$/, "");
      const kebab = stem.replace(/([A-Z])/g, (m) => `-${m.toLowerCase()}`);
      return join(PLOTS_DIR, `${kebab}.ts`);
    }

    const violations: string[] = [];
    for (const s of specs.filter((s) => s.provenance)) {
      const fns = specToFns[s.id] ?? [];
      if (fns.length === 0) {
        violations.push(`${s.id}: provenance:true but no plot fn mapped (add to PLOT_FN_SPECS)`);
        continue;
      }
      for (const fn of fns) {
        const path = fnToFile(fn);
        let src: string;
        try {
          src = readFileSync(path, "utf-8");
        } catch {
          violations.push(`${s.id} → ${fn}: plot file not found at ${path}`);
          continue;
        }
        if (!AFFORDANCE.test(src)) {
          violations.push(
            `${s.id} → ${fn} (${path.split("/").at(-1)}): provenance:true but file does ` +
            `not reference provStyle/RECON_OPACITY/historyMode — set provenance:false or add the affordance`,
          );
        }
      }
    }
    expect(violations, violations.join("\n")).toEqual([]);
  });
});
