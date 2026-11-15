r"""Generate the mpmath reference table for the Faddeeva function used by ``true_voigt``.

Writes ``faddeeva_reference.csv`` and ``faddeeva_boundaries.csv`` next to this
script. Each row holds a point
$z$ and the 50-digit mpmath values of $w(z) = e^{-z^2}\,\mathrm{erfc}(-iz)$ and of
$w'(z) = -2 z\, w(z) + 2i/\sqrt{\pi}$, rounded once to the nearest double.

The points are:

- a subsample of the x grids of the ten benchmark cases that contain a
  ``true_voigt`` component (CX-006 to CX-010, LS-001, LS-006 to LS-009), with
  their true parameters: $z = ((x - c) + i\gamma)/(\sigma\sqrt{2})$ and
  $z_0 = i\gamma/(\sigma\sqrt{2})$;
- a broad grid over $\mathrm{Re}\,z \in [-50, 50]$, $\mathrm{Im}\,z \in [0, 50]$,
  including the real axis and $\mathrm{Im}\,z \to 0^+$;
- points on every branch of the port (imaginary axis, real axis, large $|z|$,
  $\mathrm{Im}\,z < 0$) and in every reachable Chebyshev interval of its
  ``erfcx`` and ``Im w(x)`` tables.

``faddeeva_boundaries.csv`` holds point pairs at a relative offset of
$\pm 10^{-9}$ on both sides of every branch threshold of the port (see
``boundary_pairs``), with $|w''|$ for the continuity bound.

Run from the repository root (the case grids come from ``oracles.cases``):

    uv run --with mpmath python crates/spectrafit-models/tests/data/gen_faddeeva_reference.py
"""

from __future__ import annotations

from pathlib import Path

import mpmath as mp
import numpy as np
from oracles.cases import build_catalog

CASE_IDS = (
    "CX-006",
    "CX-007",
    "CX-008",
    "CX-009",
    "CX-010",
    "LS-001",
    "LS-006",
    "LS-007",
    "LS-008",
    "LS-009",
)
POINTS_PER_COMPONENT = 25
OUT = Path(__file__).with_name("faddeeva_reference.csv")
OUT_BOUNDARIES = Path(__file__).with_name("faddeeva_boundaries.csv")
# Relative offset of the two points of a boundary pair from the switch line.
BOUNDARY_OFFSET = 1e-9


def case_points() -> list[complex]:
    """Subsampled benchmark-case points plus $z_0$ for every component."""
    points: list[complex] = []
    for case in build_catalog():
        if case.id not in CASE_IDS:
            continue
        spec = case.spec
        x = np.linspace(spec.x_min, spec.x_max, spec.n_points)
        step = max(1, len(x) // POINTS_PER_COMPONENT)
        for comp in spec.components:
            if comp.model != "true_voigt":
                continue
            s2 = comp.sigma * np.sqrt(2.0)
            points += [complex(z) for z in ((x[::step] - comp.center) + 1j * comp.gamma) / s2]
            points.append(complex(0.0, comp.gamma / s2))
    return points


def broad_points() -> list[complex]:
    """Coarse broad grid; the real axis only where $e^{-x^2}$ is a normal double."""
    re_pos = [
        1e-6,
        1e-3,
        0.1,
        0.5,
        1.0,
        2.0,
        3.5,
        5.5,
        6.0,
        6.5,
        8.0,
        9.9,
        10.0,
        12.0,
        20.0,
        27.9,
        28.1,
        40.0,
        50.0,
    ]
    im = [1e-6, 1e-3, 0.05, 0.1, 0.5, 1.0, 3.0, 5.0, 5.5, 6.9, 7.1, 15.0, 50.0]
    res = [0.0] + re_pos + [-r for r in re_pos]
    points = [complex(r, i) for r in res for i in im]
    points += [complex(r, 0.0) for r in res if r != 0.0 and abs(r) <= 26.0]
    return points


def branch_points() -> list[complex]:
    """Points on the remaining branches of the port."""
    return [
        # 10 <= |x| <= 28 with |y| <= 1e-10: the two-sided Algorithm 916 sum
        *(complex(s * r, i) for s in (1, -1) for r in (10.5, 15.0, 27.5) for i in (1e-12, 1e-11)),
        # |x| < 5e-4 Taylor branch
        complex(1e-5, 0.3),
        complex(-4e-4, 2.0),
        # real axis: Taylor (|x| < 0.0101), Chebyshev table, continued fractions
        *(complex(s * r, 0.0) for s in (1, -1) for r in (1e-8, 0.005, 0.0101, 0.0102, 0.7, 25.0)),
        complex(46.0, 0.0),
        complex(-1e8, 0.0),
        # imaginary axis: erfcx table, continued fractions, negative arguments
        *(complex(0.0, i) for i in (1e-9, 0.3, 30.0, 51.0, 6e7, -0.2, -3.0, -6.5)),
        # general continued fraction at large |z| (|x| + |y| <= 4000)
        complex(100.0, 100.0),
        complex(1000.0, 500.0),
        complex(-2500.0, 1000.0),
        complex(3500.0, 400.0),
        complex(1.0, 3000.0),
        # large |z|: nu == 2 and nu == 1 continued fractions
        complex(3000.0, 2000.0),
        complex(-5000.0, 1.0),
        complex(2e7, 1.0),
        complex(1.0, 2e7),
        # Im z < 0 (reflection w(z) = 2 exp(-z^2) - w(-z))
        complex(0.7, -0.5),
        complex(-2.0, -3.0),
        complex(7.0, -0.3),
        complex(-1.0, -6.5),
        complex(3.0, -8.0),
    ]


def interval_points() -> list[complex]:
    r"""One point near the edge of every reachable Chebyshev interval of the port.

    ``erfcx`` uses interval $k$ of $y = 4/(4+x)$ for $0 \le x \le 50$ ($k \ge 7$),
    reached through $w(iy) = \mathrm{erfcx}(y)$; ``w_im`` uses interval $k$ of
    $y = 1/(1+x)$ for $0 \le x \le 45$ ($k \ge 2$), reached on the real axis.
    """
    # Interval k is evaluated in t = 2(100 y) - (2k + 1) in [-1, 1]. The points sit
    # at t = 0.95, not at the midpoint t = 0 where only the constant
    # coefficient would be exercised.
    erfcx_args = [400.0 / (k + 0.975) - 4.0 for k in range(7, 100)]
    w_im_args = [100.0 / (k + 0.975) - 1.0 for k in range(2, 99)]
    return [complex(0.0, y) for y in erfcx_args] + [complex(x, 0.0) for x in w_im_args]


def _across(value: float) -> tuple[float, float]:
    r"""The two sides of a switch at ``value``: relative offset $\pm 10^{-9}$."""
    return value * (1.0 - BOUNDARY_OFFSET), value * (1.0 + BOUNDARY_OFFSET)


def _re_pairs(label: str, x0: float, ims: list[float]) -> list[tuple[str, complex, complex]]:
    r"""Pairs across the vertical line $\mathrm{Re}\,z = x_0$, one per ray $\mathrm{Im}\,z$."""
    lo, hi = _across(x0)
    return [(label, complex(lo, y), complex(hi, y)) for y in ims]


def _im_pairs(label: str, y0: float, res: list[float]) -> list[tuple[str, complex, complex]]:
    r"""Pairs across the horizontal line $\mathrm{Im}\,z = y_0$, one per ray $\mathrm{Re}\,z$."""
    lo, hi = _across(y0)
    return [(label, complex(x, lo), complex(x, hi)) for x in res]


def _sum_pairs(label: str, s0: float, fractions: list[float]) -> list[tuple[str, complex, complex]]:
    r"""Pairs across $|\mathrm{Re}\,z| + |\mathrm{Im}\,z| = s_0$ along rays $x = f s$, $y = (1 - f) s$."""
    lo, hi = _across(s0)
    return [
        (label, complex(f * lo, (1 - f) * lo), complex(f * hi, (1 - f) * hi)) for f in fractions
    ]


def boundary_pairs() -> list[tuple[str, complex, complex]]:
    r"""Point pairs straddling every branch threshold of ``w`` and of its derivative.

    Each pair sits at a relative offset of $\pm 10^{-9}$ from the switch line
    (absolute $10^{-9}$ for the axis switches $\mathrm{Re}\,z = 0$ and
    $\mathrm{Im}\,z = 0$, where one side lies exactly on the axis), on several
    rays along the line where the switch is active.
    """
    a = 0.518321480430085929872  # Algorithm 916 step a for relerr = machine epsilon
    pairs: list[tuple[str, complex, complex]] = []
    # continued fraction vs Algorithm 916 (and the derivative's region switch)
    pairs += _im_pairs("cf_im7", 7.0, [0.0, 0.5, 3.0, 5.9])
    pairs += _re_pairs("cf_re6", 6.0, [0.2, 1.0, 3.0, 6.9])
    pairs += _im_pairs("cf_im0.1", 0.1, [6.5, 7.5])
    pairs += _re_pairs("cf_re8", 8.0, [1e-9, 1e-5, 0.05])
    pairs += _im_pairs("cf_im1e-10", 1e-10, [9.0, 12.0, 20.0, 27.0])
    pairs += _re_pairs("cf_re28", 28.0, [0.0, 1e-12, 1e-11])
    # Algorithm 916 x < 10 sums vs the two-sided sum (|y| <= 1e-10)
    pairs += _re_pairs("sums_re10", 10.0, [0.0, 1e-12, 1e-11])
    # Taylor branch x < 5e-4 of the Algorithm 916 sums
    pairs += _re_pairs("taylor_re5e-4", 5e-4, [0.01, 0.5, 3.0, 6.5])
    # y > 5: imaginary terms dropped
    pairs += _im_pairs("drop_im5", 5.0, [1e-3, 0.5, 2.0, 5.5])
    # y > -6: erfcx(y) vs 2 exp(y^2 - x^2)
    pairs += _im_pairs("erfcx_im-6", -6.0, [0.5, 2.0, 5.0])
    # continued fraction: general / two-term / one-term
    pairs += _sum_pairs("cf_sum4000", 4000.0, [0.25, 0.5, 0.75, 0.99975])
    pairs += _sum_pairs("cf_sum1e7", 1e7, [0.1, 0.5, 0.9])
    # sinh Taylor switch 2 a n x = 1e-2 (n = 1) in the derivative sums
    pairs += _re_pairs("sinh_2ax1e-2", 1e-2 / (2 * a), [0.1, 1.0, 4.0])
    # sinc switches |x y| = 1e-4 and |2 x y| = 1e-4
    pairs += _re_pairs("sinc_xy1e-4_y0.5", 2e-4, [0.5])
    pairs += _re_pairs("sinc_xy1e-4_y2", 5e-5, [2.0])
    pairs += _re_pairs("sinc_2xy1e-4", 1e-4, [0.5])
    # axis special cases: one side exactly on the axis
    pairs += [
        ("axis_re0", complex(0.0, y), complex(BOUNDARY_OFFSET, y)) for y in (0.3, 3.0, 10.0, 60.0)
    ]
    pairs += [("axis_re0_neg", complex(-BOUNDARY_OFFSET, y), complex(0.0, y)) for y in (0.3, 3.0)]
    pairs += [
        ("axis_im0", complex(x, 0.0), complex(x, BOUNDARY_OFFSET))
        for x in (0.005, 0.5, 3.0, 20.0, 30.0, 50.0)
    ]
    pairs += [("axis_im0_neg", complex(x, -BOUNDARY_OFFSET), complex(x, 0.0)) for x in (0.5, 3.0)]
    # erfcx thresholds on the imaginary axis (x = 0)
    pairs += _im_pairs("erfcx_im50", 50.0, [0.0])
    pairs += _im_pairs("erfcx_im5e7", 5e7, [0.0])
    pairs += _im_pairs("erfcx_im-6.1", -6.1, [0.0])
    # w_im thresholds on the real axis (y = 0)
    pairs += _re_pairs("wim_re45", 45.0, [0.0])
    pairs += _re_pairs("wim_re5e7", 5e7, [0.0])
    pairs += _re_pairs("wim_taylor", 100.0 / 99.0 - 1.0, [0.0])
    return pairs


def second_derivative_abs(z: complex) -> float:
    r"""$|w''(z)| = |-2w - 2z w'|$ at 50 digits."""
    zz = mp.mpc(z.real, z.imag)
    w = mp.exp(-(zz**2)) * mp.erfc(-1j * zz)
    dw = -2 * zz * w + 2j / mp.sqrt(mp.pi)
    return float(abs(-2 * w - 2 * zz * dw))


def reference(z: complex) -> tuple[float, float, float, float]:
    """$w(z)$ and $w'(z)$ at 50 digits, each part rounded once to a double."""
    zz = mp.mpc(z.real, z.imag)
    w = mp.exp(-(zz**2)) * mp.erfc(-1j * zz)
    dw = -2 * zz * w + 2j / mp.sqrt(mp.pi)
    return float(w.real), float(w.imag), float(dw.real), float(dw.imag)


def main() -> None:
    """Write the reference table."""
    mp.mp.dps = 50
    seen: set[complex] = set()
    header = (
        "# zr,zi,re_w,im_w,re_dw,im_dw (mpmath, 50 digits); generated by gen_faddeeva_reference.py"
    )
    rows = [header]
    for z in case_points() + broad_points() + branch_points() + interval_points():
        if z in seen:
            continue
        seen.add(z)
        values = (z.real, z.imag, *reference(z))
        rows.append(",".join(repr(v) for v in values))
    OUT.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"wrote {len(rows) - 1} points to {OUT}")

    header = (
        "# label,zr_lo,zi_lo,zr_hi,zi_hi,lo: re_w,im_w,re_dw,im_dw,hi: re_w,im_w,re_dw,im_dw,"
        "max |w''| of the two points (mpmath, 50 digits); generated by gen_faddeeva_reference.py"
    )
    rows = [header]
    for label, lo, hi in boundary_pairs():
        ddw = max(second_derivative_abs(lo), second_derivative_abs(hi))
        values = (lo.real, lo.imag, hi.real, hi.imag, *reference(lo), *reference(hi), ddw)
        rows.append(label + "," + ",".join(repr(v) for v in values))
    OUT_BOUNDARIES.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"wrote {len(rows) - 1} boundary pairs to {OUT_BOUNDARIES}")


if __name__ == "__main__":
    main()
