#!/usr/bin/env bash
set -euo pipefail
# Install a release-candidate wheel from this project's PyPI package registry
# into a fresh venv and run the smoke tests against it (#93). Run by the manual
# CI job `rc-wheel:install-smoke` (.gitlab/72-rc-wheel.yml) from the repository
# root, after `rc-wheel:publish` in the same pipeline.
#
# Steps: validate RC_VERSION and match it against the publish job's manifest ->
# fresh venv outside the checkout -> runtime and test dependencies from the
# default index at their uv.lock versions -> spectrafit-core==RC_VERSION from the
# registry with --no-deps, pinned to the manifest's sha256 (pip hash-checking mode)
# -> `pip check` (the wheel's own requirements are satisfied) -> assert the import
# resolves to the venv's site-packages, not the checkout's python/, and reports
# RC_VERSION -> pytest tests/scenario/test_smoke.py (`poe scenario_smoke`'s target)
# and tests/regression/test_lm_success_implies_stationary.py (EELS cross-check
# starts) with the venv's interpreter.
#
# Dependencies come from the default index first and the registry install uses
# --no-deps, so nothing depends on the registry forwarding unknown names to
# pypi.org. `poe scenario_smoke` itself is not used: it is `uv run pytest`, which
# would sync and build the checkout from source.
#
# Inputs (environment):
#   RC_VERSION     the version rc-wheel:publish uploaded (same regex as there).
#   CI_API_V4_URL, CI_PROJECT_ID, CI_JOB_TOKEN   GitLab predefined; the job token
#                  reaches pip through a netrc file, never through a URL.
#   RC_WHEEL_OUT   directory holding rc-wheel.json, default rc-wheel.
#   RC_SMOKE_OUT   output directory, default rc-wheel-smoke.
#   PYTHON         interpreter for the venv, default python3.
# Outputs: $RC_SMOKE_OUT/pip-install-report.json, import.json, junit-*.xml.
# Exit codes: 0 all checks passed; 1 otherwise.

readonly RC_VERSION_RE='^[0-9]+\.[0-9]+\.[0-9]+(a|b|rc)[0-9]+$'
readonly DIST_NAME=spectrafit-core
readonly PREINSTALL=(numpy pydantic pytest lmfit pyyaml)
MANIFEST=${RC_WHEEL_OUT:-rc-wheel}/rc-wheel.json
OUT_DIR=${RC_SMOKE_OUT:-rc-wheel-smoke}

die() {
  echo "ERROR rc_wheel_install_smoke: $*" >&2
  exit 1
}

# RC_VERSION must be a pre-release and equal the version rc-wheel:publish built.
validate_version() {
  [[ "${RC_VERSION:-}" =~ $RC_VERSION_RE ]] ||
    die "RC_VERSION='${RC_VERSION:-}' is not a pre-release matching $RC_VERSION_RE"
  [[ -f "$MANIFEST" ]] || die "$MANIFEST missing: rc-wheel:publish did not emit it"
  local built
  built=$(manifest_field version)
  [[ "$built" == "$RC_VERSION" ]] || die "RC_VERSION=$RC_VERSION but rc-wheel:publish built $built"
}

manifest_field() {
  python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$MANIFEST" "$1"
}

# Print "name==version" for each name from uv.lock, so test dependencies match
# the versions the repository's own test runs use.
locked_requirements() {
  python3 - "$@" <<'PY'
import sys, tomllib
with open("uv.lock", "rb") as fh:
    locked = {p["name"]: p["version"] for p in tomllib.load(fh)["package"]}
for name in sys.argv[1:]:
    print(f"{name}=={locked[name]}")
PY
}

# netrc for the registry host (port stripped, as netrc matches host names).
write_netrc() {
  local host=${CI_API_V4_URL#*://}
  host=${host%%/*}
  host=${host%%:*}
  NETRC=$(mktemp)
  trap 'rm -f "$NETRC"' EXIT
  chmod 600 "$NETRC"
  printf 'machine %s login gitlab-ci-token password %s\n' "$host" "$CI_JOB_TOKEN" >"$NETRC"
  export NETRC
}

install() {
  local venv_dir requirements index
  venv_dir=$(mktemp -d)
  "${PYTHON:-python3}" -m venv "$venv_dir/venv"
  VENV_PY="$venv_dir/venv/bin/python"
  "$VENV_PY" -m pip install --quiet --upgrade pip
  mapfile -t requirements < <(locked_requirements "${PREINSTALL[@]}")
  "$VENV_PY" -m pip install --quiet "${requirements[@]}"
  printf '%s==%s --hash=sha256:%s\n' "$DIST_NAME" "$RC_VERSION" "$(manifest_field sha256)" \
    >"$OUT_DIR/rc-requirement.txt"
  index="$CI_API_V4_URL/projects/$CI_PROJECT_ID/packages/pypi/simple"
  write_netrc
  "$VENV_PY" -m pip install --disable-pip-version-check --no-cache-dir --no-deps \
    --index-url "$index" \
    --require-hashes --report "$OUT_DIR/pip-install-report.json" \
    --requirement "$OUT_DIR/rc-requirement.txt"
  rm -f "$NETRC"
  "$VENV_PY" -m pip check
}

# Same interpreter and working directory as the pytest runs below.
assert_installed_import() {
  "$VENV_PY" - "$RC_VERSION" "$PWD" "$OUT_DIR/import.json" <<'PY'
import json, sys, sysconfig
from importlib import metadata
from pathlib import Path

import spectrafit_core
from spectrafit_core import _core

expected, checkout, out = sys.argv[1], Path(sys.argv[2]).resolve(), sys.argv[3]
site = {Path(sysconfig.get_path(k)).resolve() for k in ("purelib", "platlib")}
dist = metadata.distribution("spectrafit-core")
info = {
    "spectrafit_core": str(Path(spectrafit_core.__file__).resolve()),
    "_core": str(Path(_core.__file__).resolve()),
    "version": dist.version,
    "__version__": spectrafit_core.__version__,
    "direct_url_json": dist.read_text("direct_url.json"),
    "site_packages": sorted(str(s) for s in site),
}
print(json.dumps(info, indent=2))
Path(out).write_text(json.dumps(info, indent=2) + "\n")
errors = [
    f"{key} at {info[key]} is not under site-packages"
    for key in ("spectrafit_core", "_core")
    if not any(Path(info[key]).is_relative_to(s) for s in site)
    or Path(info[key]).is_relative_to(checkout)
]
if info["version"] != expected or info["__version__"] != expected:
    errors.append(f"installed version {info['version']}/{info['__version__']} != {expected}")
if info["direct_url_json"] is not None:
    errors.append("installed from a direct URL or editable, not from the index")
sys.exit("\n".join(errors) or None)
PY
}

run_tests() {
  "$VENV_PY" -m pytest -p no:cacheprovider -v tests/scenario/test_smoke.py \
    --junitxml="$OUT_DIR/junit-scenario-smoke.xml"
  "$VENV_PY" -m pytest -p no:cacheprovider -v \
    tests/regression/test_lm_success_implies_stationary.py \
    --junitxml="$OUT_DIR/junit-eels-regression.xml"
}

main() {
  validate_version
  : "${CI_API_V4_URL:?}" "${CI_PROJECT_ID:?}" "${CI_JOB_TOKEN:?}"
  [[ -z "${PYTHONPATH:-}" ]] || die "PYTHONPATH is set ($PYTHONPATH); the import check needs it empty"
  rm -rf "$OUT_DIR"
  mkdir -p "$OUT_DIR"
  install
  assert_installed_import
  run_tests
  echo "$DIST_NAME $RC_VERSION from the registry: install, import and smoke tests passed"
}

main "$@"
