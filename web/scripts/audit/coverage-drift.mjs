// Applies findCoverageDrift to the real manifest + concatenated panel/binding
// source. Run from web/:  npx tsx scripts/audit/coverage-drift.mjs
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { findCoverageDrift } from "../../src/audit/coverageDrift.ts";

// The contractCoverage manifest is a TS object literal; extract the "leaf": "class"
// pairs with a tolerant regex (discovery tool — good enough, not a parser).
const covSrc = readFileSync("src/__tests__/contractCoverage.test.ts", "utf8");
const manifest = {};
for (const m of covSrc.matchAll(/"([^"]+)":\s*"((?:ignored|rendered)[^"]*)"/g)) {
  manifest[m[1]] = m[2];
}

const dirs = ["src/panels", "src/shell", "src/contract"];
let source = "";
for (const d of dirs) {
  for (const f of readdirSync(d)) {
    if (f.endsWith(".tsx") || f.endsWith(".ts")) source += readFileSync(join(d, f), "utf8");
  }
}

const drift = findCoverageDrift(manifest, source);
console.log(`coverage-drift candidates: ${drift.length}`);
for (const d of drift) console.log(`  ${d.leaf}  [${d.classification}]`);
