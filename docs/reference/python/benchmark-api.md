---
icon: lucide/server
description: The FastAPI app serving the frozen BenchReport contract — the /api/v1 vs legacy /api dual mount, its RFC 8594 deprecation window, and the CORS constraint tied to the report's embedded git provenance.
tags:
  - Benchmarking
  - Python
---

# Python: benchmark API

!!! note
    Like [Python: benchmark harness](benchmark-harness.md), this documents
    `python/oracles/api.py` — internal to this repository's own benchmark
    tooling, not the stable public API described in
    [Python: core API](core-api.md).

`oracles.api` is the only runtime bridge between a benchmark run's
`results.json` and the `web/` React UI: the React app fetches
`/api/v1/report` at load time instead of inlining a build-time fixture, and
the response models *are* the frozen `oracles.bench_contract.BenchReport`
contract, so the OpenAPI schema this app publishes is the type source for
`web/src/contract.ts`.

::: oracles.api
    options:
      show_source: false
      members_order: source
      heading_level: 3
      filters: ["!^_"]

## The `/api/v1` vs `/api` dual mount

Every route above is registered once, on a single `APIRouter`, then mounted
twice — the module docstring calls this the "Rosetta bridge." `/api/v1/*` is
the canonical prefix going forward and carries no deprecation headers.
`/api/*` is a legacy alias kept for one cycle: every response on that prefix
is stamped with `Deprecation: true` and a `Sunset` date per
[RFC 8594](https://www.rfc-editor.org/rfc/rfc8594) / the
`draft-ietf-httpapi-deprecation-header` convention, so callers see the
migration window in the HTTP response itself rather than a changelog.

::: oracles.api._LEGACY_PREFIX
    options:
      show_source: false
      heading_level: 4

The middleware that stamps those headers only tags responses whose *request*
path actually resolved under the legacy prefix — a bare `/apicruft` 404 does
not inherit them:

::: oracles.api._DeprecatedAliasMiddleware
    options:
      show_source: false
      members_order: source
      heading_level: 4
      filters: ["!^_"]

## CORS is scoped deliberately, not by default

The module docstring's `Security` note is an operational constraint, not
incidental configuration: `/api/v1/trust` and `/api/v1/report` embed the run's
git provenance in the response body, so a wildcard CORS origin would turn
that provenance into a cross-origin exposure the moment this app binds to
anything beyond the local Vite dev server. `allow_origins` is pinned to
`http://localhost:5173` and `http://127.0.0.1:5173` — add a production origin
explicitly if one is ever needed; do not widen it to `"*"`.

## See also

- **Related explanation**: [The self-auditing benchmark](../../explanation/self-auditing-benchmark.md) —
  what `/api/v1/trust`'s payload (wires, NIST validation, inference) means.
- **Reference**: [Python: benchmark harness](benchmark-harness.md) — the
  `BenchReport` and `TrustBlock` contract types these endpoints serve.
