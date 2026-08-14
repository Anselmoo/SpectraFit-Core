> Applies to: frontend/render_report.tsx|frontend/tailwind.config.js

# Benchmark theme extraction

## Rules

- HTML aesthetics and layout parameters must be governed strictly within the frontend React (TSX) and Tailwind setup.
- Prefer Tailwind utility classes and semantic token mappings over ad-hoc inline styling.
- The view layer is fully decoupled from the JSON export pipeline. Do not introduce HTML styling properties or theme settings into `python/benchmarkmark/report.py` or JSON payloads.
- Maintain light/dark themes using Tailwind's `dark:` pseudo-classes instead of injecting separate CSS payload blocks from Python.
- Use neutral semantic color families (slate/blue/green/amber/red) rather than brand-locked Material palettes.

## Parallel rendering guidance

- Structure JSX report rendering so per-case sections (fit evidence, residual proof, summary rows) are safe for parallelized generation.
- After parallel generation, merge sections with stable deterministic ordering by case key.
- Parallelization must preserve benchmark table/evidence contracts unchanged.

## Do not

- Do not hardcode hex values in Python payload generation scripts.
- Do not try to synchronize Python Matplotlib configurations for benchmark exports; they have been completely removed.
- Do not embed CSS variables in Python strings.
