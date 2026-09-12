/**
 * Unit tests for ExportButton.
 *
 * TDD: renders the ⤓ SVG button, is inert (no-op) when no SVG is in the container,
 * and triggers a download with the correct filename attribute when an SVG is present.
 */
// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, cleanup, fireEvent } from "@testing-library/react";
import { useRef } from "react";
import type { ReactNode } from "react";
import { ExportButton } from "./ExportButton";

afterEach(cleanup);

/** Wrapper that provides a containerRef pointing to a div with optional SVG child. */
function Wrapper({ hasSvg, children }: { hasSvg: boolean; children?: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  return (
    <>
      <div ref={ref}>
        {hasSvg ? (
          <svg data-testid="inner-svg" xmlns="http://www.w3.org/2000/svg">
            <circle cx="50" cy="50" r="10" />
          </svg>
        ) : (
          <p>no chart</p>
        )}
      </div>
      <ExportButton containerRef={ref as any} filename="test-panel" />
      {children}
    </>
  );
}

describe("ExportButton", () => {
  it("renders the ⤓ SVG button label", () => {
    const { getByRole } = render(<Wrapper hasSvg={false} />);
    const btn = getByRole("button", { name: /Download test-panel as SVG/i });
    expect(btn).toBeTruthy();
    expect(btn.textContent).toContain("SVG");
  });

  it("is a no-op when the container has no svg (click does not throw)", () => {
    const { getByRole } = render(<Wrapper hasSvg={false} />);
    const btn = getByRole("button");
    // Should not throw — a missing SVG is silently ignored
    expect(() => fireEvent.click(btn)).not.toThrow();
  });

  it("triggers a download (a.click called) when SVG is present", () => {
    // Stub URL.createObjectURL so it returns a stable string
    const fakeUrl = "blob:fake-url";
    const createObjectURL = vi.spyOn(URL, "createObjectURL").mockReturnValue(fakeUrl);
    const revokeObjectURL = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});

    const { getByRole, container } = render(<Wrapper hasSvg />);
    const btn = getByRole("button");

    // Spy on the hidden anchor's click
    const anchor = container.querySelector("a[aria-hidden]") as HTMLAnchorElement;
    const anchorClick = vi.spyOn(anchor, "click");

    fireEvent.click(btn);

    expect(createObjectURL).toHaveBeenCalled();
    expect(anchorClick).toHaveBeenCalled();
    expect(anchor.download).toBe("test-panel.svg");

    createObjectURL.mockRestore();
    revokeObjectURL.mockRestore();
  });
});
