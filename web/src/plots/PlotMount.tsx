import { useEffect, useRef } from "react";

const SVG_NS = "http://www.w3.org/2000/svg";

/** Mounts an imperatively-built SVG (e.g. Observable Plot) inside a React leaf
 *  div, isolating it from React reconciliation. `make(width)` builds the node at
 *  the measured container width (or returns null to render nothing); it re-runs
 *  whenever `deps` change OR the container resizes. replaceChildren keeps React
 *  from ever seeing foreign children (the insertBefore-desync fix).
 *
 *  `title`, when given, is the chart's accessible name (S6 a11y fix): it is
 *  wired onto the mounted SVG as `role="img"` + `aria-label` + a leading
 *  `<title>` element, so a screen reader announces the same scientific
 *  question the panel already declares in `plots/spec.ts` — without that,
 *  every chart is silent to assistive tech (role/aria-label/title all null). */
export function PlotMount({
  make,
  deps,
  title,
}: {
  make: (width: number) => SVGSVGElement | null;
  deps: unknown[];
  title?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const makeRef = useRef(make);
  makeRef.current = make;
  const titleRef = useRef(title);
  titleRef.current = title;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let raf = 0;
    const paint = () => {
      const w = el.clientWidth || 640;
      const node = makeRef.current(w);
      if (node && titleRef.current) {
        node.setAttribute("role", "img");
        node.setAttribute("aria-label", titleRef.current);
        const titleEl = document.createElementNS(SVG_NS, "title");
        titleEl.textContent = titleRef.current;
        node.insertBefore(titleEl, node.firstChild);
      }
      el.replaceChildren(...(node ? [node] : []));
    };
    paint();
    if (typeof ResizeObserver === "undefined") {
      return () => el.replaceChildren();
    }
    const ro = new ResizeObserver(() => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(paint);
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      cancelAnimationFrame(raf);
      el.replaceChildren();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return <div ref={ref} style={{ width: "100%" }} />;
}
