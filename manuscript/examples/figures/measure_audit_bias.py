"""Re-derive the two numbers the Validation section reports for the audit finding.

The manuscript states, in the paragraph whose whole function is to show that
this project reports its own biases, that routing the reference implementations'
model evaluation through the compiled kernel charged every competitor a
serialisation cost -- and it quotes a per-evaluation figure and a kernel-parity
spread. Those numbers were measured but not committed, which made them
unreproducible from this repository: exactly the defect the paper faults
elsewhere. This script re-derives both, so the figures in the text can be
checked rather than taken on trust.

Run:  uv run python manuscript/examples/figures/measure_audit_bias.py
"""

from __future__ import annotations

import json
import sys
import timeit
from pathlib import Path

import numpy as np
from oracles.models import MODEL_REGISTRY, _wheel_eval, get_model

# The parity test already fixes a grid and a parameter set per kernel; reusing
# them keeps this measurement and that assertion describing the same thing.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tests" / "parity"))
from test_kernel_parity import _X, _params_for

OUT = Path(__file__).with_name("audit_bias.json")


def _bias() -> dict[str, float]:
    """Time one residual evaluation on each path: pure numpy vs wheel round-trip."""
    key = "gaussian"
    model = get_model(key)
    params = _params_for(key)

    # min over repeated batches, not a single mean. A mean over one batch is
    # contaminated by whatever else the scheduler did during it: single-batch
    # runs of this function moved 75-96 us and swung the ratio between 17x and
    # 29x, which is useless for a figure the manuscript invites a reader to
    # reproduce. The minimum is the least noisy estimate of the underlying cost.
    n, n_w, repeat = 2000, 200, 7
    t_np = min(timeit.repeat(lambda: model.one(_X, params), number=n, repeat=repeat)) / n
    t_wh = (
        min(
            timeit.repeat(lambda: _wheel_eval(key, _X, params), number=n_w, repeat=repeat),
        )
        / n_w
    )
    return {
        "numpy_us": t_np * 1e6,
        "wheel_us": t_wh * 1e6,
        "ratio": t_wh / t_np,
        "n_points": int(_X.size),
    }


def _parity() -> dict[str, object]:
    """Measure, rather than merely assert, how closely each kernel pair agrees."""
    devs: dict[str, float] = {}
    for key in sorted(MODEL_REGISTRY):
        model = get_model(key)
        params = _params_for(key)
        try:
            got = np.asarray(_wheel_eval(key, _X, params), dtype=float)
        except (RuntimeError, ValueError, KeyError) as exc:
            # Not reachable through the wheel path. Named rather than swallowed:
            # a silently skipped kernel would inflate the agreement fraction.
            print(f"  skipped {key}: {type(exc).__name__}: {exc}")
            continue
        want = np.asarray(model.one(_X, params), dtype=float)
        scale = max(float(np.max(np.abs(want))), 1e-300)
        devs[key] = float(np.max(np.abs(got - want)) / scale)
    exact = sorted(k for k, v in devs.items() if v == 0.0)
    rest = {k: v for k, v in devs.items() if v > 0.0}
    return {
        "n_kernels": len(devs),
        "n_exact": len(exact),
        "exact": exact,
        "worst_key": max(rest, key=rest.get) if rest else None,
        "worst_dev": max(rest.values()) if rest else 0.0,
        "deviations": devs,
    }


def main() -> None:
    """Measure both, write the JSON sidecar, and print a one-line summary."""
    result = {"bias": _bias(), "parity": _parity()}
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    b, p = result["bias"], result["parity"]
    print(f"numpy   {b['numpy_us']:8.2f} us/eval")
    print(f"wheel   {b['wheel_us']:8.2f} us/eval   ratio {b['ratio']:.0f}x")
    print(
        f"kernels {p['n_kernels']}, exact {p['n_exact']}, "
        f"worst {p['worst_key']} at {p['worst_dev']:.2e}",
    )
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
