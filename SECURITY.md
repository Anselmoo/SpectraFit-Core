# Security Policy

## Supported versions

`spectrafit-core` is **beta** software (`0.1.x`, promoted from alpha 2026-06-23). Only the latest `0.1.x` release on
`main` receives security fixes.

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅        |
| < 0.1   | ❌        |

## Reporting a vulnerability

Please report security issues **privately**, not via the public issue tracker:

- Open a [GitHub Security Advisory](https://github.com/Anselmoo/spectrafit-core/security/advisories/new), or
- Email anselm.hahn@gmail.com with subject `SECURITY: spectrafit-core`.

Reports are typically acknowledged within about a week. Response times are
best-effort and depend on maintainer availability; no service level is
guaranteed. Because this is a numerical
library, please also flag **correctness** issues that could silently corrupt
scientific results (e.g. a fit returning wrong parameters without erroring) —
those are treated with security-level priority.
