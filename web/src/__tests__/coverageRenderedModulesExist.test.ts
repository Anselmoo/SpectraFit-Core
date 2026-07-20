/**
 * I-DRIFT meta-guard: every "rendered:<moduleToken> ..." classification in
 * contractCoverage.test.ts must name a moduleToken that corresponds to a real
 * source directory under web/src/.
 *
 * The guard is intentionally coarse — the moduleToken is the first word after
 * "rendered:" (alphanum + underscore only, no slash, stops at "/" or space).
 * Checking directory existence is sufficient to catch the failure mode where a
 * module is deleted but its coverage classification is not updated (I-DRIFT).
 *
 * If this test fails, offenders lists the tokens that have no matching
 * web/src/<token>/ directory. Either:
 *   (a) genuine drift: a module directory was deleted — reclassify the
 *       coverage entry as "ignored:" (do not simply widen this guard); or
 *   (b) false positive: the guard's source list needs to be broader so
 *       legitimate tokens resolve.
 */
import { describe, it, expect } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";

const COVERAGE_FILE = join(
  dirname(import.meta.url.replace("file://", "")),
  "contractCoverage.test.ts",
);

/**
 * Extract every moduleToken from "rendered:<token>..." classifications.
 * The token is the first alphanum word after "rendered:" (optional space),
 * matching [a-zA-Z][\w]* — stops at "/" or whitespace.
 * Example: "rendered:plots/ciIntervalPlot ..." → token = "plots"
 *          "rendered: panels/registry ..."     → token = "panels"
 *          "rendered:contract gate ..."         → token = "contract"
 */
function extractRenderedTokens(source: string): string[] {
  const re = /"[^"]+"\s*:\s*"rendered:\s*([a-zA-Z][\w]*)([^"]*?)"/g;
  const tokens: string[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(source)) !== null) {
    tokens.push(m[1]);
  }
  return tokens;
}

describe("I-DRIFT: rendered: module tokens exist in web/src/", () => {
  it("every rendered:<moduleToken> names a real web/src/<moduleToken>/ directory", () => {
    const source = readFileSync(COVERAGE_FILE, "utf-8");
    const tokens = extractRenderedTokens(source);

    // Deduplicate for a clean error message.
    const unique = [...new Set(tokens)];

    const webSrc = join(
      dirname(import.meta.url.replace("file://", "")),
      "..", // web/src/__tests__ → web/src
    );

    const offenders = unique.filter(
      (token) => !existsSync(join(webSrc, token)),
    );

    expect(offenders, [
      "The following rendered: moduleToken(s) have no matching web/src/<token>/ directory.",
      "This means a module was deleted without updating its contractCoverage.test.ts classification.",
      "Fix: change the affected 'rendered:' entry to 'ignored:' with the reason 'cut (module deleted)'.",
      `Offending tokens: ${offenders.join(", ")}`,
    ].join("\n")).toEqual([]);
  });

  it("extracts at least 5 distinct module tokens (smoke-check the regex)", () => {
    const source = readFileSync(COVERAGE_FILE, "utf-8");
    const tokens = [...new Set(extractRenderedTokens(source))];
    // Known tokens: panels, plots, series, shell, chrome
    // Note: "narrative" entries were reclassified to ignored:ledger-only when Audit UI was removed;
    // "contract" is a bare (unquoted) key so it doesn't match the regex pattern.
    expect(tokens.length, `expected ≥5 distinct tokens, got ${tokens.length}: ${tokens.join(", ")}`).toBeGreaterThanOrEqual(5);
  });
});
