/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

/**
 * Vitest config for the greenfield web tests. These lock the rebuild's guarantees:
 * distinct plots per case, optfn renders without jax, no silent PRIMARY fallback, and
 * no hardcoded backend ids. Tests are excluded from the production `tsc` build.
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "happy-dom",
    include: ["src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
    // A few tests are slow-but-correct under parallel load: openapiSync.test.ts
    // shells out to `openapi-typescript` (execFileSync) and warmup.test.ts renders
    // canvas. Under full parallel workers these exceed the 5s default and get killed
    // mid-run (they pass in isolation), causing intermittent red. A generous timeout
    // lets them finish without masking real failures — a genuine mismatch still fails,
    // it just waits. (Hotspots #3, 2026-06-20.)
    testTimeout: 30_000,
    hookTimeout: 30_000,
    coverage: {
      provider: "v8",
      // 'lcov' is REQUIRED: scripts/coverage_atlas.py and both GitHub's
      // coverage-atlas-fused job and GitLab's coverage:atlas job only consume
      // web/coverage/lcov.info. Vitest's default reporters (text/html/json/clover)
      // never produce it, so it silently never existed until this fix.
      reporter: ["text", "html", "json", "clover", "lcov"],
    },
  },
});
