---
type: gap
title: "[Low] ci-topology: stale .gitlab-ci.yml header comment about GitHub CI"
description: ".gitlab-ci.yml:5 — Stale .gitlab-ci.yml header comment: claims GitHub 'does not run CI of its own' and that mirror publishing is 'manual', contradicted by real workflows and by README/CONTRIBUTING"
tags: ["kind:bug", "status:closed", "domain:ci-topology", "severity:low"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/unattributed]]
- On constraint: false
- Location: `.gitlab-ci.yml:5`
- Finding domain: ci-topology
- Suggested fix / explanation: Correct the header comment to match reality (GitHub does run CI;
  the publish job is not manual).
- Resolved by: [[evidence/unattributed-ci-ev1]]
- Proposal: Confirmed both parts of the claim are wrong: (1) `.github/workflows/` has 6 real
  workflow files (ci.yml, benchmark.yml, claude-code-review.yml, claude.yml, pre-commit-check.yml,
  release.yml) — GitHub clearly runs CI of its own, and README.md itself already says so
  explicitly ("GitHub does run its own CI (lint/review workflows fire on PRs...)"), directly
  contradicting this comment. (2) `.gitlab/70-publish.yml`'s `publish:github` job (the one this
  comment names) has `rules: [{if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'}]`, i.e. runs
  automatically on every push to main — not `when: manual`. Only the separate
  `publish:github:fast` job is manual. Rewrote the comment to state both facts accurately,
  matching README.md's own already-correct language. Docs-only change. Strategy: e
  (structural/connectivity). Blast radius: local+reversible.
