import { render, cleanup } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { Callout } from "./Callout";

afterEach(cleanup);

test("Callout renders its body content and default note label", () => {
  const { getByText } = render(<Callout>Global fitting requires a shared FitGraph.</Callout>);
  getByText("Global fitting requires a shared FitGraph.");
  getByText("Note");
});

test("Callout kind label is real text, not color-only (accessibility)", () => {
  const { getByText } = render(<Callout kind="warning">Bounds are enforced by projection.</Callout>);
  getByText("Warning");
});

test("Callout title overrides the default kind label", () => {
  const { getByText, queryByText } = render(
    <Callout kind="tip" title="Heads up">Custom label</Callout>,
  );
  getByText("Heads up");
  expect(queryByText("Tip")).toBeNull();
});

test("Callout danger kind renders the Caution label", () => {
  const { getByText } = render(<Callout kind="danger">Irreversible.</Callout>);
  getByText("Caution");
});
