/**
 * Normalise an `@observablehq/plot` render result to a raw SVGSVGElement for
 * mounting. `Plot.plot()` returns `(SVGSVGElement | HTMLElement) & Plot` —
 * either a bare `<svg>` or a `<figure>` wrapper containing one; this unwraps
 * the wrapper case. Shared by every plot factory in this directory so the
 * unwrap logic (previously duplicated per-file, several copies typed `any`)
 * lives in exactly one place.
 */
export function toSvg(
  plot: (SVGSVGElement | HTMLElement) & { querySelector?: (s: string) => Element | null },
): SVGSVGElement {
  if (plot instanceof SVGSVGElement) return plot;
  const svg = plot.querySelector?.("svg");
  if (svg instanceof SVGSVGElement) return svg;
  return plot as unknown as SVGSVGElement;
}
