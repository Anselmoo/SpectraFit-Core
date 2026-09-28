# Branch protection — `main`

Required status checks (all must pass before merge):

| Check | Source job |
|-------|-----------|
| `lint` | `.github/workflows/ci.yml` → `lint` (clippy + blocking ty) |
| `build-and-test` | `ci.yml` → `build-and-test` |
| `web` | `ci.yml` → `web` |
| `regression-gate` | `ci.yml` → `regression-gate` |
| `citation` | `ci.yml` → `citation` |

> **Sequencing — read before applying.** A required status check that has
> never reported is treated as *pending* and blocks **every** merge. Land
> each job and let it run green on at least one pipeline **before** marking
> it required; otherwise you lock the branch against yourself.

Apply (requires repo-admin; run once):

```bash
gh api -X PUT repos/Anselmoo/SpectraFit-Core/branches/main/protection \
  -H "Accept: application/vnd.github+json" \
  -f "required_status_checks[strict]=true" \
  -f "required_status_checks[checks][][context]=lint" \
  -f "required_status_checks[checks][][context]=build-and-test" \
  -f "required_status_checks[checks][][context]=web" \
  -f "required_status_checks[checks][][context]=regression-gate" \
  -f "required_status_checks[checks][][context]=citation" \
  -F "enforce_admins=false" \
  -F "required_pull_request_reviews=null" \
  -F "restrictions=null"
```

Verify:

```bash
gh api repos/Anselmoo/SpectraFit-Core/branches/main/protection/required_status_checks \
  | jq '.checks[].context'
```
