/**
 * ExportButton — downloads the first <svg> found inside a container element as
 * an SVG file. The button is always rendered (panel headers mount it
 * unconditionally), but it is disabled while the container holds no <svg>, so a
 * text/table-only panel — or a chart that has not painted yet — shows an inert,
 * visibly-disabled control instead of a silent dead-click.
 *
 * Usage:
 *   <ExportButton containerRef={myRef} filename="timing-distribution" />
 *
 * SVG presence is tracked with a MutationObserver on the container so the button
 * enables itself the moment a chart renders asynchronously after mount, and
 * disables again if the chart is torn down. The click handler re-queries at
 * click time as a final guard.
 */
import { useEffect, useRef, useState } from "react";
import type { RefObject } from "react";

export interface ExportButtonProps {
  /** Ref to the container element that wraps the panel body (including the SVG). */
  containerRef: RefObject<HTMLElement | null>;
  /** Base filename for the download (no extension). */
  filename: string;
}

export function ExportButton({ containerRef, filename }: ExportButtonProps) {
  const anchorRef = useRef<HTMLAnchorElement>(null);
  const [hasSvg, setHasSvg] = useState(false);

  // Track <svg> presence in the container: it may appear/disappear after mount
  // when a chart renders or tears down asynchronously. Keeps `disabled` honest
  // so the button is never a silent dead-click on text/table-only panels.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const sync = () => setHasSvg(container.querySelector("svg") !== null);
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(container, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [containerRef]);

  const handleClick = () => {
    const container = containerRef.current;
    if (!container) return;
    const svgEl = container.querySelector("svg");
    if (!svgEl) return;

    const serialized = new XMLSerializer().serializeToString(svgEl);
    const blob = new Blob([serialized], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const a = anchorRef.current;
    if (!a) return;
    a.href = url;
    a.download = `${filename}.svg`;
    a.click();
    // Revoke after a short delay to allow the download to start
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return (
    <>
      {/* Hidden anchor used as the download trigger */}
      {/* eslint-disable-next-line jsx-a11y/anchor-has-content */}
      <a ref={anchorRef} style={{ display: "none" }} aria-hidden />
      <button
        type="button"
        onClick={handleClick}
        disabled={!hasSvg}
        aria-disabled={!hasSvg}
        title={hasSvg ? `Download ${filename}.svg` : "No chart to export"}
        aria-label={`Download ${filename} as SVG`}
        style={{
          background: "none",
          border: "1px solid var(--hairline)",
          borderRadius: 4,
          color: "var(--ink-faint)",
          cursor: hasSvg ? "pointer" : "not-allowed",
          opacity: hasSvg ? 1 : 0.45,
          fontFamily: "var(--font-mono)",
          fontSize: "0.72rem",
          padding: "2px 7px",
          lineHeight: 1.4,
          whiteSpace: "nowrap",
          flexShrink: 0,
        }}
      >
        ⤓ SVG
      </button>
    </>
  );
}
