import { describe, it, expect } from "vitest";
import { DESTINATIONS, destinationFromHash, hashOf } from "./nav";
import { PANELS } from "../panels/registry";

describe("destination routing", () => {
  it("Standing leads with the facts-landing card (neutral masthead, not the old gate-verdict)", () => {
    const standing = PANELS.filter((p) => p.dest === "standing");
    expect(standing[0]?.id).toBe("facts-landing");
    // The old rung-as-hero pair is gone.
    expect(standing.some((p) => p.id === "gate-verdict")).toBe(false);
    expect(standing.some((p) => p.id === "render-truth")).toBe(false);
  });
  it("lists the two destinations — Standing leads (facts masthead + table)", () => {
    expect(DESTINATIONS.map((d) => d.id)).toEqual(["standing", "evidence"]);
  });
  it("Standing destination is facts-first (neutral label)", () => {
    const standing = DESTINATIONS.find((d) => d.id === "standing");
    expect(standing?.label).toBe("Standing");
    expect(standing?.blurb.toLowerCase()).toContain("fact");
  });
  it("parses a valid hash", () => {
    expect(destinationFromHash("#standing")).toBe("standing");
    expect(destinationFromHash("#evidence")).toBe("evidence");
  });
  it("#audit redirects to evidence (Audit destination removed)", () => {
    expect(destinationFromHash("#audit")).toBe("evidence");
  });
  it("falls back to standing on empty/unknown hash", () => {
    expect(destinationFromHash("")).toBe("standing");
    expect(destinationFromHash("#nope")).toBe("standing");
  });
  it("round-trips hashOf", () => {
    expect(hashOf("evidence")).toBe("#evidence");
  });
  it("routes a deep-linked case (#case=<id>) to the Evidence destination", () => {
    expect(destinationFromHash("#case=EZ-001")).toBe("evidence");
    expect(destinationFromHash("#case=OF-001")).toBe("evidence");
  });
});
