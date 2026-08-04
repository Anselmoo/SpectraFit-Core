import { render, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PlotMount } from "./PlotMount";

afterEach(cleanup);

function svgOf(w: number): SVGSVGElement {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("data-w", String(w));
  return s;
}

describe("PlotMount", () => {
  it("PlotMount calls make with a width and mounts the returned svg", () => {
    const make = vi.fn((w: number) => svgOf(w));
    const { container } = render(<PlotMount make={make} deps={[]} />);
    expect(make).toHaveBeenCalledTimes(1);
    expect(typeof make.mock.calls[0][0]).toBe("number");
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("PlotMount re-mounts when deps change", () => {
    let n = 0;
    const make = (_w: number) => svgOf(++n);
    const { rerender, container } = render(<PlotMount make={make} deps={[1]} />);
    rerender(<PlotMount make={make} deps={[2]} />);
    expect(container.querySelector("svg")?.getAttribute("data-w")).toBeTruthy();
  });

  it("PlotMount renders nothing when make returns null", () => {
    const { container } = render(<PlotMount make={() => null} deps={[]} />);
    expect(container.querySelector("svg")).toBeNull();
  });
});
