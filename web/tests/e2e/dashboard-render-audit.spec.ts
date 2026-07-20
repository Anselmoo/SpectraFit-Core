/**
 * Evidence render-audit — the guard for the bug class that unit tests cannot see:
 * live React render crashes, blank panels, colorless solver marks, and IA scope
 * drift. Each was found by hand via Playwright; this encodes them permanently.
 *
 * Requires the FastAPI API on :8000 (serves /api/report) and the Vite dev server
 * (auto-started by playwright.config). Run: `npx playwright test evidence-render-audit`.
 */
import { test, expect, type Page } from "@playwright/test";

// One representative case per category (+ a decimated worst case).
const CASES = ["EZ-001", "CX-001", "RL-001", "OF-001", "SC-006", "ED-001", "LS-001"];

const SINGLE_TITLES =
  /Peak contributions|Parameter recovery|Pull calibration|Convergence|Timing distribution|Cold → hot|Scaling|Reproducibility|Conditioning|Fit — reference/;
const OVERALL_TITLES =
  /All cases \(suite\)|Saturation map|Winner stability|Multi-dimensional fit|Global fit — one shared model/;

/** Per-panel audit: title, svg count, whether any svg is present-but-empty. */
function auditPanels(page: Page) {
  return page.evaluate(() => {
    const isData = (a: string | null) =>
      !!a && /(^|\s)(dot|line|bar|cell|link|area|tick|rect)(\s|$)/.test(a) && !/axis|grid/.test(a);
    return [...document.querySelectorAll(".glass")]
      .filter((p) => p.querySelector("h2,h3"))
      .map((p) => {
        const title = (p.querySelector("h2,h3") as HTMLElement).textContent!.trim();
        const svgs = [...p.querySelectorAll("svg")];
        const marks = svgs.map((s) =>
          [...s.querySelectorAll("g[aria-label]")]
            .filter((g) => isData(g.getAttribute("aria-label")))
            .reduce((n, g) => n + g.querySelectorAll("path,circle,rect,line").length, 0),
        );
        return { title, svgCount: svgs.length, blank: svgs.length > 0 && marks.some((m) => m === 0) };
      });
  });
}

function attachErrorSink(page: Page): string[] {
  const errs: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error" && !/DevTools/.test(m.text())) errs.push(m.text());
  });
  page.on("pageerror", (e) => errs.push(String(e)));
  return errs;
}

async function ensureLoaded(page: Page) {
  // Wait for the real shell nav (the report finished loading) — NOT just `.glass`,
  // which ALSO matches the "Loading report…" card and races the spinner under
  // parallel workers + a cold API (the cause of intermittent count===0 failures).
  await page.waitForSelector('nav[aria-label="Narrative navigation"] button', {
    timeout: 15_000,
  });
  // EvidencePanel mounts plots in effects; give them a beat.
  await page.waitForTimeout(500);
  const body = await page.evaluate(() => document.body.innerText);
  expect(body, "report failed to load — is the API on :8000 up?").not.toMatch(
    /Report load failed|unsupported schema|can.t be reached/i,
  );
}

test.describe("Evidence render audit", () => {
  // Serialize within this file: all tests share the same Vite/API dev servers;
  // running 5 workers simultaneously causes timeout races on the svg-line waitFor.
  test.describe.configure({ mode: "serial" });

  test("Overview: no console errors, no blank panels, only overall panels", async ({ page }) => {
    const errs = attachErrorSink(page);
    await page.goto("/#evidence");
    await ensureLoaded(page);
    const audit = await auditPanels(page);
    // scope contract: Overview shows NO single-case panels
    expect(audit.map((a) => a.title).join(" ")).not.toMatch(SINGLE_TITLES);
    // no present-but-empty panels
    expect(audit.filter((a) => a.blank).map((a) => a.title)).toEqual([]);
    // no console errors (catches the PlotMount deps-size warning + any crash)
    expect(errs).toEqual([]);
  });

  for (const id of CASES) {
    test(`Case ${id}: no console errors, no blank panels, only single-case panels`, async ({ page }) => {
      const errs = attachErrorSink(page);
      await page.goto(`/#case=${id}`);
      await ensureLoaded(page);
      const audit = await auditPanels(page);
      // scope contract: Case shows NO overall panels
      expect(audit.map((a) => a.title).join(" ")).not.toMatch(OVERALL_TITLES);
      // no present-but-empty panels (a panel with no data must render text/null, not an empty chart)
      expect(audit.filter((a) => a.blank).map((a) => a.title)).toEqual([]);
      // no console errors
      expect(errs).toEqual([]);
    });
  }

  test("solver fit lines resolve to visible (non-transparent) colors", async ({ page }) => {
    attachErrorSink(page);
    await page.goto("/#case=CX-001"); // all backends converge → ≥6 colored fit lines
    await ensureLoaded(page);
    // wait for the spectrum line marks to actually mount (PlotMount effect)
    await page.locator('.glass:has-text("Fit — reference") g[aria-label="line"] path').first().waitFor({ timeout: 8000 });
    const strokes = await page.evaluate(() => {
      const fit = [...document.querySelectorAll(".glass")].find((p) =>
        /Fit — reference/.test(p.querySelector("h2")?.textContent || ""),
      );
      const svg = fit?.querySelector("svg");
      const lines = [...(svg?.querySelectorAll('g[aria-label="line"] path') ?? [])];
      return lines.map((p) => getComputedStyle(p as Element).stroke);
    });
    expect(strokes.length).toBeGreaterThan(1);
    for (const s of strokes) {
      expect(s).not.toMatch(/rgba\(0,\s*0,\s*0,\s*0\)|transparent|none/);
    }
  });

  test("every plot fills its card width (no fixed-640 dead space)", async ({ page }) => {
    for (const dest of ["#standing", "#evidence"]) {
      await page.goto(`/${dest}`);
      await ensureLoaded(page);
      const gaps = await page.evaluate(() => {
        const out: { title: string; gap: number }[] = [];
        for (const card of document.querySelectorAll(".glass")) {
          const svg = card.querySelector("svg");
          if (!svg) continue;
          // Dead space = how far the SVG falls short of its *content box* (the
          // padded inner width), NOT the padded card edge. Subtracting padding
          // keeps this guard about the fixed-640 regression and independent of
          // the card's padding token (--s5 → --s6 must not trip it).
          const cs = getComputedStyle(card as HTMLElement);
          const padX = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
          const contentW = (card as HTMLElement).clientWidth - padX;
          const svgW = (svg as SVGElement).getBoundingClientRect().width;
          const title = card.querySelector("h2,h3")?.textContent ?? "?";
          out.push({ title, gap: contentW - svgW });
        }
        return out;
      });
      for (const g of gaps)
        expect(g.gap, `${dest} "${g.title}" leaves ${g.gap}px dead space`).toBeLessThan(64);
    }
  });

  // The REAL guard: in-app navigation (Overview ↔ Case) must not leak stale
  // plots or fire React warnings — the PlotMount fiber-reuse class that fresh
  // loads never exercise.
  test("in-app navigation Overview↔Case stays clean (no stale panels, no console errors)", async ({ page }) => {
    const errs = attachErrorSink(page);
    await page.goto("/#evidence");
    await ensureLoaded(page);

    // Pick two distinct cases from the LIVE suite table — never hardcode an id.
    // A hardcoded id silently absent from a partial run is a vacuous guard (the
    // same derive-from-data invariant the dashboard itself enforces).
    // Wait for the first row before evaluating (table renders after API response).
    await page.locator("tr[data-case-id]").first().waitFor({ timeout: 10_000 });
    const caseIds = await page
      .locator("tr[data-case-id]")
      .evaluateAll((rows) =>
        rows.map((r) => r.getAttribute("data-case-id")).filter((v): v is string => !!v),
      );
    expect(caseIds.length, "suite table rendered no case rows").toBeGreaterThanOrEqual(2);
    const firstCase = caseIds[0];
    const secondCase = caseIds[caseIds.length - 1];

    // open a case by clicking its suite-table row
    await page.locator(`tr[data-case-id="${firstCase}"]`).click();
    await page.waitForURL(new RegExp(`#case=${firstCase}`));
    await page.waitForTimeout(500);
    let audit = await auditPanels(page);
    expect(audit.map((a) => a.title).join(" "), "Case view leaked overall panels").not.toMatch(OVERALL_TITLES);
    expect(audit.filter((a) => a.blank).map((a) => a.title), "blank panel after nav").toEqual([]);

    // back to overview
    await page.getByRole("button", { name: /All cases/ }).click();
    await page.waitForTimeout(400);
    audit = await auditPanels(page);
    expect(audit.map((a) => a.title).join(" "), "Overview leaked single-case panels").not.toMatch(SINGLE_TITLES);

    // re-enter another case
    await page.locator(`tr[data-case-id="${secondCase}"]`).click();
    await page.waitForURL(new RegExp(`#case=${secondCase}`));
    await page.waitForTimeout(500);
    audit = await auditPanels(page);
    expect(audit.filter((a) => a.blank).map((a) => a.title), "blank panel after 2nd nav").toEqual([]);

    // after all the in-app transitions: zero console errors (catches the deps-size warning)
    expect(errs, "console errors accumulated during navigation").toEqual([]);
  });

  test("#audit redirects to #evidence (Audit destination removed)", async ({ page }) => {
    await page.goto("/#audit");
    await ensureLoaded(page);
    // After removing the Audit destination, #audit hash-redirects to #evidence.
    // The page should show Evidence panels (suite table), not a blank or error.
    // Wait for the top nav to actually render (the report finished loading) — not
    // just the loading card's .glass — before counting, or we race the spinner.
    await page.waitForSelector('nav[aria-label="Narrative navigation"] button', {
      timeout: 10_000,
    });
    const body = await page.evaluate(() => document.body.innerText);
    expect(body, "#audit redirect should land on Evidence content").not.toMatch(
      /Report load failed|unsupported schema/i,
    );
    // The nav should show only 2 destinations (no Audit button).
    const navBtns = await page
      .locator('nav[aria-label="Narrative navigation"] button')
      .count();
    expect(navBtns).toBe(2);
  });

  test("Standing shows neutral masthead (no 'crowned', facts-derived counts)", async ({ page }) => {
    await page.goto("/#standing");
    await ensureLoaded(page);
    const body = await page.evaluate(() => document.body.innerText);
    // The facts-landing card must NOT contain advocacy/boast language. (Note: the
    // neutral disclaimer "nothing here is crowned" legitimately uses "crowned",
    // so we scan for actual boast words, not the word "crowned".)
    expect(body.toLowerCase()).not.toMatch(/\b(wins|fastest|the best|beats|winner is)\b/);
    // The masthead includes "measured" (neutral framing)
    expect(body.toLowerCase()).toMatch(/measured/);
    // Gate status is present (PASS/FAIL or similar)
    expect(body.toUpperCase()).toMatch(/PASS|FAIL/);
  });

  // ---------------------------------------------------------------------------
  // R4 — render-defect class guard: overflow / blank / leak across all destinations
  //
  // Sweeps every destination (standing, audit, evidence, and ≥2 live case ids)
  // and asserts three render-defect classes that unit tests cannot see:
  //   (a) no .glass descendant overflows horizontally (scrollWidth − clientWidth ≤ 2,
  //       non-SVG elements only — SVGs are ResponsiveObserver-managed and exempt)
  //   (b) no blank data-panel (a panel with an SVG but zero data marks)
  //   (c) no leaked undefined / NaN / Infinity / [object Object] in body text
  //
  // FAILS today on #audit: the wire-matrix <ul>/<li> rows overflow 118px because
  // the evidence column is `auto` and the 10-dataset W8 string does not wrap.
  // ---------------------------------------------------------------------------
  test("R4 sweep: all destinations free of overflow / blank panels / text leaks", async ({ page }) => {
    // --- Derive case ids from the live suite table (never hardcode) ---
    await page.goto("/#evidence");
    await ensureLoaded(page);
    // Wait for at least one suite row (table renders after the API response arrives).
    await page.locator("tr[data-case-id]").first().waitFor({ timeout: 10_000 });
    const allCaseIds = await page
      .locator("tr[data-case-id]")
      .evaluateAll((rows) =>
        rows.map((r) => r.getAttribute("data-case-id")).filter((v): v is string => !!v),
      );
    expect(allCaseIds.length, "suite table rendered no case rows").toBeGreaterThanOrEqual(2);
    // Pick first and last for ≥2 case destinations (avoids hardcoded ids).
    const caseDestinations = [
      `#case=${allCaseIds[0]}`,
      `#case=${allCaseIds[allCaseIds.length - 1]}`,
    ];

    const destinations = ["#standing", "#evidence", ...caseDestinations];

    for (const dest of destinations) {
      await page.goto(`/${dest}`);
      await ensureLoaded(page);
      // Give React effects (PlotMount, deferred renders) a beat.
      await page.waitForTimeout(400);

      // --- (a) Horizontal overflow check: no .glass descendant overflows ---
      // SVG elements are exempt: they are set by a ResizeObserver and their
      // scrollWidth is undefined / unreliable. Check every non-SVG descendant
      // of .glass cards.
      const overflowing = await page.evaluate(() => {
        const results: { dest: string; tag: string; cls: string; overflow: number }[] = [];
        const destStr = location.hash;
        for (const card of document.querySelectorAll(".glass")) {
          const allEls = [card, ...card.querySelectorAll("*")];
          for (const el of allEls) {
            // Skip SVG and SVG descendants — their scrollWidth/clientWidth are
            // managed by ResizeObserver and do not reflect overflow the user sees.
            if (el instanceof SVGElement || el.closest("svg") != null) continue;
            const hw = el as HTMLElement;
            const overflow = hw.scrollWidth - hw.clientWidth;
            if (overflow > 2) {
              results.push({
                dest: destStr,
                tag: el.tagName,
                cls: el.className?.toString() ?? "",
                overflow,
              });
            }
          }
        }
        return results;
      });
      expect(
        overflowing,
        `${dest}: .glass descendants overflow horizontally:\n${JSON.stringify(overflowing, null, 2)}`,
      ).toEqual([]);

      // --- (b) No blank data-panel ---
      const panels = await auditPanels(page);
      expect(
        panels.filter((p) => p.blank).map((p) => p.title),
        `${dest}: blank panels (SVG present but no data marks)`,
      ).toEqual([]);

      // --- (c) No leaked undefined / NaN / Infinity / [object Object] in body text ---
      // Checks for JS value leaks — React rendering `undefined`, `NaN`, etc. as text.
      // Strategy: scan text nodes (leaves of the DOM) for bare sentinel values so that
      // prose descriptions like "was undefined →" in the taxonomy panel are not caught
      // (they are legitimate technical descriptions, not JS render bugs).
      const leakedNodes = await page.evaluate(() => {
        const LEAK = /^(undefined|NaN|Infinity|\[object Object\])$/;
        const found: { text: string; parent: string; cls: string }[] = [];
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let node: Text | null;
        while ((node = walker.nextNode() as Text | null) != null) {
          const t = node.textContent?.trim() ?? "";
          if (LEAK.test(t)) {
            const p = node.parentElement;
            found.push({
              text: t,
              parent: p?.tagName ?? "?",
              cls: p?.className?.toString() ?? "",
            });
          }
        }
        // Also check for [object Object] anywhere in body (it never appears in prose).
        if (/\[object Object\]/.test(document.body.innerText)) {
          found.push({ text: "[object Object]", parent: "body", cls: "full-scan" });
        }
        return found;
      });
      expect(
        leakedNodes,
        `${dest}: JS value leaked into rendered text (bare undefined/NaN/Infinity/[object Object] in a text node):\n${JSON.stringify(leakedNodes, null, 2)}`,
      ).toEqual([]);
    }
  });
});
