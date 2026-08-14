> Applies to: python/benchmarkmark/report.py|frontend/render_report.tsx

# Benchmark table contract

## Rules

- Render benchmark report tables with this required column order:
  - `Backend`
  - `Median ms`
  - `IQR ms`
  - `CV%`
  - `R²`
  - `χ²red`
  - `MSE`
  - `AIC`
  - `BIC`
  - `n_iter`
  - `n_reps`
  - `Speedup vs lmfit`
  - `Status`
- Keep required column labels exact and stable; do not rename them, reorder them, or drop units/symbols to make the table easier to style.
- Treat these fields as optional extensions only:
  - `cold start ms`
  - `param_stderr` JSON/details
  - `nfree`
- Optional columns may be shown when available, but they must never replace or obscure the required columns.
- Keep backend-details compatibility markers stable in report HTML when details blocks are present:
  - summary text `Fit values + MSE`
  - legacy schema marker `<dt>MSE</dt>`
- When any table value is missing, render an em dash (`—`) instead of leaving the cell empty or showing `null`/`None`.
- Apply the same missing-data rendering rule to required columns, optional columns, and summary rows.

## Do not

- Do not emit blank `<td>` cells for missing values.
- Do not use ASCII hyphens, empty strings, or placeholder words in place of the em dash.
- Do not introduce backend-specific column variants that break the shared contract.
