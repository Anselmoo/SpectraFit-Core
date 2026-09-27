// Redirects Zensical's own bundled GLightbox CSS loader away from unpkg.com.
//
// Read from the installed Zensical build (0.0.52, zensical/templates/assets/
// javascripts/bundle.*.min.js): the moment a page has a `.glightbox` element,
// its bundled `Hp()`/`$i()` helpers unconditionally append a
// `<link rel="stylesheet" href="https://unpkg.com/glightbox@3/dist/css/...">`
// to <head> — no `typeof`/existence check, unlike the JS half (`Cp()`, which
// checks `typeof GLightbox=="undefined"` and is pre-empted just by loading
// glightbox.min.js as a plain script — see zensical.toml's extra_javascript
// comment). Confirmed empirically: with only glightbox.min.js vendored, a
// Playwright network trace on a gallery page still showed a live request to
// unpkg.com/glightbox.../css/glightbox.min.css even though no JS request
// fired. Neither zensical.toml nor the `glightbox` plugin's config schema
// (zensical/extensions/glightbox.py's `GlightboxConfig`) exposes a switch
// for this — it is not a config gap on our side, there is nothing to set.
//
// This rewrites that <link>'s href to the vendored stylesheet already loaded
// via extra_css instead of dropping the tag outright: Zensical's own loader
// pipeline waits for the link's `load` event before calling GLightbox's
// `.reload()` (which is what actually wires up newly-added `.glightbox`
// anchors) — swallowing the appendChild instead would silently break the
// lightbox rather than just avoiding the CDN hit.
(function () {
  var vendored = document.querySelector(
    'link[rel="stylesheet"][href$="stylesheets/glightbox.min.css"]',
  );
  if (!vendored) return;
  var localHref = vendored.href;
  var originalAppendChild = Node.prototype.appendChild;
  Node.prototype.appendChild = function (node) {
    if (
      node &&
      node.tagName === "LINK" &&
      typeof node.href === "string" &&
      node.href.indexOf("unpkg.com/glightbox") !== -1
    ) {
      node.href = localHref;
    }
    return originalAppendChild.call(this, node);
  };
})();
