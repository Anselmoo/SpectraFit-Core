> Applies to: frontend/**/*.{tsx,jsx}

# Frontend modular JSX structure

Keep frontend UI code modular and easy to edit by default.

## Rules

- Build pages from small JSX/TSX components; keep orchestration in top-level files and move view logic into colocated component modules.
- Split large render files into focused modules (`sections/`, `charts/`, `utils/`, `types/`) when a concern can be isolated without behavior changes.
- Keep each component responsible for one UI concern; pass data through typed props rather than reading cross-module globals.
- Extract inline client scripts and long style blocks into dedicated frontend modules when they exceed simple glue code.
- Keep JSX markup declarative; move heavy data shaping into utility functions before rendering.
- Preserve stable component APIs and DOM data-attributes used by existing tests and report contracts.
- Reuse existing shared components before adding new parallel variants.
- Name files and exports by responsibility (`CaseSection`, `ScalingSection`, `...Chart`) and keep naming consistent across imports.

## Do not

- Do not add new feature logic directly into monolithic entry files when an existing section/component module is available.
- Do not duplicate JSX blocks across multiple sections; extract shared components.
- Do not couple rendering components to Python/export-layer concerns.
- Do not use plain `.jsx` in TypeScript areas when `.tsx` is already the project standard.
