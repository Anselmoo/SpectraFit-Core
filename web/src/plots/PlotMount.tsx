import { useEffect, useRef } from "react";

/** Mounts an imperatively-built SVG (e.g. Observable Plot) inside a React leaf
 *  div, isolating it from React reconciliation. `make(width)` builds the node at
 *  the measured container width (or returns null to render nothing); it re-runs
 *  whenever `deps` change OR the container resizes. replaceChildren keeps React
 *  from ever seeing foreign children (the insertBefore-desync fix). */
export function PlotMount({
  make,
  deps,
}: {
  make: (width: number) => SVGSVGElement | null;
  deps: unknown[];
}) {
  const ref = useRef<HTMLDivElement>(null);
  const makeRef = useRef(make);
  makeRef.current = make;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let raf = 0;
    const paint = () => {
      const w = el.clientWidth || 640;
      const node = makeRef.current(w);
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
