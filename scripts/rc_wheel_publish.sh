#!/usr/bin/env bash
set -euo pipefail
# Build a release-candidate wheel and publish it to this project's PyPI package
# registry (#93). Run by the manual CI job `rc-wheel:publish`
# (.gitlab/72-rc-wheel.yml) from the repository root.
#
# The committed version stays untouched: only this checkout's pyproject.toml
# [project].version is rewritten to RC_VERSION, which is what maturin writes into
# the wheel file name and METADATA (PEP 621 static version wins over Cargo's). The
# Cargo workspace version stays at the committed value; no crate reads
# CARGO_PKG_VERSION, and leaving it keeps Cargo.lock valid for `--locked`.
#
# Steps: validate RC_VERSION -> refuse if the registry already lists that version
# -> rewrite the version -> `maturin build --release --locked` for the runner's
# platform (no manylinux claim; maturin picks the tag) -> check the wheel and
# write the manifest (scripts/rc_wheel_manifest.py) -> `uv publish`.
#
# Duplicates fail twice over: the pre-check refuses any file of RC_VERSION already
# in the registry (any platform tag), and the upload runs without --check-url, so
# a concurrent upload that slips past the pre-check gets the registry's
# "400 Bad Request" for an existing package version and fails the job.
#
# Inputs (environment):
#   RC_VERSION     PEP 440 pre-release in canonical form, matching
#                  ^[0-9]+\.[0-9]+\.[0-9]+(a|b|rc)[0-9]+$ (e.g. 0.1.3rc1).
#   CI_API_V4_URL, CI_PROJECT_ID, CI_JOB_TOKEN   GitLab predefined; the job token
#                  authenticates as user `gitlab-ci-token`. No other credential.
#   RC_WHEEL_OUT   output directory, default rc-wheel.
#   MATURIN        maturin command, default `uv run --no-sync maturin` (the
#                  `setup` job's .venv, pinned by uv.lock).
# Outputs: $RC_WHEEL_OUT/<wheel>.whl, rc-wheel.json, SHA256SUMS.
# Exit codes: 0 published; 1 invalid version, version already in the registry,
# registry index unreadable, version rewrite failed, wheel check failed, or upload
# rejected.

readonly RC_VERSION_RE='^[0-9]+\.[0-9]+\.[0-9]+(a|b|rc)[0-9]+$'
readonly DIST_NAME=spectrafit-core
OUT_DIR=${RC_WHEEL_OUT:-rc-wheel}
read -r -a MATURIN_CMD <<<"${MATURIN:-uv run --no-sync maturin}"

die() {
  echo "ERROR rc_wheel_publish: $*" >&2
  exit 1
}

# Refuse anything that is not a canonical PEP 440 pre-release (no final versions).
validate_version() {
  [[ "${RC_VERSION:-}" =~ $RC_VERSION_RE ]] ||
    die "RC_VERSION='${RC_VERSION:-}' is not a pre-release matching $RC_VERSION_RE"
}

# Write a curl config carrying the job-token credentials, so the token never
# appears in a command line or URL. Prints the file path.
write_curl_auth() {
  local cfg
  cfg=$(mktemp)
  chmod 600 "$cfg"
  printf 'user = "gitlab-ci-token:%s"\n' "$CI_JOB_TOKEN" >"$cfg"
  echo "$cfg"
}

# Fail if the registry's simple index for the package lists any file of
# RC_VERSION. Redirects are not followed: an unknown package may be forwarded to
# pypi.org, which says nothing about this registry. 200 -> parse, 3xx/404 ->
# absent, anything else -> fail (cannot prove the version is new).
assert_version_absent() {
  local index="$CI_API_V4_URL/projects/$CI_PROJECT_ID/packages/pypi/simple/$DIST_NAME/"
  local status pattern
  auth=$(write_curl_auth)
  page=$(mktemp)
  trap 'rm -f "$auth" "$page"' EXIT
  if ! status=$(curl --silent --show-error --config "$auth" --output "$page" \
    --write-out '%{http_code}' "$index"); then
    die "registry index unreachable: $index"
  fi
  pattern="spectrafit[-_]core-${RC_VERSION//./\\.}[-.]"
  case "$status" in
    200)
      if grep -Eq "$pattern" "$page"; then
        grep -Eo "spectrafit[-_]core-${RC_VERSION//./\\.}[^\"<#]*" "$page" | sort -u >&2
        die "$DIST_NAME $RC_VERSION is already in the registry; choose a new RC_VERSION"
      fi
      ;;
    301 | 302 | 303 | 307 | 308 | 404) ;;
    *) die "registry index returned HTTP $status for $index" ;;
  esac
  echo "registry: $DIST_NAME $RC_VERSION not present (HTTP $status)"
}

# Rewrite [project].version (the first `version = "..."` line of pyproject.toml)
# in this checkout and prove exactly one line changed and tomllib reads RC_VERSION.
rewrite_version() {
  sed -i "0,/^version = \"[^\"]*\"\$/s//version = \"$RC_VERSION\"/" pyproject.toml
  [[ "$(git diff --numstat -- pyproject.toml)" == $'1\t1\tpyproject.toml' ]] ||
    die "version rewrite did not change exactly one line of pyproject.toml"
  python3 - "$RC_VERSION" <<'PY' || die "pyproject.toml [project].version is not $RC_VERSION after rewrite"
import sys, tomllib
with open("pyproject.toml", "rb") as fh:
    sys.exit(tomllib.load(fh)["project"]["version"] != sys.argv[1])
PY
  echo "pyproject.toml [project].version -> $RC_VERSION (checkout only, not committed)"
}

build_wheel() {
  rm -rf "$OUT_DIR"
  mkdir -p "$OUT_DIR"
  "${MATURIN_CMD[@]}" build --release --locked --interpreter python3 --out "$OUT_DIR"
}

write_manifest() {
  python3 scripts/rc_wheel_manifest.py --out-dir "$OUT_DIR" --version "$RC_VERSION" \
    --maturin-version "$("${MATURIN_CMD[@]}" --version)"
}

upload() {
  UV_PUBLISH_USERNAME=gitlab-ci-token UV_PUBLISH_PASSWORD="$CI_JOB_TOKEN" \
    uv publish --publish-url "$CI_API_V4_URL/projects/$CI_PROJECT_ID/packages/pypi" \
    "$OUT_DIR"/*.whl
}

main() {
  validate_version
  : "${CI_API_V4_URL:?}" "${CI_PROJECT_ID:?}" "${CI_JOB_TOKEN:?}"
  assert_version_absent
  rewrite_version
  build_wheel
  write_manifest
  upload
  echo "published $DIST_NAME $RC_VERSION: $(cat "$OUT_DIR/SHA256SUMS")"
}

main "$@"
