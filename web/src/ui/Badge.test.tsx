import { render, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Badge } from "./Badge";

afterEach(cleanup);

describe("Badge", () => {
  it("Badge renders its label text", () => {
    const { getByText } = render(<Badge tone="success">PASS</Badge>);
    getByText("PASS");
  });

  it("Badge defaults to neutral tone", () => {
    const { container } = render(<Badge>v2.0.0</Badge>);
    const span = container.querySelector("span");
    expect(span?.style.color).toBe("var(--text-secondary)");
  });

  it("Badge sm size uses tighter padding than md", () => {
    const { container: smContainer } = render(<Badge size="sm">x</Badge>);
    const { container: mdContainer } = render(<Badge size="md">x</Badge>);
    const sm = smContainer.querySelector("span");
    const md = mdContainer.querySelector("span");
    expect(sm?.style.padding).not.toBe(md?.style.padding);
  });

  it("Badge is a static span — never a button or link", () => {
    const { container } = render(<Badge tone="danger">FAIL</Badge>);
    expect(container.querySelector("button,a")).toBeNull();
  });
});
