<!--
Thanks for opening a pull request against spectrafit-core. Please read the note
below before you invest more time here — it explains something about this
GitHub repository that isn't obvious from the compose box.
-->

## Before you go further: this GitHub repo is a disposable mirror

> GitLab MPCDF is the primary development host and CI source of truth — it runs
> the full test/lint/coverage gates on every push to `main` and publishes the
> Coverage Atlas + benchmark dashboard to GitLab Pages. This GitHub repository
> carries a public, history-free snapshot mirror of `main` (republished via
> `rrt git publish-snapshot`). GitHub does run its own CI (lint/review workflows
> fire on PRs, including Dependabot's) but it does not gate `main` — the mirror
> is periodically force-pushed as a fresh snapshot, discarding prior GitHub-side
> history **and any commits/PRs made here in the meantime**.
> — [`README.md`](../README.md)

In practice: don't open a PR *targeting* this GitHub mirror expecting it to
merge here — any work merged directly into GitHub `main` is silently erased on
the next snapshot publish. Real merges always happen on GitLab. See
[`CONTRIBUTING.md`](../CONTRIBUTING.md#git-remotes) for the full remote/mirror
mechanics, and
[`docs/contributor-guide/github-mirror-workflow.md`](../docs/contributor-guide/github-mirror-workflow.md)
for how a fix made directly here can be carried back to GitLab.

This is **not** a reason to hold back — pushing a feature branch here for fast
CI iteration is a sanctioned pattern (CONTRIBUTING.md's "Fast iteration on
GitHub"), and opening a draft PR is exactly how that CI gets triggered. It just
won't be *this* PR that lands the change on `main`.

**If you don't have a GitLab MPCDF account** (most outside contributors won't —
it's institutional access), the exact intake path for your contribution isn't
documented yet; see the "For outside contributors" note in
`docs/contributor-guide/github-mirror-workflow.md`. Opening this PR is still
useful — it gives the maintainer something concrete to carry over by hand.

---

## What this PR does

<!-- Summary of the change and why it's needed -->

## How it was tested

<!-- pytest / cargo test / vitest / manual verification, as applicable -->

## Checklist

- [ ] I've read the mirror note above
- [ ] Relevant checks pass locally (`uv run poe lint_ci`, `cargo test -p <crate>`, `npm run typecheck`, etc.)
- [ ] Docs updated if user-facing behavior changed
