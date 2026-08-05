"""Render ``docs/performance/index.md`` and the homepage proof strip from the latest benchmark ``manifest.json``.

Run before ``zensical build`` (wired into ``poe docs_build``, `.gitlab/65-docs.yml`'s
``build:docs`` job, and `.github/workflows/docs-pages.yml`), mirroring the
``docs/tutorials/gallery/_render.py`` precedent: small, deterministic, data-derived
fragments regenerated at build time rather than hand-maintained prose that drifts from
the actual numbers.

    uv run --group docs python docs/_render_benchmark_summary.py

Locates the manifest via the ``BENCHMARK_MANIFEST_PATH`` env var — CI sets this to
whichever artifact/downloaded manifest.json is available for the current run (see the
CI job comments for the fallback chain); local dev can point it at any
``.spectrafit_reports/benchmark/<run>/manifest.json``. When unset or missing, writes
"no data yet" placeholders instead of failing the build — a docs build must not depend
on a benchmark run having happened first.

Writes two artifacts from the same manifest read: ``docs/performance/index.md`` (the
full page) and ``overrides/_generated/hero-proof.html`` (a compact fragment
``{% include %}``'d into the homepage hero by ``overrides/home.html`` — the same
headline numbers the motto's "self-auditing benchmark" claim describes in prose, made
visible where a first-time visitor actually lands, not three clicks away in the
sidebar). The proof fragment lives under ``overrides/``, not ``docs/``, because
Zensical's Jinja loader only searches ``overrides/`` and the bundled theme's own
template directory (confirmed by reading ``zensical.config.get_custom_theme_dir`` /
``_load_theme_config`` in the installed package) — an ``{% include %}`` pointed at
``docs/`` resolves nothing and silently no-ops under ``ignore missing`` rather than
failing the build, which is exactly what happened on the first pass of writing this.

Gap B9 (2026-08-02): the docs published benchmark *values* but no *plots* — the seven
Observable Plot modules in ``web/src/plots/`` render only inside ``report.html``, never
in the docs (``analysis/ci/CI_MATRIX.md`` §5). This module's manifest read now ALSO
drives 0-6 static SVG figures under ``docs/performance/_figures/`` (see the "Figures"
section below), written by the same call and gitignored the same way as the two
artifacts above. ``matplotlib>=3.8`` is already a ``docs`` dependency-group package
(``pyproject.toml``), so this adds no new dependency — only a third write from the one
manifest read this module already does.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DOCS_DIR = Path(__file__).parent
REPO_ROOT = DOCS_DIR.parent
PAGE_PATH = DOCS_DIR / "performance" / "index.md"
HERO_PROOF_PATH = REPO_ROOT / "overrides" / "_generated" / "hero-proof.html"
# Figures live in their own subdirectory (not directly in docs/performance/)
# so the single `docs/performance/_figures/` gitignore entry covers every file
# this module writes there without needing per-filename entries.
FIGURES_DIR = DOCS_DIR / "performance" / "_figures"

_NO_DATA_PAGE = """\
---
icon: lucide/gauge
---

# Current performance

No benchmark run is available for this build yet — this page is normally generated
from the latest run's `manifest.json` (geomean speedup, win rate, gate status).

See [Benchmark engine](../contributor-guide/benchmark-engine.md) for how to
produce one (`uv run poe benchmark`) and the CI jobs that publish it on every push
(GitLab: `build:report_html`; GitHub: `benchmark.yml`).
"""

_NO_DATA_HERO_PROOF = """\
<div class="sf-hero__proof">
  <span class="sf-hero__proof-badge sf-hero__proof-badge--pending">Benchmark: not yet run for this build</span>
  <a class="sf-hero__proof-link" href="{{ 'performance/' | url }}">What this claim means &rarr;</a>
</div>
"""


def _format_summary(manifest: dict, figures: dict[str, str]) -> str:
    """Render the manifest's headline fields as a markdown page.

    *figures* is whatever :func:`_render_figures` managed to write for this
    manifest (``{}`` when matplotlib wasn't importable) — passed in rather
    than recomputed here so this stays a pure string builder like every
    other ``_format_*`` function; the actual file I/O lives in :func:`render`.
    """
    gate = manifest["gate_state"]
    gate_badge = "✅ **PASS**" if gate == "pass" else f"❌ **{gate.upper()}**"
    baseline = manifest["baseline_solver_id"]
    speedup = manifest["geomean_speedup_vs_baseline"]
    win_rate = manifest["spectrafit_win_rate"]
    max_dr2 = manifest["max_abs_delta_r2"]
    regressions = manifest["regressions"]
    return f"""\
---
icon: lucide/gauge
---

# Current performance

Generated from run `{manifest["run_id"]}` ({manifest["date"]}), {manifest["n_cases"]} cases,
baseline solver `{baseline}`. Regenerated on every docs build from the latest benchmark
run — see [Benchmark engine](../contributor-guide/benchmark-engine.md) for how
this number is produced and what it gates.

!!! note "This page is a teaser — the full report is one click away"
    Everything below is a summary. For the complete, self-contained
    interactive benchmark report — every one of the
    {manifest["n_cases"]} cases, every backend, every diagnostic plot from
    this same run — open `report.html`. Linked page-relative (`../report.html`),
    not root-absolute: GitLab Pages happens to serve this project from its own
    unique domain root, but GitHub Pages serves it as a project page under
    `/SpectraFit-Core/`, so a root-absolute `/report.html` 404s there even
    though it isn't part of the docs source tree itself (see
    `tests/audit/test_audit_built_site_links.py`'s `_CI_ASSEMBLED` handling,
    which resolves relative CI-assembled links against the page before
    exempting them).

    [Open interactive report :lucide-external-link:](../report.html){{ .md-button .md-button--primary target="_blank" rel="noopener" }}

| Metric | Value |
| --- | --- |
| Gate | {gate_badge} |
| Geomean speedup vs. `{baseline}` | {speedup:.2f}× |
| spectrafit win rate | {win_rate:.1%} |
| Max \\|Δr²\\| vs. `{baseline}` | {max_dr2:.2e} |
| Regressions | {regressions} |

!!! note "Reading the win rate: `optfn` pulls it down on quality, not speed"
    `spectrafit win rate` is a composite score (r²·speedup) blended across
    **every** case category, including `optfn` — deliberately multimodal
    global-optimization landscapes. On those cases spectrafit's `"global"`
    solver is typically the *fastest* backend (its median per-case speedup
    there tends to be the highest of any category), but it can converge to a
    different — sometimes worse — local optimum than lmfit's
    population-based differential-evolution search, so it loses on the
    composite score more often than every other category despite winning on
    raw wall-clock time. `optfn` is excluded from the accuracy (\\|Δr²\\|)
    gate above for the same reason (see
    [Benchmark engine](../contributor-guide/benchmark-engine.md)).
    A single blended win-rate number can't show this split — see
    [`report.html`](../report.html) to filter by category and check yourself.
{_format_speedup_figure(figures, baseline)}
{_format_backend_table(manifest, figures)}"""


def _fmt_ms(value: float | None) -> str:
    """Milliseconds, switching to µs below 1 ms so sub-ms solves stay readable."""
    if value is None:
        return "—"
    return f"{value * 1000:.0f} µs" if value < 1.0 else f"{value:.2f} ms"


def _format_backend_table(manifest: dict, figures: dict[str, str]) -> str:
    """Render the per-backend comparison, or nothing when the manifest predates it.

    ``.get`` rather than ``manifest["backend_facts"]`` is load-bearing, not defensive
    habit: both CI pipelines point ``BENCHMARK_MANIFEST_PATH`` at a *downloaded*
    artifact (`.github/workflows/docs-pages.yml`, `.gitlab/65-docs.yml`), which can be
    an older run written before this field existed. A bare subscript there is a
    ``KeyError`` that fails the docs build.

    Each row carries a swatch coloured with the solver-identity tokens ported in the
    docs palette, so a backend is the same colour here as on the dashboard. The swatch
    sets both a fill and an edge: several identity colours (systemYellow worst, at
    1.51:1 on white) fail even WCAG 1.4.11's 3:1 non-text bar, so the fill alone is not
    a reliable boundary — the edge uses the AA-safe ``-text`` variant.
    """
    facts = manifest.get("backend_facts")
    if not facts:
        return ""
    baseline = manifest.get("baseline_solver_id", "lmfit")
    rows = []
    for solver_id in sorted(facts):
        f = facts[solver_id]
        swatch = (
            f'<span class="sf-solver-dot" style="'
            f"--sf-solver: var(--c-{solver_id}); "
            f'--sf-solver-edge: var(--c-{solver_id}-text)"></span>'
        )
        r2 = f["med_r2"]
        speedup = f["med_speedup"]
        cells = [
            f"{swatch} `{solver_id}`",
            _fmt_ms(f["med_ms"]),
            f"{r2:.4f}" if r2 is not None else "—",
            f"{speedup:.2f}×" if speedup is not None else "—",
            str(f["cases_run"]),
        ]
        rows.append("| " + " | ".join(cells) + " |")
    table = "\n".join(rows)
    # Wrapped in a classed div (md_in_html is enabled) rather than styling
    # `.md-typeset table` globally: the numerals here want mono so digits align
    # in columns the way they do on the dashboard, but the crate table, the
    # model-formula table and every other prose table read better in sans.
    # `markdown="1"` is what lets the markdown table inside still be parsed.
    return f"""
## All backends, side by side

One row per backend, sorted alphabetically — order implies nothing. Speedup is relative
to the baseline (`{baseline}` = 1.00×): a measured ratio, not a ranking. These are the
same medians the dashboard shows, computed by the same reduction.

<div class="sf-numeric" markdown="1">

| Backend | Median solve | Median r² | Speedup vs `{baseline}` | Cases run |
| --- | ---: | ---: | ---: | ---: |
{table}

</div>
{_format_backend_medians_figure(figures)}{_format_speed_figure(figures)}{_format_convergence_figure(figures)}{_format_pareto_figure(figures)}{_format_speedup_distribution_figure(figures)}"""


# --------------------------------------------------------------------------- #
# Figures (gap B9) — the manifest read above already drives two text
# artifacts; these render 0-6 static SVGs from the SAME manifest, using only
# fields the manifest actually carries (nothing here is a stand-in for data
# the manifest doesn't have — see each figure function's docstring for which
# fields back it and why the missing-field case degrades rather than raises).
# The six: geomean/harmonic-mean speedup headline, per-backend median
# speedup, per-backend median solve time (log scale), per-backend
# convergence rate, a per-case speed-vs-accuracy (Pareto) scatter, and a
# per-case speedup-distribution box plot (the last two need `per_case_points`,
# a manifest field additive on top of `backend_facts` — see
# `oracles.reports._per_case_points`).
#
# Colour choice: the docs site has a light/dark toggle
# (``zensical.toml``'s ``theme.palette`` pair), and ``docs/stylesheets/tokens/
# palette.css`` already carries a per-solver identity colour for EACH scheme,
# switched live by the page's ``[data-md-color-scheme]`` attribute. A static
# build-time SVG can't react to that attribute — matplotlib's SVG writer has
# no notion of it — so shipping the palette.css hexes verbatim would mean
# picking one scheme's colours and being wrong (illegible, not just
# "off-brand") every time a reader is on the other one. Reproducing the CSS
# toggle for images (two files + a display:none pair, the trick
# ``pages/hero.css`` already uses for the homepage art) would need a
# docs-side CSS/markup change, out of scope for this manifest-reading module.
#
# Instead every hex below was solved for the best contrast ratio achievable
# against BOTH real backgrounds AT ONCE — white #FFFFFF (the light scheme)
# and #0B0C0F (the slate scheme's background; both measured exactly as
# palette.css's own header comment measures them): fix a hue, sweep HLS
# lightness/saturation, keep whichever point maximises
# min(contrast-vs-white, contrast-vs-0B0C0F). Every colour here lands at
# ~4.4:1 on both — just under AA text (4.5:1) on either alone, which is the
# mathematical ceiling for a single flat colour spanning two backgrounds this
# far apart (~20:1 luminance ratio to each other); nothing scores higher on
# the worse background without giving up more than it gains on the better
# one. Hues were kept close to their palette.css counterpart (blue for
# spectrafit, green for lmfit, etc.) so a reader who has learned "spectrafit
# is blue" from the table two paragraphs up isn't handed a fourth, unrelated
# colour on the chart below it — same vocabulary, different lightness/
# saturation because the constraint is different (one static file, two
# audiences, not one CSS rule per audience).
# --------------------------------------------------------------------------- #

# Neutral ink for spines/ticks/labels/the baseline reference line — the
# 4.42:1-both-ways grey from the sweep described above.
_FIG_INK = "#787878"
# Two-bar headline figure (see _render_speedup_figure): blue/green hues at
# the same solved lightness/saturation, echoing spectrafit/lmfit's identity
# colours in docs/stylesheets/tokens/palette.css without being either
# scheme's exact hex.
_FIG_ACCENT_PRIMARY = "#3376db"
_FIG_ACCENT_SECONDARY = "#228a33"
# Per-backend palette for the medians figure (see
# _render_backend_medians_figure) — one dual-theme-solved hue per backend id,
# in the same hue family as that backend's palette.css token pair. Unknown/
# future backend ids fall back to _FIG_INK via `.get` (still legible, just
# not colour-differentiated) rather than raising: the same "don't invent,
# don't crash on a schema this function doesn't fully know" rule
# `_format_backend_table` already follows for the table version of this data.
# scipy-ls-dogbox uses amber, not yellow: palette.css's own header comment
# notes yellow structurally cannot clear AA against white even as a single
# scheme's colour (1.51:1), so no dual-theme solve exists for it either.
_SOLVER_COLORS: dict[str, str] = {
    "spectrafit": "#3376db",
    "lmfit": "#228a33",
    "jax": "#e6225d",
    "scipy-ls-lm": "#1a8493",
    "scipy-ls-trf": "#7c62e3",
    "scipy-ls-dogbox": "#927424",
}


def _rgba(hex_color: str, alpha: float) -> tuple[float, float, float, float]:
    """Parse a ``#rrggbb`` string into an ``(r, g, b, alpha)`` tuple in ``[0, 1]``.

    A local hex parser rather than ``matplotlib.colors.to_rgba``: every other
    matplotlib access in this module goes through the lazily-guarded
    :func:`_pyplot`, and pulling in ``matplotlib.colors`` at module level
    would be the one import here that isn't deferred.
    """
    stripped = hex_color.lstrip("#")
    r, g, b = (int(stripped[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return (r, g, b, alpha)


def _bar_color(solver_id: str) -> tuple[float, float, float, float]:
    """Bar/point colour: spectrafit-core highlighted, every other backend muted.

    Per explicit follow-up feedback on this page: on a quick-glance teaser,
    the reader's eye should go to spectrafit-core first without the other
    backends' data disappearing entirely — full-opacity identity colour for
    ``spectrafit``, the same hue at reduced opacity for everything else.
    Applied uniformly across every backend-comparison figure on this page.
    """
    hex_color = _SOLVER_COLORS.get(solver_id, _FIG_INK)
    return _rgba(hex_color, 1.0 if solver_id == "spectrafit" else 0.4)


def _pyplot():
    """Import ``matplotlib.pyplot`` lazily, forced onto the non-interactive Agg backend.

    Lazy AND guarded for the same reason ``resolve_manifest``'s ``oracles.reports``
    import is: ``matplotlib`` is a ``docs`` dependency-group package, not a base
    one (``pyproject.toml``), and this module's one hard rule is that a docs
    build must not fail because a piece of optional tooling isn't importable
    in whatever environment invoked it — a performance page with numbers but
    no plots beats no page at all. Returns ``None`` (never raises) on
    ``ImportError``; every caller here already treats "no figure" as a valid,
    silent outcome.

    ``matplotlib.use("Agg")`` must run before ``pyplot`` is imported anywhere
    in the process — matplotlib locks in its backend on first `pyplot` import,
    and the default backend probes for a display that CI doesn't have. Doing
    it here, immediately before the only `import matplotlib.pyplot` in this
    module, is what makes running this script headless in CI safe without a
    separate rcParams file or ``MPLBACKEND`` env var.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    return plt


def _new_figure(height: float):
    """Create a transparent-background figure/axes pair with shared chart chrome.

    Returns ``(None, None)`` when matplotlib isn't importable, so callers can
    propagate the same "no figure" outcome as :func:`_pyplot` with one check.

    Transparent, not white: the docs dark scheme's real background is
    ``#0B0C0F`` (see the module-level colour comment above), and a solid
    white canvas here is exactly the anti-pattern this module's brief warns
    against. Three spines are dropped (a horizontal bar chart doesn't need a
    full box) and everything that's left — the bottom spine, ticks, tick
    labels, axis labels — uses ``_FIG_INK``.
    """
    plt = _pyplot()
    if plt is None:
        return None, None
    fig, ax = plt.subplots(figsize=(5.4, height))
    fig.patch.set_alpha(0.0)
    ax.patch.set_alpha(0.0)
    for spine_name, spine in ax.spines.items():
        if spine_name == "bottom":
            spine.set_color(_FIG_INK)
        else:
            spine.set_visible(False)
    ax.tick_params(colors=_FIG_INK, labelcolor=_FIG_INK, labelsize=9)
    ax.xaxis.label.set_color(_FIG_INK)
    ax.yaxis.label.set_color(_FIG_INK)
    return fig, ax


def _save_figure(fig, filename: str) -> str:
    """Write *fig* as SVG under ``FIGURES_DIR``; return the page-relative path.

    SVG, not PNG: vector output stays crisp at any zoom level with a tiny
    file size, and needs no DPI decision. ``transparent=True`` on top of the
    already-alpha-0 figure/axes patches (:func:`_new_figure`) is deliberate
    belt-and-suspenders — matplotlib's SVG writer has, on some past versions,
    still emitted an opaque background ``<rect>`` even with the patches made
    transparent in code; passing it explicitly here is cheap insurance
    against that regressing across matplotlib versions.

    Closes *fig* before returning: this module can render up to two figures
    per invocation, and an unclosed ``Figure`` is exactly the kind of leak
    that's invisible in a one-shot CLI script but would matter if this ever
    ran in a long-lived process (matplotlib also warns past ~20 open figures).
    """
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURES_DIR / filename
    fig.savefig(path, format="svg", transparent=True)
    plt = _pyplot()
    if plt is not None:
        plt.close(fig)
    return f"_figures/{filename}"


def _render_speedup_figure(manifest: dict) -> str | None:
    """Render the geomean-/harmonic-mean-speedup-vs-baseline bar chart.

    ``geomean_speedup_vs_baseline`` is a required manifest field — present on
    every run this repo has ever written. ``harmonic_mean_speedup_vs_baseline``
    is additive-optional (``bench_contract.ManifestSignals``); when a
    pre-Eeckhout-metric payload lacks it, this renders a single-bar figure
    rather than fabricating a 0.0 bar, which would misreport "not measured"
    as "measured zero speedup".

    Returns ``None`` (writes nothing) when matplotlib isn't importable.
    """
    fig, ax = _new_figure(height=1.7)
    if fig is None or ax is None:
        return None
    baseline = manifest.get("baseline_solver_id", "lmfit")
    rows = [
        ("Geometric mean", manifest["geomean_speedup_vs_baseline"], _FIG_ACCENT_PRIMARY)
    ]
    harmonic = manifest.get("harmonic_mean_speedup_vs_baseline")
    if harmonic is not None:
        rows.append(("Harmonic mean", harmonic, _FIG_ACCENT_SECONDARY))
    labels = [row[0] for row in rows]
    values = [row[1] for row in rows]
    colors = [row[2] for row in rows]
    positions = list(range(len(rows)))
    ax.barh(positions, values, color=colors, height=0.5, zorder=3)
    ax.axvline(1.0, color=_FIG_INK, linestyle="--", linewidth=1, zorder=2)
    xmax = max(values + [1.0]) * 1.22
    ax.set_xlim(0, xmax)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.set_yticks(positions)
    ax.set_yticklabels(labels)
    ax.set_xlabel(f"Speedup vs. {baseline} (×)")
    ax.text(
        1.0,
        len(rows) - 0.45,
        f" {baseline} baseline = 1.0×",
        color=_FIG_INK,
        fontsize=8,
        ha="left",
        va="top",
    )
    for pos, value in zip(positions, values, strict=True):
        ax.text(
            value + xmax * 0.015,
            pos,
            f"{value:.2f}×",
            va="center",
            fontsize=9,
            color=_FIG_INK,
        )
    fig.tight_layout(pad=0.6)
    return _save_figure(fig, "speedup-headline.svg")


def _render_backend_medians_figure(manifest: dict) -> str | None:
    """Render the per-backend median-speedup bar chart, when the manifest has it.

    Mirrors ``_format_backend_table``'s own optional handling field-for-field:
    ``backend_facts`` is a manifest-only, additive key (deliberately NOT on
    ``ManifestSignals``/the OpenAPI contract — see ``reports._headline``'s
    comment), so both CI pipelines can hand this script an older downloaded
    manifest that predates it. Same rule as the table: ``.get``, not a
    subscript, and a silent "no figure" rather than a ``KeyError`` that fails
    the docs build.
    """
    facts = manifest.get("backend_facts")
    if not facts:
        return None
    solver_ids = sorted(facts)
    labels: list[str] = []
    values: list[float] = []
    colors: list[tuple[float, float, float, float]] = []
    for solver_id in solver_ids:
        speedup = facts[solver_id].get("med_speedup")
        if speedup is None:
            continue  # backend ran zero cases, or every case was non-finite
        labels.append(solver_id)
        values.append(speedup)
        colors.append(_bar_color(solver_id))
    if not values:
        return None
    fig, ax = _new_figure(height=0.5 * len(values) + 1.1)
    if fig is None or ax is None:
        return None
    baseline = manifest.get("baseline_solver_id", "lmfit")
    positions = list(range(len(values)))
    ax.barh(positions, values, color=colors, height=0.6, zorder=3)
    ax.axvline(1.0, color=_FIG_INK, linestyle="--", linewidth=1, zorder=2)
    xmax = max(values + [1.0]) * 1.22
    ax.set_xlim(0, xmax)
    ax.set_ylim(-0.6, len(values) - 0.4)
    ax.set_yticks(positions)
    ax.set_yticklabels(labels, fontfamily="monospace")
    ax.set_xlabel(f"Median speedup vs. {baseline} (×)")
    for pos, value in zip(positions, values, strict=True):
        ax.text(
            value + xmax * 0.015,
            pos,
            f"{value:.2f}×",
            va="center",
            fontsize=9,
            color=_FIG_INK,
        )
    fig.tight_layout(pad=0.6)
    return _save_figure(fig, "backend-medians.svg")


def _render_speed_figure(manifest: dict) -> str | None:
    """Render the per-backend median solve time (``med_ms``) on a log-x axis.

    Log scale, not linear: ``_render_backend_medians_figure`` already shows
    *relative* speed (``med_speedup``, all backends on one comparable linear
    scale by construction — they're ratios to the same baseline). This figure
    shows *absolute* solve time instead, and absolute per-case solve times
    genuinely span orders of magnitude here (spectrafit's own manifest-wide
    speedup is 10x+, i.e. its ``med_ms`` sits roughly a full decade below the
    slower backends') — a linear axis would crush the fast end of the chart
    into a sliver against the slow end, which is precisely the failure mode a
    log axis exists to fix. Kept as a horizontal bar chart (not a different
    chart type) so it reads as a sibling of the medians figure directly above
    it on the page: same orientation, same per-backend colour vocabulary,
    same layout, only the x-axis transform and the underlying field differ.

    Same optional-field handling as ``_render_backend_medians_figure``:
    ``backend_facts`` is manifest-only and additive, so ``.get`` plus a silent
    ``None`` return (no figure) is what keeps an older downloaded manifest
    from failing the docs build.
    """
    facts = manifest.get("backend_facts")
    if not facts:
        return None
    solver_ids = sorted(facts)
    labels: list[str] = []
    values: list[float] = []
    colors: list[tuple[float, float, float, float]] = []
    for solver_id in solver_ids:
        med_ms = facts[solver_id].get("med_ms")
        if med_ms is None or med_ms <= 0:
            continue  # log scale can't place a zero/negative/missing value
        labels.append(solver_id)
        values.append(med_ms)  # already milliseconds, per _fmt_ms's own convention
        colors.append(_bar_color(solver_id))
    if not values:
        return None
    fig, ax = _new_figure(height=0.5 * len(values) + 1.1)
    if fig is None or ax is None:
        return None
    positions = list(range(len(values)))
    ax.barh(positions, values, color=colors, height=0.6, zorder=3)
    ax.set_xscale("log")
    ax.set_ylim(-0.6, len(values) - 0.4)
    ax.set_yticks(positions)
    ax.set_yticklabels(labels, fontfamily="monospace")
    ax.set_xlabel("Median solve time (ms, log scale)")
    # Grid on the major log decades only — a horizontal bar chart's own bars
    # already carry the per-category comparison, the grid is purely a
    # log-scale reading aid so "one gridline = one order of magnitude" is
    # visible at a glance.
    ax.grid(
        axis="x", which="major", color=_FIG_INK, alpha=0.25, linewidth=0.6, zorder=1
    )
    for pos, value in zip(positions, values, strict=True):
        label = _fmt_ms(value)
        ax.text(
            value * 1.12,
            pos,
            label,
            va="center",
            fontsize=9,
            color=_FIG_INK,
        )
    # Extra headroom on the right for the value labels beyond the last bar,
    # consistent in spirit with the *1.22 xmax pad used on the linear-scale
    # figures above (here expressed as a log-scale multiplicative factor).
    ax.set_xlim(min(values) / 1.8, max(values) * 2.2)
    fig.tight_layout(pad=0.6)
    return _save_figure(fig, "backend-speed.svg")


def _render_convergence_figure(manifest: dict) -> str | None:
    """Render each backend's ``success_rate`` (fraction of cases that converged) as a %.

    Speed and accuracy (the two figures above) say nothing about whether a
    backend actually finishes — a solver that fails half its cases could
    still look fast/accurate on the half it completes. ``success_rate`` is
    the field ``python/oracles/reports._backend_facts`` already computes for
    exactly this (``success_hits / success_total``); this figure is the only
    place on the page that surfaces it visually.

    Handles two distinct "can't plot this backend" cases, per instructions:
    ``success_rate is None`` (``_backend_facts`` returns ``None`` when
    ``success_total`` is 0 — see ``reports.py`` line ~402) and
    ``cases_run == 0`` (the backend is present in the manifest but never ran
    a case this run) both `continue` past that backend rather than plotting
    a fabricated 0%, mirroring ``_render_backend_medians_figure``'s existing
    "backend ran zero cases" skip.
    """
    facts = manifest.get("backend_facts")
    if not facts:
        return None
    solver_ids = sorted(facts)
    labels: list[str] = []
    values: list[float] = []
    colors: list[tuple[float, float, float, float]] = []
    for solver_id in solver_ids:
        f = facts[solver_id]
        if f.get("cases_run", 0) == 0:
            continue
        success_rate = f.get("success_rate")
        if success_rate is None:
            continue
        labels.append(solver_id)
        values.append(success_rate * 100.0)
        colors.append(_bar_color(solver_id))
    if not values:
        return None
    fig, ax = _new_figure(height=0.5 * len(values) + 1.1)
    if fig is None or ax is None:
        return None
    positions = list(range(len(values)))
    ax.barh(positions, values, color=colors, height=0.6, zorder=3)
    ax.set_xlim(0, 108)
    ax.set_ylim(-0.6, len(values) - 0.4)
    ax.set_yticks(positions)
    ax.set_yticklabels(labels, fontfamily="monospace")
    ax.set_xlabel("Cases converged (%)")
    for pos, value in zip(positions, values, strict=True):
        ax.text(
            value + 2.0,
            pos,
            f"{value:.1f}%",
            va="center",
            fontsize=9,
            color=_FIG_INK,
        )
    fig.tight_layout(pad=0.6)
    return _save_figure(fig, "backend-convergence.svg")


def _render_pareto_figure(manifest: dict) -> str | None:
    """Scatter of median solve time (log-x) vs. r², one point per case per backend.

    The three bar charts above each collapse a whole backend down to one
    aggregate number (its median). This shows the real per-case spread behind
    those medians — whether a backend's speed/accuracy trade-off is tight and
    consistent or scattered — using ``per_case_points`` (built by
    ``oracles.reports._per_case_points``): a manifest-only, additive field
    like ``backend_facts``, so an older manifest that predates it simply has
    no Pareto figure rather than a build failure.

    spectrafit-core is drawn LAST (so it sits on top of, not under, the other
    backends' points) at full opacity and a larger marker; every other
    backend is muted underneath — the same highlight/mute rule
    :func:`_bar_color` applies to the bar charts, extended to a scatter where
    z-order also matters, not just colour.
    """
    points = manifest.get("per_case_points")
    if not points:
        return None
    # spectrafit-core sorts last so it draws on top of the muted backends.
    solver_ids = sorted(points, key=lambda s: (s == "spectrafit", s))
    series: list[tuple[str, list[float], list[float]]] = []
    for solver_id in solver_ids:
        ms = [p["ms"] for p in points[solver_id] if p.get("ms", 0) > 0]
        r2 = [p["r2"] for p in points[solver_id] if p.get("ms", 0) > 0]
        if ms:
            series.append((solver_id, ms, r2))
    if not series:
        return None
    fig, ax = _new_figure(height=3.4)
    if fig is None or ax is None:
        return None
    for solver_id, ms, r2 in series:
        highlight = solver_id == "spectrafit"
        ax.scatter(
            ms,
            r2,
            s=22 if highlight else 11,
            color=_SOLVER_COLORS.get(solver_id, _FIG_INK),
            alpha=1.0 if highlight else 0.35,
            edgecolors="none",
            zorder=3 if highlight else 2,
            label=solver_id,
        )
    ax.set_xscale("log")
    ax.set_xlabel("Median solve time (ms, log scale)")
    ax.set_ylabel("r²")
    legend = ax.legend(loc="lower left", frameon=False, fontsize=8, labelcolor=_FIG_INK)
    for handle in legend.legend_handles:
        handle.set_alpha(1.0)  # legend swatches stay legible even for muted series
    fig.tight_layout(pad=0.6)
    return _save_figure(fig, "pareto.svg")


def _render_speedup_distribution_figure(manifest: dict) -> str | None:
    """Horizontal box plot of per-case speedup spread (vs. the baseline), per backend.

    ``_render_backend_medians_figure`` already shows median speedup as one bar
    per backend; this shows the full per-case distribution behind that single
    number — a backend fast on median but wildly inconsistent case-to-case
    looks very different here from one that is consistently fast. Same
    manifest-only ``per_case_points`` field as the Pareto figure above (a
    manifest predating it simply has no distribution figure).
    """
    points = manifest.get("per_case_points")
    if not points:
        return None
    solver_ids = [s for s in sorted(points) if any("speedup" in p for p in points[s])]
    if not solver_ids:
        return None
    data = [
        [p["speedup"] for p in points[solver_id] if "speedup" in p]
        for solver_id in solver_ids
    ]
    fig, ax = _new_figure(height=0.6 * len(solver_ids) + 1.3)
    if fig is None or ax is None:
        return None
    positions = list(range(len(solver_ids)))
    box_plot = ax.boxplot(
        data,
        positions=positions,
        vert=False,
        widths=0.55,
        patch_artist=True,
        showfliers=False,
        medianprops={"color": _FIG_INK, "linewidth": 1.4},
    )
    for i, solver_id in enumerate(solver_ids):
        highlight = solver_id == "spectrafit"
        hex_color = _SOLVER_COLORS.get(solver_id, _FIG_INK)
        box = box_plot["boxes"][i]
        box.set_facecolor(_rgba(hex_color, 0.85 if highlight else 0.35))
        box.set_edgecolor(hex_color)
        box.set_linewidth(1.6 if highlight else 1.0)
    for whisker in box_plot["whiskers"]:
        whisker.set_color(_FIG_INK)
        whisker.set_alpha(0.6)
    for cap in box_plot["caps"]:
        cap.set_color(_FIG_INK)
        cap.set_alpha(0.6)
    baseline = manifest.get("baseline_solver_id", "lmfit")
    ax.axvline(1.0, color=_FIG_INK, linestyle="--", linewidth=1, zorder=1)
    ax.set_xscale("log")
    ax.set_ylim(-0.6, len(solver_ids) - 0.4)
    ax.set_yticks(positions)
    ax.set_yticklabels(solver_ids, fontfamily="monospace")
    ax.set_xlabel(f"Per-case speedup vs. {baseline} (×, log scale)")
    fig.tight_layout(pad=0.6)
    return _save_figure(fig, "speedup-distribution.svg")


def _render_figures(manifest: dict) -> dict[str, str]:
    """Render every figure this manifest supports; return ``{key: page-relative path}``.

    The single I/O entry point for this section — called once from
    :func:`render`, never from inside a ``_format_*`` function, so those stay
    pure string builders (existing convention in this module). A key is
    simply absent from the returned dict for any figure that didn't render
    (missing matplotlib, or — for ``backend_medians``, ``backend_speed``, and
    ``backend_convergence`` — a manifest that predates ``backend_facts``, or
    one where every backend is missing the specific field that figure needs);
    callers check with ``.get`` and degrade to no image rather than a broken
    link, same failure mode as the rest of this module's "missing data means
    less page, not a crashed build" rule.
    """
    figures: dict[str, str] = {}
    speedup_path = _render_speedup_figure(manifest)
    if speedup_path is not None:
        figures["speedup"] = speedup_path
    medians_path = _render_backend_medians_figure(manifest)
    if medians_path is not None:
        figures["backend_medians"] = medians_path
    speed_path = _render_speed_figure(manifest)
    if speed_path is not None:
        figures["backend_speed"] = speed_path
    convergence_path = _render_convergence_figure(manifest)
    if convergence_path is not None:
        figures["backend_convergence"] = convergence_path
    pareto_path = _render_pareto_figure(manifest)
    if pareto_path is not None:
        figures["pareto"] = pareto_path
    distribution_path = _render_speedup_distribution_figure(manifest)
    if distribution_path is not None:
        figures["speedup_distribution"] = distribution_path
    return figures


def _format_speedup_figure(figures: dict[str, str], baseline: str) -> str:
    """Markdown fragment embedding the speedup-headline figure, or ``""`` without one."""
    path = figures.get("speedup")
    if not path:
        return ""
    return f"""
![Horizontal bar chart of geometric-mean and harmonic-mean speedup versus the {baseline} baseline, with a dashed reference line at 1.0×.]({path})
"""


def _format_backend_medians_figure(figures: dict[str, str]) -> str:
    """Markdown fragment embedding the backend-medians figure, or ``""`` without one."""
    path = figures.get("backend_medians")
    if not path:
        return ""
    return f"""
![Horizontal bar chart of each backend's median speedup versus the baseline, one bar per backend, coloured to match the table above.]({path})
"""


def _format_speed_figure(figures: dict[str, str]) -> str:
    """Markdown fragment embedding the backend-speed figure, or ``""`` without one."""
    path = figures.get("backend_speed")
    if not path:
        return ""
    return f"""
![Horizontal bar chart of each backend's median solve time in milliseconds, log-scaled on the x-axis because solve times span orders of magnitude, one bar per backend, coloured to match the table above.]({path})
"""


def _format_convergence_figure(figures: dict[str, str]) -> str:
    """Markdown fragment embedding the convergence figure, or ``""`` without one."""
    path = figures.get("backend_convergence")
    if not path:
        return ""
    return f"""
![Horizontal bar chart of the percentage of cases each backend converged on, one bar per backend, coloured to match the table above.]({path})
"""


def _format_pareto_figure(figures: dict[str, str]) -> str:
    """Markdown fragment embedding the Pareto scatter, or ``""`` without one."""
    path = figures.get("pareto")
    if not path:
        return ""
    return f"""
### Speed vs. accuracy, case by case

Every dot is one benchmark case for one backend — spectrafit-core drawn on
top and at full colour, the other backends muted underneath, so the real
per-case spread is visible without erasing the comparison.

![Scatter plot of median solve time (log scale) versus r² for every benchmark case, spectrafit-core highlighted in full colour on top of the muted other backends.]({path})
"""


def _format_speedup_distribution_figure(figures: dict[str, str]) -> str:
    """Markdown fragment embedding the speedup-distribution figure, or ``""`` without one."""
    path = figures.get("speedup_distribution")
    if not path:
        return ""
    return f"""
### Speedup spread across cases

The median-speedup bar above is one number; this is the distribution behind
it — how consistent each backend actually is from case to case.

![Horizontal box plot of per-case speedup versus the baseline, one box per backend, spectrafit-core highlighted.]({path})
"""


def _format_hero_proof(manifest: dict) -> str:
    """Render the manifest's headline fields as a compact homepage proof strip."""
    gate = manifest["gate_state"]
    passed = gate == "pass"
    badge_class = (
        "sf-hero__proof-badge--pass" if passed else "sf-hero__proof-badge--fail"
    )
    badge_text = "Gate: PASS" if passed else f"Gate: {gate.upper()}"
    baseline = manifest["baseline_solver_id"]
    speedup = manifest["geomean_speedup_vs_baseline"]
    regressions = manifest["regressions"]
    return f"""\
<div class="sf-hero__proof">
  <span class="sf-hero__proof-badge {badge_class}">{badge_text}</span>
  <span class="sf-hero__proof-metric">{speedup:.2f}&times; geomean vs. {baseline}</span>
  <span class="sf-hero__proof-metric">{regressions} regressions</span>
  <a class="sf-hero__proof-link" href="{{{{ 'performance/' | url }}}}">Full benchmark &rarr;</a>
</div>
"""


def render(manifest_path: str | None) -> tuple[Path, Path]:
    """Write ``docs/performance/index.md`` and the hero proof strip, returning both paths.

    Falls back to the "no data yet" placeholders when *manifest_path* is unset or the
    file doesn't exist — never raises for a missing manifest. The no-data branch
    returns BEFORE ``_render_figures`` is ever called: no manifest means no figures,
    not empty/placeholder ones, and it means matplotlib is never even imported for a
    no-data build — the same "don't pay for what you don't need" reasoning as
    ``resolve_manifest``'s lazy ``oracles.reports`` import below.
    """
    PAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    HERO_PROOF_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not manifest_path or not Path(manifest_path).is_file():
        PAGE_PATH.write_text(_NO_DATA_PAGE, encoding="utf-8")
        HERO_PROOF_PATH.write_text(_NO_DATA_HERO_PROOF, encoding="utf-8")
        return PAGE_PATH, HERO_PROOF_PATH
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    figures = _render_figures(manifest)
    PAGE_PATH.write_text(_format_summary(manifest, figures), encoding="utf-8")
    HERO_PROOF_PATH.write_text(_format_hero_proof(manifest), encoding="utf-8")
    return PAGE_PATH, HERO_PROOF_PATH


def resolve_manifest(explicit: str | None) -> str | None:
    """Return the manifest path to render from, or ``None`` for the placeholders.

    *explicit* (``BENCHMARK_MANIFEST_PATH``) always wins — both CI pipelines set
    it (`.gitlab/65-docs.yml`, `.github/workflows/docs-pages.yml`), so CI
    behaviour is unchanged by this function.

    When it is unset, fall back to the newest local run instead of rendering the
    "no data yet" placeholder. Without this, ``poe docs_build`` produced a
    different page than CI did for the same commit — a local-vs-remote parity gap
    with no documented rule covering it, and the reason the performance page read
    "no benchmark run is available" on every local build while completed runs sat
    in ``.spectrafit_reports/``.

    ``latest_results`` returns a *path* and never reads the (large) results.json,
    so this stays cheap. The import is lazy and guarded: a docs build must not
    fail because the benchmark engine isn't importable in the docs dep group —
    the same principle as the missing-manifest fallback in ``render``.
    """
    if explicit:
        return explicit
    try:
        from oracles.reports import latest_results
    except ImportError:
        return None
    latest = latest_results("benchmark")
    if latest is None:
        return None
    manifest = latest.parent / "manifest.json"
    return str(manifest) if manifest.is_file() else None


if __name__ == "__main__":
    resolved = resolve_manifest(os.environ.get("BENCHMARK_MANIFEST_PATH"))
    # Name the run actually used — a silent fallback to an unexpected local run
    # is otherwise indistinguishable from a correct one in the build log.
    print(f"manifest: {resolved or '<none — rendering placeholders>'}")
    page, proof = render(resolved)
    print(f"wrote {page}")
    print(f"wrote {proof}")
