import { render, cleanup, fireEvent } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { Button } from "./Button";

afterEach(cleanup);

test("Button renders its label and type", () => {
  const { getByRole } = render(<Button>Run fit</Button>);
  const btn = getByRole("button", { name: "Run fit" });
  expect(btn.getAttribute("type")).toBe("button");
});

test("Button fires onClick when enabled", () => {
  let clicks = 0;
  const { getByRole } = render(<Button onClick={() => (clicks += 1)}>Run fit</Button>);
  fireEvent.click(getByRole("button", { name: "Run fit" }));
  expect(clicks).toBe(1);
});

test("Button disabled sets the native disabled attribute (not just visual)", () => {
  const { getByRole } = render(<Button disabled>Run fit</Button>);
  expect(getByRole("button", { name: "Run fit" }).hasAttribute("disabled")).toBe(true);
});

test("Button renders an optional leading icon before the label", () => {
  const { getByRole } = render(
    <Button icon={<span data-testid="icon">*</span>}>Run fit</Button>,
  );
  const btn = getByRole("button", { name: /Run fit/ });
  expect(btn.querySelector('[data-testid="icon"]')).toBeTruthy();
});

test("Button supports the submit type", () => {
  const { getByRole } = render(<Button type="submit">Save</Button>);
  expect(getByRole("button", { name: "Save" }).getAttribute("type")).toBe("submit");
});
