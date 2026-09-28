// Mermaid rendering, done entirely by this file.
//
// Zensical's bundle contains its own mermaid handling: it finds every element
// with the literal class `mermaid`, replaces the `<pre>` with an empty `<div>`,
// and calls `mermaid.run()`. That path does not render anything in this site:
// the builtin's DOM-batch approach leaves the diagram elements empty with no
// console error to explain why.
//
// So the fences are emitted as `class = "sf-mermaid"` (zensical.toml's
// `custom_fences`), which the bundle does not recognise and therefore never
// touches, and this file renders them with `mermaid.render()` per diagram
// instead — called directly with the source, it produces real nodes and a
// viewBox sized to that diagram, rather than a shared fallback viewBox.
//
// The rename is only possible because mermaid.min.js is VENDORED
// (docs/javascripts/, pinned in scripts/vendored_assets.toml). The bundle uses
// the `.mermaid` class as its trigger to fetch mermaid from
// `unpkg.com/mermaid@11` — an unpinned major, executed by every reader — so
// without vendoring, renaming the class would mean mermaid never loads at all.
//
// Two things this arrangement removes: the load-order race (the bundle would
// otherwise rewrite the element before `extra_javascript` runs, destroying the
// fence source), and any build step needed to survive that race by baking the
// sources into a JSON payload. Neither is needed once nothing else is
// competing for the elements.
//
// Diagram colouring follows the site palette via a plain stylesheet
// (docs/stylesheets/components/mermaid.css) targeting mermaid's structural
// class names (`.node rect`, `.actor`, `.edgeLabel`, …) with the site's
// `--md-mermaid-*` custom properties — not via mermaid's `themeVariables` JS
// config. CSS custom properties already follow `[data-md-color-scheme]`, so
// this needs no re-render on theme toggle and no MutationObserver, which the
// themeVariables route would require.

const FENCE_SELECTOR = ".sf-mermaid";

function captureMermaidSources() {
  document.querySelectorAll(FENCE_SELECTOR).forEach((el) => {
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
  // Vendored mermaid is a plain <script> ahead of this one, so `window.mermaid`
  // is normally set already. The poll remains as a cheap guard for a future
  // ordering change rather than as the expected path.
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
  document.querySelectorAll(FENCE_SELECTOR).forEach((el, index) => {
    if (!el.dataset.mermaidSource || el.dataset.mermaidRendered) return;
    const id = `mermaid-manual-${generation}-${index}`;
    window.mermaid
      .render(id, el.dataset.mermaidSource)
      .then(({ svg, bindFunctions }) => {
        el.innerHTML = svg;
        el.dataset.mermaidRendered = "1";
        if (bindFunctions) bindFunctions(el);
      })
      .catch((error) => {
        // Loud on purpose. A mermaid parse error produces no build failure, no
        // link-check failure and nothing under `zensical build --strict` — the
        // console is the only place it can surface. A reserved-keyword node id
        // (`graph`, `end`, `class`, `style`, `click`, `subgraph`, `default`)
        // silently killed one diagram for weeks before anyone looked here.
        console.error("mermaid-init: render failed for diagram", index, error);
      });
  });
}

whenMermaidReady(() => {
  document$.subscribe(renderMermaidDiagrams);
});
