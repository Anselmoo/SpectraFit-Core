import { render, cleanup } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { PanelCard, PanelTitle, Caption } from "./chrome";

afterEach(cleanup);

test("PanelCard renders a titled glass card with caption + children", () => {
  const { container, getByText } = render(
    <PanelCard title="Timing distribution" caption="lower is faster">
      <span>body</span>
    </PanelCard>,
  );
  expect(container.querySelector(".glass")).toBeTruthy();
  expect(container.querySelector("h2,h3")?.textContent).toBe("Timing distribution");
  getByText("lower is faster");
  getByText("body");
});

test("Caption renders nothing when text is empty", () => {
  const { container } = render(<Caption>{undefined}</Caption>);
  expect(container.querySelector(".panel-caption")).toBeNull();
});

test("PanelTitle renders an h2", () => {
  const { container } = render(<PanelTitle>Hello</PanelTitle>);
  expect(container.querySelector("h2")?.textContent).toBe("Hello");
});
