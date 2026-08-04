> Applies to: python/benchmarkmark/export.py|python/benchmarkmark/export_paths.py|python/benchmarkmark/export_metadata.py|python/benchmarkmark/export_manifest.py

# Benchmark export compatibility

## Rules

- Preserve the benchmark artifact directory contract as `.spectrafit_reports/<category>/YYYY-MM-DD_run_NNN/`. Do not silently switch helper modules to a nested `YYYY-MM-DD/run_NNN` layout without migrating all callers and tests together.
- Keep `ExportManager` and the `export_*` helper modules aligned to the same run-directory format, file names, and metadata keys. Refactors are incomplete if the helpers and manager disagree on those contracts.
- When extracting helper modules from `export.py`, wire the production `ExportManager` through those helpers immediately so tests exercise the real delegated path instead of an unused side implementation.
- Validate any generated artifact manifest against the files actually written in the run directory. If you add manifest helpers, return or persist the manifest from the same code path that writes the artifacts.

## Do not

- Do not introduce a new export helper module that is never called by `ExportManager`.
- Do not change `run_directory`, `report_files`, or artifact file-name semantics in metadata without updating benchmark tests and documentation in the same change.
