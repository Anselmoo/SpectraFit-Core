import { render, cleanup, fireEvent } from "@testing-library/react";
import { afterEach, expect, test, describe } from "vitest";
import { TaxonomyPanel } from "./TaxonomyPanel";
afterEach(cleanup);

describe("TaxonomyPanel — Wave B2 progressive disclosure", () => {
  test("shows Track-0 self-catch rows by default (W2a + W3)", () => {
    const { container, getAllByText } = render(<TaxonomyPanel />);
    // Track-0 catches are always visible (2 rows).
    expect(container.querySelectorAll("[data-failure-row]").length).toBe(2);
    // W2a and W3 guard ids confirm the right rows are shown.
    expect(getAllByText(/W2a/).length).toBeGreaterThanOrEqual(1);
    expect(getAllByText(/W3/).length).toBeGreaterThanOrEqual(1);
  });

  test("expand button reveals all 6 failure-mode rows", () => {
    const { container, getByText } = render(<TaxonomyPanel />);
    const btn = container.querySelector("[data-taxonomy-expand]") as HTMLButtonElement;
    expect(btn).toBeTruthy();
    fireEvent.click(btn);
    expect(container.querySelectorAll("[data-failure-row]").length).toBe(6);
    getByText(/insertBefore/);
    getByText(/replaceChildren/);
  });

  test("warm lead-in text is rendered (Kare)", () => {
    const { container } = render(<TaxonomyPanel />);
    const lead = container.querySelector("[data-taxonomy-lead]");
    expect(lead?.textContent).toMatch(/benchmark|trustworthy|audit/i);
  });
});
