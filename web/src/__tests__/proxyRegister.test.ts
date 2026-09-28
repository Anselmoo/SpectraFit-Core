/**
 * V5 — no silent proxy (Invariant V, render side).
 *
 * A panel that renders a *proxy* metric (a stand-in for a quantity not yet
 * computed for real at the source) must MACHINE-DECLARE it via `PanelRecord.proxy`
 * — not disclose it only in prose — AND that declaration must be backed by a
 * LIMITATIONS.md entry. This mirrors the Python `VALUE_PROVENANCE` spine
 * (status="proxy" ⟹ proxy_task) on the web side.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { PANELS } from "../panels/registry";

const LIMITATIONS = readFileSync(
  join(import.meta.dirname, "..", "..", "..", "LIMITATIONS.md"),
  "utf-8",
).toLowerCase();

const proxyPanels = PANELS.filter((p) => p.proxy);

describe("proxyRegister — V5: no silent proxy", () => {
  it("every declared proxy carries a reason and a tracked task", () => {
    for (const p of proxyPanels) {
      expect(p.proxy?.reason, `panel ${p.id}: proxy.reason`).toBeTruthy();
      expect(p.proxy?.task, `panel ${p.id}: proxy.task`).toBeTruthy();
    }
  });

  it("every declared proxy is disclosed in LIMITATIONS.md", () => {
    const undisclosed = proxyPanels
      .filter((p) => {
        // A proxy is disclosed when LIMITATIONS.md mentions a proxy AND a
        // keyword tying to this panel (its id words or first title word).
        const idWords = p.id.split("-");
        const titleWord =
          typeof p.title === "string" ? p.title.split(" ")[0].toLowerCase() : "";
        const tied =
          idWords.some((w) => w.length > 3 && LIMITATIONS.includes(w)) ||
          (titleWord.length > 3 && LIMITATIONS.includes(titleWord));
        return !(LIMITATIONS.includes("proxy") && tied);
      })
      .map((p) => p.id);
    expect(
      undisclosed,
      `proxy panel(s) not disclosed in LIMITATIONS.md: ${undisclosed.join(", ")}`,
    ).toHaveLength(0);
  });

  it("the convergence panel is no longer a proxy (Phase 4 swapped it to the real metric)", () => {
    const conv = PANELS.find((p) => p.id === "convergence-truth");
    expect(conv, "convergence-truth panel must exist").toBeTruthy();
    // It now renders the real θ-distance series (FitResult.params_history →
    // engine dₖ → contract thetaDistance), so it must NOT be flagged a proxy.
    expect(
      conv?.proxy,
      "convergence-truth renders the real θ-distance metric — not a proxy",
    ).toBeUndefined();
  });
});
