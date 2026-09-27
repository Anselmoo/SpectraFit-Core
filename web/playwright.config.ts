/**
 * Playwright configuration for SpectraFit benchmark web UI end-to-end tests.
 *
 * Prerequisites (one-time, not run here to avoid downloading ~300 MB):
 *   npx playwright install chromium
 *
 * Run via project root:
 *   uv run poe web_e2e
 *
 * Or directly from the web/ directory:
 *   npx playwright test
 */
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "tests/e2e",

  // Each test file gets a fresh browser context; no global state leaks.
  fullyParallel: true,

  // Fail the CI step on test.only() left in source.
  forbidOnly: !!process.env.CI,

  // No retries locally — flaky failures should be investigated, not hidden.
  retries: 0,

  // Chromium only — skip firefox/webkit to keep the install footprint small.
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  use: {
    baseURL: "http://localhost:5173",

    // Capture traces on first failure for easier debugging.
    trace: "on-first-retry",
  },

  // Start the Vite dev server before running tests — UNLESS REPORT_HTML_PATH is
  // set, in which case the static-bundle spec (report-ux.spec.ts) opens the file
  // directly via file:// and no dev server is needed.
  webServer: process.env.REPORT_HTML_PATH
    ? undefined
    : {
        command: "npm run dev",
        url: "http://localhost:5173",
        reuseExistingServer: !process.env.CI,
        // Allow up to 30 s for Vite to cold-start.
        timeout: 30_000,
      },
});
