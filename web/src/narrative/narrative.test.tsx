// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { RungLadder, WireMatrix } from "./index";
import type { TrustBlock } from "../contract";

describe("RungLadder", () => {
  it("marks the current rung and shows the gap to the top (5)", () => {
    const html = renderToStaticMarkup(<RungLadder rung={2} max={5} />);
    expect(html).toMatch(/2\s*\/\s*5/);
    expect(html).toMatch(/data-current="2"/);
  });

  it("renders all steps up to max", () => {
    const html = renderToStaticMarkup(<RungLadder rung={3} max={5} />);
    // 5 individual step spans rendered (not the container "rung-steps")
    const matches = html.match(/class="rung-step"/g);
    expect(matches).not.toBeNull();
    expect(matches!.length).toBe(5);
  });

  it("shows gap text when rung < max", () => {
    const html = renderToStaticMarkup(<RungLadder rung={2} max={5} />);
    expect(html).toMatch(/gap to top/i);
    expect(html).toMatch(/3\s*rungs?/);
  });

  it("omits gap text when at the top", () => {
    const html = renderToStaticMarkup(<RungLadder rung={5} max={5} />);
    expect(html).not.toMatch(/gap to top/i);
  });

  it("shows the verification-completeness legend caption (with ASME hedge, not bare ASME V&V)", () => {
    const html = renderToStaticMarkup(<RungLadder rung={2} max={5} />);
    // Must carry the hedge ("not conformant"), not bare "V&V ladder (ASME)" authority.
    expect(html).toMatch(/Verification-completeness ladder/i);
    expect(html).toMatch(/inspired by ASME/i);
    expect(html).toMatch(/not conformant/i);
  });

  it("carries a per-rung definition tooltip on each step", () => {
    const html = renderToStaticMarkup(<RungLadder rung={2} max={5} />);
    expect(html).toMatch(/title="Rung 1 — reproducibility/);
    expect(html).toMatch(/title="Rung 5 — independent differential validation/);
  });

  it("renders the verification-completeness legend in compact mode too (with ASME hedge)", () => {
    const html = renderToStaticMarkup(<RungLadder rung={2} max={5} compact />);
    expect(html).toMatch(/Verification-completeness ladder/i);
    expect(html).toMatch(/inspired by ASME/i);
    expect(html).toMatch(/not conformant/i);
  });
});

describe("WireMatrix", () => {
  const wires = [
    { id: "W2a", name: "metric_identity", status: "pass", evidence: "recomputed to 1e-15" },
    { id: "W2c", name: "jacobian_kappa", status: "fail", evidence: "κ(J) missing for 337 entries" },
  ];

  it("renders one row per wire with its status", () => {
    const html = renderToStaticMarkup(<WireMatrix wires={wires as any} />);
    expect(html).toMatch(/W2a/);
    expect(html).toMatch(/W2c/);
    expect(html).toMatch(/data-status="pass"/);
    expect(html).toMatch(/data-status="fail"/);
    expect(html).toMatch(/κ\(J\) missing/);
  });

  it("renders wire names", () => {
    const html = renderToStaticMarkup(<WireMatrix wires={wires as any} />);
    expect(html).toMatch(/metric_identity/);
    expect(html).toMatch(/jacobian_kappa/);
  });

  it("renders evidence text", () => {
    const html = renderToStaticMarkup(<WireMatrix wires={wires as any} />);
    expect(html).toMatch(/recomputed to 1e-15/);
  });

  it("renders a `gap` wire with a neutral (non-fail) treatment", () => {
    const gapWires = [
      { id: "W2c", name: "jacobian_kappa", status: "gap", evidence: "κ(J) not exposed — capability gap" },
    ];
    const html = renderToStaticMarkup(<WireMatrix wires={gapWires as any} />);
    expect(html).toMatch(/data-status="gap"/);
    // neutral/amber, NOT the red fail token
    expect(html).toMatch(/var\(--warn\)/);
    expect(html).not.toMatch(/var\(--fail\)/);
    expect(html).toMatch(/capability gap/);
  });
});

describe("wiresOf adapter", () => {
  it("maps contract wireId to id", async () => {
    const { wiresOf } = await import("./index");
    const trustBlock = {
      rung: 2,
      wires: [
        { wireId: "W1", name: "timing_isolation", status: "pass", evidence: "bench harness ok" },
        { wireId: "W2c", name: "jacobian_kappa", status: "warn", evidence: "partial coverage" },
      ],
    } as TrustBlock;
    const rows = wiresOf(trustBlock);
    expect(rows[0].id).toBe("W1");
    expect(rows[1].id).toBe("W2c");
    expect(rows[0].status).toBe("pass");
    expect(rows[1].status).toBe("warn");
  });

  it("returns empty array for missing wires", async () => {
    const { wiresOf } = await import("./index");
    expect(wiresOf(undefined)).toEqual([]);
    expect(wiresOf({} as TrustBlock)).toEqual([]);
    expect(wiresOf({ wires: [] } as TrustBlock)).toEqual([]);
  });

  it("preserves a `gap` status (not coerced to skipped)", async () => {
    const { wiresOf } = await import("./index");
    const rows = wiresOf({
      wires: [{ wireId: "W2c", name: "jacobian_kappa", status: "gap", evidence: "κ(J) not exposed" }],
    } as TrustBlock);
    expect(rows[0].status).toBe("gap");
  });
});
