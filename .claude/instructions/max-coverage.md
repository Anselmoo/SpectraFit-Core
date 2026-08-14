> Applies to: **/*.{py,rs}

# Maximize test coverage for Python and Rust

This instruction enforces clear, verifiable rules to keep and raise test coverage for both `python/` and `src/` (Rust) sources. Follow these rules on every PR that adds or modifies `.py` or `.rs` files.

## Rules

- Scope: applies to all files matched by `**/*.py` and `**/*.rs`. Any PR touching `python/` or `src/` must include tests that exercise the new or changed behavior.

- Coverage thresholds (per-module and pragmatic default):
  - New Python modules: aim for >= 98% line coverage.
  - New Rust modules/crates: aim for >= 95% line coverage.
  - Repository-level target: 95%+ line coverage overall. CI should be configured to fail PRs that reduce overall coverage below the repository target or drop the touched-module coverage below the module threshold.

- Test location and style:
  - Python: place tests under `tests/` mirroring package layout (e.g., `tests/test_module.py` for `python/spectrafit_core/module.py`). Use `pytest` and `pytest-cov`.
  - Rust: put integration tests under `tests/` or unit tests inside modules with `#[cfg(test)]` and `#[test]` functions. Prefer small, focused unit tests for deterministic logic.

- Measurement & reporting (verifiable):
  - Python: produce a coverage XML using `pytest --cov=python --cov-report=xml:coverage-python.xml` and attach it to the PR or let CI upload it to the coverage service.
  - Rust: produce a coverage report (recommended tools: `cargo-tarpaulin` or `grcov`) and attach an XML/LCOV artifact for CI consumption.
  - PRs must include the coverage delta for the touched modules (increase/neutral/decrease). If coverage decreases, the PR body must state a short mitigation plan.

- Determinism & flakiness:
  - Tests must be deterministic. For any randomized test, fix and document the seed so CI runs are reproducible.
  - Flaky tests must be clearly marked in the test name or metadata and excluded from enforced thresholds with a short justification and linked issue for stabilization.

- Exemptions:
  - Generated code, large experimental prototypes, or third-party vendored code can be exempted only when the PR includes an explicit exemption section and a linked issue describing why coverage cannot be achieved now and a remediation plan.

## PR checklist (required)

- Add or update tests that cover the changed code.
- Include coverage artifacts (XML/LCOV) in CI or attach them to the PR.
- State the coverage delta for touched modules in the PR description.
- If an exemption is requested, add a link to the tracking issue and a short justification.

## Do not

- Do not merge code changes to `python/` or `src/` without tests unless an approved exception is recorded in the PR and linked to a tracking issue.
- Do not silence or remove coverage reporting from CI to bypass thresholds.

## How to run locally (recommended)

Python (local quick check):

```bash
python -m pip install -U pytest pytest-cov
pytest --cov=python/spectrafit_core --cov-report=xml:coverage-python.xml
```

Rust (recommended, example using cargo-tarpaulin):

```bash
# install: cargo install cargo-tarpaulin
cargo tarpaulin --out Xml --output-dir coverage || true
# or use grcov in CI where required to produce lcov/xml artifacts
```

## Validation checklist

- [ ] Every rule is imperative and verifiable (no soft language).
- [ ] `applyTo` pattern is precise: `**/*.{py,rs}` covers source files.
- [ ] Commands above are platform-agnostic and reference common coverage tools.
- [ ] Exemptions require a linked issue and explicit PR justification.

---

Recommended path: `.github/instructions/max-coverage.instructions.md`
Recommended scope: workspace-wide (applies to all contributors and CI)
