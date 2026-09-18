---
icon: lucide/life-buoy
description: Where to report a spectrafit-core bug, what to include, and the platform caveats worth checking first.
tags:
  - Governance
---

# Support

spectrafit-core does not have a Discussions forum or a support mailing
list — GitHub Discussions is not enabled for this repository. The
[issue tracker](https://github.com/Anselmoo/spectrafit-core/issues) is the
place to report bugs and ask usage questions.

For security vulnerabilities, do **not** use the public issue tracker — see
[Security](security.md) instead.

## Reporting a bug

Open an issue at
[github.com/Anselmoo/spectrafit-core/issues](https://github.com/Anselmoo/spectrafit-core/issues).
There is no issue template yet, so include, wherever relevant:

- The installed version, and whether it came from source or a wheel.
- Your OS and platform — results can depend on the platform's LAPACK
  backend (see the platform caveats below).
- A minimal script that reproduces the issue, including the model shape
  (peak count, dimensionality, tied/fixed parameters).
- The full error output or traceback, not just the last line.
- For a numerical/correctness problem — a fit that converges to a wrong
  answer without erroring — say so explicitly; these are treated with the
  same priority as security issues (see [Security](security.md)).

## Platform caveats worth checking first

Before filing, check whether a report is really a build-environment gap
rather than a spectrafit-core bug — see
[Installation](getting-started/installation.md) for the full detail:

- **Linux**: building from source needs a Fortran compiler, CMake, and
  LAPACK/OpenBLAS headers (`gfortran`, `cmake`, `liblapack-dev`,
  `libopenblas-dev` on Debian/Ubuntu). A missing-library error at build
  time is usually one of these, not a spectrafit-core bug.
- **macOS**: no extra system packages are needed — the VarPro solver links
  against the OS-provided Accelerate framework.
- **Windows**: unverified. This project's test CI has no Windows job, so
  the Windows build path has never been exercised by the test suite — only
  wheel-building is automated there. A Windows-specific issue may be the
  first report of its kind; please file it anyway.

## What to expect

This is beta software from a small team. Issues are read and triaged as
time allows; there is no guaranteed response time or support SLA. Pull
requests that fix a reported bug are welcome — see
[Contributing](contributor-guide/index.md).
