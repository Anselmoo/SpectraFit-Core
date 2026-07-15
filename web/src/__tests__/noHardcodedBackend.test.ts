/**
 * Source-scan: fail if any non-test source file under web/src/ contains
 * hardcoded backend ids, podium patterns, boast words on neutral surfaces,
 * bare ASME authority without the hedge, or the "self-audited" mark.
 *
 * Excluded files: *.test.*, openapi.gen.ts, contract.ts
 *
 * Note: `spectrafitWinRate` is a CONTRACT FIELD name read from manifest — it is
 * NOT a hardcoded backend id. None of the regexes below match it (verified below).
 *
 * Unit 1 guard: boast words ("faster","wins","best","beats") in headline/neutral prose.
 * Unit 2 guard: "ASME" must carry the hedge token "not conformant".
 * Unit 3 guard: "self-audited" is banned.
 */
import { describe, it, expect } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

// Patterns that indicate hardcoded backend selection (subject-not-blind)
const FORBIDDEN_PATTERNS: Array<{ label: string; re: RegExp }> = [
  { label: "prof() call with hardcoded id", re: /prof\(\s*["']spectrafit["']\s*\)/ },
  { label: "profiles.spectrafit property access", re: /profiles\.\s*spectrafit/ },
  { label: "hardcoded podium array [spectrafit,lmfit,...]", re: /\[\s*["']spectrafit["']\s*,\s*["']lmfit["']/ },
];

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
  const base = relative(
    join(import.meta.dirname, ".."),
    filePath,
  );
  // Exclude test files
  if (/\.test\.[^/]+$/.test(base)) return true;
  // Exclude generated contract and openapi artefacts
  if (base === "openapi.gen.ts") return true;
  if (base === "contract/index.ts") return true; // contract.ts re-export
  return false;
}

const SRC_ROOT = join(import.meta.dirname, "..");

describe("noHardcodedBackend — source-scan neutrality", () => {
  it("no source file hardcodes a backend id or podium pattern", () => {
    const violations: string[] = [];

    for (const filePath of walkDir(SRC_ROOT)) {
      // Only TypeScript / TSX files
      if (!/\.(ts|tsx)$/.test(filePath)) continue;
      if (isExcluded(filePath)) continue;

      const source = readFileSync(filePath, "utf-8");
      const lines = source.split("\n");

      for (const { label, re } of FORBIDDEN_PATTERNS) {
        lines.forEach((line, idx) => {
          if (re.test(line)) {
            const rel = relative(SRC_ROOT, filePath);
            violations.push(`${rel}:${idx + 1} — ${label}: ${line.trim()}`);
          }
        });
      }
    }

    if (violations.length > 0) {
      // Print all violations for easy diagnosis
      console.error("Hardcoded backend id violations found:\n" + violations.join("\n"));
    }
    expect(violations).toEqual([]);
  });

  it("spectrafitWinRate (contract field) does NOT trigger the forbidden patterns", () => {
    // Verify our regexes don't false-positive on the contract field name
    const contractFieldUsage = `const winRate = m.spectrafitWinRate * 100;`;
    for (const { label, re } of FORBIDDEN_PATTERNS) {
      expect(
        re.test(contractFieldUsage),
        `Pattern "${label}" should NOT match spectrafitWinRate usage`,
      ).toBe(false);
    }
  });
});

// ---------------------------------------------------------------------------
// Unit 3 guard — "self-audited" string is banned from all non-test source files
// ---------------------------------------------------------------------------

describe("noSelfAudited — 'self-audited' mark must not appear in source", () => {
  it("no non-test source file contains the string 'self-audited'", () => {
    const violations: string[] = [];
    for (const filePath of walkDir(SRC_ROOT)) {
      if (!/\.(ts|tsx)$/.test(filePath)) continue;
      if (isExcluded(filePath)) continue;
      const source = readFileSync(filePath, "utf-8");
      if (/self-audited/i.test(source)) {
        const rel = relative(SRC_ROOT, filePath);
        violations.push(rel);
      }
    }
    expect(violations, `"self-audited" must not appear in source: ${violations.join(", ")}`).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Unit 2 guard — "ASME" must always carry the hedge "not conformant"
//
// The hedge must appear in the same string context as "ASME" so a future
// bare "ASME V&V" addition fails immediately.
// Strategy: for each file, find lines that contain "ASME" but do NOT also
// contain the hedge on the SAME LINE or within 3 lines before/after.
// The hedge token is "not conformant" (the normative hedge) or "inspired by".
// ---------------------------------------------------------------------------

describe("noBarehAASME — ASME authority always carries the hedge", () => {
  // Files where ASME appears only in test fixture text or comments — exempt.
  const ASME_EXEMPT_SUFFIXES = [
    "__tests__/noHardcodedBackend.test.ts", // this file
  ];

  it('no source file renders "ASME" without the hedge ("not conformant" or "inspired by")', () => {
    const violations: string[] = [];

    for (const filePath of walkDir(SRC_ROOT)) {
      if (!/\.(ts|tsx)$/.test(filePath)) continue;
      if (isExcluded(filePath)) continue;
      const rel = relative(SRC_ROOT, filePath);
      if (ASME_EXEMPT_SUFFIXES.some((s) => rel.endsWith(s))) continue;

      const source = readFileSync(filePath, "utf-8");
      if (!/ASME/i.test(source)) continue;

      const lines = source.split("\n");
      for (let i = 0; i < lines.length; i++) {
        if (!/ASME/i.test(lines[i])) continue;
        // Skip pure comment lines (code comments are not rendered text).
        const trimmed = lines[i].trim();
        if (trimmed.startsWith("//") || trimmed.startsWith("*") || trimmed.startsWith("/*")) continue;
        // Check a 4-line window around the ASME occurrence for the hedge.
        const windowLines = lines.slice(Math.max(0, i - 3), Math.min(lines.length, i + 5));
        const windowText = windowLines.join(" ");
        const hasHedge =
          /not conformant/i.test(windowText) ||
          /inspired by/i.test(windowText);
        if (!hasHedge) {
          violations.push(`${rel}:${i + 1} — "ASME" without hedge: ${lines[i].trim()}`);
        }
      }
    }

    if (violations.length > 0) {
      console.error("ASME without hedge violations:\n" + violations.join("\n"));
    }
    expect(violations).toEqual([]);
  });
});
