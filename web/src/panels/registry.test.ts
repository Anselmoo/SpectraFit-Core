import { describe, expect, it } from "vitest";
import { PANELS } from "./registry";
import { OVERALL_PANELS, SINGLE_PANELS } from "../shell/evidenceScope";
describe("panel registry", () => {
  it("every panel has a unique id and a make()", () => {
    const ids = PANELS.map((p) => p.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const p of PANELS) expect(typeof p.make).toBe("function");
  });
  it("each destination has at least one panel (audit removed — Unit 5)", () => {
    for (const d of ["standing", "evidence"] as const)
      expect(PANELS.some((p) => p.dest === d)).toBe(true);
    // Audit destination removed; verify no audit panels remain in the registry.
    expect(PANELS.some((p) => p.dest === ("audit" as any))).toBe(false);
  });
  it("every evidence panel carries a caption", () => {
    for (const p of PANELS.filter((p) => p.dest === "evidence"))
      expect(p.caption && p.caption.length, `${p.id} missing caption`).toBeGreaterThan(0);
  });
  it("evidence panels preserve the existing scope contract", () => {
    const overview = PANELS.filter((p) => p.dest === "evidence" && p.scope === "overview").map((p) => p.id);
    const single = PANELS.filter((p) => p.dest === "evidence" && p.scope === "case").map((p) => p.id);
    for (const id of OVERALL_PANELS) expect(overview).toContain(id);
    for (const id of SINGLE_PANELS) expect(single).toContain(id);
  });
});
