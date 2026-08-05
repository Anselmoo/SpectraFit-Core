// Custom Mermaid init, replacing Zensical's own bundled auto-render.
//
// Found while adding a second Mermaid diagram to contributor-guide/architecture.md
// (which brought that page to 3 diagrams): Zensical's bundled `mermaid.run()`
// (its default `startOnLoad` auto-render) reliably left every `.mermaid`
// element on a page with 3+ diagrams as an empty SVG shell — a `<style>`
// block with zero `.node`/`.actor` elements, and every one sharing the same
// fallback `viewBox="0 0 2412 512"` regardless of the diagrams' actual
// (very different) content. Confirmed this is `.run()`'s own DOM-batch
// path, not the renderer: `window.mermaid.render(id, sourceText)` called
// directly per-diagram, with the exact same source, renders correctly
// (real nodes, a viewBox sized to that diagram's actual content). This
// re-implements the DOM-scanning step on top of the working `render()` API.
//
// mermaid.js loads dynamically from unpkg.com (Zensical's own bundled JS
// injects that <script> tag once it detects a `.mermaid` element exists —
// do NOT rename the class to dodge the startOnLoad race, that skips this
// loading trigger entirely, see zensical.toml's custom_fences comment).
// Its bundled auto-run can fire *synchronously as part of mermaid.js's own
// module load*, in the same tick that makes `window.mermaid` truthy, if
// `document.readyState` is already past "loading" by the time that script
// finally arrives (near-guaranteed, since it loads well after DOMContentLoaded).
// So rather than trying to disable `startOnLoad` before that auto-run fires
// (a race we can lose), every `.mermaid` element's original fence source is
// captured into a `data-mermaid-source` attribute *synchronously, at the top
// of this script* — before mermaid.js has even been requested, let alone
// executed — so a later auto-run corrupting the live DOM can't corrupt the
// source we render from.
//
// Diagram coloring follows the site's palette via a plain CSS stylesheet
// (docs/stylesheets/components/mermaid.css, copied from Zensical's own
// bundled rule set) targeting mermaid's structural class names (`.node
// rect`, `.actor`, `.edgeLabel`, ...) with the site's `--md-mermaid-*`
// custom properties — not via mermaid's `themeVariables` JS config. CSS
// custom properties already follow `[data-md-color-scheme]` on their own,
// so this needs no re-render-on-toggle logic and no MutationObserver (an
// earlier version of this file tried the themeVariables route and needed
// exactly that extra complexity — reverted, see DECISIONS.md's [2026-08-02]
// mermaid entry).
function captureMermaidSources() {
  document.querySelectorAll(".mermaid").forEach((el) => {
    if (el.dataset.mermaidSource) return;
    const source = el.textContent.trim();
    if (source) el.dataset.mermaidSource = source;
  });
}
captureMermaidSources();

function whenMermaidReady(callback) {
  if (window.mermaid) {
    callback();
    return;
  }
  const intervalId = setInterval(() => {
    if (window.mermaid) {
      clearInterval(intervalId);
      callback();
    }
  }, 50);
}

let renderGeneration = 0;

function renderMermaidDiagrams() {
  window.mermaid.initialize({ startOnLoad: false });
  captureMermaidSources(); // instant-nav may have introduced new elements
  renderGeneration += 1;
  const generation = renderGeneration;
  document.querySelectorAll(".mermaid").forEach((el, index) => {
    if (!el.dataset.mermaidSource || el.dataset.mermaidRendered) return;
    const id = `mermaid-manual-${generation}-${index}`;
    window.mermaid
      .render(id, el.dataset.mermaidSource)
      .then(({ svg, bindFunctions }) => {
        el.innerHTML = svg;
        el.dataset.mermaidRendered = "1";
        // Zensical's own bundled JS also watches for `.mermaid` elements and
        // will try to render any it still finds un-removed — dropping the
        // class the same way its own renderer does signals "already handled"
        // to it too, so a same-element double-render can't race this one.
        el.classList.remove("mermaid");
        if (bindFunctions) bindFunctions(el);
      })
      .catch((error) => {
        console.error("mermaid-init: render failed for diagram", index, error);
      });
  });
}

whenMermaidReady(() => {
  document$.subscribe(renderMermaidDiagrams);
});
