<!--
Thanks for opening a pull request against spectrafit-core. Please read the note
below before you invest more time here — it explains something about this
GitHub repository that isn't obvious from the compose box.
-->

## Before you go further: this GitHub repo is a mirror

> Development and the authoritative CI run on an institutional GitLab instance;
> this repository is its public mirror, updated after every green pipeline on
> `main`. Issues and pull requests here are welcome — see
> [CONTRIBUTING.md](../CONTRIBUTING.md).
> — [`README.md`](../README.md)

**Outside contributors** (no account on the GitLab instance): this PR is the
supported path in. Once it is reviewed and squash-merged here, the scheduled
`backport:github` job carries it over to GitLab automatically — see
[`docs/contributor-guide/github-mirror-workflow.md`](../docs/contributor-guide/github-mirror-workflow.md).
Please keep it to files that exist on this mirror.

**Maintainers with GitLab access**: open the MR on GitLab instead. Nobody pushes
branches to this mirror by hand — only the CI sync writes here (see
CONTRIBUTING.md, "Pushing: GitLab only").

---

## What this PR does

<!-- Summary of the change and why it's needed -->

## How it was tested

<!-- pytest / cargo test / vitest / manual verification, as applicable -->

## Checklist

- [ ] I've read the mirror note above
- [ ] Relevant checks pass locally (`uv run poe lint_ci`, `cargo test -p <crate>`, `npm run typecheck`, etc.)
- [ ] Docs updated if user-facing behavior changed
