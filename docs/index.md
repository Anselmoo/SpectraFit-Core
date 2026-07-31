---
template: home.html
---

# spectrafit-core

<!--
  The blockquote intro paragraph, the "Status: beta (0.1.0b1)" line, and the
  "Where to go next" list that used to live here are now the hero's
  `.sf-hero__motto`, `.sf-hero__status` badge, and `.sf-button` CTAs
  respectively — see overrides/home.html (rendered above this content
  via the `template: home.html` front-matter key). Kept below rather than
  duplicated: the "What is this?" explanation, and the Limitations link.
-->

## What is this?

spectrafit-core fits spectroscopic and general nonlinear models with a Rust
Levenberg–Marquardt / trust-region core, exposed to Python through a PyO3 wheel
and a Pydantic schema mirror. Its distinguishing feature is a **trustworthy
benchmark**: rather than asking you to take its speed/accuracy claims on faith,
it ships a dashboard that verifies its own numbers (independent parity oracle,
timing-isolation guards, render-truth provenance, NIST StRD validation) and
visibly discloses what it has *not* verified. See
[Limitations](limitations.md) for disclosed gaps.

## Citing

If you use spectrafit-core in academic work, please cite it via `CITATION.cff`
(GitHub's "Cite this repository" button reads it).

## License

MIT © Anselm Hahn. See also the [Contributor Guide](contributor-guide/setup.md),
[Code of Conduct](contributor-guide/code-of-conduct.md), and [Security](security.md).
