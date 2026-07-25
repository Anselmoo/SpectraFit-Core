/**
 * check-openapi-sync.mjs
 *
 * Regenerate TypeScript types from the checked-in OpenAPI snapshot and compare
 * against the checked-in openapi.gen.ts. Exits 1 (and prints a helpful message)
 * if they differ — meaning someone edited python/oracles/contract.py and forgot
 * to run `npm run contract`.
 *
 * Usage (from web/):
 *   node scripts/check-openapi-sync.mjs
 *
 * Called by:
 *   npm run check:contract
 *
 * To regenerate both the snapshot and openapi.gen.ts from a live API:
 *   curl -s localhost:8000/openapi.json | python3 -m json.tool > openapi.snapshot.json
 *   npm run contract
 */

import { execSync } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const webRoot = join(__dirname, "..");

const snapshotPath = join(webRoot, "openapi.snapshot.json");
const genPath = join(webRoot, "src", "openapi.gen.ts");
const tmpPath = join("/tmp", "openapi.check.ts");

if (!existsSync(snapshotPath)) {
  console.error(
    `[check-openapi-sync] FAIL: openapi.snapshot.json not found at ${snapshotPath}.\n` +
      `  To create it: curl -s localhost:8000/openapi.json | python3 -m json.tool > openapi.snapshot.json`
  );
  process.exit(1);
}

if (!existsSync(genPath)) {
  console.error(
    `[check-openapi-sync] FAIL: openapi.gen.ts not found at ${genPath}.\n` +
      `  To create it: npm run contract`
  );
  process.exit(1);
}

// Regenerate from snapshot into /tmp
try {
  execSync(
    `node node_modules/.bin/openapi-typescript ${snapshotPath} -o ${tmpPath}`,
    { cwd: webRoot, stdio: "pipe" }
  );
} catch (err) {
  console.error(
    `[check-openapi-sync] FAIL: openapi-typescript failed.\n${err.stderr?.toString() ?? err.message}`
  );
  process.exit(1);
}

/**
 * Strip the leading JSDoc comment block (the auto-generated header) from a
 * TypeScript source string. This isolates the structural content for comparison
 * so that extra documentation lines in the header never cause false positives.
 */
function stripHeader(src) {
  return src.replace(/^\/\*\*[\s\S]*?\*\/\s*\n/, "");
}

// Compare the regenerated file against the checked-in gen file (headers stripped)
const checked = stripHeader(readFileSync(genPath, "utf8"));
const fresh = stripHeader(readFileSync(tmpPath, "utf8"));

if (checked === fresh) {
  console.log(
    "[check-openapi-sync] OK: openapi.gen.ts matches the contract snapshot."
  );
  process.exit(0);
} else {
  // Show a brief diff to help identify what changed
  let diffOutput = "";
  try {
    // Write stripped versions to temp files for a clean diff
    const { writeFileSync } = await import("node:fs");
    const strippedGen = tmpPath + ".gen-stripped.ts";
    const strippedFresh = tmpPath + ".fresh-stripped.ts";
    writeFileSync(strippedGen, checked, "utf8");
    writeFileSync(strippedFresh, fresh, "utf8");
    diffOutput = execSync(`diff ${strippedGen} ${strippedFresh}`, {
      cwd: webRoot,
      encoding: "utf8",
    });
  } catch (diffErr) {
    diffOutput = diffErr.stdout ?? "(diff unavailable)";
  }

  console.error(
    `[check-openapi-sync] FAIL: openapi.gen.ts is OUT OF SYNC with the contract snapshot.\n` +
      `\nTo fix:\n` +
      `  1. Start the API: uv run poe serve\n` +
      `  2. Capture a new snapshot: curl -s localhost:8000/openapi.json | python3 -m json.tool > openapi.snapshot.json\n` +
      `  3. Regenerate the TS types: npm run contract\n` +
      `  4. Commit both files together.\n` +
      `\nDiff (gen.ts → fresh from snapshot, headers stripped):\n${diffOutput}`
  );
  process.exit(1);
}
