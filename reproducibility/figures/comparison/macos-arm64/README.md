# NIST agreement tables from macOS arm64 (v0.1.0 archive)

These three files are the NIST StRD tables that v0.1.0 shipped in
`reproducibility/figures/`, moved here unchanged. They are kept for comparison;
the tables of record are the ones in `reproducibility/figures/`, which record the
host that produced them.

| | |
|---|---|
| Generated | 2026-08-16 (first committed then; the files record no date) |
| Host | macOS arm64 (Apple silicon). The machine is not recorded in the files. |
| spectrafit-core | the code of v0.1.0; the files record no build |
| Comparators | lmfit 1.3.4, SciPy 1.18.0, NumPy 2.5.1 |

**What is established about them.** The v0.1.0 PyPI wheel on an Apple M1 Pro
(macOS 27.0.1, Accelerate) reproduces 88 of the 108 cells of
`nist_table2.json` bit for bit: every spectrafit-core, sigma, lmfit and
SciPy `lm` cell; `nist_head_to_head.json` is reproduced exactly apart from the
wall-clock `ms` fields. The 20 remaining cells are all SciPy `trf`, which calls
LAPACK on every step; neither Accelerate on that machine nor OpenBLAS reproduces
them, so the LAPACK the archive was made with is not known.

**Why they differ from the tables of record.** On Linux x86-64 the same release
gives different last significant figures, in spectrafit-core's own columns as
well as in the comparators' (up to 2.3 significant figures on Misra1b at 1e-12).
On two different x86-64 Linux CPUs spectrafit-core's columns were identical,
while lmfit and SciPy moved. The agreement with the certified values stays far
above four significant figures for spectrafit-core on every host; which solver
is the most accurate on a given dataset can change between hosts when the
differences are in the last digits.
