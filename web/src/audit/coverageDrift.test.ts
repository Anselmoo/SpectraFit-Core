import { describe, it, expect } from "vitest";
import { findCoverageDrift } from "./coverageDrift";

describe("findCoverageDrift", () => {
  it("flags an `ignored:` leaf whose field name appears in panel source", () => {
    const manifest = {
      "manifest.pinned.runId": "ignored: deferred (pinned-baseline panel)",
      "solvers[].color": "rendered: legend swatch",
    };
    const source = `const id = report.manifest.pinned.runId; // reproduce card`;
    const drift = findCoverageDrift(manifest, source);
    expect(drift.map((d) => d.leaf)).toContain("manifest.pinned.runId");
    // a rendered leaf is never reported as drift
    expect(drift.map((d) => d.leaf)).not.toContain("solvers[].color");
  });

  it("does not flag an ignored leaf absent from the source", () => {
    const manifest = { "analyzed[].schedule": "ignored: structural" };
    const drift = findCoverageDrift(manifest, "no references here");
    expect(drift).toHaveLength(0);
  });
});
