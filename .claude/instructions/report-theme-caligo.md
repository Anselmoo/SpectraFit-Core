> Applies to: frontend/render_report.tsx

# Benchmark report theming (Caligo OKLCH Inversion)

## Rules

- **Base Space**: Use OKLCH (`oklch(L C H)`) for all color definitions to ensure perceptual uniformity.
- **Canonical Seed (Midnight Butterfly)**:
  - Base Dark: `oklch(14% 0.02 250)` (Deep Navy)
  - Base Light: `oklch(98% 0.02 250)` (Cool White)
- **Inversion Logic**: Generate the light mode by inverting the Lightness ($L$) value of the dark mode ($L_{light} \approx 100 - L_{dark}$), while keeping Chroma ($C$) and Hue ($H$) constant.
- **Semantic Mapping**: Use semantic CSS tokens (`--surface`, `--surface-low`, `--surface-high`, `--heading`, `--text`, `--muted`, `--line`) with these OKLCH shifts.
- **Accent Families**:
  - Blue: Informational (spectrafit) -> `oklch(70% 0.18 250)`
  - Green: Success (lmfit) -> `oklch(70% 0.18 145)`
  - Amber: Warning (jax) -> `oklch(70% 0.18 70)`
  - Red: Failure -> `oklch(65% 0.18 25)`
- **No White Flash**: Theme detection and variable injection MUST be placed in a blocking `<script>` within the HTML `<head>` before the body renders.
- **No Gray-Out**: Avoid pure grays (`C=0`). Use $C \approx 0.01-0.02$ to keep the surface biased toward the theme hue.

## Do not

- Do not use hex codes or RGB/HSL in the TSX components or CSS definitions.
- Do not manually pick "pleasing" colors for light/dark modes—rely on the mathematical inversion.
- Do not allow brand-locked palette dependencies in benchmark templates.
- Do not remove theme toggles from report templates.
