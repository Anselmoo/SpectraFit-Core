---
icon: lucide/git-merge
description: How the disposable, force-pushed GitHub mirror relates to GitLab as the source of truth, and how to flow a direct GitHub edit back into GitLab.
tags:
  - Governance
  - CI
---

# GitHub mirror workflow

GitHub (`Anselmoo/spectrafit-core`) is a disposable, periodically-squashed mirror —
every `publish:github`/`publish:github:fast` run force-pushes a fresh, history-free
snapshot of GitLab's `main`, erasing whatever commit history previously existed on
GitHub. This makes GitHub a safe, low-cost place to iterate directly on
`.github/workflows/*.yml` (GitLab CI never executes `.github/**` at all, so there is
nothing to lose testing there) — but a fix made directly on GitHub needs a way to flow
back into GitLab (the real source of truth) before the next publish overwrites it.

## Mechanism 1 — cherry-picking a direct GitHub edit back to GitLab

`git cherry-pick` works across unrelated histories (only `git merge` requires
`--allow-unrelated-histories` — cherry-pick has no such restriction, since it replays a
diff, not a history graph). This licenses a simple recipe:

1. **Fetch the `github` remote** to see its current state:

    ```bash
    git remote add github https://github.com/Anselmoo/spectrafit-core.git 2>/dev/null || true
    git fetch github main
    ```

2. **Identify the commit(s) made directly on GitHub** that are not yet on GitLab's
   `main`. Since GitHub's history is a single-commit squash snapshot of some past
   GitLab state, plus zero or more direct-edit commits layered on top since the last
   publish, the direct edits are exactly the commits on `github/main` that come after
   that squash commit:

    ```bash
    git log github/main --oneline    # eyeball: the squash commit, then any commits after it
    ```

3. **Cherry-pick onto a GitLab feature branch** (never directly onto `main`):

    ```bash
    git checkout -b backport/<short-description> main
    git cherry-pick <sha1> [<sha2> ...]
    ```

4. **Verify/test.** Run the relevant test suite / manually validate the backported
   change makes sense in GitLab's full history context — a direct GitHub edit was made
   without the benefit of GitLab's pre-commit hooks, lint, or full CI matrix, so this
   step is not automatable and is the human-judgment gate this recipe deliberately
   preserves.

5. **Merge to GitLab `main`** via the normal GitLab MR flow (or a direct fast-forward
   merge for a trivial single-commit backport, per the team's existing merge
   conventions).

6. **Republish.** The next `publish:github`/`publish:github:fast` run naturally
   re-squashes and overwrites GitHub's history with the now-updated GitLab `main` — the
   direct-edit commit(s) that lived temporarily on GitHub are destroyed on republish,
   preserving the mirror's anonymity invariant (no trace of the interim direct-edit
   state survives).

## Mechanism 2 — GitHub-first feature branch (fast-dev-cycle)

A second, supported case: developing a whole feature primarily on GitHub for faster CI
feedback (see [Setup](setup.md)'s "Fast iteration on GitHub" section for the full
contributor-facing recipe). Summary:

1. Push a feature branch to `github` (`git push github my-feature`) — safe, since the
   mirror's force-push only ever overwrites GitHub `main`, never other branches.
2. Open a draft PR on GitHub against `main` — this triggers GitHub Actions CI feedback
   without touching GitLab at all.
3. Once the branch is ready, bring it back to GitLab the same way as Mechanism 1
   (fetch, identify the commits, cherry-pick onto a GitLab feature branch, merge via
   the normal GitLab MR flow).

## For outside contributors (no GitLab access)

Both mechanisms above assume push access to the `github` remote *and* the
ability to open a GitLab MR to actually land the change. An outside
contributor — someone without a GitLab MPCDF account, which is institutional
access, not self-service — has neither.

What's verifiable: GitHub `main` here is the same disposable mirror described
at the top of this page; nothing merged directly into it survives the next
publish; GitLab MPCDF is the real merge target.

What isn't yet decided: how a contribution from someone in this position is
supposed to reach GitLab at all.

> TODO(maintainer): document the outside-contributor intake path — see
> [`CONTRIBUTING.md`'s "External contributions" section](https://github.com/Anselmoo/spectrafit-core/blob/main/CONTRIBUTING.md#external-contributions-no-gitlab-access)
> for the exact question that needs answering. Until it's answered, an outside
> contributor's best option is to open a GitHub PR or issue as a proposal for a
> maintainer to manually carry over — not a merge request in the GitLab sense.

## Next steps

- **Make the change these mechanisms are for** — [Extending
  SpectraFit-Core](extending.md) lists the concrete touchpoints for a model
  or solver family — the two things contributors most often push to either
  remote.
- **See what actually runs on the mirror** — [CI pipeline & cache
  architecture](ci-pipeline.md#github-actions-mirrors-the-same-gates-cheaper)
  covers the GitHub Actions gates a draft PR here triggers.
