import { describe, it, expect } from "vitest";

/**
 * Contract-coverage manifest — every BenchReport leaf rendered or explicitly ignored.
 *
 * MAINTENANCE: when openapi.gen.ts adds a new field, add it to CONTRACT_LEAVES and
 * classify it in COVERAGE. The test fails on any unclassified leaf, making schema
 * drift immediately visible.
 *
 * Classification values:
 *   "rendered:<module>"  — a panel/component actually consumes this field group.
 *   "ignored:<reason>"   — deliberately not rendered; reason is load-bearing docs.
 */

// ---------------------------------------------------------------------------
// CONTRACT_LEAVES — checked-in enumeration of every BenchReport leaf path.
// Wildcard `*` = record key (backend id / solver id / category id).
// `[]` = array element.
// ---------------------------------------------------------------------------

export const CONTRACT_LEAVES: string[] = [
  // BenchReport root scalars
  "schemaVersion",
  "baselineSolverId",

  // solvers[] — SolverMeta
  "solvers[].id",
  "solvers[].label",
  "solvers[].color",
  "solvers[].soft",

  // categories[] — CategoryMeta
  "categories[].id",
  "categories[].label",
  "categories[].n",
  "categories[].hue",

  // manifest — ManifestSignals
  "manifest.geomeanSpeedupVsBaseline",
  "manifest.harmonicMeanSpeedupVsBaseline",
  "manifest.maxAbsDeltaR2",
  "manifest.spectrafitWinRate",
  "manifest.regressions",
  "manifest.gateState",
  "manifest.saturatedCategories",
  "manifest.nonfiniteDr2CaseIds",
  "manifest.sanitizedValuePaths",
  "manifest.pinned.runId",
  "manifest.pinned.recordedAt",
  "manifest.pinned.geomeanSpeedupVsBaseline",
  "manifest.pinned.nCases",

  // trustBlock — TrustBlock
  "trustBlock.rung",
  "trustBlock.wires[].wireId",
  "trustBlock.wires[].name",
  "trustBlock.wires[].status",
  "trustBlock.wires[].evidence",
  "trustBlock.wires[].details",
  "trustBlock.nClaimsAudited",
  "trustBlock.nClaimsTotal",
  "trustBlock.nistValidation.thresholdSigFigs",
  "trustBlock.nistValidation.datasets[].name",
  "trustBlock.nistValidation.datasets[].model",
  "trustBlock.nistValidation.datasets[].nParams",
  "trustBlock.nistValidation.datasets[].params[].name",
  "trustBlock.nistValidation.datasets[].params[].certified",
  "trustBlock.nistValidation.datasets[].params[].fitted",
  "trustBlock.nistValidation.datasets[].params[].sigFigsAgreed",
  "trustBlock.nistValidation.datasets[].minSigFigs",
  "trustBlock.nistValidation.datasets[].passed",
  "trustBlock.nistValidation.minSigFigs",
  "trustBlock.nistValidation.passed",

  // panels[] — PanelSpec (rendered directly by PanelRenderer, not via field map)
  "panels[].id",
  "panels[].title",
  "panels[].desc",
  "panels[].chartKind",
  "panels[].source",
  "panels[].layout.wide",
  "panels[].layout.height",

  // inference — InferenceBlock
  "inference.config.equivalenceMargin",
  "inference.config.bootstrapB",
  "inference.config.seed",
  "inference.config.fdrQ",
  "inference.config.alphaCalibration",
  "inference.config.alphaSpeed",
  "inference.config.coverageNominal",
  "inference.config.minPulls",
  "inference.cases[].caseId",
  "inference.cases[].speedupCi",
  "inference.cases[].deltaR2Ci",
  "inference.equivalence[].category",
  "inference.equivalence[].equivalent",
  "inference.equivalence[].margin",
  "inference.equivalence[].diff",
  "inference.winnerStability",

  // inference.calibration — CalibrationResult (W10)
  "inference.calibration.n",
  "inference.calibration.coverage",
  "inference.calibration.coverageCiLo",
  "inference.calibration.coverageCiHi",
  "inference.calibration.nominal",
  "inference.calibration.binomialP",
  "inference.calibration.ksStat",
  "inference.calibration.ksP",
  "inference.calibration.alpha",
  "inference.calibration.passed",
  "inference.calibration.skipped",

  // inference.speedInference — SpeedInferenceResult (W11)
  "inference.speedInference.geomeanSpeedup",
  "inference.speedInference.ciLo",
  "inference.speedInference.ciHi",
  "inference.speedInference.excludesOne",
  "inference.speedInference.signP",
  "inference.speedInference.wilcoxonP",
  "inference.speedInference.alpha",
  "inference.speedInference.passed",
  "inference.speedInference.skipped",

  // analyzed[] — Featured (case-level fields)
  "analyzed[].id",
  "analyzed[].name",
  "analyzed[].category",
  "analyzed[].x",
  "analyzed[].ref",
  "analyzed[].guess",
  "analyzed[].truth",
  "analyzed[].guessParams",
  "analyzed[].noise",
  "analyzed[].baseline",
  "analyzed[].schedule",
  "analyzed[].runsSched",
  "analyzed[].Ngrid",
  "analyzed[].crossN",
  "analyzed[].paramNames",
  "analyzed[].corr",
  "analyzed[].peaks[].label",
  "analyzed[].peaks[].y",
  "analyzed[].multidim",
  "analyzed[].globalFit",

  // analyzed[].nestedAdequacy — NestedAdequacy (W9 nested-order V&V)
  "analyzed[].nestedAdequacy.trueOrder",
  "analyzed[].nestedAdequacy.reducedRejected",
  "analyzed[].nestedAdequacy.overNotPreferredAic",
  "analyzed[].nestedAdequacy.overNotPreferredBic",
  "analyzed[].nestedAdequacy.selectedOrderAic",
  "analyzed[].nestedAdequacy.selectedOrderBic",
  "analyzed[].nestedAdequacy.recoveredTrueOrderAic",
  "analyzed[].nestedAdequacy.recoveredTrueOrderBic",
  "analyzed[].nestedAdequacy.reducedVsTrue.lrtStat",
  "analyzed[].nestedAdequacy.reducedVsTrue.lrtP",
  "analyzed[].nestedAdequacy.reducedVsTrue.fStat",
  "analyzed[].nestedAdequacy.reducedVsTrue.fP",
  "analyzed[].nestedAdequacy.reducedVsTrue.dAIC",
  "analyzed[].nestedAdequacy.reducedVsTrue.dBIC",
  "analyzed[].nestedAdequacy.trueVsOver.lrtStat",
  "analyzed[].nestedAdequacy.trueVsOver.lrtP",
  "analyzed[].nestedAdequacy.trueVsOver.fStat",
  "analyzed[].nestedAdequacy.trueVsOver.fP",
  "analyzed[].nestedAdequacy.trueVsOver.dAIC",
  "analyzed[].nestedAdequacy.trueVsOver.dBIC",

  // analyzed[].profiles.* — BackendProfile
  "analyzed[].profiles.*.fit.params",
  "analyzed[].profiles.*.fit.curve",
  "analyzed[].profiles.*.fit.resid",
  "analyzed[].profiles.*.conv",
  "analyzed[].profiles.*.grad",
  "analyzed[].profiles.*.convEff",
  "analyzed[].profiles.*.historySource",
  "analyzed[].profiles.*.thetaDistance",
  "analyzed[].profiles.*.timing.*",
  "analyzed[].profiles.*.accuracy.*",
  "analyzed[].profiles.*.summary.*",
  "analyzed[].profiles.*.paramErr",
  "analyzed[].profiles.*.ecdfResid",
  "analyzed[].profiles.*.ecdfTime",
  "analyzed[].profiles.*.warmup.curve",
  "analyzed[].profiles.*.warmup.pts",
  "analyzed[].profiles.*.warmup.hotThroughput",
  "analyzed[].profiles.*.warmup.coldMs",
  "analyzed[].profiles.*.warmup.hotMs",
  "analyzed[].profiles.*.scaling",
  "analyzed[].profiles.*.uncertainty.*",
  "analyzed[].profiles.*.paramSpread",
  "analyzed[].profiles.*.stability.*",
  "analyzed[].profiles.*.jacobianConditionNumber",

  // suite[] — SuiteCase
  "suite[].id",
  "suite[].name",
  "suite[].category",
  "suite[].difficulty",
  "suite[].m.*.speedup",
  "suite[].m.*.r2",
  "suite[].m.*.redChi2",
  "suite[].m.*.medMs",
  "suite[].m.*.paramErr",
  "suite[].m.*.success",
  "suite[].winner",
  "suite[].regression",

  // Wave B1 — code-provenance + winner-why fields
  "analyzed[].modelSourceFile",
  "analyzed[].modelFormula",

  // Track 3 — constraint structure for the FX/TI constrained-fit showcase
  "analyzed[].fixedParams",
  "analyzed[].exprEdges",
  "suite[].winnerReason",
  "suite[].m.*.convergenceEfficiency",
  "suite[].m.*.illConditioned",
  "suite[].m.*.redChi2Weighted",
  "suite[].m.*.metricUndefinedReason",

  // Wave B1 — run git-provenance fields (BenchReport root)
  "gitCommit",
  "gitBranch",
  "runTimestampUnix",
];

// ---------------------------------------------------------------------------
// COVERAGE — one entry per CONTRACT_LEAVES element.
// ---------------------------------------------------------------------------

export const COVERAGE: Record<string, string> = {
  // ---- BenchReport root scalars ----
  schemaVersion: "rendered:contract gate (loader rejects mismatched version)",
  baselineSolverId: "rendered:panels/registry (delta-r2-ci title derives solver label from baselineSolverId)",

  // ---- solvers[] ----
  "solvers[].id": "rendered:plots color + chrome legend (solverIds enumeration)",
  "solvers[].label": "rendered:plots color + chrome legend (solverLabel map)",
  "solvers[].color": "rendered:plots color + chrome legend (colors map)",
  "solvers[].soft": "ignored: deferred (soft-glow hover token, not yet wired to a panel)",

  // ---- categories[] ----
  "categories[].id": "ignored: implicit (saturationGrid reads suite[].category strings directly)",
  "categories[].label": "rendered: panels/registry accuracyParityCard (per-category label)",
  "categories[].n": "rendered:plots/saturation (N= case-count annotation on category y-axis labels)",
  "categories[].hue": "ignored: deferred (per-category color override, not yet wired)",

  // ---- manifest ----
  "manifest.geomeanSpeedupVsBaseline": "rendered:shell/Standing gate verdict panel",
  "manifest.harmonicMeanSpeedupVsBaseline": "rendered:shell/Standing gate verdict panel (harmonic mean beside geomean; Eeckhout 2024 complement)",
  "manifest.maxAbsDeltaR2": "rendered:shell/Standing gate verdict panel",
  "manifest.spectrafitWinRate": "rendered:shell/Standing gate verdict panel",
  "manifest.regressions": "rendered:shell/Standing gate verdict panel",
  "manifest.gateState": "rendered:shell/Standing gate verdict badge",
  "manifest.saturatedCategories": "rendered:panels/bodies/evidenceOverview saturationBody (saturated-category chips)",
  "manifest.nonfiniteDr2CaseIds": "ignored: gate-input (fails the python accuracy gate; gateState carries the verdict to the UI — case ids available via /api/v1/report)",
  "manifest.sanitizedValuePaths": "rendered:shell/ProvenanceFooter (G5 disclosure — count of non-finite values coerced to 0.0, paths in the title attribute)",
  "manifest.pinned.runId": "rendered:shell/ProvenanceFooter (Standing + Audit provenance line, labeled 'pinned baseline')",
  "manifest.pinned.recordedAt": "rendered: panels/registry reproduceCard (recorded-at row)",
  "manifest.pinned.geomeanSpeedupVsBaseline": "rendered: panels/bodies/methods pinnedBaselineCard (pinned-vs-current geomean)",
  "manifest.pinned.nCases": "rendered: panels/registry reproduceCard (cases row)",

  // ---- trustBlock ----
  // Unit 5: Audit destination removed. trustBlock fields are still rendered on the
  // Standing validation-scope card (renderTruthCard) and in the facts-masthead; the
  // detailed wire matrix + NIST table are served via GET /api/v1/trust (ledger-only).
  "trustBlock.rung": "rendered:shell/Standing facts-landing card (verification-completeness level)",
  "trustBlock.wires[].wireId": "ignored:ledger-only (wire matrix removed with Audit UI; available via /api/v1/trust)",
  "trustBlock.wires[].name": "ignored:ledger-only (wire matrix removed with Audit UI; available via /api/v1/trust)",
  "trustBlock.wires[].status": "rendered:panels/bodies/standing renderTruthCard (passed/gap wire ids for scope disclosure)",
  "trustBlock.wires[].evidence": "ignored:ledger-only (wire evidence text removed with Audit UI; available via /api/v1/trust)",
  "trustBlock.wires[].details": "ignored: aggregate detail map, not surfaced in the UI",
  "trustBlock.nClaimsAudited": "rendered:panels/bodies/standing renderTruthCard (claims-audited count in scope card)",
  "trustBlock.nClaimsTotal": "rendered:panels/bodies/standing renderTruthCard (claims-total in scope card)",
  "trustBlock.nistValidation.thresholdSigFigs": "ignored:ledger-only (NIST table removed with Audit UI; available via /api/v1/trust)",
  "trustBlock.nistValidation.datasets[].name": "ignored:ledger-only (NIST table removed with Audit UI; available via /api/v1/trust)",
  "trustBlock.nistValidation.datasets[].model": "ignored:ledger-only (NIST table removed with Audit UI; available via /api/v1/trust)",
  "trustBlock.nistValidation.datasets[].nParams": "ignored:ledger-only (NIST table removed with Audit UI; available via /api/v1/trust)",
  "trustBlock.nistValidation.datasets[].params[].name": "ignored:ledger-only (NIST table removed with Audit UI; available via /api/v1/trust)",
  "trustBlock.nistValidation.datasets[].params[].certified": "ignored:ledger-only (NIST table removed with Audit UI; available via /api/v1/trust)",
  "trustBlock.nistValidation.datasets[].params[].fitted": "ignored:ledger-only (NIST table removed with Audit UI; available via /api/v1/trust)",
  "trustBlock.nistValidation.datasets[].params[].sigFigsAgreed": "ignored:ledger-only (NIST table removed with Audit UI; available via /api/v1/trust)",
  "trustBlock.nistValidation.datasets[].minSigFigs": "ignored:ledger-only (NIST table removed with Audit UI; available via /api/v1/trust)",
  "trustBlock.nistValidation.datasets[].passed": "ignored:ledger-only (NIST table removed with Audit UI; available via /api/v1/trust)",
  "trustBlock.nistValidation.minSigFigs": "ignored:ledger-only (NIST table removed with Audit UI; available via /api/v1/trust)",
  "trustBlock.nistValidation.passed": "ignored:ledger-only (NIST table removed with Audit UI; available via /api/v1/trust)",

  // ---- panels[] ----
  "panels[].id": "rendered:panels directly (PanelSpec registry — source string dispatch)",
  "panels[].title": "rendered:panels directly (PanelSpec registry)",
  "panels[].desc": "rendered:panels directly (PanelSpec registry)",
  "panels[].chartKind": "rendered:panels directly (PanelSpec registry)",
  "panels[].source": "ignored: cut (BenchReport.panels emitted but web uses a hardcoded PANELS registry; no consumer)",
  "panels[].layout.wide": "rendered:panels directly (PanelSpec grid sizing hint)",
  "panels[].layout.height": "rendered:panels directly (PanelSpec grid sizing hint)",

  // ---- inference ----
  // Unit 5: cherryPickCard moved to ledger-only (not in the PANELS registry anymore).
  "inference.config.equivalenceMargin": "rendered:panels/bodies/evidenceOverview accuracyParityBody (TOST margin in equivalence panel)",
  "inference.config.bootstrapB": "ignored:ledger-only (cherryPickCard removed from UI; rendered body still importable but not in registry)",
  "inference.config.seed": "ignored:ledger-only (cherryPickCard removed from UI; rendered body still importable but not in registry)",
  "inference.config.fdrQ": "ignored:ledger-only (cherryPickCard removed from UI; rendered body still importable but not in registry)",
  "inference.config.alphaCalibration": "ignored: internal (Bonferroni α copied from InferenceConfig into CalibrationResult.alpha; the web reads that copy, not the config field)",
  "inference.config.alphaSpeed": "ignored: internal (Bonferroni α copied from InferenceConfig into SpeedInferenceResult.alpha; the web reads that copy, not the config field)",
  "inference.config.coverageNominal": "ignored: internal (nominal coverage value stored in CalibrationResult.nominal; InferenceConfig copy not directly read by the web)",
  "inference.config.minPulls": "ignored: internal (threshold used by Python engine; web reads CalibrationResult.skipped instead)",
  "inference.cases[].caseId": "rendered:plots/ciIntervalPlot (case axis label)",
  "inference.cases[].speedupCi": "rendered:plots/ciIntervalPlot (per-case speedup CI)",
  "inference.cases[].deltaR2Ci": "rendered:plots/ciIntervalPlot (per-case Δr² CI)",
  "inference.equivalence[].category": "rendered:shell/Standing TOST verdict chips",
  "inference.equivalence[].equivalent": "rendered:shell/Standing TOST verdict chips",
  "inference.equivalence[].margin": "rendered:shell/Standing TOST margin caption",
  "inference.equivalence[].diff": "rendered: panels/registry accuracyParityCard (Δ per category)",
  "inference.winnerStability": "rendered:plots/winner (bootstrap stability bar chart)",

  // ---- inference.calibration (W10) ----
  // Unit 5: Audit destination removed. W10/W11 detail is ledger-only via /api/v1/trust.
  // Standing renderTruthCard still reads .skipped to decide the "not exercised" note.
  "inference.calibration.n": "ignored: internal (pull count; gate input; CalibrationResult.passed is the rendered verdict)",
  "inference.calibration.coverage": "ignored:ledger-only (W10 detail removed with Audit UI; available via /api/v1/trust)",
  "inference.calibration.coverageCiLo": "ignored:ledger-only (W10 detail removed with Audit UI; available via /api/v1/trust)",
  "inference.calibration.coverageCiHi": "ignored:ledger-only (W10 detail removed with Audit UI; available via /api/v1/trust)",
  "inference.calibration.nominal": "ignored:ledger-only (W10 detail removed with Audit UI; available via /api/v1/trust)",
  "inference.calibration.binomialP": "rendered:panels/bodies/standing renderTruthCard (W10 binomial-p in scope card when exercised)",
  "inference.calibration.ksStat": "ignored: internal (KS statistic; KS p-value surfaced instead for readability)",
  "inference.calibration.ksP": "ignored:ledger-only (W10 detail removed with Audit UI; available via /api/v1/trust)",
  "inference.calibration.alpha": "ignored:ledger-only (W10 detail removed with Audit UI; available via /api/v1/trust)",
  "inference.calibration.passed": "rendered:panels/bodies/standing renderTruthCard (W10 pass/fail in scope card when exercised)",
  "inference.calibration.skipped": "rendered:panels/bodies/standing renderTruthCard (w10Present=false when skipped — routes to 'not exercised' note)",

  // ---- inference.speedInference (W11) ----
  // Unit 5: Audit destination removed. W11 detail is ledger-only via /api/v1/trust.
  "inference.speedInference.geomeanSpeedup": "rendered:panels/bodies/standing renderTruthCard (W11 geomean speedup in scope card when exercised)",
  "inference.speedInference.ciLo": "rendered:panels/bodies/standing renderTruthCard (W11 CI lower bound in scope card when exercised)",
  "inference.speedInference.ciHi": "rendered:panels/bodies/standing renderTruthCard (W11 CI upper bound in scope card when exercised)",
  "inference.speedInference.excludesOne": "ignored:ledger-only (W11 detail removed with Audit UI; available via /api/v1/trust)",
  "inference.speedInference.signP": "ignored:ledger-only (W11 detail removed with Audit UI; available via /api/v1/trust)",
  "inference.speedInference.wilcoxonP": "ignored:ledger-only (W11 detail removed with Audit UI; available via /api/v1/trust)",
  "inference.speedInference.alpha": "ignored:ledger-only (W11 detail removed with Audit UI; available via /api/v1/trust)",
  "inference.speedInference.passed": "rendered:panels/bodies/standing renderTruthCard (W11 pass/fail in scope card when exercised)",
  "inference.speedInference.skipped": "rendered:panels/bodies/standing renderTruthCard (w11Present=false when skipped — routes to 'not exercised' note)",

  // ---- analyzed[] case-level ----
  "analyzed[].id": "rendered:shell/Standing case selector + rendered:plots/spectrum axis title",
  "analyzed[].name": "ignored: structural/internal (display uses id + category)",
  "analyzed[].category": "rendered:shell/Standing case selector chip",
  "analyzed[].x": "rendered:plots/spectrum (x axis grid)",
  "analyzed[].ref": "rendered:plots/spectrum (observed data series)",
  "analyzed[].guess": "rendered:plots/spectrum (initial-guess overlay)",
  "analyzed[].truth": "rendered:plots/recovery (truth diamond markers)",
  "analyzed[].guessParams": "rendered:plots/recovery (initial-guess lollipop)",
  "analyzed[].noise": "ignored: cut (χ² noise-floor proxy removed in the θ-distance swap; not read by convergence)",
  "analyzed[].baseline": "ignored: structural/internal (case generation parameter)",
  "analyzed[].schedule": "ignored: structural/internal (N-grid schedule for scaling, not rendered)",
  "analyzed[].runsSched": "ignored: structural/internal (repetition schedule for scaling, not rendered)",
  "analyzed[].Ngrid": "rendered:plots/scaling (crossover N grid via crossN)",
  "analyzed[].crossN": "rendered:plots/scaling (crossN marker on scaling plot)",
  "analyzed[].paramNames": "rendered: series/conditioning (parameter coupling labels; χ² DOF use removed in the θ-distance swap)",
  "analyzed[].corr": "rendered:plots/conditioning (correlation matrix heatmap)",
  "analyzed[].peaks[].label": "rendered:plots/peaks (peak contribution label)",
  "analyzed[].peaks[].y": "rendered:plots/peaks (peak contribution curve)",
  "analyzed[].multidim": "rendered:panels/bodies/multidimShowcase (G18 — N-D projection heatmap + recovered peak params, sec-showcase)",
  "analyzed[].globalFit": "rendered:panels/bodies/globalFitShowcase (G18 — joint-fit slices + amplitude kinetics, sec-showcase)",

  // ---- analyzed[].nestedAdequacy — NestedAdequacy (W9) ----
  "analyzed[].nestedAdequacy.trueOrder": "rendered:panels/bodies/nestedAdequacy (true order m* verdict header + delta table labels)",
  "analyzed[].nestedAdequacy.reducedRejected": "rendered:panels/bodies/nestedAdequacy (reduced-rejected badge)",
  "analyzed[].nestedAdequacy.overNotPreferredAic": "ignored: internal (gate input; AIC selection exposed via selectedOrderAic)",
  "analyzed[].nestedAdequacy.overNotPreferredBic": "ignored: internal (gate input; BIC selection exposed via selectedOrderBic)",
  "analyzed[].nestedAdequacy.selectedOrderAic": "rendered:panels/bodies/nestedAdequacy (AIC selected order nuance)",
  "analyzed[].nestedAdequacy.selectedOrderBic": "rendered:panels/bodies/nestedAdequacy (BIC selected order verdict)",
  "analyzed[].nestedAdequacy.recoveredTrueOrderAic": "rendered:panels/bodies/nestedAdequacy (AIC recovery badge)",
  "analyzed[].nestedAdequacy.recoveredTrueOrderBic": "rendered:panels/bodies/nestedAdequacy (BIC recovery badge; W9 criterion gate)",
  "analyzed[].nestedAdequacy.reducedVsTrue.lrtStat": "ignored: internal (LRT statistic; p-value surfaced instead for readability)",
  "analyzed[].nestedAdequacy.reducedVsTrue.lrtP": "rendered:panels/bodies/nestedAdequacy (LRT p-value in delta table + verdict header)",
  "analyzed[].nestedAdequacy.reducedVsTrue.fStat": "ignored: internal (F statistic; p-value surfaced instead)",
  "analyzed[].nestedAdequacy.reducedVsTrue.fP": "rendered:panels/bodies/nestedAdequacy (F p-value in delta table)",
  "analyzed[].nestedAdequacy.reducedVsTrue.dAIC": "rendered:panels/bodies/nestedAdequacy (ΔAIC column in delta table)",
  "analyzed[].nestedAdequacy.reducedVsTrue.dBIC": "rendered:panels/bodies/nestedAdequacy (ΔBIC column in delta table)",
  "analyzed[].nestedAdequacy.trueVsOver.lrtStat": "ignored: internal (LRT statistic; p-value surfaced instead for readability)",
  "analyzed[].nestedAdequacy.trueVsOver.lrtP": "rendered:panels/bodies/nestedAdequacy (LRT p-value for true-vs-over comparison)",
  "analyzed[].nestedAdequacy.trueVsOver.fStat": "ignored: internal (F statistic; p-value surfaced instead)",
  "analyzed[].nestedAdequacy.trueVsOver.fP": "rendered:panels/bodies/nestedAdequacy (F p-value for true-vs-over comparison)",
  "analyzed[].nestedAdequacy.trueVsOver.dAIC": "rendered:panels/bodies/nestedAdequacy (ΔAIC for true-vs-over comparison)",
  "analyzed[].nestedAdequacy.trueVsOver.dBIC": "rendered:panels/bodies/nestedAdequacy (ΔBIC for true-vs-over comparison)",

  // ---- analyzed[].profiles.* — BackendProfile ----
  "analyzed[].profiles.*.fit.params": "rendered:plots/recovery (fitted peak parameters)",
  "analyzed[].profiles.*.fit.curve": "rendered:plots/spectrum (solver fit curve overlay)",
  "analyzed[].profiles.*.fit.resid": "rendered:plots/spectrum (residual strip)",
  "analyzed[].profiles.*.conv": "rendered:plots/convergence (cost-vs-iteration series)",
  "analyzed[].profiles.*.grad": "rendered:plots/convergence (gradient series)",
  "analyzed[].profiles.*.convEff": "rendered:plots/convergence (effective convergence series)",
  "analyzed[].profiles.*.historySource": "rendered:plots/convergence (dotted-line provenance flag)",
  "analyzed[].profiles.*.thetaDistance": "rendered:plots/convergence (real convergence-to-truth θ-distance line)",
  "analyzed[].profiles.*.timing.*": "rendered:plots/timing (timing distribution box plot)",
  "analyzed[].profiles.*.accuracy.*": "rendered:panels/bodies/evidenceCase accuracyBody (reduced-χ² distribution box plot per backend, EF-BIND-12)",
  "analyzed[].profiles.*.summary.*": "rendered:chrome/metricsTable (r², χ²_red, RMSE, speedup, iters) + plots/iterations (nIter bar) + series/infoCriteria (aic/bic/dAIC/dBIC/mae → info-criteria panel)",
  "analyzed[].profiles.*.paramErr": "rendered:plots/recovery (per-parameter fit error bars)",
  "analyzed[].profiles.*.ecdfResid": "rendered:plots/residualQQ (QQ normality plot — fallback residual source)",
  "analyzed[].profiles.*.ecdfTime": "ignored: deferred (ECDF timing panel, A10)",
  "analyzed[].profiles.*.warmup.curve": "rendered:plots/warmup (cold→hot amortization line)",
  "analyzed[].profiles.*.warmup.pts": "ignored: deferred (individual warmup annotation dots, A10)",
  "analyzed[].profiles.*.warmup.hotThroughput": "ignored: deferred (throughput annotation, A10)",
  "analyzed[].profiles.*.warmup.coldMs": "rendered:series/warmup (coldMs exposed in WarmupLine)",
  "analyzed[].profiles.*.warmup.hotMs": "rendered:series/warmup (hotMs exposed in WarmupLine)",
  "analyzed[].profiles.*.scaling": "rendered:plots/scaling (time-vs-N log-log series)",
  "analyzed[].profiles.*.uncertainty.*": "rendered:plots/pulls (parameter pull calibration)",
  "analyzed[].profiles.*.paramSpread": "ignored: deferred (param-spread band panel, A10)",
  "analyzed[].profiles.*.stability.*": "rendered:plots/stability (r² mean±sd vs run count)",
  "analyzed[].profiles.*.jacobianConditionNumber": "rendered:plots/conditioning (κ(J) bar per backend)",

  // ---- suite[] ----
  "suite[].id": "rendered:chrome/SuiteTable + plots/saturation (row key)",
  "suite[].name": "ignored: display uses id (SuiteTable renders id not name)",
  "suite[].category": "rendered:chrome/SuiteTable + plots/saturation (category column)",
  "suite[].difficulty": "ignored: deferred (difficulty sort/badge, not yet rendered)",
  "suite[].m.*.speedup": "rendered:chrome/SuiteTable + plots/saturation + plots/speedupDist (distribution box)",
  "suite[].m.*.r2": "rendered:chrome/SuiteTable + plots/saturation",
  "suite[].m.*.redChi2": "rendered:chrome/SuiteTable (reduced chi-squared column per backend)",
  "suite[].m.*.medMs": "rendered:plots/pareto (x axis — median solve time) + plots/performanceProfile (Dolan-Moré cost = medMs)",
  "suite[].m.*.paramErr": "rendered:plots/recoveryError (suite-wide recovery error box per backend)",
  "suite[].m.*.success": "rendered:plots/successRate (success rate per category bars) + chrome/SuiteTable (✓/✗ ok column per backend)",
  "suite[].winner": "rendered:chrome/SuiteTable (winner column)",
  "suite[].regression": "rendered:chrome/SuiteTable (row color + regression flag)",

  // Wave B1 — code-provenance + winner-why
  "analyzed[].modelSourceFile": "rendered:panels/bodies/codeProvenance (kernel source file path in code-provenance panel)",
  "analyzed[].modelFormula": "rendered:panels/bodies/codeProvenance (LaTeX formula string in code-provenance panel)",

  // Track 3 — constraint structure for the FX/TI constrained-fit showcase
  "analyzed[].fixedParams": "rendered:panels/bodies/constraintShowcase (per-node fixed-param names for FX showcase panels)",
  "analyzed[].exprEdges": "rendered:panels/bodies/constraintShowcase (tied-param expression edges for TI showcase panels)",
  "suite[].winnerReason": "rendered:panels/bodies/codeProvenance (winner-why sentence prominently in code-provenance panel)",
  "suite[].m.*.convergenceEfficiency": "rendered:panels/bodies/codeProvenance (per-backend convergence efficiency in supporting signals)",
  "suite[].m.*.illConditioned": "rendered:panels/bodies/codeProvenance (per-backend ill-conditioned flag in supporting signals)",
  "suite[].m.*.redChi2Weighted": "ignored: deferred (σ-weighted reduced-χ²; no panel renders it yet — Wave B2)",
  "suite[].m.*.metricUndefinedReason": "ignored: deferred (metric-undefined explanation; rendered when redChi2Weighted is surfaced — Wave B2)",

  // Wave B1 — run git-provenance fields
  "gitCommit": "rendered:shell/ProvenanceFooter (git commit short hash, gated-on-present)",
  "gitBranch": "rendered:shell/ProvenanceFooter (git branch name, gated-on-present)",
  "runTimestampUnix": "rendered:shell/ProvenanceFooter (human-readable run timestamp, gated-on-present)",
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("contract coverage manifest", () => {
  it("every CONTRACT_LEAVES entry has a COVERAGE classification", () => {
    for (const leaf of CONTRACT_LEAVES) {
      expect(COVERAGE[leaf], `leaf "${leaf}" is missing from COVERAGE`).toBeDefined();
    }
  });

  it("no COVERAGE value is an empty string", () => {
    for (const [leaf, value] of Object.entries(COVERAGE)) {
      expect(value, `COVERAGE["${leaf}"] is an empty string`).not.toBe("");
    }
  });

  it('every COVERAGE value starts with "rendered:" or "ignored:"', () => {
    for (const [leaf, value] of Object.entries(COVERAGE)) {
      const valid = value.startsWith("rendered:") || value.startsWith("ignored:");
      expect(valid, `COVERAGE["${leaf}"] = "${value}" — must start with "rendered:" or "ignored:"`).toBe(true);
    }
  });

  it("the showcase fields are classified rendered (G18 restored the renderers)", () => {
    expect(COVERAGE["analyzed[].multidim"]).toMatch(/^rendered:/);
    expect(COVERAGE["analyzed[].globalFit"]).toMatch(/^rendered:/);
  });

  it("trustBlock.rung is classified as rendered (facts-landing or similar)", () => {
    expect(COVERAGE["trustBlock.rung"]).toMatch(/^rendered:/);
  });

  it("trustBlock claims-count leaves are classified as rendered (not ignored)", () => {
    expect(COVERAGE["trustBlock.nClaimsAudited"]).toMatch(/^rendered:/);
    expect(COVERAGE["trustBlock.nClaimsTotal"]).toMatch(/^rendered:/);
  });

  it("inference CI fields are classified as rendered:plots/ciIntervalPlot", () => {
    expect(COVERAGE["inference.cases[].speedupCi"]).toMatch(/rendered:plots\/ciIntervalPlot/);
    expect(COVERAGE["inference.cases[].deltaR2Ci"]).toMatch(/rendered:plots\/ciIntervalPlot/);
  });

  it("manifest gate fields are classified as rendered:shell/Standing", () => {
    expect(COVERAGE["manifest.geomeanSpeedupVsBaseline"]).toMatch(/rendered:shell\/Standing/);
    expect(COVERAGE["manifest.gateState"]).toMatch(/rendered:shell\/Standing/);
  });
});
