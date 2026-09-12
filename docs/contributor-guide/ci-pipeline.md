---
icon: lucide/workflow
description: Why the GitLab CI cache architecture and pipeline plumbing look the way they do — the incident history behind each design decision.
tags:
  - CI
  - Rust
---

# CI pipeline & cache architecture

GitLab CI (`.gitlab/*.yml`) is the primary pipeline (see
[Remote topology](architecture.md)); GitHub Actions (`.github/workflows/ci.yml`) mirrors
the same gates for the downstream publish target. This page collects the *why* behind
the current cache-bucket layout and a few non-obvious job dependencies — history that
used to be duplicated, near-verbatim, across three separate `.gitlab/*.yml` files.

## Cache buckets

`10-setup.yml` is the only job with `policy: pull-push`; every downstream job declares
`policy: pull` on only the bucket(s) it needs:

| Bucket | Contents | Written by |
| --- | --- | --- |
| `rust-*` | `.cargo/` (registry index) | `setup` |
| `static-*` | `.uv-cache/` (uv wheel cache) + `.venv/` | `setup` |
| `web-*` | `web/node_modules/` | `setup` |

The `*` is `$CI_COMMIT_REF_SLUG`, so caches are branch-scoped and don't cross-contaminate
MR branches.

??? note "`rust-*` does not carry `target/`"
    Pipeline #18 hit `ENOSPC` mid-`rustc` (on `syn`/`serde_derive`) because a cached
    1–2 GB `target/` was pulled *and* written back on every Rust job, overflowing GWDG
    runner disk. The fix: `rust-*` was narrowed to `.cargo/` only — each Rust job now
    rebuilds from a warm cargo registry instead of a warm `target/`. Cost: ~2–3 min extra
    per Rust job; benefit: bounded disk use. This applies uniformly to `lint:rust`
    (`20-lint.yml`), `setup`/`test:python` (`10-setup.yml`), and `test:rust`
    (`30-test.yml`) — all three narrowed together as one fix, which is why the same
    rationale used to appear three times.

## Baked CI image

All `apt`/`rustup`/`cargo-llvm-cov` installation happens once, at **image build time**,
in `.gitlab/docker/Dockerfile.ci` (built by the `build:ci-image` `.pre` job) — not per
job. `00-defaults.yml`'s `before_script` is intentionally a thin ~10-line tool-check that
surfaces a missing binary in the first 5 lines of any job log, nothing more.

One consequence worth noting explicitly: the GPG-repair sequence for flaky Debian
mirrors (a workaround needed inside the `nikolaik` base image) is deliberately absent
from `before_script` — `apt` now only ever runs at image-build time, inside
`Dockerfile.ci`, where that race can't occur in a pipeline job.

## Fingerprint stage: fast signal ahead of `setup`

GitLab has no per-job priority setting, so the `fingerprint` stage
(`.gitlab/15-fingerprint.yml`) gets its jobs to the front of the pipeline
structurally instead: it sits before `setup` in `stages:`, and its two jobs
(`fingerprint:rust-fmt`, `fingerprint:python-static`) declare `needs: []`, so
they start immediately rather than waiting for `setup` to install the full
toolchain. Both duplicate the cheapest checks `lint:rust` / `lint:python`
already run (`cargo fmt --check`, `ruff format --check`, `ruff check`) plus
the PyO3/schema-sync boundary hooks — the heavier `lint:*` jobs remain the
authority; this stage only exists to turn the most common MR-blocking
mistake (a formatting or lint drift) into a red/green result in a couple of
minutes instead of after `setup` finishes.

## `build:web` needs `setup`, not just `test:web`

`build:web` (`50-build.yml`) depends on `setup` directly (in addition to `test:web`, kept
for stage ordering) because GWDG runners have no shared cache server — a cache hit on one
runner is invisible to another. Pipeline #16 failed with `sh: 1: tsc: not found` because
`build:web` landed on a runner that had never populated the `web-*` cache. **Artifacts**
(unlike caches) *are* cross-runner on GitLab, so depending on `setup` pulls
`web/node_modules/` as an artifact regardless of which runner picks up the job.

## Rust coverage moved into `test:python`

The merged Rust `lcov` + workspace/per-crate coverage gates live inside
`test:python:rust-cov`, not a separate job — `profraw` files and instrumented binaries
must be produced and consumed on the *same* runner, and (per the point above) GitLab
gives no such guarantee across two jobs on GWDG. `40-coverage.yml` is reduced to
promoting the resulting `lcov.info` to a longer-lived (14-day, vs. `test:python`'s 1-day)
artifact, then fusing python + rust + web coverage into the coverage Atlas.

## GitHub Actions mirrors the same gates, cheaper

`ci.yml`'s coverage job installs `cargo-llvm-cov` via `taiki-e/install-action` (a
prebuilt, signed-attestation tarball matching the runner arch, cached via the GH Actions
tool cache) instead of `cargo install --locked` compiling from source — the same
single-source-of-truth trick (`taiki-e` releases) as GitLab's own prebuilt tarball fetch
in `.gitlab/docker/Dockerfile.ci`. Per-module coverage percentages in the PR step summary come from a
single `uv run coverage json` call, sliced per module with `jq` — avoiding a `uv run`
re-resolution shell-out per module (~30 s/pipeline saved).

=== "GitLab (primary)"

    - `cargo-llvm-cov` prebuilt via a baked CI image (`.gitlab/docker/Dockerfile.ci`),
      not fetched per job.
    - Rust coverage lives inside `test:python:rust-cov` (profraw + binaries share a
      runner — GWDG has no shared cache server).
    - Rustdoc publishes to `public/rust-api/`.

=== "GitHub (downstream mirror)"

    - `cargo-llvm-cov` fetched per run via `taiki-e/install-action` (no baked image on
      this side).
    - Rust coverage runs inside `build-and-test`, uploaded as an artifact for the
      separate Coverage Atlas fusion job.
    - Rustdoc publishes to `site/rust-api/` (fixed 2026-08-08 — see `DECISIONS.md`).

## Next steps

- **Follow the pipeline to its mirror** — [GitHub mirror workflow](github-mirror-workflow.md)
  covers how the downstream GitHub Actions pipeline documented above relates
  to GitLab as the source of truth.
- **See where the coverage floors come from** — [`pyproject.toml`,
  explained](project-configuration.md#coverage) covers where the coverage
  percentages the Atlas job fuses actually come from.
