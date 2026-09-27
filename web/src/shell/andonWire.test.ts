/**
 * Class invariant: the first rendered block of every destination states a
 * finding or its purpose — never the self-referential credibility rung.
 * Only Standing and Evidence exist as destinations.
 *
 * Standing leads with the facts-landing card (neutral masthead + table),
 * not a gate-verdict + rung. Evidence leads with a finding panel.
 */
import { describe, it, expect } from "vitest";
import { DESTINATIONS } from "./nav";
import type { DestId } from "./nav";
import { PANELS } from "../panels/registry";

const RUNG_PANEL_ID = "render-truth";

// First registry panel a destination renders (registry order is render order).
function firstPanelId(dest: DestId): string | undefined {
  return PANELS.filter((p) => p.dest === dest)[0]?.id;
}

describe("no destination leads with the credibility rung", () => {
  it("the rung is never the first block of any destination (the class invariant)", () => {
    for (const d of DESTINATIONS) {
      expect(firstPanelId(d.id)).not.toBe(RUNG_PANEL_ID);
    }
  });

  it("Standing leads with the facts-landing card (neutral masthead, no crowning)", () => {
    const standing = PANELS.filter((p) => p.dest === "standing");
    expect(standing[0]?.id).toBe("facts-landing");
    // The old rung hero is gone — render-truth is not in the standing panels.
    expect(standing.some((p) => p.id === RUNG_PANEL_ID)).toBe(false);
  });

  it("Evidence's first registry block is a finding panel, never the rung", () => {
    expect(firstPanelId("evidence")).not.toBe(RUNG_PANEL_ID);
  });

  it("only two destinations exist", () => {
    expect(DESTINATIONS.map((d) => d.id)).toEqual(["standing", "evidence"]);
  });
});
