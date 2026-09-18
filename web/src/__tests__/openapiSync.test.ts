/**
 * openapiSync.test.ts
 *
 * Guards seam meta-gap M1: openapi.gen.ts must stay in sync with the checked-in
 * OpenAPI snapshot (openapi.snapshot.json). If someone edits python/oracles/contract.py
 * and forgets to regenerate the TS types, this test fails.
 *
 * How it works (in-process, no spawning):
 *   1. Read web/openapi.snapshot.json (the stable, committed schema source).
 *   2. Invoke openapi-typescript programmatically to regenerate TS types from
 *      the snapshot into a temp buffer.
 *   3. Compare the fresh output against the checked-in web/src/openapi.gen.ts,
 *      ignoring the file-header comment block (lines starting with "/**…" up to
 *      the first blank line) which may differ between the checked-in version and
 *      what is generated today — the meaningful structural content must match.
 *
 * Non-vacuity proof (verified manually during authoring):
 *   - Temporarily modifying openapi.snapshot.json (e.g. changing a type from
 *     "number" to "string") causes this test to FAIL.
 *   - Restoring the snapshot makes it PASS.
 *
 * To fix a failure:
 *   1. Start the API: uv run poe serve
 *   2. Capture new snapshot: curl -s localhost:8000/openapi.json | python3 -m json.tool > openapi.snapshot.json
 *   3. Regenerate TS types: npm run contract
 *   4. Commit both files together.
 *
 * Regenerate via `npm run contract`; `npm run check:contract` guards drift.
 */

import { describe, it, expect } from "vitest";
import { execFileSync } from "node:child_process";
import { readFileSync, existsSync, writeFileSync, unlinkSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { randomBytes } from "node:crypto";

const WEB_ROOT = join(import.meta.dirname, "..", "..");
const SNAPSHOT_PATH = join(WEB_ROOT, "openapi.snapshot.json");
const GEN_PATH = join(WEB_ROOT, "src", "openapi.gen.ts");
const OPENAPI_TS_BIN = join(WEB_ROOT, "node_modules", ".bin", "openapi-typescript");

/**
 * Strip the leading JSDoc comment block (the auto-generated header) from a
 * TypeScript source string. This isolates the structural content for comparison
 * so that a header phrasing change never causes a false positive.
 */
function stripHeader(src: string): string {
  // Match the opening /** ... */ block followed by optional blank lines.
  // The header is everything from the start up to and including the first
  // blank line after the closing */.
  return src.replace(/^\/\*\*[\s\S]*?\*\/\s*\n/, "");
}

describe("openapi-sync guard (meta-gap M1)", () => {
  it("openapi.snapshot.json exists", () => {
    expect(
      existsSync(SNAPSHOT_PATH),
      `openapi.snapshot.json not found at ${SNAPSHOT_PATH}. ` +
        "Create it: curl -s localhost:8000/openapi.json | python3 -m json.tool > openapi.snapshot.json"
    ).toBe(true);
  });

  it("openapi.gen.ts matches types regenerated from the snapshot", () => {
    // Unique temp file so parallel test runs don't collide
    const tmpFile = join(
      tmpdir(),
      `openapi-check-${randomBytes(6).toString("hex")}.ts`
    );

    try {
      // Regenerate from the snapshot into a temp file
      execFileSync(
        "node",
        [OPENAPI_TS_BIN, SNAPSHOT_PATH, "-o", tmpFile],
        { cwd: WEB_ROOT, stdio: "pipe" }
      );

      const fresh = readFileSync(tmpFile, "utf8");
      const checked = readFileSync(GEN_PATH, "utf8");

      // Compare structural content (after stripping the auto-generated header)
      const freshBody = stripHeader(fresh);
      const checkedBody = stripHeader(checked);

      if (freshBody !== checkedBody) {
        // Surface a useful diff excerpt so it's easy to see what drifted
        const freshLines = freshBody.split("\n");
        const checkedLines = checkedBody.split("\n");
        const diffLines: string[] = [];
        const maxLines = Math.max(freshLines.length, checkedLines.length);
        for (let i = 0; i < maxLines && diffLines.length < 20; i++) {
          if (freshLines[i] !== checkedLines[i]) {
            diffLines.push(`line ${i + 1}:`);
            diffLines.push(`  snapshot-gen: ${freshLines[i] ?? "(missing)"}`);
            diffLines.push(`  checked-in:   ${checkedLines[i] ?? "(missing)"}`);
          }
        }
        throw new Error(
          "openapi.gen.ts is OUT OF SYNC with the contract snapshot.\n" +
            "Fix: start the API (uv run poe serve), then:\n" +
            "  curl -s localhost:8000/openapi.json | python3 -m json.tool > openapi.snapshot.json\n" +
            "  npm run contract\n" +
            "  git add openapi.snapshot.json src/openapi.gen.ts\n\n" +
            "First differing lines (snapshot-regen vs checked-in):\n" +
            diffLines.join("\n")
        );
      }

      expect(freshBody).toBe(checkedBody);
    } finally {
      // Clean up temp file even if the test fails
      if (existsSync(tmpFile)) unlinkSync(tmpFile);
    }
  });

  it("NON-VACUITY: a perturbed snapshot causes a mismatch (self-test)", () => {
    // This test verifies the guard is non-trivial: mutating the snapshot
    // produces a different output that does NOT match the checked-in gen file.
    const snapshot = JSON.parse(readFileSync(SNAPSHOT_PATH, "utf8"));

    // Perturb: inject a fake path that doesn't exist in the real schema
    const perturbedSnapshot = {
      ...snapshot,
      paths: {
        ...snapshot.paths,
        "/__nonvacuity_sentinel__": {
          get: {
            operationId: "nonvacuity_sentinel",
            responses: {
              "200": {
                description: "sentinel",
                content: {
                  "application/json": {
                    schema: { type: "object" },
                  },
                },
              },
            },
          },
        },
      },
    };

    const tmpSnapshot = join(
      tmpdir(),
      `openapi-perturbed-${randomBytes(6).toString("hex")}.json`
    );
    const tmpFile = join(
      tmpdir(),
      `openapi-perturbed-out-${randomBytes(6).toString("hex")}.ts`
    );

    try {
      writeFileSync(tmpSnapshot, JSON.stringify(perturbedSnapshot, null, 4), "utf8");

      execFileSync(
        "node",
        [OPENAPI_TS_BIN, tmpSnapshot, "-o", tmpFile],
        { cwd: WEB_ROOT, stdio: "pipe" }
      );

      const perturbedFresh = readFileSync(tmpFile, "utf8");
      const checked = readFileSync(GEN_PATH, "utf8");

      // The perturbed version MUST differ from the checked-in file
      expect(stripHeader(perturbedFresh)).not.toBe(
        stripHeader(checked),
        "Non-vacuity FAILED: a perturbed snapshot produced identical output — the guard is broken."
      );
    } finally {
      if (existsSync(tmpSnapshot)) unlinkSync(tmpSnapshot);
      if (existsSync(tmpFile)) unlinkSync(tmpFile);
    }
  });
});
