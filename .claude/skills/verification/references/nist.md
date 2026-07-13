# NIST reference — StRD fixtures and certified-data harnesses

Self-contained essentials. Historical specialist content lives in git
history under `.claude/skills/nist-strd-runner/`.

## What StRD is

The NIST Statistical Reference Datasets (StRD) provide certified
solutions for nonlinear regression problems with known answers to
~12 significant digits. They are the canonical "did your fitter get
the right answer?" oracle.

## Fixture protection (CRITICAL)

The `protect-nist-fixtures.sh` hook is **BLOCKING (exit 2)**:

- Path: `tests/fixtures/nist_strd/`
- Reason: verbatim NIST certified data; any hand-edit corrupts the
  oracle.
- Only update path: re-fetch from `itl.nist.gov` and replace the file
  wholesale.
- This protected against the Cycle 16 Eckerle4 incident.

## What the harness does

1. Loads the NIST `.dat` for a problem (e.g. Misra1a, Lanczos1,
   Eckerle4).
2. Reads the certified parameter estimates and standard deviations.
3. Runs spectrafit (and the oracle backends) from the StRD starting
   values.
4. Asserts the fitted parameters agree to N significant digits with
   the certified values.

## Reading certified files

The `.dat` files have a fixed structure: header (problem name, model
formula), certified values block, then the data rows. Use the existing
loader in `tests/conftest.py` or `tests/fixtures/nist_strd/load.py`
(check via `mcp__serena__find_symbol load_nist_strd`).

## Stuck-mode entry

A NIST test that reopens after a "fix" is almost always a starting-
value drift or a units mismatch. The certified data is the truth.
Curiosity sub-cycle: `mcp__serena__find_referencing_symbols` on the
loader, then check whether a recent edit changed the starting-value
convention.
