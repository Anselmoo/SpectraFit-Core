#!/usr/bin/env python3
"""Describe a release-candidate wheel for the internal package registry (#93).

Used by ``scripts/rc_wheel_publish.sh`` (CI job ``rc-wheel:publish``) after
``maturin build`` and before the upload. Stdlib only, so it runs with the image's
``python3``.

The wheel is checked before anything is written: exactly one ``.whl`` in the
output directory, its file name and its ``METADATA`` ``Version`` both equal to the
requested release-candidate version, and its ``METADATA`` ``Name`` equal to
``spectrafit-core``. Any mismatch exits 1 without writing the manifest.

The manifest (JSON) records what package 12 needs to reproduce or audit an
install: the wheel file name and sha256, the version, the source commit and
pipeline/job ids, the wheel's Python, ABI and platform tags, the highest
``GLIBC_x.y`` symbol version the compiled extension requires (the oldest glibc it
can load on, whatever the platform tag claims), the build host's glibc, the build
interpreter, ``rustc --version`` and the ``RUSTFLAGS`` the build saw. A
``SHA256SUMS`` file next to it carries the same digest in ``sha256sum -c`` form.

The wheel file name layout is ``{dist}-{version}-{python}-{abi}-{platform}.whl``
(PyPA binary distribution format, no build tag: maturin never emits one).

Exit codes: 0 manifest written; 1 wheel missing, ambiguous or inconsistent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import zipfile
from email.parser import Parser
from pathlib import Path

DIST_NAME = "spectrafit-core"
_GLIBC_SYMBOL = re.compile(rb"GLIBC_(\d+)\.(\d+)(?:\.(\d+))?")
_CI_FIELDS = (
    "CI_COMMIT_SHA",
    "CI_COMMIT_REF_NAME",
    "CI_PIPELINE_ID",
    "CI_JOB_ID",
    "CI_PROJECT_ID",
)


class WheelCheckError(Exception):
    """The built wheel does not match the requested release candidate."""


def find_single_wheel(out_dir: Path) -> Path:
    """Return the only wheel in ``out_dir``.

    Args:
        out_dir: Directory ``maturin build --out`` wrote to.

    Returns:
        Path of the single ``*.whl`` file.

    Raises:
        WheelCheckError: No wheel, or more than one.
    """
    wheels = sorted(out_dir.glob("*.whl"))
    if len(wheels) != 1:
        msg = f"expected exactly one wheel in {out_dir}, found {[w.name for w in wheels]}"
        raise WheelCheckError(msg)
    return wheels[0]


def parse_wheel_name(wheel: Path) -> dict[str, str]:
    """Split a wheel file name into its PyPA fields.

    Args:
        wheel: Wheel path; only the file name is read.

    Returns:
        Mapping with ``dist``, ``version``, ``python_tag``, ``abi_tag`` and
        ``platform_tag``.

    Raises:
        WheelCheckError: The name does not have five dash-separated fields.
    """
    parts = wheel.name.removesuffix(".whl").split("-")
    if len(parts) != 5:
        msg = f"unexpected wheel file name layout: {wheel.name}"
        raise WheelCheckError(msg)
    dist, version, python_tag, abi_tag, platform_tag = parts
    return {
        "dist": dist,
        "version": version,
        "python_tag": python_tag,
        "abi_tag": abi_tag,
        "platform_tag": platform_tag,
    }


def read_metadata(wheel: Path) -> dict[str, str]:
    """Read ``Name`` and ``Version`` from the wheel's ``*.dist-info/METADATA``.

    Args:
        wheel: Wheel path.

    Returns:
        Mapping with ``name`` and ``version``.

    Raises:
        WheelCheckError: The wheel has no single ``METADATA`` file.
    """
    with zipfile.ZipFile(wheel) as zf:
        names = [n for n in zf.namelist() if n.endswith(".dist-info/METADATA")]
        if len(names) != 1:
            msg = f"{wheel.name}: expected one dist-info/METADATA, found {names}"
            raise WheelCheckError(msg)
        headers = Parser().parsestr(zf.read(names[0]).decode("utf-8"), headersonly=True)
    return {"name": headers.get("Name", ""), "version": headers.get("Version", "")}


def required_glibc(wheel: Path) -> str | None:
    """Highest ``GLIBC_x.y`` symbol version referenced by the wheel's extension modules.

    The dynamic loader refuses a shared object whose version-needed entries name a
    glibc newer than the host's, so this is the oldest glibc the wheel loads on.

    Args:
        wheel: Wheel path.

    Returns:
        Version string such as ``"2.34"``, or ``None`` if no ``.so`` references glibc.
    """
    best: tuple[int, ...] | None = None
    with zipfile.ZipFile(wheel) as zf:
        for name in zf.namelist():
            if ".so" not in Path(name).name:
                continue
            for match in _GLIBC_SYMBOL.finditer(zf.read(name)):
                found = tuple(int(g) for g in match.groups() if g is not None)
                if best is None or found > best:
                    best = found
    return None if best is None else ".".join(str(p) for p in best)


def sha256_of(path: Path) -> str:
    """Hex sha256 of a file.

    Args:
        path: File to hash.

    Returns:
        Lower-case hex digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rustc_version() -> str:
    """``rustc --version`` of the build host, or ``"unknown"`` if rustc is absent.

    Returns:
        The first output line.
    """
    try:
        out = subprocess.run(
            ["rustc", "--version"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out.strip()


def check_wheel(wheel: Path, version: str) -> dict[str, str]:
    """Verify name and version of the wheel against the requested release candidate.

    Args:
        wheel: Wheel path.
        version: Requested release-candidate version (PEP 440, canonical form).

    Returns:
        The parsed file-name fields.

    Raises:
        WheelCheckError: File name or METADATA disagree with ``version`` or the
            distribution name.
    """
    fields = parse_wheel_name(wheel)
    meta = read_metadata(wheel)
    problems = []
    if fields["version"] != version:
        problems.append(f"file name version {fields['version']!r} != {version!r}")
    if meta["version"] != version:
        problems.append(f"METADATA Version {meta['version']!r} != {version!r}")
    if meta["name"] != DIST_NAME:
        problems.append(f"METADATA Name {meta['name']!r} != {DIST_NAME!r}")
    if problems:
        msg = f"{wheel.name}: " + "; ".join(problems)
        raise WheelCheckError(msg)
    return fields


def build_manifest(wheel: Path, version: str, maturin_version: str) -> dict[str, object]:
    """Assemble the manifest for a checked wheel.

    Args:
        wheel: Wheel path, already passed :func:`check_wheel`.
        version: Release-candidate version.
        maturin_version: ``maturin --version`` output of the build.

    Returns:
        JSON-serialisable manifest.
    """
    fields = check_wheel(wheel, version)
    libc_name, libc_version = platform.libc_ver()
    return {
        "distribution": DIST_NAME,
        "version": version,
        "wheel": wheel.name,
        "sha256": sha256_of(wheel),
        "size_bytes": wheel.stat().st_size,
        "python_tag": fields["python_tag"],
        "abi_tag": fields["abi_tag"],
        "platform_tag": fields["platform_tag"],
        "requires_glibc": required_glibc(wheel),
        "build_libc": f"{libc_name} {libc_version}".strip(),
        "build_python": platform.python_version(),
        "rustc": rustc_version(),
        "maturin": maturin_version,
        "rustflags": os.environ.get("RUSTFLAGS", ""),
        "ci": {key.lower(): os.environ.get(key, "") for key in _CI_FIELDS},
    }


def main(argv: list[str] | None = None) -> int:
    """Check the wheel in ``--out-dir`` and write ``rc-wheel.json`` and ``SHA256SUMS``.

    Args:
        argv: Command-line arguments; ``sys.argv[1:]`` when ``None``.

    Returns:
        Process exit code: 0 written, 1 wheel check failed.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--maturin-version", default="unknown")
    args = parser.parse_args(argv)
    try:
        wheel = find_single_wheel(args.out_dir)
        manifest = build_manifest(wheel, args.version, args.maturin_version)
    except WheelCheckError as exc:
        print(f"ERROR rc_wheel_manifest: {exc}", file=sys.stderr)
        return 1
    (args.out_dir / "rc-wheel.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (args.out_dir / "SHA256SUMS").write_text(f"{manifest['sha256']}  {wheel.name}\n")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
