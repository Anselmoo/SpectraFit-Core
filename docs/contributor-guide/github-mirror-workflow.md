---
icon: lucide/git-merge
description: How GitLab and the GitHub mirror sync in both directions -- the anonymous, append-only fast-forward publish, the history-preserving scheduled auto-backport, and the emergency history reset.
tags:
  - Governance
  - CI
---

# GitHub mirror workflow

GitLab MPCDF (`gitlab`) is the primary remote and source of truth; GitHub
(`Anselmoo/SpectraFit-Core`, remotes `origin`/`github`) is the public mirror.
Until the final orphan snapshot described below, every publish force-pushed a
fresh, history-free copy of GitLab `main` onto GitHub `main`, discarding
whatever GitHub history existed before it. From that snapshot on, publishing
switched to an **append-only sync**: each GitLab publish adds one new commit
on top of GitHub `main` instead of discarding its history, so GitHub's history
now grows forward and tags/forks/PRs against it keep working across a publish.

The two directions follow opposite rules, deliberately:

- **GitLab -> GitHub is anonymous.** One bot commit per sync -- author *and*
  committer `spectrafit-core-sync[bot]`
  (`334580965+spectrafit-core-sync[bot]@users.noreply.github.com`), the bot
  account of the `spectrafit-core-sync` GitHub App, so GitHub attributes every
  sync commit to that bot and never to a person. The App needs no permissions
  and no installation for this. A fixed message, no GitLab commit messages,
  authors or history. The single piece of
  GitLab state that crosses over is the `GitLab-Commit: <sha>` trailer that
  marks the sync boundary.
- **GitHub -> GitLab keeps history.** Every GitHub commit lands on GitLab as
  its own commit, with its original author, date and message, cherry-picked
  with `-x`; the GitLab merge request is never squashed.

## The baseline: the final orphan snapshot

The last history-discarding publish (`scripts/publish_snapshot.sh`, via `rrt
git publish-snapshot`) is the seam between the two eras. Its commit message
carries a trailer:

```text
GitLab-Commit: <full GitLab main SHA>
```

Everything downstream keys off finding this trailer: `scripts/publish_sync.py`
reuses the exact string (`SYNC_TRAILER`) for every sync commit it builds, and
`scripts/backport_from_github.py` walks `github/main`'s first-parent history
looking for the newest commit that carries it — that commit is the sync
boundary, and everything after it, first-parent, is GitHub-native work (see
[Mechanism 2](#mechanism-2-the-scheduled-auto-backport-github-gitlab) below).
If no commit on `github/main` carries the trailer yet, the backport script
refuses outright rather than treating GitHub's entire (pre-snapshot, unrelated)
history as pending work.

## Mechanism 1 -- the anonymous fast-forward sync (GitLab -> GitHub)

`scripts/publish_sync.py` builds **one commit** whose tree is GitLab `HEAD`'s
tree reduced to the shared publish scope (`scripts/publish_exclusions.py`),
parented on the *currently published* GitHub `main` -- not an
orphan root -- with the fixed subject `sync: gitlab main`, a fixed body, and
the `GitLab-Commit: <full sha>` trailer. Author and committer (name, email and
date) are set explicitly to the bot identity, so nothing from the runner or a
developer's environment can reach it; the date is the GitLab `HEAD` commit
date, which makes the commit SHA reproducible. It never touches the caller's
real working tree or index (the filtering happens in a throwaway
`GIT_INDEX_FILE`).

**What triggers it** -- `.gitlab/70-publish.yml`:

- **`publish:github`** runs automatically (`when: on_success`, GitLab's
  default) on every pipeline on `main`, but only after every earlier stage
  (setup/lint/test/coverage/build/pages) has succeeded -- it has no `needs:`
  override, so normal stage-ordering still gates it.
- **`publish:github:fast`** is `when: manual`, decoupled from stage-ordering
  (`needs: []`), for `.github/**`-only changes. It first re-verifies via
  `scripts/fast_lane_gate.py` that the diff since the last published GitHub
  SHA touches nothing outside `.github/**`, then calls the same
  `publish_sync.py`.
- Both jobs share a `resource_group`, so two overlapping pipelines can't race
  and force-push `sync/gitlab` out of order.

**The mechanics**, once `publish_sync.py` runs:

1. Fetch `github/main` and compare its tree against the filtered GitLab tree.
   If they're identical, it prints `up to date` and exits 0 -- **no PR, no
   push, no-op.**
2. **Refuse to lose work** (`sync_guard`) -- only when step 1 found a
   difference, so an up-to-date pipeline stays a quiet no-op. It finds the
   sync boundary on
   `github/main` and the GitLab commit its `GitLab-Commit:` trailer names,
   then stops before building the sync commit if either would lose work:
    - **stale pipeline** -- GitHub is already synced from a GitLab commit
      *newer* than this pipeline's `HEAD` (an older pipeline finishing late).
      A sync would roll GitHub back, so the job prints `skipped — stale` and
      exits 0;
    - **pending backport** -- GitHub `main` carries native commits after the
      boundary whose patch is not on GitLab `HEAD` yet. The sync commit takes
      GitLab's tree wholesale, so it would revert them on GitHub *and* move the
      boundary past them, where Mechanism 2 never looks again. The job prints
      `REFUSED` with the commit list and exits 1 until `backport:github` has
      landed them.

   Both checks need the GitLab commit named in the trailer, so the sync jobs
   run with `GIT_DEPTH: "0"`; a missing commit is itself a refusal.
3. If neither applies, it builds the sync commit, force-pushes it to `sync/gitlab` on
   GitHub through the deploy-key `github-push` remote (force is safe here:
   `sync/gitlab` is a disposable staging branch,
   rewritten on every run -- never build on it by hand), and creates or
   updates a **draft** PR `sync/gitlab -> main`. A draft has no merge button,
   so nobody -- and no auto-merge -- can squash it and re-author the bot
   commit.
4. It reads the required status checks that the repository's rulesets apply
   to `main` and waits until every one of them has passed **on the sync
   commit** (the PR runs `.github/workflows/ci.yml`). No required check
   configured means **no landing** -- the script refuses rather than land
   unguarded. A failed check leaves the PR open and exits non-zero; a check
   still pending after `--check-timeout` leaves the PR open and exits 0, and
   the next run rebuilds the identical commit and resumes waiting.
5. It then **fast-forwards** `main` to exactly that commit -- a plain `git
   push`, never `--force`, through the same `github-push` SSH remote,
   authenticated by the deploy key that is the rulesets' only bypass actor. GitHub
   marks the PR merged by itself. If `main` moved in the meantime, the push is
   rejected as a non-fast-forward and the run aborts loudly.

**Why not a squash merge**: GitHub rewrites a squash (or auto-merge) commit's
author to the PR author -- the owner of the token that opened it -- and its
committer to `GitHub <noreply@github.com>`. That would put a personal identity
on every sync commit. Landing the already-built bot commit by fast-forward is
the only path that keeps it anonymous; the PR exists for CI and visibility,
not as the merge mechanism.

Because the sync commit's tree is already reduced to what
`scripts/publish_exclusions.py` includes, and it's parented on the real GitHub
`main` rather than an orphan root, GitHub's mirror history is now a normal,
append-only sequence of bot commits -- each one carrying its own
`GitLab-Commit:` trailer, so the boundary-finding logic above keeps working
release after release.

**Private mirror**: every fetch is authenticated as well as every push --
both jobs export `GITHUB_TOKEN` as an `http.https://github.com/.extraheader`
(never in a URL or `.git/config`), so the sync also works while the mirror is
a private repository.

## Mechanism 2 -- the scheduled auto-backport (GitHub -> GitLab)

Not everything reaching GitHub `main` originates on GitLab: a Dependabot PR
or an outside contributor's PR can be merged straight into GitHub `main`.
`scripts/backport_from_github.py --open-mr`, wired into `.gitlab/75-backport.yml`
as the `backport:github` job, finds and lands that work automatically:

1. **Find the boundary** -- the newest first-parent commit on `github/main`
   carrying the `GitLab-Commit:` trailer (see above).
2. **Candidates** -- every first-parent commit after that boundary that does
   *not* itself carry the trailer, oldest first, with each merge commit (a PR
   merged with "Create a merge commit") **expanded into the PR's own
   commits** (`<merge>^1..<merge>^2`, merges inside the PR branch left out).
   This is exactly the
   GitHub-native work: nothing that came from a GitLab sync is ever picked up
   as a candidate. This list can still contain a commit an *earlier*
   `--open-mr` run already backported -- see "Recognising an already-applied
   candidate" below for why the boundary alone doesn't prevent that. With no
   candidates at all, the script exits 0 here -- nothing to do.
3. **Drop already-applied candidates** (`filter_already_applied`) -- before
   touching git history, each candidate is checked against `gitlab/main` and
   removed if it's already there (see below). If every candidate turns out
   to already be applied, this is a **clean no-op, exit 0** -- not an empty
   cherry-pick treated as a failure.
4. **Cherry-pick** each remaining candidate with `-x` onto a fresh
   `backport/github-<YYYYMMDD>` branch (suffixed `-2`, `-3`, ... if that name
   is already taken) created from `gitlab/main`. Each commit keeps its
   original author name, email and date and its full message, plus the
   `(cherry picked from commit <sha>)` line `-x` appends -- nothing is
   squashed and nothing is re-attributed to the CI identity. Only a merge that
   still reaches this step (feature-branch mode, or a PR without a single
   non-merge commit) falls back to a `-m 1` replay against its first parent. As a
   defense-in-depth layer under step 3 -- covering, for example, a
   hand-resolved backport with no `-x` trailer -- a candidate that turns out
   to be empty against the branch's current tip is skipped (`--empty=drop`
   on git >=2.45, otherwise a detected "cherry-pick is now empty" stop
   resolved with `git cherry-pick --skip`) rather than treated as a conflict.
5. **Conflict behaviour**: on the first *real* conflicting cherry-pick, the
   script aborts the pick and exits non-zero -- **there is no auto-resolve.**
   A maintainer resolves it by hand and opens the MR manually (the same
   recipe the non-`--open-mr` mode prints).
6. **Push and open a GitLab MR** against `main`, via the GitLab REST API,
   with `squash: false` -- keep the project's squash option on "Allow" or
   "Do not allow", and leave the squash box unticked when merging it.
   Before doing any of this, it checks for an already-open
   `backport/github-*` MR and skips (exit 0) if one exists -- the idempotent
   guard that makes it safe to run on a fixed schedule as well as manually.

**What triggers it** -- `backport:github` runs on a `schedule` pipeline with
the CI/CD variable `BACKPORT_GITHUB` set to `true` (configured on a GitLab
schedule under *Settings > CI/CD > Schedules*; absent on an ordinary
pipeline, so a normal push to `main` never fires it), or manually
(`when: manual`) from any pipeline on `main`. It needs `BACKPORT_TOKEN` -- a
GitLab project access token scoped to `api` + `write_repository`, masked and
protected -- because `CI_JOB_TOKEN` cannot push to the project's own
repository from a job, and `GITHUB_TOKEN` to fetch the mirror once it is
private. Each token travels only to its own host: `GIT_CONFIG_COUNT=2`, one
`http.<host>.extraheader` per host.

### Recognising an already-applied candidate

Idempotency here is **not** "by construction" -- it needs the check in step 3
above, for a concrete reason: the sync boundary on `github/main` only
advances when a GitLab -> GitHub sync produces a commit whose *content*
actually differs from what's already published (Mechanism 1's tree-diff
no-op, above), and a backport-only round doesn't by itself produce that --
it makes GitLab's tree converge on GitHub's, not diverge. So after a backport
MR merges on GitLab, the *next* `publish_sync.py` run can easily find nothing
to sync and no-op, in which case the boundary never moves and a later
scheduled `backport:github` run recomputes the exact same candidate list --
including the one already landed.

`filter_already_applied` is what makes that safe: it drops a candidate that
is already present on `gitlab/main`, checked two ways. The primary,
cheap signal is provenance -- `git cherry-pick -x` leaves a `(cherry picked
from commit <sha>)` trailer in the commit it creates, and that full SHA is
scanned for across `gitlab/main`'s history. The secondary signal is content
equivalence -- `git patch-id --stable`, matched against every first-parent
commit between the (possibly stale) boundary's GitLab SHA and `gitlab/main`
-- for a backport that landed without that trailer (e.g. resolved and
committed by hand). Only once neither signal matches does a candidate reach
the actual cherry-pick in step 4. This is a separate mechanism from
Mechanism 1's tree-diff no-op above: that one skips a whole *sync* when
nothing changed; this one skips an individual *candidate* that's already
there, regardless of what the sync boundary currently thinks.

## Why the two directions cannot loop

Three independent guards keep a GitLab -> GitHub sync and a GitHub -> GitLab
backport from re-triggering each other forever:

1. **The trailer boundary.** Every sync commit carries a `GitLab-Commit:`
   trailer, and Mechanism 2 only considers first-parent commits on
   `github/main` *after* the newest trailer-carrying commit. A sync commit
   itself is never picked up as backport-native work, so a GitLab -> GitHub
   publish can never be read back as a GitHub-originated change.
2. **No-op on an equal tree.** Mechanism 1 compares the filtered GitLab tree
   against GitHub `main`'s current tree before building anything, and exits
   without pushing or opening a PR when they already match. A backport that
   merely brings GitLab's tree in line with GitHub's therefore produces
   nothing for the *next* sync to sync.
3. **Patch-id dedupe.** `filter_already_applied` drops a backport candidate
   already present on `gitlab/main`, by cherry-pick provenance or by
   `git patch-id` content match. A candidate the previous run already landed
   is never cherry-picked a second time, even if the trailer boundary hasn't
   moved.

**The one caveat**: these guards only protect paths inside the publish scope.
A change merged straight into GitHub `main` at a path *outside*
`scripts/publish_exclusions.py`'s scope still gets backported to GitLab (it's
ordinary GitHub-native work as far as Mechanism 2 is concerned) — but the very
next GitLab -> GitHub sync then removes it from GitHub again, because that
path was never meant to be published in the first place. A PR touching such a
path should be redirected to open against GitLab directly rather than merged
on GitHub.

## Who may write to the mirror

The invariant: **no tree reaches GitHub that contains a path outside
`scripts/publish_exclusions.py`'s include list.** Only the CI jobs above
(`publish:github`, `publish:github:fast`, `publish:github:reset`) write to the
mirror, and all three filter through that module first. Nothing else may push
there -- not a feature branch, not a benchmark branch, not a one-off fix: a
hand-pushed branch carries the full, unfiltered tree.

Two layers enforce it:

1. **Client side -- the `guard-public-push` pre-push hook**
   (`scripts/guard_public_push.py`, `.pre-commit-config.yaml`). For a push to
   any github.com remote it lists the FULL tree of the pushed commit and
   refuses if any path is excluded; pushes to GitLab are never inspected, and
   there is no bypass variable. Its limits are git's: `--no-verify` skips it,
   and under pre-commit only the first ref of a multi-ref push is reported.
   Disabling the push URL of each GitHub remote in a clone
   (`git remote set-url --push <remote> DISABLED`) removes the
   hand-push path entirely.
2. **Server side -- the mirror repository's rules.** Set up when the GitHub
   repository is (re)created, before the first sync:
    - a branch ruleset (`restrict-all-branches`) over all branches **except
      the default branch** that restricts creation, update and deletion, with
      **only the sync deploy key** (the public half of `GITHUB_DEPLOY_KEY`)
      on the bypass list and `dependabot/**` excluded from it -- no personal
      account can push any branch, so an unfiltered tree has no way in
      (outside contributors work from forks). `main` must be excluded here:
      a PR merge is an update of `main`, and with `main` in this ruleset no
      PR could ever be merged, not even by an admin;
    - on `main` (`main-protection`): pull request required, required status
      checks `lint` and `claude-review-gate` (see below), force pushes and
      deletion blocked, again with only the deploy key on the bypass list.
      The required checks are also what Mechanism 1 waits for before it
      lands. **"Require approval for unattributed changes" stays off**:
      branch pushes by the deploy key are unattributed, so with a single
      maintainer every PR would wait for an approval nobody can give;
    - merge method for contributor PRs: **squash only** (repository setting
      and the `main` ruleset's allowed merge methods), with the PR title as
      the commit title and the commit messages as its body -- one commit per
      PR keeps `main`'s history short, and Mechanism 2 backports that single
      commit as it is (a non-merge commit stands for itself). The squash
      commit is authored by the PR author; anyone else who committed to the
      PR appears as a `Co-authored-by:` trailer. **Repository auto-merge is
      off**: enabled once on a sync PR, it squashed the bot commit under a
      personal name. The sync PR never goes through a merge button at all --
      it is a draft and lands by the deploy-key fast-forward above;
    - no other account with write access.

    Create the `main` ruleset **disabled** until `publish:github:reset` has
    seeded the repository -- the reset force-pushes `main` with
    `GITHUB_TOKEN`, which an active ruleset refuses -- then enable it.


`publish:github:reset` (`.gitlab/70-publish.yml`, `when: manual`) is the
original history-discarding orphan snapshot, kept unchanged as a last resort:
it still runs `scripts/publish_snapshot.sh` (including its stale
GitHub-Actions-run purge) exactly as before Mechanism 1 existed. It is
**not** part of the normal sync path and never runs automatically.

**Cost**: it rewrites GitHub `main`'s public history from scratch. Any fork
that has based work on the previous history, and any open GitHub PR against
`main` (including an outside contributor's PR or a Dependabot PR not yet
merged), is orphaned by the rewrite -- their base commit no longer
exists on `main`. Use it only when the append-only sync history itself needs
to be discarded and restarted from a single fresh commit, and be prepared to
ask anyone with open work against GitHub `main` to rebase.

## Review gate on GitHub pull requests

Every PR gets the commit status `claude-review-gate` from
`.github/workflows/claude-code-review.yml`, and `main-protection` requires it:

| Light | Meaning | Merge |
|---|---|---|
| 🔴 | at least one *must* finding (breaks build, tests, a contract, security or data, or a quotable `CLAUDE.md` rule) | blocked |
| 🟠 | *should* findings only | allowed |
| 🟡 | minor *could* findings only | allowed |
| 🟢 | nothing to change | allowed |

The review runs on Sonnet only and writes one comment per PR (updated on
every push) plus inline comments for *must* findings; the run's transcript is
kept as a workflow artifact. A maintainer overrides a red light for the
current commit with a PR comment `/claude-override <reason>`. The sync PR and
Dependabot PRs get a green "skipped" status; a PR from an author without
write access gets red until a maintainer overrides it, so Claude never runs
on untrusted input unasked.

**Where a change should start.** Anything whose correctness depends on more
than Linux -- wheels, Windows or macOS behaviour, a new CPython -- is best
opened as a GitHub PR: GitHub's runners give the full platform matrix that
GitLab CI does not have, and Mechanism 2 brings the squash commit back to
GitLab. GitLab-only work (release bumps, benchmark gates, the docs site)
stays on GitLab.

## For outside contributors (no GitLab access)

This is now resolved: an outside contributor -- someone without a GitLab
MPCDF account, which is institutional access, not self-service -- opens a
**normal GitHub pull request** against `Anselmoo/SpectraFit-Core`'s `main`
branch, same as on any GitHub project. Once it passes GitHub Actions CI and
is reviewed and squash-merged on GitHub (one commit per PR, authored by the
PR author, other committers as `Co-authored-by:` trailers), that commit sits
on `github/main` after the sync boundary -- exactly the "GitHub-native work" Mechanism 2 exists to
find. The next `backport:github` run (scheduled or
manual) cherry-picks it onto a `backport/github-<date>` branch and opens the
GitLab MR that actually lands it on the source of truth. No separate
intake channel, manual replay, or maintainer copy-paste step is needed.

## Next steps

- **Make the change these mechanisms are for** -- [Extending
  SpectraFit-Core](extending.md) lists the concrete touchpoints for a model
  or solver family -- the two things contributors most often change.
- **See what actually runs on the mirror** -- [CI pipeline & cache
  architecture](ci-pipeline.md#github-actions-mirrors-the-same-gates-cheaper)
  covers the GitHub Actions gates an outside contributor's PR triggers.
- **Cutting a release** -- [Cutting a release](releasing.md) covers which
  commit to tag once the append-only sync history is in place.
