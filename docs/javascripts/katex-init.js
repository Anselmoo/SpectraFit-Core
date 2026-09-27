// Renders KaTeX math wherever pymdownx.arithmatex (generic mode) has wrapped
// it in `.arithmatex` inline `\( ... \)` / block `\[ ... \]` markup.
//
// `document$` is Zensical/Material's instant-navigation observable (see
// zensical's own bootstrap docs/index.md's MathJax example for the same
// pattern): with `navigation.instant` enabled (zensical.toml), page
// navigations swap `document.body`'s content in place without a full
// reload, so a plain `DOMContentLoaded` listener would only ever fire once
// and math on every subsequently-visited page would never render. Vendored
// KaTeX + auto-render, not a MathJax CDN script, per the self-hosted-fonts
// precedent (zensical.toml's `theme.font = false`).
document$.subscribe(() => {
  renderMathInElement(document.body, {
    delimiters: [
      { left: "\\(", right: "\\)", display: false },
      { left: "\\[", right: "\\]", display: true },
    ],
    throwOnError: false,
  });
});
