// Makes every `<abbr title>` pymdownx.abbr renders (docs/includes/abbreviations.txt,
// auto-appended site-wide — see zensical.toml's markdown_extensions.abbr / auto_append
// comment) reachable by keyboard and touch, and upgrades the ~third of terms with a
// docs/glossary.md anchor into a real link there.
//
// The defect, measured on the live site: `content.tooltips` is enabled in
// zensical.toml's theme features, but this Zensical build (0.0.52) never mounts a
// tooltip host for it — grepping the installed bundle
// (assets/javascripts/bundle.*.min.js) for `data-md-component=tooltip` finds nothing,
// unlike `announce`/`search`/`tabs`/etc, which do exist. `.md-tooltip` is a real,
// styled theme component (see docs/stylesheets/components/abbr.css's header comment)
// with simply no JS in this build that ever creates one for an abbr. So every
// `<abbr>` renders its dotted-underline "hover me" affordance (the theme's own bare
// `abbr{}` rule) with `tabIndex === -1` — a synthesised tap produces nothing, and
// there is nothing to Tab to. A promise with no mechanism behind it.
//
// `pymdownx.abbr` cannot be configured around this: it only ever emits
// `<abbr title="...">`, never a link — so the two-part fix is: (1) this script does
// the DOM work every abbr needs (tabIndex, an accessible description, and a
// touch/keyboard-triggered reveal), and (2) docs/_render_abbr_map.py's generated
// `window.SF_ABBR_MAP` (loaded immediately before this script — see zensical.toml's
// extra_javascript ordering) tells it which abbr terms have a real docs/glossary.md
// anchor to link to instead of merely reveal. An abbr not in the map still gets the
// keyboard/touch fix; it just has nowhere to link, so it gets a reveal-only popover.
//
// Re-subscribes to Zensical/Material's `document$` instant-navigation observable
// (see docs/javascripts/katex-init.js's header comment for why a one-shot
// `DOMContentLoaded` handler would miss every page visited after the first) rather
// than running once. With this script absent or blocked, every `<abbr>` renders
// exactly as it does today — dotted underline, native mouse-hover title tooltip,
// unreachable by keyboard or touch — the pre-existing behaviour, not a broken one.

const TOOLTIP_ID = "sf-abbr-tooltip";

// The one abbr currently showing its reveal-on-demand popover, or null. Only one
// can be open at a time — a second tap/focus elsewhere always closes the first,
// matching the standard single-open-tooltip convention every OS/browser follows.
let activeTrigger = null;

function ensureTooltipHost() {
  let host = document.getElementById(TOOLTIP_ID);
  if (host) return host;
  host = document.createElement("div");
  host.id = TOOLTIP_ID;
  host.className = "sf-abbr-tooltip";
  host.setAttribute("role", "tooltip");
  host.hidden = true;
  document.body.appendChild(host);
  return host;
}

function hideTooltip() {
  const host = document.getElementById(TOOLTIP_ID);
  if (host) {
    host.hidden = true;
    host.textContent = "";
  }
  if (activeTrigger) {
    activeTrigger.removeAttribute("aria-describedby");
    activeTrigger.classList.remove("sf-abbr-active");
    activeTrigger = null;
  }
}

function showTooltip(trigger, text) {
  const host = ensureTooltipHost();
  host.textContent = text;
  host.hidden = false;
  // getBoundingClientRect is viewport-relative; add the scroll offset to place
  // the popover in document coordinates (it is `position: absolute`, not `fixed`).
  const rect = trigger.getBoundingClientRect();
  host.style.top = `${window.scrollY + rect.bottom + 6}px`;
  host.style.left = `${window.scrollX + rect.left}px`;
  trigger.setAttribute("aria-describedby", TOOLTIP_ID);
  trigger.classList.add("sf-abbr-active");
  activeTrigger = trigger;
}

function toggleTooltip(trigger, text) {
  const reopening = activeTrigger === trigger;
  hideTooltip();
  if (!reopening) showTooltip(trigger, text);
}

// `__md_scope` is a `new URL(base_url, location)` global the theme itself sets in
// <head> (partials/javascripts/base.html), well before extra_javascript runs — the
// same mechanism the theme's own instant-nav/localStorage-scoping code relies on.
// `base_url` is page-relative ("..", ".", "../..", ...), not root-absolute, which is
// what lets this resolve correctly on both GitLab Pages (served at its domain root)
// and GitHub Pages (served under /SpectraFit-Core/) without knowing which one it's
// on — see zensical.toml's repo_url comment for why a root-absolute link would break
// on the latter. Falls back to the current directory if the theme ever stops
// defining it, so a missing global degrades to a same-directory guess rather than
// throwing.
function glossaryHref(anchor) {
  const scope = window.__md_scope || new URL(".", window.location.href);
  return new URL(`glossary/#${anchor}`, scope).href;
}

// Wraps (does not replace) the abbr in a real, natively-focusable `<a>` — the abbr
// itself, its title attribute and its dotted underline are untouched, so the mouse
// hover-title behaviour anyone already relies on keeps working exactly as before.
function linkAbbr(el, anchor, term, title) {
  const link = document.createElement("a");
  link.className = "sf-abbr-link";
  link.href = glossaryHref(anchor);
  link.setAttribute("aria-label", `${term}: ${title} — opens the glossary entry`);
  el.parentNode.insertBefore(link, el);
  link.appendChild(el);
}

// No glossary anchor for this term: make the abbr itself the interactive element —
// a real tab stop (`[tabindex]:focus-visible` in utilities/focus.css supplies the
// visible ring for free) with an aria-label a screen reader announces on focus, and
// a click/Enter/Space-triggered reveal for the touch and keyboard users the native
// `title` attribute alone can never reach.
function makeRevealable(el, term, title) {
  el.tabIndex = 0;
  el.setAttribute("role", "button");
  el.setAttribute("aria-label", `${term}: ${title}`);
  el.addEventListener("click", (event) => {
    event.preventDefault();
    toggleTooltip(el, title);
  });
  el.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " " || event.key === "Spacebar") {
      event.preventDefault();
      toggleTooltip(el, title);
    } else if (event.key === "Escape") {
      hideTooltip();
    }
  });
  el.addEventListener("blur", hideTooltip);
}

function upgradeAbbr(el) {
  // Guards against re-processing the same element if `document$` were ever to fire
  // twice for one page (mermaid-init.js's captureMermaidSources uses the identical
  // dataset-flag pattern for the same reason) — cheap insurance, not a load-bearing
  // assumption about how often the observable fires.
  if (el.dataset.sfAbbrDone) return;
  el.dataset.sfAbbrDone = "1";

  const term = el.textContent;
  const title = el.getAttribute("title");
  if (!title) return;

  const map = window.SF_ABBR_MAP || {};
  const anchor = Object.hasOwn(map, term) ? map[term] : null;
  if (anchor) {
    linkAbbr(el, anchor, term, title);
  } else {
    makeRevealable(el, term, title);
  }
}

function upgradeAll() {
  document.querySelectorAll("abbr[title]").forEach(upgradeAbbr);
}

// Close the popover on any click outside it/its trigger — the standard
// click-outside-dismisses-tooltip convention. Attached once at module load
// (not inside `document$.subscribe`) since `document` itself survives instant
// navigation; only its contents get swapped.
document.addEventListener("click", (event) => {
  if (activeTrigger && event.target !== activeTrigger && !activeTrigger.contains(event.target)) {
    hideTooltip();
  }
});

document$.subscribe(() => {
  // A fresh page swap discards the old popover's trigger along with the rest of the
  // old DOM; drop our reference and the host's content so a stale `aria-describedby`
  // can't point at last page's element.
  hideTooltip();
  upgradeAll();
});
