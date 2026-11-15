"""``nist_table2.py --start START2`` writes exactly what the script wrote before ``--start``.

The golden (``fixtures/nist_table2_start2_golden.json``) is the output of the base
script, generated once with the installed build:

    git worktree add <base> <base commit>
    python <base>/reproducibility/figures/nist_table2.py \
        --out tests/integration/reproducibility/fixtures/nist_table2_start2_golden.json

It is never written by hand. The last significant figures of an ill-conditioned fit
depend on the host (see ``_host`` in ``nist_table2.py``), so the byte comparison runs
only where the golden was made: same host record and same package versions.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "reproducibility" / "figures" / "nist_table2.py"
GOLDEN = Path(__file__).parent / "fixtures" / "nist_table2_start2_golden.json"

pytestmark = pytest.mark.skipif(
    not GOLDEN.exists(),
    reason="golden not generated yet: run the base commit's nist_table2.py with --out <golden>",
)


@pytest.mark.parametrize("argv", [["--start", "START2"], []], ids=["explicit", "default"])
def test_start2_output_is_byte_identical_to_the_base_script(
    tmp_path: Path,
    argv: list[str],
) -> None:
    out = tmp_path / "nist_table2.json"
    subprocess.run(
        [sys.executable, str(SCRIPT), *argv, "--out", str(out)],
        check=True,
        cwd=SCRIPT.parent,
        capture_output=True,
    )
    golden_bytes = GOLDEN.read_bytes()
    got, want = json.loads(out.read_text()), json.loads(golden_bytes)
    if (got["host"], got["versions"]) != (want["host"], want["versions"]):
        pytest.skip("the golden was recorded on another host or build; bytes are host-specific")
    assert out.read_bytes() == golden_bytes
