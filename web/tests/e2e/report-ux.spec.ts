/**
 * Static bundle UX smoke test — self-contained report.html opened via file://.
 *
 * Tests the bundled `report.html` produced by `uv run poe report_html` (or
 * `poe bundle_report_only`). No dev server: Playwright loads the file directly,
 * exercising the `window.__BENCH__` inline-data path (viteSingleFile +
 * inlineBench plugins).
 *
 * Run:
 *   uv run poe report_e2e          (from project root — resolves REPORT_HTML_PATH)
 *   REPORT_HTML_PATH=/.../report.html npx playwright test tests/e2e/report-ux.spec.ts
 *
 * The test skips gracefully when REPORT_HTML_PATH is absent.
 *
 * Shell note (rewritten 2026-06-20): the dashboard is the two-destination shell
 * — Standing (#standing, default) / Evidence (#evidence)
 * — not the old Suite/Case tabs. The Audit destination was removed; #audit now
 * redirects to #evidence. Stable hooks in the offline bundle: the `nav`
 * buttons, `window.__BENCH__`, and (on Evidence) the rendered plot SVGs + the
 * subject name. The previous spec waited on `.kpi-row` / clicked `Suite`/`Case`,
 * which the Shell 1126→110 refactor removed — hence the rewrite.
 */
import { existsSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test } from "@playwright/test";

const reportPath = process.env.REPORT_HTML_PATH ?? "";
const reportExists = reportPath !== "" && existsSync(resolve(reportPath));
const reportUrl = reportExists ? `file://${resolve(reportPath)}` : "about:blank";

// Destination label → hash (web/src/shell/nav.ts).
const DESTINATIONS: [label: string, hash: string][] = [
  ["Standing", "#standing"],
  ["Evidence", "#evidence"],
];

test.describe("Static report.html bundle — UX smoke", () => {
  test.beforeEach(async ({ page }) => {
    if (!reportExists) {
      test.skip(true, "REPORT_HTML_PATH not set or file not found — run `uv run poe report_html` first");
      return;
    }
    await page.goto(reportUrl);
    // The shell nav mounts only after React hydrates window.__BENCH__.
    await page.waitForSelector("nav button", { timeout: 15_000 });
  });

  // 1. Shell mounts with exactly the two destinations (Audit removed).
  test("shell mounts with the two destinations", async ({ page }) => {
    if (!reportExists) return;
    const nav = page.locator("nav button");
    await expect(nav).toHaveCount(2);
    const labels = (await nav.allTextContents()).join(" ");
    for (const [label] of DESTINATIONS) expect(labels).toContain(label);
  });

  // 2. Each destination navigates (sets its hash) without error.
  test("each destination navigates", async ({ page }) => {
    if (!reportExists) return;
    for (const [label, hash] of DESTINATIONS) {
      await page.locator("nav button").filter({ hasText: label }).click();
      await expect.poll(() => page.evaluate(() => location.hash)).toBe(hash);
    }
  });

  // 3. Evidence — the data destination — renders backend plots and names the
  //    subject solver (replaces the old "≥3 backend cards" + "headline" tests).
  test("Evidence renders plots and names the subject solver", async ({ page }) => {
    if (!reportExists) return;
    await page.locator("nav button").filter({ hasText: "Evidence" }).click();
    await page.waitForSelector("svg", { timeout: 15_000 });
    expect(await page.locator("svg").count()).toBeGreaterThanOrEqual(3);
    const text = (await page.locator("body").textContent()) ?? "";
    expect(text.toLowerCase()).toContain("spectrafit");
  });

  // 4. Inline-data path — window.__BENCH__ carries the backend roster.
  test("window.__BENCH__ carries the backend roster", async ({ page }) => {
    if (!reportExists) return;
    const roster = await page.evaluate(() => {
      const b = (window as unknown as { __BENCH__?: { solvers?: { id: string }[] } }).__BENCH__;
      return b?.solvers?.map((s) => s.id) ?? [];
    });
    expect(roster.length).toBeGreaterThanOrEqual(3);
    expect(roster).toContain("spectrafit");
  });
});
