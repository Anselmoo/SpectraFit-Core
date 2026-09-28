---
template: home.html
icon: lucide/house
description: A Rust-accelerated, Python-first spectral fitting library with analytical Jacobians, a DAG model composition IR, and a self-auditing benchmark verified against lmfit, JAX, scipy, and NIST StRD certified values.
tags:
  - NIST StRD
  - Benchmarking
  - Models
  - Rust
---

# SpectraFit-Core

<!--
  The blockquote intro paragraph, the "Status: beta (<version>)" line, and the
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
[Why spectrafit-core](why-spectrafit-core.md) for the full case for a new
implementation over wrapping lmfit/scipy, and [Limitations](limitations.md)
for disclosed gaps.

**The library reads no files.** There is no reader for any instrument or
exchange format, and none is planned: a fit takes in-memory arrays as
`MeasurementData(x, y, sigma=None)`, and getting your measurement into those
arrays is your code's job. That boundary is deliberate rather than an omission
— supplying the I/O, project handling and interactive layer is the role
[SpectraFit](https://github.com/Anselmoo/spectrafit) is intended to play. Note
that SpectraFit today is built on lmfit; adopting spectrafit-core as its engine
is planned for a future version, not something already shipped.

## Citing

If you use spectrafit-core in academic work, please cite it via
[`CITATION.cff`](https://github.com/Anselmoo/SpectraFit-Core/blob/main/CITATION.cff)
(GitHub's "Cite this repository" button reads the same file).

- **Title:** SpectraFit-Core: a Rust-cored nonlinear curve-fitting library with
  a self-auditing cross-backend benchmark
- **Author:** Anselm W. Hahn
  ([ORCID: 0000-0003-4543-4833](https://orcid.org/0000-0003-4543-4833))
- **Type:** software
- **Version:** 0.1.0
- **License:** MIT
- **Repository:** <https://github.com/Anselmoo/SpectraFit-Core>

`CITATION.cff` deliberately omits a `date-released` field: 0.1.0 has not yet
been tagged or archived, so no release date is asserted. A companion journal
article is recorded there as `preferred-citation` with `status:
in-preparation` — no DOI, journal, or publication year exists for it yet, and
none is claimed here.

## Acknowledgements

The measured spectrum used by the
[misspecified-model gallery page](tutorials/gallery/misspecified_model.md) comes
from the [EELS Database](https://eelsdb.eu/), contributed by Qiang Xu and
redistributed here under the
[Open Data Commons Open Database License](https://opendatacommons.org/licenses/odbl/).
Credit is due to the EELS Data Base and its contributors; the database itself is
described in Ewels et al. (2016),
[doi:10.1017/S1431927616000179](https://doi.org/10.1017/S1431927616000179).
Provenance, licence notice and checksum: `reproducibility/spectra/eelsdb-fe2o3-l23/`.

## License

MIT © Anselm Hahn — for the **code**. Third-party measured data vendored under
`reproducibility/spectra/` carries its own licence, recorded per asset in
`reproducibility/assets.toml` and in each directory's `README.md`; the MIT
notice does not extend to it.

See also the [Contributor Guide](contributor-guide/setup.md),
[Code of Conduct](contributor-guide/code-of-conduct.md), and [Security](security.md).
