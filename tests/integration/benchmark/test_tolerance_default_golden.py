"""``--tolerance-mode default`` is bit-identical to the benchmark before the modes existed.

The golden (``fixtures/tolerance_default_golden.json``) is generated from the base code
by ``fixtures/gen_tolerance_default_golden.py``; these tests re-run the same backends and
cases through the default mode and compare every deterministic field bit for bit.

Every row is host-bound, each group for its own reason (:data:`HOST_BOUND`):
spectrafit's Rust core uses faer, which selects CPU-specific SIMD kernels at runtime;
jax compiles each fit with XLA for the host ISA; and lmfit and the scipy
``least_squares`` backends run through OpenBLAS and NumPy, which select CPU-specific
BLAS/SIMD kernels at runtime. The rows are compared only on a host whose CPU
fingerprint matches the one recorded in the golden, where every row is asserted bit for
bit; elsewhere their test items are skipped with the reason. The backend set and the
partition of the backends into groups do not depend on numerics and are checked on
every host.

The CPU-independent guarantee is the adapter-level one: in the default mode each
adapter makes exactly the library call of the base code (``tests/unit/benchmark/
test_tolerance_mode.py``), and ``test_tolerance_default_base_call.py`` compares the
default-mode outcomes with that literal base call on the running host.
"""

from __future__ import annotations

import functools
import importlib.metadata as md
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from oracles.backends import get_backends
from oracles.cases import build_catalog

# The golden records a jax row and the jax/optimistix versions, so the file needs the
# optional ``jax`` extra; without it ``get_backends()`` drops the jax backend. Skip
# like the other jax tests (CI ``test-matrix`` deliberately installs without jax).
pytest.importorskip("jax", reason="the tolerance golden needs the optional jax extra")
pytest.importorskip("optimistix", reason="the tolerance golden needs the optional jax extra")

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = FIXTURES / "tolerance_default_golden.json"
BASE_COMMIT = "34cf94d63ecb2f2057291a71aabd5c4d54d42e76"
CALLS = ("explicit_default", "no_argument")
HOST_BOUND: dict[str, tuple[frozenset[str], str]] = {
    "jax": (frozenset({"jax"}), "XLA compiles for the host ISA"),
    "openblas": (
        frozenset({"lmfit", "scipy-ls-dogbox", "scipy-ls-lm", "scipy-ls-trf"}),
        "OpenBLAS and NumPy select CPU-specific BLAS/SIMD kernels at runtime",
    ),
    "spectrafit": (
        frozenset({"spectrafit"}),
        "faer selects CPU-specific SIMD kernels at runtime",
    ),
}
"""Host-bound backend groups: group id -> (backend names, why the rows are host-bound)."""
ALL_BOUND: frozenset[str] = frozenset().union(*(names for names, _ in HOST_BOUND.values()))
"""Every backend of the golden; each is in exactly one host-bound group."""

pytestmark = pytest.mark.skipif(
    not GOLDEN.exists(),
    reason="golden not generated yet: run fixtures/gen_tolerance_default_golden.py against the base commit",
)


@functools.cache
def _generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "gen_golden",
        FIXTURES / "gen_tolerance_default_golden.py",
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _golden() -> dict[str, Any]:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def _backends(call: str) -> list[Any]:
    return get_backends(tolerance_mode="default") if call == "explicit_default" else get_backends()


def _cases(golden: dict[str, Any]) -> dict[str, Any]:
    return {c.id: c for c in build_catalog() if c.id in golden["cases"]}


def _assert_rows(
    golden: dict[str, Any],
    got: dict[str, Any],
    names: set[str] | frozenset[str],
) -> None:
    """Every golden row of the backends in ``names`` equals ``got`` bit for bit."""
    for backend in sorted(names):
        for cid, want in golden["outcomes"][backend].items():
            assert got[backend][cid] == want, f"{backend} {cid}"


def _skip_unless_golden_host(golden: dict[str, Any], group: str) -> None:
    """Skip the calling test unless this host's CPU fingerprint is the golden's."""
    names, why = HOST_BOUND[group]
    here = _generator().host_fingerprint()
    if here != golden["host"]:
        pytest.skip(
            f"{', '.join(sorted(names))} rows are host-bound: {why}; "
            f"golden recorded on {golden['host']}, this host {here}",
        )


def test_golden_comes_from_the_base_code() -> None:
    golden = _golden()
    assert golden["oracles_commit"] == BASE_COMMIT
    for pkg, version in golden["versions"].items():
        assert md.version(pkg) == version, f"{pkg}: golden made with {version}"
    assert set(golden["host"]) == set(_generator().host_fingerprint())


def test_every_golden_backend_is_in_exactly_one_host_bound_group() -> None:
    """Runs on every host: the partition does not depend on numerics."""
    groups = [names for names, _ in HOST_BOUND.values()]
    assert sum(len(g) for g in groups) == len(ALL_BOUND), "groups overlap"
    assert set(_golden()["outcomes"]) == ALL_BOUND


@pytest.mark.parametrize("call", CALLS)
def test_default_mode_runs_exactly_the_golden_backends(call: str) -> None:
    """Runs on every host: the default roster is the golden's backend set."""
    assert {b.name for b in _backends(call)} == set(_golden()["outcomes"])


@pytest.mark.parametrize("group", sorted(HOST_BOUND))
@pytest.mark.parametrize("call", CALLS)
def test_default_mode_host_bound_rows_are_bit_identical_on_the_golden_host(
    call: str,
    group: str,
) -> None:
    """The rows of one host-bound group, only on a host with the golden's CPU fingerprint."""
    golden = _golden()
    _skip_unless_golden_host(golden, group)
    names, _ = HOST_BOUND[group]
    bound = [b for b in _backends(call) if b.name in names]
    assert {b.name for b in bound} == names
    got = _generator().run_golden(bound, _cases(golden))
    _assert_rows(golden, got, names)


_FOREIGN = {"cpu_model": "other host", "avx2": True, "avx512f": True, "fma": True}
_NEXT_ULP = "0x1.0000000000001p+0"


def _synthetic_golden() -> dict[str, Any]:
    row = {"supported": True, "chi2": "0x1.0p+0"}
    names = ALL_BOUND
    return {
        "host": {"cpu_model": "recording host", "avx2": True, "avx512f": False, "fma": True},
        "outcomes": {name: {"CX-001": dict(row)} for name in sorted(names)},
    }


@pytest.mark.parametrize(
    ("group", "want"),
    [
        (
            "jax",
            "jax rows are host-bound: XLA compiles for the host ISA; golden recorded on ",
        ),
        (
            "openblas",
            (
                "lmfit, scipy-ls-dogbox, scipy-ls-lm, scipy-ls-trf rows are host-bound: "
                "OpenBLAS and NumPy select CPU-specific BLAS/SIMD kernels at runtime; "
                "golden recorded on "
            ),
        ),
        (
            "spectrafit",
            (
                "spectrafit rows are host-bound: faer selects CPU-specific SIMD kernels "
                "at runtime; golden recorded on "
            ),
        ),
    ],
    ids=["jax", "openblas", "spectrafit"],
)
def test_on_a_foreign_host_each_host_bound_group_skips_with_its_reason(
    monkeypatch: pytest.MonkeyPatch,
    group: str,
    want: str,
) -> None:
    golden = _synthetic_golden()
    monkeypatch.setattr(_generator(), "host_fingerprint", lambda: dict(_FOREIGN))

    with pytest.raises(pytest.skip.Exception) as skipped:
        _skip_unless_golden_host(golden, group)
    reason = str(skipped.value)
    assert reason.startswith(want)
    assert f"golden recorded on {golden['host']}, this host {_FOREIGN}" in reason


@pytest.mark.parametrize("backend", sorted(ALL_BOUND))
def test_on_the_golden_host_every_row_is_compared(
    monkeypatch: pytest.MonkeyPatch,
    backend: str,
) -> None:
    golden = _synthetic_golden()
    monkeypatch.setattr(_generator(), "host_fingerprint", lambda: dict(golden["host"]))

    for group in HOST_BOUND:
        _skip_unless_golden_host(golden, group)  # no group skips
    got = json.loads(json.dumps(golden["outcomes"]))
    _assert_rows(golden, got, ALL_BOUND)
    got[backend]["CX-001"]["chi2"] = _NEXT_ULP
    with pytest.raises(AssertionError, match=f"{backend} CX-001"):
        _assert_rows(golden, got, ALL_BOUND)


def test_host_fingerprint_reads_model_and_exact_flags(tmp_path: Path) -> None:
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text(
        "processor\t: 0\nmodel name\t: Test CPU\nflags\t\t: sse2 avx2 fma4 avx512fp16\n"
        "processor\t: 1\nmodel name\t: Other CPU\nflags\t\t: fma avx512f\n",
        encoding="utf-8",
    )
    gen = _generator()
    assert gen.host_fingerprint(cpuinfo) == {
        "cpu_model": "Test CPU",
        "avx2": True,
        "avx512f": False,
        "fma": False,
    }
    assert gen.host_fingerprint(tmp_path / "missing") == {
        "cpu_model": None,
        "avx2": False,
        "avx512f": False,
        "fma": False,
    }
