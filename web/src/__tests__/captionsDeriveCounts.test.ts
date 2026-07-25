/**
 * Source-scan: a panel caption must not hardcode a case/dataset count.
 *
 * The served report can be a 15-case quick run or a 139-case full run; a caption
 * that states "All 139 cases" as a static string drifts from the data the moment
 * the run size changes (a real presentation-vs-data bug we hit). Counts in a
 * caption must come from the report — i.e. a `caption: (r) => ...${r.suite.length}...`
 * function, never a static string with a baked-in number followed by
 * "case(s)"/"dataset(s)".
 *
 * This is the enforcement of the invariant "every factual claim in a caption is
 * derived from the data it describes" — generalized from the I1/L3 claim⇒evidence
 * work to the caption surface.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// Scan registry.tsx AND the bodies/ modules: captions live in the PANELS records
// (registry.tsx today) but a caption can move into a body — scanning registry.tsx
// alone would silently stop checking it (the bodies-split vacuity class). Mirror
// plotSpec.test.ts and concatenate the panel source.
const PANEL_DIR = join(import.meta.dirname, "..", "panels");
const BODY_FILES = [
  join(PANEL_DIR, "registry.tsx"),
  join(PANEL_DIR, "bodies", "standing.tsx"),
  join(PANEL_DIR, "bodies", "methods.tsx"),
  join(PANEL_DIR, "bodies", "evidenceOverview.tsx"),
  join(PANEL_DIR, "bodies", "evidenceCase.tsx"),
  join(PANEL_DIR, "bodies", "shared.tsx"),
];
const REGISTRY = BODY_FILES.map((p) => readFileSync(p, "utf8")).join("\n");

// A static (double-quoted) caption value: `caption: "..."`. Function captions
// (`caption: (r) => \`...\``) use backticks and are intentionally NOT matched —
// they are the correct, data-derived form.
const STATIC_CAPTION = /caption:\s*"((?:[^"\\]|\\.)*)"/g;

// A baked-in count: one or more digits, optional separators, then a case/dataset
// noun. Thresholds like "4 sig figs" or "±1σ" are not counts and are allowed.
const HARDCODED_COUNT = /\b\d[\d,]*\s+(?:cases?|datasets?)\b/i;

// A hardcoded grid dimension like "28×28" or "28x28" — a data-fact (the 2-D map
// shape) that must come from the series, never a baked-in literal. This caught a
// real drift: the removed multidim/time-resolved showcase captions stated
// "28×28" / "12 time slices" while the contract carried the true shape.
const HARDCODED_GRID = /\b\d+\s*[×x]\s*\d+\b/;

// Unit 4 guard: no hardcoded integer denominators next to "backends"/"of 27"/etc.
// in body modules. Scans the entire body source (not just captions).
// Pattern: `const <IDENT> = <int>;` for well-known sentinel values, OR
// a bare numeric literal followed by "backends" or "of 27" etc.
const HARDCODED_DENOM_PATTERNS: Array<{ label: string; re: RegExp }> = [
  // Ban `const NIST_STRD_TOTAL = <number>` — denominator must come from the contract.
  { label: "hardcoded NIST total const", re: /const\s+NIST_STRD_TOTAL\s*=\s*\d+/ },
  // Ban bare numeric literal "of 27" / "of 6" etc. followed by a noun (case-insensitive).
  // Exceptions: "of the NIST" or "of each" or similar prose are OK — only digit immediately before "of" is flagged.
  { label: 'hardcoded "of 27" denominator in prose', re: /\bof\s+27\b/ },
  // Ban " 6 backends" / " 5 backends" hardcoded.
  { label: 'hardcoded backend count literal ("N backends")', re: /\b[456]\s+backends?\b/i },
];

describe("captions derive counts from data", () => {
  it("no static caption hardcodes a case/dataset count", () => {
    const src = REGISTRY;
    const offenders: string[] = [];
    for (const m of src.matchAll(STATIC_CAPTION)) {
      const text = m[1];
      if (HARDCODED_COUNT.test(text)) offenders.push(text);
    }
    expect(
      offenders,
      `Static captions must not bake in a case/dataset count — use a ` +
        `caption: (r) => \`...\${r.suite.length} cases...\` so it tracks the served run.\n` +
        offenders.map((o) => `  • "${o}"`).join("\n"),
    ).toEqual([]);
  });

  it("no static caption hardcodes a grid dimension (e.g. 28×28)", () => {
    const src = REGISTRY;
    const offenders: string[] = [];
    for (const m of src.matchAll(STATIC_CAPTION)) {
      if (HARDCODED_GRID.test(m[1])) offenders.push(m[1]);
    }
    expect(
      offenders,
      `Static captions must not bake in a grid dimension — derive it from the ` +
        `series (e.g. \`\${s.rows}×\${s.cols}\`) so it tracks the served data.\n` +
        offenders.map((o) => `  • "${o}"`).join("\n"),
    ).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Unit 4 guard — body modules must not hardcode counts/denominators
// ---------------------------------------------------------------------------

describe("body modules derive counts (Unit 4 — data-derived invariant)", () => {
  it("no body module hardcodes NIST_STRD_TOTAL or a bare 'of 27' denominator", () => {
    const offenders: string[] = [];
    for (const [idx, src] of BODY_FILES.map((p) => readFileSync(p, "utf8")).entries()) {
      for (const { label, re } of HARDCODED_DENOM_PATTERNS) {
        const lines = src.split("\n");
        lines.forEach((line, li) => {
          if (re.test(line)) {
            offenders.push(`${BODY_FILES[idx].split("/").slice(-2).join("/")}:${li + 1} — ${label}: ${line.trim()}`);
          }
        });
      }
    }
    if (offenders.length > 0) {
      console.error("Hardcoded count/denominator violations:\n" + offenders.join("\n"));
    }
    expect(offenders).toEqual([]);
  });
});
