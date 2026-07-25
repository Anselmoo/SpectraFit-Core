/**
 * Source-scan: assert the κ(J) narrative is honest after the W2c semantics
 * fix (EF-RUST-03/04).
 *
 * Forbidden: any non-test source file that claims spectrafit does NOT expose
 * κ(J) — specifically the old "capability gap" framing that wrongly grouped
 * the subject (spectrafit) together with oracle backends (lmfit/jax).
 *
 * The following are still ALLOWED (correct state):
 * - "lmfit/jax do not expose" — accurate; they don't
 * - "capability gap" in a generic `gap`-status label (components.tsx)
 * - "not a subject capability gap" — the correct reframing
 * - Text in *.test.* files (fixtures may use `status="gap"` to test the gap path)
 *
 * Excluded: *.test.*, openapi.gen.ts, contract.ts
 */
import { describe, it, expect } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

/** Walk a directory recursively; yields absolute paths of files. */
function* walkDir(dir: string): Generator<string> {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      yield* walkDir(full);
    } else {
      yield full;
    }
  }
}

/** Files to exclude from the scan. */
function isExcluded(filePath: string): boolean {
  const base = relative(join(import.meta.dirname, ".."), filePath);
  if (/\.test\.[^/]+$/.test(base)) return true;
  if (base === "openapi.gen.ts") return true;
  if (base === "contract/index.ts") return true;
  return false;
}

const SRC_ROOT = join(import.meta.dirname, "..");

/**
 * Patterns that assert the old, incorrect narrative: spectrafit does not
 * expose κ(J), or all three backends (spectrafit/lmfit/jax) share a
 * "capability gap" in conditioning.
 *
 * Each regex targets a phrase that is only false — it will not match the
 * correct reframing ("lmfit and jax do not expose", "oracle limitation", etc.).
 */
const FORBIDDEN_KAPPA_PATTERNS: Array<{ label: string; re: RegExp }> = [
  {
    label: "old 'spectrafit/lmfit/jax' never-expose κ(J) claim",
    // Matches the literal grouping "spectrafit, lmfit and jax never surface"
    // or "spectrafit/lmfit/jax ... not exposed" — the false claim.
    re: /spectrafit[,/].*lmfit.*jax.*(?:never surface|not exposed|capability gap)/i,
  },
  {
    label: "old 'not exposed by spectrafit/lmfit/jax' claim",
    // Matches "not exposed by spectrafit" followed by lmfit anywhere on the line.
    re: /not exposed by spectrafit.*lmfit/i,
  },
  {
    label: "old 'spectrafit … never surface κ(J)' claim",
    // Matches "spectrafit ... never surface κ(J)" — the false per-backend claim.
    re: /spectrafit.*never surface κ\(J\)/i,
  },
];

describe("kappaNarrative — source-scan for correct κ(J) narrative", () => {
  it("no non-test source file contains the old false claim that spectrafit does not expose κ(J)", () => {
    const violations: string[] = [];

    for (const filePath of walkDir(SRC_ROOT)) {
      if (!/\.(ts|tsx)$/.test(filePath)) continue;
      if (isExcluded(filePath)) continue;

      const source = readFileSync(filePath, "utf-8");
      const lines = source.split("\n");

      for (const { label, re } of FORBIDDEN_KAPPA_PATTERNS) {
        lines.forEach((line, idx) => {
          if (re.test(line)) {
            const rel = relative(SRC_ROOT, filePath);
            violations.push(`${rel}:${idx + 1} — ${label}: ${line.trim()}`);
          }
        });
      }
    }

    if (violations.length > 0) {
      console.error(
        "Stale κ(J) narrative violations found (spectrafit DOES expose κ(J)):\n" +
          violations.join("\n"),
      );
    }
    expect(violations).toEqual([]);
  });

  it("the forbidden regexes do NOT false-positive on the correct reframing", () => {
    const correctPhrases = [
      "lmfit and jax do not expose a Jacobian condition number",
      "lmfit/jax absence is a disclosed oracle limitation",
      "not a subject capability gap",
      "spectrafit (the subject) and scipy-ls report κ(J)",
      "κ(J) verified for spectrafit (subject)",
    ];
    for (const phrase of correctPhrases) {
      for (const { label, re } of FORBIDDEN_KAPPA_PATTERNS) {
        expect(
          re.test(phrase),
          `Pattern "${label}" should NOT match the correct phrase: "${phrase}"`,
        ).toBe(false);
      }
    }
  });
});
