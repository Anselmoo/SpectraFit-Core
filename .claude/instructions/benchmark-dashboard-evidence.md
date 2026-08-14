> Applies to: python/benchmarkmark/reporting.py|frontend/render_report.tsx

# Benchmark dashboard evidence

## Rules

- Every benchmark dashboard artifact must include both:
  - a function-evidence view
  - a dedicated residual evidence / fit-quality proof view
- Treat this requirement as mandatory for:
  - aggregate quick dashboards
  - per-problem one-pagers
  - detailed benchmark report pages
- For aggregate dashboards that summarize multiple scenarios, include scenario-level evidence cards or galleries so each scenario still shows both plots.
- Embed matplotlib figures as `<img src="data:image/svg+xml;base64,...">` (base64-encoded SVG). Never inject raw matplotlib SVG strings inline into the HTML body — matplotlib SVG contains font path data and XML declarations that the browser's HTML parser renders as visible body text when uncontained by an `<img>` element.
- Reserve inline `<svg>` injection only for icon SVGs under 2KB with no embedded fonts or path coordinate data.
- Use dimension-aware plotting rules:
  - 1-D: signal/fit curve + residual plot
  - 2-D: coordinate projection colored by observed/fitted value + residual projection
  - 3-D: 3-D projection + 3-D residual proof
  - higher-D: projected evidence with explicit disclosure of which dimensions are shown
- When a single backend must be chosen for a residual proof panel, prefer `spectrafit`, then `lmfit`, then `jax`, unless the page explicitly documents another choice.
- Quality-proof captions should name the proof backend and surface at least one numeric quality indicator such as reduced χ².
- Keep charts visually subordinate to tables and summary metrics: bound figure containers with a reasonable `max-height` and `overflow` behavior so tabular evidence remains the primary decision surface.
- When a benchmark template uses Chart.js with `maintainAspectRatio: false`, give every summary canvas an explicit bounded CSS height and ensure the runtime selector targets the same chart container class used by the template markup.
- In `frontend/render_report.tsx`, when emitting injected `<script>` content from TypeScript template strings, never nest unescaped JavaScript template literals (`` `...${...}` ``) inside the emitted string; use string concatenation or escaped placeholders to keep the TS source parseable.

## Do not

- Do not ship a dashboard page that only shows timing/leaderboard summaries without any function or residual evidence.
- Do not hide higher-dimensional fallbacks; always disclose when a projection is being shown.
- Do not let charts expand without bounds or push tables out of primary view in HTML benchmark reports.
- Do not rely on intrinsic canvas sizing for local file reports; unbounded Chart.js canvases can stretch to page-height and effectively hide the plotted data.
- Do not replace residual proof with decorative status chips alone.
