---
icon: lucide/rocket
description: Checklist for cutting a release -- the one-time environment and trusted-publisher setup, a workflow_dispatch build dry run, a release-candidate rehearsal through TestPyPI, and the final tag through PyPI and the GitHub Release -> Zenodo DOI mint.
tags:
  - Governance
  - CI
---

# Cutting a release

This page is the checklist for cutting a release of `Anselmoo/SpectraFit-Core`
-- from the one-time environment and trusted-publisher setup, through a
release-candidate rehearsal that only reaches TestPyPI, to the final tag that
reaches PyPI and mints a Zenodo DOI. It covers the mechanics of getting from a
tagged commit to a published, archived release -- not the version-bump policy
itself, which is covered in [`pyproject.toml`, explained](project-configuration.md#versioning-rrt).

## Prerequisites (once)

Set these up once, before the first release candidate is tagged. None of them
are per-release steps.

1. **Two GitHub deployment environments** on `Anselmoo/SpectraFit-Core`
   (*Settings > Environments*):
   - **`testpypi`** -- no required reviewers, so a release-candidate tag can
     publish to TestPyPI without a manual approval.
   - **`pypi`** -- one required reviewer (`Anselmoo`), plus a deployment
     protection rule restricting it to tags matching `v*`. A tag push
     reaches PyPI only after that reviewer approves the `pypi` environment's
     deployment.
2. **Pending trusted publishers on TestPyPI and PyPI**, one each, configured
   with:
   - PyPI/TestPyPI project name: `spectrafit-core`
   - Owner: `Anselmoo`
   - Repository: `SpectraFit-Core`
   - Workflow: `release.yml`
   - Environment: `testpypi` (for the TestPyPI publisher) / `pypi` (for the
     PyPI publisher)

   OIDC trusted publishing needs no stored token on either side -- each
   publisher checks the workflow's `id-token: write` permission against the
   repo, workflow and environment above, not a secret.
3. **Enable Zenodo's GitHub integration** before the first *final* tag: sign
   in at [zenodo.org](https://zenodo.org) with the GitHub account that owns
   the mirror, open the GitHub integration page, and flip the toggle for
   `Anselmoo/SpectraFit-Core` to on. Zenodo then watches the repository for
   new, non-prerelease GitHub Releases; nothing further needs to be done
   there. This does not need to be done before the release-candidate
   rehearsal below -- a release candidate is published as a GitHub
   prerelease, which Zenodo's integration does not archive -- but it must be
   on before the first tag meant to actually mint a DOI.

## Step 1 -- build dry run

Before touching any version number, confirm the build side of `release.yml`
works on its own: trigger it via `workflow_dispatch` (the Actions tab, or
`gh workflow run release.yml`) for a build-and-SBOM-only run -- no tag, no
upload. This exercises the `build` and `sbom/attest` jobs (see [job
graph](#job-graph) below) without moving any version target or publishing
anywhere, and is safe to re-run as often as needed while iterating on the
workflow itself.

Most of this is already covered before you get here: the build lives in
`.github/workflows/build-wheels.yml`, which `release.yml` calls, and
`wheel-smoke.yml` runs the same build on every PR and `main` push that
touches the wheel (`crates/`, `python/spectrafit_core/`, `Cargo.*`,
`pyproject.toml`). It installs each wheel where the repository cannot help
it -- the manylinux wheels in bare `python:3.13-slim`/`python:3.14-slim`
containers, the macOS and Windows wheels in a fresh virtual environment
outside the checkout (plus a `lipo -archs` check that the universal2 wheel
carries both architectures) -- and runs the README quick start. A green
`wheel-smoke` on the commit you tag means the wheels themselves were
installed and exercised, not just a `maturin develop` build.

## Step 2 -- release-candidate rehearsal

Rehearse the full tag-to-publish path on a release candidate before cutting
the real thing:

1. **Bump the version first** with `rrt bump` to the release-candidate
   version, spelled semver-style (`X.Y.Z-rc.N`, e.g. `0.1.0-rc.1`) per the
   semver rule in [Versioning (`rrt`)](project-configuration.md#the-canonical-version-must-be-semver-parseable)
   -- one bump updates every tracked version target. The build backend
   normalises that spelling to PEP 440 in the wheel and sdist metadata
   (`0.1.0-rc.1` becomes `0.1.0rc1`), which is the version the tag must
   name.
2. Open an MR on GitLab, get it reviewed, and merge it to `main`.
3. **Wait for the GitLab -> GitHub sync** (`publish:github` in
   `.gitlab/70-publish.yml`) to land the merge commit on GitHub `main` -- see
   [GitHub mirror workflow](github-mirror-workflow.md#mechanism-1-the-anonymous-fast-forward-sync-gitlab-github).
4. **Find the commit to tag**: the commit on GitHub `main` whose message
   carries a `GitLab-Commit: <sha>` trailer equal to the GitLab merge
   commit's SHA (`git log --grep='^GitLab-Commit:' -1 github/main` to find
   it, `git log -1 --format=%B <candidate-sha>` to confirm a specific one).
5. **Only then tag it `vX.Y.ZrcN`** (e.g. `v0.1.0rc1`, the canonical PEP 440
   spelling) on GitHub at that commit, and tag the *same name* on GitLab at
   the `<sha>` from its trailer -- both remotes end up with an identical tag
   name pointing at the two mirrors' respective copies of the same content.
   Nothing mirrors tags in either direction, so both are set by hand:

   ```bash
   TAG=v0.1.0; MSG="spectrafit-core 0.1.0"
   git fetch gitlab main
   git fetch https://github.com/Anselmoo/SpectraFit-Core.git +main:refs/remotes/github/main
   GH=$(git rev-parse github/main)   # the sync commit that landed the release MR
   GL=$(git log -1 --format='%(trailers:key=GitLab-Commit,valueonly,separator=)' "$GH")
   git rev-parse "$GL" && git merge-base --is-ancestor "$GL" gitlab/main   # the trailer names a GitLab main commit

   # GitHub: annotated tag with the anonymous bot as tagger, pushed with the deploy key
   git -c user.name="spectrafit-core-sync[bot]" \
       -c user.email="334580965+spectrafit-core-sync[bot]@users.noreply.github.com" \
       tag -a "$TAG-github" -m "$MSG" "$GH"
   GIT_SSH_COMMAND="ssh -i ~/.ssh/spectrafit_gitlab_sync -o IdentitiesOnly=yes" \
       git push git@github.com:Anselmoo/SpectraFit-Core.git "refs/tags/$TAG-github:refs/tags/$TAG"
   git tag -d "$TAG-github"

   # GitLab: the same tag name and message on the trailer SHA
   git tag -a "$TAG" -m "$MSG" "$GL"
   git push gitlab "refs/tags/$TAG"
   ```

   The GitHub tag carries the bot as tagger because every commit on the
   mirror is anonymous; a tag with a personal tagger would be the one place
   a name and e-mail appear. The local `-github` helper name only keeps the
   two annotated tags apart in one clone.

The order matters, and `release.yml` enforces it: its `version-guard` job
reads the version out of every built wheel's `METADATA` and the sdist's
`PKG-INFO` (never the file names) and fails the run unless all of them equal
the tag without its leading `v`. A tag pushed before the bump -- or spelled
`v0.1.0-rc.1` instead of `v0.1.0rc1` -- therefore stops the run before any
upload job starts; nothing reaches TestPyPI, PyPI or a GitHub Release.

Pushing the GitHub tag runs `release.yml`. For a release-candidate tag,
expect:

- `build` and `sbom` run, same as the dry run; `version-guard` confirms
  every artifact carries the tagged version and reports it as a
  pre-release; `attest` follows it.
- `publish-testpypi` uploads to TestPyPI through the `testpypi`
  environment's trusted publisher -- no reviewer gate.
- `verify-testpypi` installs the just-published package from TestPyPI on
  Linux, macOS and Windows and smoke-tests it on all three.
- `publish-pypi` does **not** run -- a release-candidate tag never reaches
  the `pypi` environment.
- `github-release` runs right after `verify-testpypi` passes, and creates
  the GitHub Release as a **prerelease**. A prerelease is not what Zenodo's
  integration archives, which is deliberate: a release candidate never mints
  a DOI.

If any of that doesn't hold -- a PyPI upload from an rc tag, a non-prerelease
GitHub Release, a `verify-testpypi` that didn't actually exercise the
TestPyPI upload on all three OSes -- stop and fix `release.yml` before
attempting a final release.

## Step 3 -- final release

Once the rehearsal above is clean, cut the real release:

1. **Bump the version** with `rrt bump` to the final version `X.Y.Z` (no
   pre-release suffix).
2. **Set `date-released` in `CITATION.cff`** (and `datePublished` in
   `codemeta.json`) to the day the tag will be cut, and promote the changelog
   to `[X.Y.Z] - <that day>`. If the tag slips to a later day, move all three
   dates before tagging: a harvested citation must not claim a release date
   the tag doesn't have.
3. **Regenerate the FAIR bundle and checksums**, since `datePublished` in the
   bundle reads `CITATION.cff`'s `date-released`:

   ```bash
   uv run poe fair bundle
   uv run --no-sync python scripts/fair.py checksums
   ```

4. **Run the `rrt` release flow** (`rrt_release_check` / `rrt_doctor` via the
   `rrt` MCP tools, or the equivalent CLI) to confirm every version target --
   `pyproject.toml`, `Cargo.toml`, `CITATION.cff`, `codemeta.json`,
   `web/package.json`, the five status strings -- agrees, and that
   `date-released` and the regenerated FAIR bundle are consistent, before
   the tag is cut.
5. Open the MR, merge, wait for the sync, find the sync commit and tag it --
   the same mechanism as [step 2](#step-2-release-candidate-rehearsal) above,
   this time tagging `vX.Y.Z` (no `rc` suffix) on both GitHub and GitLab at
   their matching commits.

Pushing the final tag runs `release.yml` again:

- `build` and `sbom/attest` run.
- `publish-testpypi` and `verify-testpypi` run exactly as in the rehearsal.
- `publish-pypi` then waits on the `pypi` environment's deployment approval
  -- the required reviewer (`Anselmoo`) approves it from the workflow run's
  *Review deployments* prompt, and the environment's `v*` tag protection
  rule from the prerequisites is re-checked at the same time.
- `github-release` runs after `publish-pypi`, creating a normal
  (non-prerelease) GitHub Release.
- **Zenodo's GitHub integration observes the new Release and mints a DOI**
  automatically -- no manual upload, and only because the integration was
  enabled ahead of time in the prerequisites above.

What the v0.1.0 run showed, so a slow step isn't mistaken for a broken one:

- **`verify-testpypi` can lose the race against TestPyPI's index.** Four of
  the six jobs gave up after their eight retries (under three minutes) with
  `from versions: 0.1.0rc1` although the upload had succeeded. Nothing was
  published past TestPyPI (`publish-pypi` needs every verify job). Check
  that the log shows only that message, then re-run the failed jobs
  (`gh run rerun <run-id> --failed`); the upload is not repeated.
- **The `pypi` approval has to be confirmed in the dialog.** Until
  *Approve and deploy* is clicked the run stays `waiting`;
  `gh api repos/Anselmoo/SpectraFit-Core/actions/runs/<run-id>/pending_deployments`
  shows whether an approval is still open.
- **Zenodo can take close to an hour.** Its GitHub page listed the release
  as *Received* for about 45 minutes before the record appeared. *Received*
  is a queue, not an error -- a failed import is listed as *Failed* with an
  *Errors* tab. Do not re-tag, edit the release or press *Create release*
  while it waits; each risks a second record.
- **The DOI resolves later than the record exists.** `doi.org` answers 404
  until Zenodo has registered the DOI with DataCite; the record page and the
  badge work before that.

## After the DOI is minted

1. Zenodo assigns both a **version DOI** (this release) and a **concept
   DOI** (resolves to the latest version, stable across future releases).
   Copy the concept DOI.
2. Add it to `CITATION.cff` under `identifiers`:

   ```yaml
   identifiers:
     - type: doi
       value: "10.5281/zenodo.XXXXXXX"
       description: "Concept DOI: always resolves to the latest archived version."
   ```

3. Add the same identifier to `codemeta.json` as its JSON-LD `@id`
   (`"@id": "https://doi.org/10.5281/zenodo.XXXXXXX"`), alongside the
   existing `identifier` key used for the software name slug -- do not
   overwrite that one.
4. Add a DOI badge to `README.md`, next to the existing status/license/python
   badges:

   ```markdown
   [![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)
   ```

   These three edits can go either way: as a GitLab MR, which the sync
   carries to GitHub, or as a GitHub PR squash-merged into `main`, which
   `backport:github` carries to GitLab; see [GitHub mirror
   workflow](github-mirror-workflow.md). The version bump itself stays a
   GitLab MR -- `rrt bump` also rewrites lockfiles and the FAIR bundle.

This is a one-time step. SpectraFit-Core's concept DOI is
[`10.5281/zenodo.23043544`](https://doi.org/10.5281/zenodo.23043544), minted
with v0.1.0 (version DOI `10.5281/zenodo.23043545`). Later releases only
add version DOIs under it, so the three places above keep the concept DOI;
`tests/meta/test_citation_metadata_consistency.py` fails if they disagree.

The GitHub repository `Anselmoo/SpectraFit-Core` is never deleted and
re-created again: the Zenodo webhook, the PyPI and TestPyPI trusted
publishers and the DOI record are all bound to it. A restart of the mirror's
history only ever goes through `publish:github:reset` (see
[GitHub mirror workflow](github-mirror-workflow.md)).

## Job graph

`release.yml`'s jobs run in this order:

```text
build -> version-guard -> sbom/attest -> publish-testpypi -> verify-testpypi -> publish-pypi -> github-release
```

- **`build`** -- builds the release wheels and sdist.
- **`version-guard`** -- tag runs only. Reads the version from every
  artifact's metadata and fails unless all equal the tag without its `v`;
  exports `version` and `is_prerelease` (from
  `packaging.version.Version(...).is_prerelease`). Every upload job --
  `attest`, `publish-testpypi`, `publish-pypi`, `github-release` -- depends
  on it, and the pre-release decision below comes from its output, not from
  the tag's spelling.
- **`sbom/attest`** -- generates the SBOM and build attestations for the
  artifacts `build` produced.
- **`publish-testpypi`** -- uploads to TestPyPI via the `testpypi`
  environment's trusted publisher.
- **`verify-testpypi`** -- installs the just-published package from
  TestPyPI on Linux, macOS and Windows and smoke-tests it on each.
- **`publish-pypi`** -- uploads to PyPI via the `pypi` environment's trusted
  publisher, gated on that environment's required reviewer and its `v*` tag
  protection rule. Runs only when `version-guard` reports
  `is_prerelease == 'false'`.
- **`github-release`** -- creates the GitHub Release from the tag, with
  `prerelease` set from `version-guard`'s `is_prerelease`. On a
  **release-candidate** it runs right after `verify-testpypi` (skipping
  `publish-pypi`, which does not run for a pre-release) and marks the release
  **prerelease**; on a **final** tag it runs after `publish-pypi` and
  creates a normal release, which is what Zenodo's integration archives into
  a DOI.
