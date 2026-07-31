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
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DOCS_DIR = Path(__file__).parent
REPO_ROOT = DOCS_DIR.parent
PAGE_PATH = DOCS_DIR / "performance" / "index.md"
HERO_PROOF_PATH = REPO_ROOT / "overrides" / "_generated" / "hero-proof.html"

_NO_DATA_PAGE = """\
# Current performance

No benchmark run is available for this build yet — this page is normally generated
from the latest run's `manifest.json` (geomean speedup, win rate, gate status).

See [Benchmark engine (internal)](../contributor-guide/benchmark-engine.md) for how to
produce one (`uv run poe benchmark`) and the CI jobs that publish it on every push
(GitLab: `build:report_html`; GitHub: `benchmark.yml`).
"""

_NO_DATA_HERO_PROOF = """\
<div class="sf-hero__proof">
  <span class="sf-hero__proof-badge sf-hero__proof-badge--pending">Benchmark: not yet run for this build</span>
  <a class="sf-hero__proof-link" href="{{ 'performance/' | url }}">What this claim means &rarr;</a>
</div>
"""


def _format_summary(manifest: dict) -> str:
    """Render the manifest's headline fields as a markdown page."""
    gate = manifest["gate_state"]
    gate_badge = "✅ **PASS**" if gate == "pass" else f"❌ **{gate.upper()}**"
    baseline = manifest["baseline_solver_id"]
    speedup = manifest["geomean_speedup_vs_baseline"]
    win_rate = manifest["spectrafit_win_rate"]
    max_dr2 = manifest["max_abs_delta_r2"]
    regressions = manifest["regressions"]
    return f"""\
# Current performance

Generated from run `{manifest["run_id"]}` ({manifest["date"]}), {manifest["n_cases"]} cases,
baseline solver `{baseline}`. Regenerated on every docs build from the latest benchmark
run — see [Benchmark engine (internal)](../contributor-guide/benchmark-engine.md) for how
this number is produced and what it gates.

| Metric | Value |
| --- | --- |
| Gate | {gate_badge} |
| Geomean speedup vs. `{baseline}` | {speedup:.2f}× |
| spectrafit win rate | {win_rate:.1%} |
| Max \\|Δr²\\| vs. `{baseline}` | {max_dr2:.2e} |
| Regressions | {regressions} |

For the full per-case breakdown and every backend side by side, see the live `web/`
dashboard or the self-contained `report.html` bundle published alongside GitLab Pages
(not hyperlinked here — both are published outside this docs site's own root, and only
on GitLab Pages currently, so a relative link would 404 depending on which Pages host
served this page).
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
    file doesn't exist — never raises for a missing manifest.
    """
    PAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    HERO_PROOF_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not manifest_path or not Path(manifest_path).is_file():
        PAGE_PATH.write_text(_NO_DATA_PAGE, encoding="utf-8")
        HERO_PROOF_PATH.write_text(_NO_DATA_HERO_PROOF, encoding="utf-8")
        return PAGE_PATH, HERO_PROOF_PATH
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    PAGE_PATH.write_text(_format_summary(manifest), encoding="utf-8")
    HERO_PROOF_PATH.write_text(_format_hero_proof(manifest), encoding="utf-8")
    return PAGE_PATH, HERO_PROOF_PATH


if __name__ == "__main__":
    page, proof = render(os.environ.get("BENCHMARK_MANIFEST_PATH"))
    print(f"wrote {page}")
    print(f"wrote {proof}")
