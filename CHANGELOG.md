# Changelog

All notable changes to `spectrafit-core` will be documented in this file.

This project follows repository release policy enforced by `repo-release-tools`.

> **Release status — nothing below has been tagged or published.**
> No version tag exists in this repository (`git tag -l` lists only `pr/*` refs,
> on the primary remote as well), and there is no `spectrafit-core` project on
> PyPI. The `[0.1.0b1]` and `[0.1.0a1]` sections below record the dates on which
> those version bumps were *prepared in-tree*; neither was ever cut as a release,
> so neither date is a release date. `CITATION.cff` omits its `date-released`
> field for exactly this reason.
>
> The package currently ships as **`0.1.0`** (`pyproject.toml`, `Cargo.toml`).
> Everything since the `0.1.0b1` bump — including that version's own promotion to
> `0.1.0` — is collected under `[Unreleased]` below, and will be folded into the
> first `[0.1.0]` section when a release is actually tagged and deposited.

## [Unreleased]

### Fixed
- **GitHub mirror's Docs & Pages build hard-failed on a source file the mirror
  never has (2026-08-23).** `docs/_render_references.py` reads
  `manuscript/draft/references.ris` to generate `docs/references.md`, and
  correctly treats a missing source as fatal — but `manuscript/draft/*` is
  deliberately excluded from the GitHub mirror, so on that remote the file
  can never exist and the `Docs & Pages` workflow failed on every run.
  `.github/workflows/docs-pages.yml` now writes an honest placeholder
  `references.md` when the RIS source is absent instead of calling the
  script, keeping the `zensical.toml` nav entry (and the internal
  link-resolution gate) satisfied; `docs/_render_references.py`'s own
  hard-fail-on-missing contract is unchanged and still applies on GitLab.
- **GitHub mirror CI broken by a stale architecture-tree entry (2026-08-23).**
  `ADR-INDEX.md` was added to `scripts/publish_exclusions.py`'s GitHub mirror
  exclude list on 2026-08-21 but never registered in
  `render_architecture_tree.py`'s own `EXCLUDED_PATHS`, so the committed
  `docs/contributor-guide/architecture.md` tree snapshot kept listing a file
  the mirror never has. The mirror's `lint` job and `pre-merge-arch-tree`
  pre-commit hook regenerate the tree from the actual (stripped) filesystem
  and diff it against the doc, so this failed on every GitHub Actions run —
  `main` and every open Dependabot PR — since the exclusion was added.
- **VarPro reported permuted standard errors (2026-08-21).** `fill_parameter_stderr`
  walked the covariance diagonal in VarPro's *internal* solve order — the nonlinear
  alpha keys first, then the linear amplitude coefficients — but the matrix it
  indexed comes from `jacobian_compiled`, whose columns follow
  `CompiledGraph::free_keys` (node-id sorted, then model-param order: amplitude,
  center, sigma). That is a genuine 3-cycle, not a swap: amplitude was handed
  center's error bar, center was handed sigma's, sigma was handed amplitude's. On a
  symmetric Gaussian, center and sigma carry numerically equal variances, so it
  presented as a plain amplitude/center transposition and hid the third leg.

  Fitted values were never affected — only the uncertainties. Amplitude's 1-sigma
  coverage measured **11 % (11/100)** because it was shown center's much tighter
  bar; center measured **100 %** because it was shown amplitude's much wider one.
  After the fix, at N=100 and seed 20260821: amplitude **68 %**, center 78 %,
  sigma 56 % — all inside the [54 %, 82 %] acceptance envelope. Two
  `xfail(strict=True)` marks in `tests/unit/spectrafit_core/test_recovery_coverage.py`
  become ordinary passing assertions, and a new `test_varpro_stderr_vector_matches_lm`
  pins the whole stderr vector across lm/trf/varpro so a rescale cannot pass where a
  permutation failed.

  The fix is to index by name against `compiled.free_keys`, which is what the LM and
  TRF path already did in `spectrafit-solver::postfit::build_parameter_results`.
  `FitResultSpec::covariance_param_order` advertised the same wrong order and now
  reports `free_keys` too — `covariance` is `None` on the VarPro path today, so
  nothing consumed it yet, but it was primed to fire the moment the matrix is
  exposed. The upstream `varpro` crate's Kaufman (1975) Jacobian approximation is
  untouched: this corrects indexing only, and the covariance remains approximate by
  construction on that path.

- **Floating-point values crossing the PyO3 boundary could round to a different
  double than the one that went in (2026-08-21).** Every `#[pyfunction]` returns a
  JSON string, so every `f64` entering Rust is re-parsed by `serde_json`. Its
  serializer is correctly rounded by default; its deserializer is best-effort
  unless the `float_roundtrip` feature is enabled, and the workspace pinned
  `serde_json = "1"` with no features at all. Measured over 2000 random `f64`s:
  **589 of 2000 came back 1 ULP off** — e.g. `5.114226694005648e+71` parsed as
  `5.114226694005649e+71`, the next representable double up. Enabling the feature
  re-measures at **0 of 2000**.

  The loss was on the way *in* (Python -> JSON -> Rust), so it perturbed x, y, sigma
  and initial guesses on entry rather than results on the way out. The practical
  impact was already bounded before the fix was made: the companion significant-digits
  measurement (below) shows the computation is stable to 14.61 significant digits
  under exactly this perturbation. The fix is one line and was taken anyway.

  Pinned by `tests/parity/test_pyo3_float_roundtrip.py`, whose two
  `xfail(strict=True)` marks become ordinary passing assertions. A genuinely separate
  finding is pinned there as a passing regression test rather than fixed: a
  kernel-produced non-finite value serialises to JSON `null`, which is
  indistinguishable on the wire from a legitimately uncomputed `stderr` or
  `condition_number`. `float_roundtrip` fixes the parser, not the serialiser, so
  that collapse is correctly unchanged.

- **The rat43 NIST StRD fixture certified the wrong degrees of freedom
  (2026-08-21).** Fifteen observations minus four certified parameters is 11, not
  the 9 the fixture carried — rat43 was the sole violator of that invariant across
  all 22 NIST StRD fixtures. NIST's own dataset URL now 302s to a landing page, so
  the citation could not be used to settle it; the dataset validated itself instead.
  `sqrt(RSS/11)` = `2.8262414662e+01` reproduces NIST's published residual standard
  deviation **exactly, to eleven significant figures**, while `sqrt(RSS/9)` =
  `3.1245275035e+01` matches nothing. Corrected in both the header line and the
  constant in `python/oracles/nist_strd/rat43.py`, with the evidence recorded in the
  docstring the way `gauss3` and `mgh17` already record their corrected tier strings.

  Three earlier reviews flagged this and dismissed it as pre-existing and out of scope.
  They were right that it predates this work and wrong that it did not matter: a wrong
  certified reference value on a verification-hardening branch is not deferrable.

- **Three published model formulas were wrong (2026-08-21).** `log_normal`'s docstring
  gave the argument as `ln(x) - c` where the implementation computes `ln(x/c)`;
  `split_pearson7` omitted the `(2^(1/m) - 1)` factor; `explain()` reported a condition
  number on the wrong axis. Also disclosed rather than changed: `chi2` is unweighted,
  and the DOF clamp is now stated where a reader meets it. Documentation only — no
  numerical behaviour changed, and the OpenAPI goldens were regenerated because these
  strings are contract text.

### Added
- **The credibility ladder's rung-3 hole is closed: significant digits are now
  measured (2026-08-21).** The ladder claimed rung 5 while never measuring how many
  digits of its own post-fit statistics are meaningful. `scripts/measure_significant_digits.py`
  measures it by ULP-perturbation Monte-Carlo (N=50, `s = -log10(sd/|mu|)`):
  `chi2` and `reduced_chi2` are the tied worst at **14.61 significant digits**;
  everything else lands between 14.89 and the float64 noise floor. An over-precision
  audit across `python/oracles/`, `web/src/` and `docs/tutorials/gallery/` found
  **none** — the tightest formatter is `r_squared` at `.10f`
  (`docs/tutorials/gallery/shared_params.py:239`) against a measured >15.9 digits, so
  every reported quantity carries more digits than any formatter prints. Rung 3 now
  has all three legs: metamorphic relations, condition number, and measured digits.
  Written to `analysis/vv/significant-digits.md`.

- **An uncertainty budget split into numerical, model-form and input terms
  (2026-08-21).** All three quantified, none left pending. Numerical error is
  **~6.6e-11 sigma** — ten or more orders of magnitude below the input uncertainty
  (1 sigma, the reference scale). The dominant term by a wide margin is **model-form
  error**: fitting a Gaussian against a true-Voigt truth biases the amplitude by
  **4.75x its own reported standard error** (-2.85 % relative).

  The consequence is worth stating plainly, because it redirects effort: numerical
  precision is not where this project's error lives. Effort spent there would be
  wasted; effort spent on model selection and adequacy is where the error actually
  is. That could not have been said before the measurement. The method is an
  one-at-a-time sensitivity sweep, explicitly labelled *not* Sobol, with its
  interaction-blindness stated. VarPro is excluded from every measurement, with the
  permuted-stderr defect above and the Kaufman-approximation caveat recorded in the
  document. Written to `analysis/vv/uncertainty-budget.md`.

- **Surrogate oracles — relations that must hold with no known answer
  (2026-08-21).** Four new suites covering what certified values cannot:
  `tests/parity/test_solver_invariance.py` (all ten dispatch arms reach the same
  optimum, within ~1e-10 relative of the lm reference, with no per-arm tolerance
  override needed); `tests/parity/test_varpro_equivalence.py` (VarPro must match full
  LM, and the Jacobian variant is now documented in `crates/spectrafit-varpro/src/lib.rs`);
  `tests/unit/oracles/test_graph_metamorphic.py` (superposition, `evaluate_components`
  cross-check and JSON round-trip, all at max deviation exactly 0.0); and
  `tests/unit/oracles/test_tied_parameter_uncertainty.py` (both tie mechanisms —
  `ExprEdge` and `Parameter.expr` — report `stderr is None` on the tied parameter, so
  the target's uncertainty never leaks; DOF 175 = 174 + 1). The trust ledger's
  "Tied-parameter uncertainty: MISSING" row becomes HAVE.

- **Analytic Jacobians are now checked across every kernel, in multiple regimes
  (2026-08-21).** Four kernels had no analytic-Jacobian cross-check at all; the other
  eighteen had one-sided finite differences at a single point. All twenty-two now use
  central differences swept across centre, near-centre and far-field, with zero
  surviving one-sided quotients.

  Two of the resulting failures were real and are worth separating. `cauchy_dispersion`
  was a genuine finite-difference artefact, confirmed by an h-sweep in which the FD
  estimate swung orders of magnitude while the analytic value stayed pinned at 1.0.
  `rational_cubic` was **not**: Kirby2 has `b3 = 0` exactly, which collapses a
  parameter-relative step to its absolute floor of 1.0, which the cubic denominator
  then amplifies catastrophically. The first fix capped the tested domain at x <= 5
  and so hid a real coverage gap — `rational_cubic` backs Kirby2 (x to 371),
  Hahn1 (x to 852) and Thurber, which are the project's only external validation
  anchor, leaving ~99 % of two datasets' actual domain unverified. Replaced with a
  D-relative, x-aware step that restores coverage to x = 850.

### Changed
- **All 22 NIST StRD data modules now carry one `Attributes:` section
  (2026-08-21).** The certified constants were documented by scattered PEP-224
  attribute docstrings, four per module; they are now consolidated into a single
  Google-style section per module, pinned by a new gate
  (`tests/meta/test_nist_strd_docstring_shape.py`) that accepts both the bare
  `NAME: description` and the type-annotated `NAME (type): description` form already
  used elsewhere in the repo. Every constant's value is byte-identical, verified by an
  AST `literal_eval` comparison of all seven constants across all 22 modules against
  the pre-change tree. Three `Cross-check: sqrt(RSS/DOF) = ...` prose lines were
  dropped as a derived identity whose operands both remain documented;
  `CERTIFIED`'s do-not-round instruction was preserved, because an instruction is not
  a derivation.

- **The unwired `.claude/validators/` layer is gone; three pre-commit hooks are
  registered (2026-08-21).** See the ADR of the same date for the full reasoning.
  `.pre-commit-config.yaml` claimed three times that semantic analysis ran through
  `pydantic_edit.py`; that layer had never been registered as a hook. Deleted rather
  than wired, because it duplicated checks the `pre-merge-*` shell hooks already
  enforce live. `warn-match-dispatch.sh` and `warn-tag-residue.sh` are added
  warn-only, sharing one detection module with the existing PreToolUse hook so the
  two copies cannot drift.

### Added
- **Two figures answering whether the speed is bought with accuracy
  (2026-08-18).** The stability figure plots one quantity on both of its axes,
  geometric-mean speedup against repetition depth and against random seed, and
  carries accuracy only as a footnote. A benchmark that reports speed alone
  cannot answer the question a reader has, and this project's own argument is
  that agreement on the residual is the weaker test, so a speed-only stability
  result is the same blind spot the manuscript criticises in FitBenchmarking.

  `fig_speed_accuracy_joint.py` draws the joint view on all three axes. Depth
  moves speed by 4.2 % and *cannot* move accuracy, which the shipped artifacts
  confirm: `max_abs_delta_r2` is bit-identical at all five rungs. Across the 50
  seeds it is not invariant at all, taking 50 distinct values spanning a factor
  of 1111, and speed and accuracy are uncorrelated there (r = -0.02). Per case
  against lmfit, all 151 are faster and the parameter-recovery ratio lies
  between 8.5 % better and 3.2 % worse for every case bar CX-017.

  **The footnote it was written against is wrong on one of its two axes.**
  `fig_ladder_stability.py` prints "accuracy invariant across both axes",
  computed as the maximum over rungs *and* seeds, which turns "the worst value
  is bounded" into "the value does not change". `validation.md` said the
  opposite in prose the whole time. Left in place for now; correcting it is an
  editorial decision about Figure 5.

  `fig_weighted_win.py` answers the follow-up: a win that small is not a win.
  It applies an equivalence margin, sweeping it rather than picking one, with
  both comparisons put in the log-relative error so a single margin means the
  same thing in each. Against NIST's certified values the win survives, 19 win
  / 2 tie / 1 loss of 22 at half a significant figure, still 11 wins and no
  losses at a full two figures. Against lmfit on our own suite it evaporates:
  the raw 56-win / 72-loss count reaches zero wins at a margin of **0.039**
  significant figures, and even CX-017 is only 0.22 of one.

  The consequence worth acting on is that the accuracy claim rests on NIST and
  not on the head-to-head, which is the stronger position: NIST is external to
  this project and the head-to-head is not. The composite win rate quoted as
  "133 of 151, scored on r^2 times speedup" is the claim most exposed, because
  it multiplies a real speed difference by an accuracy difference that is below
  any defensible margin.

  Both are analysis figures rather than manuscript figures: unregistered in
  `manuscript-state.json`, like the eight already in that directory, and both
  byte-reproducible under the pinned epoch.

### Fixed
- **`rational_cubic`, `generalised_logistic` and `exp_over_linear` are now
  fully wired, not just kernel-registered (2026-08-18).** The commit that
  added these three model kernels and the twelve new NIST StRD fixtures
  wired the Rust kernel, `ModelType`, and `evaluate`/`jax_evaluate`, but left
  the VarPro separability guard, the bench case registry, the compose-DSL and
  jax-parity test fixtures, and a NIST dataset-count assertion (still
  hardcoded at 10 instead of 22) unfinished — all four CI test jobs on this
  branch were red as a result. Completed the chain: VarPro classification
  (`rational_cubic`/`exp_over_linear` non-separable, `generalised_logistic`
  eligible-but-deferred), three new bench-case lineshape recipes, the missing
  test fixtures/envelopes, and the corrected dataset count.

  **Follow-up (same day):** completing that wiring legitimately grows the
  benchmark catalog 151 -> 154 cases (127 -> 130 JAX-eligible), which drifted
  two purely-structural doc/test counts —
  `docs/reference/models/catalog-roadmap.md`, `docs/contributor-guide/
  architecture.md`, and `tests/meta/test_manuscript_jax_coverage.py`'s
  `EXPECTED_TOTAL`/`EXPECTED_ELIGIBLE` — now updated to match. Left
  deliberately untouched: `manuscript/draft/sections/evidence.md`, which
  quotes the same old denominators alongside benchmark-derived numbers
  (fastest-count, planted-truth count, geometric mean, win rates) that can
  only be corrected honestly by re-running the benchmark against the grown
  catalog — flagged in the test file, not silently edited.

- **The docx render is now actually byte-reproducible (2026-08-18).** The
  manifest's staleness design rests on it, and its docstring asserted it, but
  pandoc stamps wall-clock time into `docProps/core.xml` as `dcterms:created`
  and `dcterms:modified`. Two renders of identical input therefore differed, and
  every commit that round-tripped the file reported `STALE: MANUSCRIPT.docx` for
  a document nobody had touched — which trains a reader to ignore exactly the
  signal that would catch a genuinely stale submission. Pandoc honours
  `SOURCE_DATE_EPOCH`, so one variable fixes it, using the same fixed constant
  `render_figures.py` adopted after the same failure with the figures.

### Changed
- **The manuscript, rebuilt against the first outside review (2026-08-18).** A
  three-persona panel (skimming reader, peer reviewer, handling editor) returned
  a verdict of *return before review* with 19 anchored Word comments. Its
  blocking reason — no release, no registry, no archival DOI — is deliberately
  **not** acted on here: a Zenodo deposit is immutable, so minting one against a
  manuscript under revision means minting a second one later. Tag, wheel and DOI
  are the last step, and the Availability section still states every absence
  plainly.

  Structure: the hand-added *Validation* section is dissolved into Quality
  control, which the venue's Overview actually has. All 261 claims re-homed,
  none dropped; the superseded prose is kept under `sections/_superseded/`
  because its longer treatments have no other home yet. The worked example is
  cut from 1,460 words to a capability demonstration that keeps the C-versus-D
  verdict and its bridge to CX-017. A new Table 3 replaces the denominator
  carousel (151/147/146/131/127/124/93/31) the skimmer said they stopped
  tracking. The evidence-grade passage is deleted rather than defined, as the
  reviewer suggested. Every qualification survives, consolidated into one
  closing subsection instead of trailing each number.

  Prose: the abstract is rewritten as what it does, what a call looks like, the
  headline result, one boundary. First person restored throughout, per author
  decision — there had been exactly one "we" in the whole Overview. *expression
  edge*, *oracle*, *optfn* and *the ladder* are defined at first use; the
  chemistry motivation that had two sentences now opens the paper; a roadmap
  sentence closes the Introduction; the auto-routing gap is answered rather than
  only conceded; Reuse potential closes by re-joining the two halves.

  Word output: chemistry and oxidation states are sub/superscript text runs
  (`Fe L~2,3~-edge`, `[FeCl~4~]^-^`, `d^5^`), mathematics stays in Word's
  equation format with an explicit base, and no `$`-span may open on `_` or `^`.
  Listings 1-3 are fenced code rather than raster images of code, with their
  `.tex`/`.pdf`/`.png` left untouched on disk. Citations are Vancouver numerals.
  Footnotes are a Notes list before the references. Table titles sit on top,
  figures and listings beneath. Alt text is 468 words down to 72, captions 934
  down to ~500, with the long forms kept as `long_description` and
  `caption_long`.

  Word count: 10,833 to ~9,950. The target was ~6,000 and this misses it. The
  restructuring cut roughly 2,700 words and the review's own demands put about
  1,800 back. What remains is fact-carrying, so the next cut is a scientific
  decision rather than an editing one; `manuscript/review-2/RESPONSE.md` ranks
  the five candidates.

  A second round folded back 99 hand edits the author made directly in Word,
  which the next render would have destroyed: em dashes out (61 removed, none
  remain), clause-joining colons turned into full stops (39), table em-dash
  cells to `N/A`. One edit was **not** propagated — Word autocorrected
  `minimisers` to `minimizers`, against the British spelling used everywhere
  else.

### Fixed
- **Figure 3 draws scenario D, the row the paper's verdict argues from
  (2026-08-18).** The figure showed A, B and C. D was excluded deliberately, and
  the script's docstring argued the case: D is a single joint fit spanning both
  spectra, so a row of it puts two halves of one fit where every other row has
  two separate ones, and the row stops meaning what the rows above it mean.

  That is true and it was the wrong call. The paper's verdict *is* the
  C-versus-D comparison — pooled C buys a 9 % better residual with a 9.27 eV
  splitting that is below any 2p spin-orbit splitting iron has, while D lands at
  13.67 eV — so a figure without D asked the reader to take the comparison on
  trust. The author read the draft and asked where D was.

  D's 90-parameter joint vector already shipped in
  `fecl4_constraint_scenarios.json`, prefixed `a_` for the d5 half and `b_` for
  the d6 half. Splitting on that prefix gives each spectrum's curve exactly as
  the joint fit determined it, replayed through the same pure forward pass as
  every other panel. The ties are deliberately not re-declared: D's expressions
  name components in *both* spectra and cannot exist on a single-spectrum graph,
  and the stored values already satisfy them.

  The row is labelled "one joint fit, both panels", carries the joint 86 free
  parameters in either column, and shows no per-column reduced chi-squared
  because that quantity is not defined for it. The cross-check was extended to
  match: D is verified once, pooled, against the stored 0.008351 over 576
  degrees of freedom, and the prefix split is checked to yield 43 and 47
  parameters so a change to the bind expressions cannot pass silently. The
  receipt now reports eight panels agreeing with the table rather than six.

  The three-row rendering is kept rather than overwritten, under
  `manuscript/examples/fecl4/_superseded/`, with a README saying why: it is
  still the cleaner object when the point is only about the per-spectrum
  hypotheses.

### Fixed
- **The docx guards can now see what they were written to catch (2026-08-18).**
  Three defects that all had the same shape: a check that looked in one place
  and the fault living in another.

  `unresolved_styles()`, whose docstring says the silent Normal-fallback "cannot
  evade" it, matched `w:pStyle` in `word/document.xml` and nothing else. So it
  could not see `VerbatimChar`, which is a *character* style — and
  `VerbatimChar` was referenced but never defined, meaning every backticked
  identifier in the paper (`pseudo_voigt`, `MeasurementData(x, y, sigma=None)`)
  had been setting as ordinary Times body text with nothing on the page to say
  so. `FootnoteReference` and `FootnoteText` were undefined for the same reason.
  The guard now matches `w:pStyle`/`w:rStyle`/`w:tblStyle` across `document.xml`,
  `footnotes.xml`, `header1.xml` and `comments.xml`, and all four styles are
  defined.

  `scripts/audit_latex.py` reported the manuscript clean while the Word output
  had 12 empty equation boxes. `Fe L$_{2,3}$` puts the base *outside* the math,
  which is invalid LaTeX; pandoc rescues it with a U+200B base and Word draws
  the empty slot as a placeholder floating off the `L`. The audit now bans a
  `$`-span opening on `_` or `^`, flags unconverted `Fe3+`/`d5`/bare `sigma`,
  catches an unpaired `^` or `~` under the new reader extensions, and reads
  `manuscript-state.json` — which it never had, and where the figure captions
  live, so Figure 3's caption had kept a plain `(Fe3+, d5)` beside a correctly
  marked-up `[FeCl$_4$]$^-$` in the same sentence. The Word-path rules are
  scoped to the manuscript; `docs/` keeps the original three.

  `check_tables()` checked that a caption existed and not where it sat, so
  placement was held by nothing. It now enforces the house convention (table
  titles on top, figures and listings beneath) and fails either way round. New
  `check_figure_lengths()` holds the venue's caption and alt-text limits, and
  the image-count guard derives from a `rendered_as` field rather than assuming
  every registered listing is a raster.

  `extract_dependencies.py` spelled "eleven" into the generated dependency
  block, so applying the venue's number rule to the manuscript made the drift
  check fail on the manuscript rather than on the generator that caused it. Its
  number-word table now stops at nine.

### Changed
- **`manuscript/review-2/` is stripped from the public mirror (2026-08-18).**
  The exclusion list is an allowlist of what to *strip*, so a new `manuscript/`
  subdirectory ships to the GitHub mirror from the moment it exists. That
  trade-off is documented in `publish_exclusions.py`, and it has now come due a
  second time: `review-2/` holds an outside reviewer's panel report, their
  annotated Word copy carrying 19 anchored comments, and the author's response
  to it — private working material of exactly the same class as
  `manuscript/review/*`, which was added for the same reason three days earlier.
  A dated sibling of an already-stripped directory is the shape this failure
  keeps taking, so the comment now says plainly that whoever creates `review-3/`
  has to add it too. Both lists updated and pinned by
  `tests/meta/test_publish_exclusions.py`.
- **Figure 6's agreement panel is now readable without the legend
  (2026-08-17).** Shown the new dumbbell, the author asked which of the two
  backends was more accurate — of a panel built to answer that, and then asked
  whether the drawn curve was even spectrafit-core's. Neither question was about
  the data, which was right throughout; both were about labelling that named the
  backend *not* drawn and left the drawn one anonymous.

  Fixed: a vestigial lollipop stem ran from the pass threshold to
  spectrafit-core's dot *underneath* lmfit's ring, so a row read as one line
  with a ring sitting on it as a waypoint rather than as two values with a gap —
  removed, and the dumbbell is now the only line on a row. The legend's
  "fit (lmfit's coincides)" named the backend that is not drawn and left the one
  that is unnamed; it now reads "spectrafit-core fit". The axis said what the
  quantity was but never which way was better. Both the measure's name and its
  direction now sit in the third column's header — the column had no header at
  all, and the direction cue had been under the ticks, three thousand pixels
  below the point where a reader first meets the marks. The axis label is gone
  entirely, the definition of the measure moved to the caption, and the bottom
  margin closed by the 98px band the label had held. The legend is centred, on
  one row, at six columns.

  (For the record: on Rat42, the row that prompted it, spectrafit-core matches
  the certified parameters to 8.52 significant figures against lmfit's 6.17.
  Across all 22, spectrafit-core is ahead on 21 and lmfit on one, Lanczos1.)

- **Figure 6 groups its tiers by position, and draws lmfit beside
  spectrafit-core (2026-08-17).** Three attempts to make hue carry tier
  membership all failed the same way — a 5.87x luminance spread, then 12.33x,
  then one ink at three derived opacities. Each was a better *ordinal* encoding
  and none answered *which tier is this row in*, because that question needs a
  comparison against rows up to twenty away and colour is a poor grouping
  channel at 22 rows of this height. Membership moved to position: a serifed
  bracket in the left margin spanning each tier's rows, beside the row names
  where the reader starts, plus a boundary hairline across the full width. The
  ink reverted to the hand-picked blues and now carries rank only, redundantly
  with position.

  The agreement panel now draws both backends as a dumbbell per row —
  spectrafit-core filled, lmfit as an open ring, joined by the gap between
  them. `nist_head_to_head.json` already carried lmfit's figure, so nothing was
  re-run. This is where the paper's own argument is visible in one picture: the
  two fitted curves differ by 5e-14 to 8e-7 of a dataset's range, which is why
  only one is drawn, while the parameters recovered from them differ by up to
  3.46 significant figures and by at least one on **17 of the 22** datasets.
  The residual difference was considered and declined: subtracting the two
  residual arrays cancels the observations exactly and leaves a ~1e-8 curve
  difference standing in for a 3.46-significant-figure disagreement — the same
  substitution of cost-function space for parameter space this paper faults
  FitBenchmarking for.

### Added
- **Two gallery pages about being wrong (2026-08-18).** Every one of the
  fourteen existing pages ends `success=True`, which taught readers nothing
  about how the library reports trouble. `failed_fit.md` runs three fits of one
  dataset: one returns `success=False` naming `degenerate_fit`, one returns
  **`success=True` with $r^2 = -0.53$**, and one recovers the planted truth from
  the second's own starting guess by switching to `solver="global"`. The middle
  case is the point -- the demotion rule in
  `crates/spectrafit-solver/src/postfit.rs` fires only when a free amplitude
  falls below 1% of `max |y|`, and this fit landed at 2.7%, so a converged fit
  that is worse than a flat line reports success. Behaviour documented, not
  changed.

  `misspecified_model.md` fits the measured FeCl4 L-edge with a ladder of three
  models. $r^2$ climbs 0.872 -> 0.991 and AIC falls by 300 while a
  Wald-Wolfowitz runs test on the residuals stays at $z \approx -8$ at every
  rung: both scalar scores are order-blind, and the residual keeps its shape
  while shrinking its amplitude. The page carries the Wasinger citation and the
  spectra's by-permission carve-out, and states the oversampling caveat that
  stops the runs $z$ being read as a calibrated p-value.

### Added
- **Tier B review panel and desk-reject tribunal run against the draft
  (2026-08-18).** Seven reviewers in one parallel batch -- the five defaults for a
  software paper plus a working spectroscopist with no coding background and a
  hostile numerical-methods referee -- then a blind advocate/prosecutor tribunal and
  an adjudicator on the record. 88 findings, all quotes verified verbatim against
  the draft; 1 finding rejected and recorded with its refutation. Verdict
  `escalate-to-author`: six of ten blocking criteria pass, four fail, no ties, with
  the escalation fired by `install-instructions-present` passing at 0.74 confidence.
  Written to `manuscript/review/`; the prior 2026-08-15 panel is preserved under
  `manuscript/review/archive/2026-08-15/`.

### Fixed
- **The submitted docx had unruled tables, no equations, and build plumbing in
  its captions (2026-08-18).** Three separate defects in what a reviewer opens.

  *Tables.* They were already real Word tables -- four `w:tbl` elements -- but
  the JORS template defines no `Table` style, and Word resolves an unknown style
  id to nothing *silently*, so all four rendered without a single rule.
  `render_manuscript.py` now injects a `Table` style alongside the paragraph
  aliases it already supplied: three horizontal rules in the scholarly
  convention (top, under the header, bottom), no vertical lines, header row bold.
  Pandoc was already emitting `tblHeader`, so headers now repeat across pages.

  *Equations.* The docx carried **zero** OMML elements because the manuscript
  carried zero `$` -- every formula was running text. Pandoc converts `$...$` to
  real Word math natively, so this was a source problem throughout. The reason it
  survived to a full draft is that `scripts/audit_latex.py` audited `docs/**`
  only and had never looked at the manuscript; it now covers
  `manuscript/draft/sections/*.md` too, taking the audit from 51 files to 66.
  Symbols and prose formulas are LaTeX now; numeric table cells keep plain
  e-notation, which is standard in a data column and would only add noise as
  math.

  *Captions.* Every figure and table caption ended in a "Generated by
  `<script>.py` from `<artifact>.json`" sentence -- build plumbing in the reading
  flow, and duplication besides: the state file already records exactly that in a
  `derivation` field the renderer never emits. Those are gone. The three heaviest
  captions (274/297/281 words) are cut to what a reader needs to decode the
  panels; the argument they carried was, in almost every case, already in the
  adjacent body text. Captions fall 1729 -> 1285 words.

### Fixed
- **Table 2's nested scenarios inverted, and fixing it found a modelling defect
  (2026-08-18).** Scenario B is A plus one equality tie, so B's residual sum of
  squares cannot be smaller than A's -- yet on d5 it was, and the same happened
  on d6 between B and C. Each scenario was solved once from a common cold start,
  and at least one had stopped short. Every scenario is now restarted from every
  other's optimum, iterated to a mutual fixed point; D gets the same treatment
  and gains nothing from it, so the C-versus-D comparison is like for like.

  The corrected table says something different from the old one. On d6 all three
  scenarios reach the same optimum to six significant figures. On d5 the 2:1 tie
  is likewise free, but the spin-orbit tie moves the splitting to 9.27 eV -- 4.45
  eV below what A and B recover, and below any 2p spin-orbit splitting iron has.
  The cause is in the constraint, not the solver: `C` writes the L2 white line as
  the L3 white line plus the separation of the two `arctan` step centres, and
  those steps are broad terms the data barely constrains, with `step_l2.center`
  on its bound in all three d5 scenarios. The two C fits now pool to 0.0077
  against D's 0.0084, so D is 9 % worse -- but pooled C buys that with d5's
  unphysical splitting while D lands at 13.67 eV. The arrangement with the better
  residual is the one that has abandoned the physics, which is the CX-017 failure
  mode from Validation appearing inside a single model.

  `fig_constraint_grid.py` no longer fits anything. The scenario table now ships
  each row's full parameter vector and the figure replays it through
  `evaluate()`, a pure forward pass, so rendering figures cannot re-time Table 2
  -- and its cross-check got stronger, recomputing the reduced chi-squared from
  the replayed residual rather than trusting a refit to agree.

- **Declarations corrected (2026-08-18).** "The authors declare" was plural
  against a single author. The Archive block stated "Version published: 0.1.0"
  where every neighbouring field is explicitly forward-looking; it now is too.

### Fixed
- **Five lineshape rows rendered as literal text, not a table (2026-08-18).** A
  paragraph sat inside the symmetric-lineshape table in
  `docs/reference/models/index.md`, and the blank line before it terminated the
  table, so `pearson7`, `moffat`, `students_t`, `log_normal` and `harmonic_ir`
  had no header or delimiter row of their own. Rendering the page before the fix
  yields a six-row table with all five kernels outside it; after, one eleven-row
  table. This is the likeliest reason those kernels were repeatedly described as
  "formula-only" -- six of the eight so described do carry prose, and only
  `moffat` and `students_t` did not. Both now have it: they are Lorentzians with
  an adjustable wing weight (exactly Lorentzian at $\beta=1$ and $\nu=1$
  respectively, verified numerically), catalogued to mirror lmfit's so a familiar
  wire string resolves to the same curve. Stated as catalogue parity only --
  the benchmark's lmfit backend wraps spectrafit-core's own kernel and uses lmfit
  purely as the optimiser, so no published number compares these shapes against
  lmfit's independent implementations.

- **`manuscript_deps_check` was permanently red (2026-08-18).** Every number
  agreed; the generator's template had not followed a hand-improved sentence in
  `availability.md`. The template now emits the better wording ("not on the
  install path for either the Python package or the Rust crates"), so `--check`
  goes back to being a real drift guard rather than noise. Its failure message
  named a command that regenerates nothing -- the script only prints -- and now
  says so and names the block to replace.

- **Four wrong scientific statements and seven silent omissions in `docs/`
  (2026-08-17).** Distinct from the doc-vs-code drift sweep already done: nothing
  here is a stale count or a dead path, and everything here would mislead a reader
  who understood the code perfectly.

  Wrong as written: `chi2_reduced` was named after the textbook statistic while
  being computed from an unweighted sum of squares, so it never carried the
  "near 1 means a good fit given the noise" reading that division by `sigma_i^2`
  buys. The glossary defined the trust-region family so as to exclude `lm`, in
  contrast to methods "taking an unconstrained Gauss-Newton step" — but LM bounds
  its step through the damping term, and this repo's own Rust overview already
  said the trust-region core is shared by LM/TRF/dogleg/geodesic/Newton-CG; the
  real distinction is explicit vs implicit radius. Four kernels violated the
  blanket "amplitude = peak value at center" convention without being listed as
  exceptions (`fano` and `breit_wigner` give `A*q^2` at the center, and `fano`'s
  true maximum is not even at the center; `doniach_sunjic` gives
  `A*cos(pi*gamma/2)`; `asym_ir` gives `A/2`). And the `voigt` wire string aliases
  the pseudo-Voigt formula while `true_voigt` carries the actual convolution,
  which needed saying outright given what "Voigt profile" means in the
  literature.

  Absent rather than wrong: `stderr` can be `None` on an ill-conditioned
  Jacobian, and the confidence-interval tutorial built a CI straight from it; the
  i.i.d. Gaussian-residuals assumption under chi2/AIC/BIC/covariance was stated
  nowhere; AIC/BIC carried no comparability precondition and no warning against
  use as an automatic peak-count selector — the trap this project's own FeCl4
  case study fell into and documented, in the manuscript only. Also: the Wald
  caveat was stated once and never cross-referenced from the other page relying
  on it, `dogleg`/`newton-cg` had "use when" guidance and no "avoid when", the
  Voigt family had three formulas and no word on why the shape exists, and
  `gaussian2d`/`gaussian_nd`'s axis-aligned restriction was an inline
  parenthetical rather than a flagged limitation.

- **The manuscript's last audit blocker, and the last five open review findings
  (2026-08-17).** `manuscript-state.json` carried no `claims[]` on any section, so
  no claim-to-evidence pointer existed to resolve for any numeral in the paper —
  the claim-evidence audit could not run at all. All fifteen sections now carry
  claims (256 of them, the fuller behavioural set rather than only the headline
  numerals), each with an evidence pointer verified against the artifact it cites.
  The audit then ran and found three blockers and three should-fix items across
  those 256, all corrected: two pointers resolved to the wrong content, and
  twenty-two claims carried a status whose hedging convention the prose never
  implemented.

  Of the five open findings, three were already closed by earlier commits and the
  ledger had not been re-checked against the files. The two that were real:
  `fig_fecl4_case_study.py` held a **fourth** hand-typed copy of the Fe L-edge
  step tie — the "confirm no fourth copy exists" check the finding was left open
  for found one — and `fecl4_constraint_scenarios.json` had no guard against
  direct regeneration, which moves every timing in Table 2 while leaving the
  physics identical to twelve decimals.

  `F-016` (lmfit's covariance computation falls inside its timer, SciPy's outside)
  is closed by measuring rather than re-running the ladder: lmfit's covariance
  step is a median 12.6 % of its own timed solve, so its reported speedup is
  inflated by about that much; SciPy's excluded stderr step would add a median
  4.4 % if counted, so its speedup is conservative by about that much. Both are
  comparable to the ladder's own 4.2 % depth-trend margin. Open findings: five to
  zero.

- **Restored two review findings a tag restore had silently reverted
  (2026-08-17).** They were committed, then undone when the preserved
  figure-redesign snapshot was checked out wholesale — the snapshot predated them,
  so the commit message claimed findings the file no longer carried. A reminder
  that `git checkout <tag> -- .` restores *everything* in the snapshot, including
  files that have legitimately moved on since.

- **Documentation claims the code does not support (2026-08-17).** An audit of
  `docs/` found fifteen false or stale claims and one that turned out to be already
  fixed. The install page documented `pip install spectrafit-core`, which 404s --
  `CITATION.cff` already refused to make that claim. `why-spectrafit-core.md`
  described routing that was replaced on 2026-06-03, misstated all three regression-
  gate axes, and asserted that lmfit's accuracy claims are "not independently
  re-verified per release" when lmfit ships and runs the NIST StRD suite in its own
  CI. `LIMITATIONS.md` still said NIST coverage was 10 of 27. The glossary and the
  sitewide abbreviations tooltip both defined win rate as "faster than the baseline"
  when it is a composite of r^2 and speedup. `how-to/choosing-a-solver.md` cited a
  solver bake-off whose report does not exist in this repository, a citation echoed
  in two code comments, now reworded to what the surviving ADR actually supports.
- **Counts across `docs/` that had drifted unguarded (2026-08-17).** 34 -> 37 wire
  variants, 33 -> 36 shape factories, 139 -> 151 benchmark cases across 9 categories
  rather than 7, six -> eleven kernels without an analytic Jacobian, 19 -> 26
  pre-commit hooks, and Node >= 18 -> >= 20.19. Eight dead module paths pointing at a
  `problem.rs` that is named `lm_problem.rs` and is crate-private. `tests/meta/
  test_catalog_drift.py` grew from 4 to 13 tests to pin every one of these, deriving
  each expected value from the source of truth rather than hardcoding it, and was
  mutation-tested by reintroducing all eight drifts.

### Fixed
- **Four figures reviewed against a composition grammar, three carrying real
  defects (2026-08-17).** The grammar is distilled from Figure 5 and kept at
  `.superpowers/specs/2026-08-17-figure-composition-grammar.md`.
  **Figure 6's third column was not aligned to its own rows** — one axis spanning
  rows of unequal height, displacing marks by up to 62 % of a row pitch and
  sign-flipping down the figure, so a reader tracking across from a dataset name
  could land on a neighbour's agreement dot. Now 0.0 px.
  **Figure 4's tau axis was cropped with no disclosure**, which left lmfit ending
  at 0.986 and scipy-ls-lm at 0.980 while their legends read 147/147 and 146/147
  solved — two curves contradicting the figure's own caveat that a plateau below
  1.0 means unsolved cases. The crop is removed.
  **Figure 3's docstring named the wrong region**: the spin-orbit tie's cost is a
  4.93 % excursion at 708.20 eV, astride the L3 white line, not in L2. It is now
  drawn — a dashed rule at each row's own fitted white-line centre, carried into
  the residual panel beneath it.
  **Figure 2 printed 32 kernels**, transcribed and stale against a manifest of 37;
  the count and the crate count are now derived at render time, and the 11-of-21
  drawn dependency edges are disclosed.
  Two hue collisions closed: Figure 6's difficulty tiers were exactly the three
  hues Figure 4 gives scipy-ls-trf, lmfit and spectrafit-core, at luminances within
  1.07x of each other — replaced by an ordinal indigo ramp with 5.87x lightness
  spread. Figure 4 keeps its measured five-hue ramp, since the colliding script
  renders no manuscript figure.
  Figure 6's caption is corrected: the fitted curves diverge by at most 7.7e-5 % of
  a dataset's range, on Rat43 — not the 0.0001 % on Thurber previously stated.

### Changed
- **Figure 1 redrawn as a declaration ledger (2026-08-17).** The previous version
  showed boxes near boxes; three readers understood the prose and could not picture
  the object. The canvas now splits into two registers holding different kinds of
  thing — left, the components the analyst declares and the parameter names each
  introduces; right, one cell for each of the 43 parameters, grouped in a run per
  component. The two expression edges are the only marks crossing the divider, and
  each terminates on the single cell it removes, drawn open. "An edge removes a free
  parameter" stops being a sentence and becomes a struck cell with an arrow in it,
  with the ledger restating it as 43 -> 42 -> 41. No fitted value is read or drawn,
  so the figure is independent of any particular solve — which dissolves the old
  arithmetic gap where the drawn edges were scenario C's while the printed energies
  came from a fit that applied only one of the two ties.
- **Figure 4 rebuilt on three panels (2026-08-17).** Every backend is scored over
  the cases it was actually offered, so all 151 stay in and no result rides on a
  shared denominator: spectrafit-core fastest on 131, lmfit on none, JAX fastest on
  none of the 127 it solved. Panel B reads the same measurement by problem family
  and surfaces the largest lead in the benchmark, 14.3x median on the
  tied-parameter cases — the expression edges the paper is about, previously
  measured and never stated. Panel C is panel A read cumulatively, a performance
  profile in the sense of Dolan and More, which keeps that citation honest.

- **Figure 5 redrawn so a reader can actually read it (2026-08-17).** The author
  could not read the previous version, which is the only verdict that matters. Two
  attempts at a shared y-axis both squashed one panel: the per-case spread and the
  per-run spread are different kinds of quantity and no single scale serves both.
  Each panel now has its own relative axis. Panel A is a scattered boxplot -- box and
  quartiles per depth with all 755 per-case points drawn small and translucent, and
  the aggregate trend over the top -- and panel B is a violin with a deterministic
  beeswarm of the 50 seeds. What ties them is better than a shared scale: the entire
  seed range is drawn as a band across panel A, so a reader sees at a glance that all
  50 seeds fall inside the ordinary spread of a single depth's cases. Off-scale
  points are disclosed with a count and a range (12 of 755, -55 % to +710 %) rather
  than a vague note; the earlier "one case reaches 132x" was the scaled value and the
  raw figure is 214.28x.

### Fixed
- **The regression disclosure named two of the three failing backends
  (2026-08-17).** `validation.md` reported "lmfit on four seeds, SciPy dogbox on
  two" for the six seeds that flag a regression. Reading the per-seed manifests,
  `scipy-ls-lm` fails on **all six** -- the omitted backend was the one that failed
  every time, and 4 + 2 = 6 made two overlapping sets look like a complete partition.
  spectrafit-core solved all 151 cases on all 50 seeds.

### Added
- **The paper's two sharpest scope disclosures now appear in the docs too
  (2026-08-18).** "The library reads no files" is stated in `docs/index.md`, and
  the harness-reuse hedge -- that running the rig against another library is a
  documented capability and not a demonstrated one -- in
  `docs/why-spectrafit-core.md`. Both previously existed only in the manuscript,
  so a user landing on the documentation got the capability without the caveat.

- **`scripts/render_figures.py` and two poe tasks (2026-08-17).** One command
  regenerates every manuscript figure. It discovers `fig_*.py` rather than carrying
  a list — a hardcoded list is what went stale in `build_fair_package.py`, which
  named 20 files and missed 46 real inputs — and that glob is a safety boundary,
  not a convention: it structurally cannot execute
  `fecl4_constraint_scenarios.py`, whose invocation re-times seven fits and moves
  every millisecond in Table 2. `--check` renders into an isolated mirror of the
  repository and reports which figures *would* change without writing a byte.
  Available as `python manuscript figures` and `python manuscript figures --check`.

- **Figure 5 becomes a two-axis stability figure (2026-08-17).** Panel A keeps the
  repetition-depth ladder; panel B adds 50 independent seeds at one fixed depth,
  drawn as an empirical distribution function so every draw is plotted and the
  sample size is visible rather than asserted. The two axes answer different
  questions and only one can carry an interval: the ladder's 151 cases are a fixed
  hand-designed set, so bootstrapping over them would describe a population that
  does not exist, whereas each seed is a genuine independent draw. Geometric mean
  15.95x, 95 % CI [15.84, 16.05] in log space with Student t, range 15.08-16.67,
  all 50 exiting 0. This closes review finding `F-027`. The two datasets overlap at
  the same draw -- the ladder's rungs and the sweep's first seed share a catalogue
  fingerprint -- and report 15.7846x against 15.8657x, 0.51 % apart, bounding
  run-to-run noise below both plotted axes. The seed does move accuracy where depth
  does not, because it moves the data: six of 50 seeds flag one regression, and on
  every one of the 50 spectrafit-core solved all 151 cases, so those flags are
  comparator non-convergence.

- **A figure-freshness guard in the manuscript renderer (2026-08-17).**
  `render_manuscript.py` now records a SHA-256 per registered figure in
  `.render-manifest.json` (schema 3) and `--check` fails when an image no longer
  matches the draft it was rendered into. The failure this closes is concrete:
  Figure 5 shipped a caption reading "for all ten implemented datasets" over an
  image whose own subtitle said "22 of 27", and nothing could notice, because the
  number a caption contradicts lives inside a PNG no source-level check can read.
  Hashes rather than modification times, so a fresh checkout does not read as stale.
  `manuscript-state.json` also gains `evidence_role_carriers`: the hand-extended
  JORS binding gives `validation.md` the role `validation`, which is not in the
  venue profile's closed vocabulary, so every check keyed on `role == "evidence"`
  skipped the file where nearly all the drift lived.

- **The measurement artifacts, generators and datasets the paper rests on are now
  tracked (2026-08-17).** None of them were: a clean clone could not reproduce the
  manuscript, and the FAIR package's stated premise -- that every input is already
  under version control -- was false. This lands the four measurement generators
  and their pinned outputs, the figures the paper and its appendix carry, the three
  deeper ladder rungs, the five NIST datasets no kernel covers, and a new
  **seed sweep**: 50 independent seeds at fixed repetition depth, under
  `manuscript/examples/seed-sweep/`. The sweep is the paper's second stability
  axis and answers a question the reps ladder structurally cannot. The ladder varies
  how often each case is *timed* and asks whether the measurement settles; the sweep
  varies the seed that generates the data and asks whether the result depends on the
  draw. Because each seed is an independent realisation, the 50 values are a genuine
  sampling distribution, so an interval can honestly be quoted there and not on the
  ladder, whose case catalogue is a fixed hand-designed set rather than a sample.
  Its `.gz` payloads stay with the run that produced them and are not distributed:
  the GitHub mirror is an orphan snapshot branch, so an LFS pointer published here
  would resolve against a remote that never received the objects and a reader would
  clone a 131-byte stub instead of data. `checksums.sha256` and
  `ro-crate-metadata.json` are pruned of those payloads, and of the 50 per-seed
  `run.log` files that `.gitignore`'s `*.log` rule keeps out of every clean clone
  (they duplicate numbers the tracked `provenance.json` already carries). Both
  manifests describe exactly the 152 files that ship and verify clean from a fresh
  checkout. `scripts/build_fair_package.py` skips `.log` for the same reason and
  now **fails** on any untracked input instead of warning: packaging one made the
  deposit depend on which machine built it, which is what its own
  version-control premise existed to prevent.

- **Table 2's NIST agreement numbers have a generator, and cover all 22 datasets
  (2026-08-16).** The table reported forty numbers that resolved to no committed
  script: correct on re-derivation, but not reproducible by a reader.
  `manuscript/examples/figures/nist_table2.py` now measures them and writes
  `nist_table2.json`, extending the sweep from the ten printed datasets to all
  twenty-two the audit implements. Every backend -- spectrafit-core, lmfit,
  `least_squares(method="lm")` and `least_squares(method="trf")` -- runs from NIST's
  Start 2 at `ftol=xtol=gtol=1e-12`, the tolerance the shipped audit actually uses;
  quoting a comparison at a tolerance the software does not run at would describe a
  configuration nobody ships. The roster, model graphs and NIST-parameterization
  projections are read from `oracles.audit.nist._RECIPES`, so the table cannot drift
  from the audit. A fitted standard error only survives a projection that is linear
  in one fitted parameter; on Eckerle4 (`b1 = A*sigma`) and DanWood (`b2 = -1/s`) it
  does not, so those rows carry a null with a machine-readable reason rather than a
  number.

### Changed
- **The manuscript reports the committed benchmark ladder, not the CI run (2026-08-16).**
  The paper quoted 14.0x geometric mean from `2026-08-13_run_001` while
  `manuscript/examples/ladder/` shipped, in the same repository, a run reporting
  15.80/15.96/15.74 across three repetition depths. A reader downloading the data
  package found different numbers from the paper, which is the self-contradiction the
  paper spends a section warning against. Every derived figure was recomputed rather
  than transcribed, and the recomputed geometric mean reproduces the manifest's own
  value to the digit. Consequences: harmonic 11.7 -> 13.0x, the SciPy range 5.0-6.8 ->
  6.1-7.6x, and JAX moves from "contributes no measurements" to 127 of 151 cases, which
  invalidated Figure 2's exclusion argument. Figure 2 stays at five backends, and the
  reason is now argued in the text rather than assumed: the 127 cases all six backends
  ran are exactly the non-`optfn` cases, on which spectrafit-core is fastest on every
  one, so a six-backend profile would be a flat line that hides the `optfn` deficit the
  paper discloses.
- **The manuscript revised against an end-user review (2026-08-16).** The abstract was
  rebuilt from 165 words to 111 around what a caller can express rather than a speed
  ratio, covering the four points the venue requires. The Introduction now reaches
  "This work" before the comparison with similar software; Quality control opens with
  the worked Fe L-edge case study and a short check a reader can run, which is an
  element the venue requires and the paper did not have. No Conclusion section was
  added: the JORS metapaper template has none, and the closing argument went to Reuse
  potential instead.

### Changed
- **`pyproject.toml` is configuration only now (2026-08-16).** The earlier pass left
  the file at 41 % comments with pointers, which is the worst of both arrangements.
  All 463 explanatory comment lines are gone and
  `docs/contributor-guide/project-configuration.md` carries the reasoning in full:
  every ruff round with its measured counts and its rejections, the ty rules and
  what each catches in this codebase, the rrt version targets and why each is
  tracked, the coverage floors, the poe tasks, the publish-exclusion allow-list.
  1,212 -> 694 lines, 44 % -> 2 % comments; the 11 that remain are a header saying
  where the reasoning went.

  The stripper tracks TOML multi-line strings, because the `poe` shell tasks are
  full of `#` lines that are shell script rather than TOML comments; removing
  those would have silently broken the tasks.

  The semver claim was **re-verified rather than renumbered**: against rrt 1.15.0,
  `Version.parse("0.1.0b1")` still raises and `"0.1.1-beta.1"` still parses, so the
  behaviour is unchanged since 1.14.1 and the page now records the check itself
  rather than a version number to trust.

- **`pyproject.toml`'s decision records moved to the contributor guide (2026-08-16).**
  The file was 44 % comments, and they were not noise: version-pinned rationale
  ("verified against rrt 1.14.1", "verified live against ty 0.0.65"), each entry
  written to stop a specific regression returning. A word-overlap check suggested
  most of it was already in `DECISIONS.md`; checking again with verbatim phrase
  matching showed almost none of it was, so nothing was deleted on that basis.

  `docs/contributor-guide/project-configuration.md` now carries the reasoning where
  a developer will look for it, and the file keeps a one-line pointer at each site.
  1,212 -> 1,148 lines so far, comments 44 % -> 41 %, with no rationale lost.

### Added
- **The constraint scenarios are shown, not only tabulated (2026-08-16).** The paper
  discussed seven fits and pictured one. `fig_constraint_grid.py` draws the six
  single-spectrum fits as a grid, one row per hypothesis with its residual beneath
  and one shared residual scale per column, so the rows are comparable. It locates
  what Table 3 could only score: the spin-orbit tie is invisible on the d6 residual
  and puts a single derivative-shaped excursion at the d5 L3 white line near 708 eV.
  A factor of three in reduced chi-squared turns out to be one feature, not a
  spectrum-wide degradation.

  Panels carry the individual components in the case study's own palette, a light
  grey grid, and a boxed scenario/chi-squared/free-parameter annotation with
  headroom reserved so it cannot land on a curve. The residual is drawn in a
  signal colour rather than body-text ink, since the residual is where the
  finding lives; it is the same hue as the emphasised expression edges in
  `fig_model_graph.py`, so "look here" reads consistently across the figures.

  **Residuals are normalised to each spectrum's own white-line maximum, and all
  six panels share one scale.** The first draft autoscaled per column and so drew
  the two spectra at different magnifications: in absolute units the unconstrained
  fits sit at 0.295 and 0.282, all but identical, yet the axes were +/-0.5 and
  +/-0.25, making the d6 misfit look twice the size of the d5 one. Normalised, the
  ordering reverses and is the true one -- d5 free is 1.9 % of its peak against
  d6's 2.4 % -- and the d5 spin-orbit excursion stands at 4.9 % against everything
  else under 2.6 %.

### Fixed
- **The dependency table omitted the build backend (2026-08-16).**
  `scripts/extract_dependencies.py` read `[project]` and the optional extras and
  never `[build-system]`, so `maturin>=1.4,<2.0` — the tool that compiles the Rust
  workspace into the PyO3 extension module the package imports — appeared nowhere.
  For a paper whose architecture is a PyO3 wheel that is not a detail. The Rust
  list was audited at the same time and is complete: all 12 third-party crates in
  `[workspace.dependencies]` are listed, and the table now says so, with the nine
  `spectrafit-*` path entries identified as workspace members rather than silently
  dropped.

### Added
- **The manuscript now names its models, and shows a model graph (2026-08-16).**
  The paper counted 32 registered shapes and listed none, so a spectroscopist could
  not learn whether their lineshape was supported. `scripts/model_inventory.py`
  generates the inventory from `MODEL_REGISTRY` and refuses to run when a model has
  no category, so the table cannot fall behind the code. It turned out the paper was
  underselling: `voigt`, `true_voigt`, `doniach_sunjic` and `fano` are all present,
  three of the four shapes a reader had reported as undeterminable. Shirley and
  Tougaard backgrounds are genuinely absent and the paper now says so.

  A new Figure 1 draws a model graph with its expression edges, the abstraction the
  paper had described only in prose. Figures are renumbered by order of first
  citation, which moves the model graph and the Fe L-edge fit to the front and the
  crate architecture to the back. That ordering is what the venue's numbering rule
  produces and also what readers asked for; the architecture diagram is last because
  it is genuinely cited last, in Reuse potential.

  Also stated for the first time: `MeasurementData` takes optional per-point
  uncertainties that weight the residual, so counting-statistics data can be fitted
  with its own error bars, and interval estimation by profile likelihood or sampling
  is not implemented.

- **The Fe L-edge case study now tests four constraint hypotheses, and times them
  (2026-08-16).** `manuscript/examples/fecl4/fecl4_constraint_scenarios.py` fits the
  same components under four sets of expression edges: free, the 2:1 continuum-step
  tie, a spin-orbit tie pinning the L2 white line one splitting above the L3, and a
  single joint fit over both spectra requiring that splitting to be the same in the
  d5 and d6 complexes. It emits Table 3 and a JSON sidecar, and recomputes the
  branching ratios on every run so the prose cannot drift from the data.

  Two results came out of it. The constraint is free on d6 (reduced chi-squared
  0.00421 to 0.00422, one parameter removed for nothing) and costs a factor of
  three on d5 (0.00817 to 0.02463), and the two spectra disagree by 0.70 eV about a
  splitting that is a property of the iron 2p level and should not depend on
  oxidation state. Neither is resolved here; both are reported because the
  machinery made them visible. All seven fits take 676 ms together, which is the
  argument the speed number is actually good for: a constraint can be tried and
  discarded rather than assumed.

  **What is deliberately not tied is the L3:L2 intensity ratio.** The 2:1
  degeneracy governs the edge jump, not the white lines; measured on these spectra
  the branching ratio is 2.4 and 2.9, so imposing 2:1 would be wrong by about a
  fifth and a half and would erase the observable that most distinguishes the two
  complexes.

### Fixed
- **A tolerance claim that was corrected in the wrong direction (2026-08-16).** The
  benchmark ladder records stopping tolerances as "not normalized across backends", and
  its `config.solvers` block lists only `max_iterations` for spectrafit-core. Reading
  the absence of a tolerance there as the absence of a stopping tolerance was wrong: the
  block records what the harness explicitly passes, and `FitOptions.tolerance` defaults
  to 1e-8, reaching the trust-region driver as `ftol`, `xtol` and `gtol`. spectrafit-core
  therefore stops on the same three criteria at the same value as the three scipy
  configurations; only lmfit differs, at MINPACK's 1.49e-8. That looser tolerance stops
  lmfit sooner, so the reported ratio is conservative on that axis rather than inflated,
  and the manuscript now says so.
- **Algorithm 1 existed three times and had no source (2026-08-16).** Its caption was
  baked into the PNG, repeated as the document caption and paraphrased in the prose
  above it, while a grep of the sources found one occurrence because two of the three
  were inside a binary. The figure also had no source anywhere in the repository, while
  the text claimed one, and `algorithm2e` small-caps had flattened
  `TrustRegionLevenbergMarquardt` into an unbroken run of capitals. A committed `.tex`
  source and a driver now exist, the caption is set once inside the float, and the
  pseudocode carries the fourth guard it was missing: `graph_prefers_varpro` has four
  conjuncts, and the omitted one is what keeps variable projection from being
  auto-selected for simultaneous multi-dataset graphs.

### Added
- **The author's review of the manuscript, captured durably (2026-08-15).** 50 Word
  comments read out of the reviewed `.docx` and preserved three ways: the reviewed
  document itself, the raw marks with their anchors as JSON and text, and a triage
  grouping them into 35 items. The largest theme is not a defect list: the paper
  argues that the library is faster, where the author's stated motivation is that an
  agent-driven workflow needs a different contract between the interface and the
  fitting engine — a contribution the manuscript does not currently make.
- **Word review marks are readable and protected (2026-08-15).**
  `manuscript/read_docx_comments.py` extracts comments from a reviewed `.docx` with
  the passage each anchors to, and `render_manuscript.py --docx` now REFUSES to
  overwrite a document carrying them. `MANUSCRIPT.docx` is a build output rewritten
  in full on every render, so comments written into it were one render from being
  destroyed; the render is reproducible from its sources and the author's words are
  not, so the irreproducible side wins. Also renders Algorithm 1 as a real
  algorithm2e float via LaTeX rather than a code block, with an `algorithms`
  registry and caption guard mirroring tables.
- **`comment-to-docstring` skill and a warning-only grey-comment hook (2026-08-15).**
  The skill converts Python comment blocks into real docstrings while refusing to
  pretend that a triple-quoted string after executable code documents anything. A new
  `warn-grey-comments` pre-commit hook points out staged files whose comment blocks sit
  where a docstring belongs — greyed out in the editor and invisible to `help()`,
  mkdocstrings and the API reference. It prints and exits 0 unconditionally: whether a
  leading comment is documentation or an implementation note is the author's call, and
  a blocking gate would force that decision at the worst moment. The hook uses only the
  skill's `--check` detector, never its converter, which can misplace a docstring.
- **Manuscript review, planning and decision-index artifacts (2026-08-15).**
  `manuscript/review/` carries the reviewer panel's report (five personas plus a blind
  desk-reject tribunal), the author's inline replies, a finishing plan ordered
  easy-to-difficult, and a derived TODO. `manuscript/ADR-INDEX.md` maps open review
  findings to the decision records that answer them — 19 line references, each validated
  against an actual ADR heading — so `DECISIONS-archive.md`'s 354 entries are navigable
  from a question rather than by reading. All are excluded from the public mirror.
- **Benchmark ladder artifact under `manuscript/examples/ladder/` (2026-08-15).** A
  three-rung run (reps 2/4/10) from the dedicated benchmark host, 1.0 MB, packaged with
  `checksums.sha256`, RO-Crate metadata, a JSON schema and per-case `results.json.gz`
  per rung — 20 files, all checksum-verified in place. Geomean 15.80 / 15.96 / 15.74
  across the rungs, within 1.4 %, with identical max |dr2| and win rate: the stability
  evidence the reported CI ladder could no longer supply, since its artifacts had
  expired. It ships publicly by design, because the data-availability statement points
  readers at this directory.
- **Table-count guard in the manuscript renderer (2026-08-15).** A pipe table whose
  header cell contains an unescaped `|` — `$|\Delta r^2|$` rather than
  `$\lvert \Delta r^2 \rvert$` — is parsed as prose, not as a table, and pandoc exits
  0 having silently produced one table where the source had two. `--docx` now compares
  the markdown table count against the count in the rendered document and fails on a
  mismatch, the same shape as the existing style- and image-count guards.
- **Reproducible manuscript docx render (2026-08-15).** `manuscript/render_manuscript.py`
  gained `--docx`, rendering `MANUSCRIPT.docx` through pandoc against the official
  JORS template (committed unmodified at `manuscript/assets/jors-template.docx`).
  The docx previously had no regeneration path at all and had drifted a full
  revision behind the section sources. Three guards close the silent-failure modes
  pandoc leaves open, each of which produces a plausible-looking document rather
  than an error: unresolved style ids (pandoc names `Heading1`/`BodyText`, the
  template ships `UPPaperTitle`/`UPSectionHeading`, and Word resolves an unknown id
  to Normal), an image count that falls short because pandoc downgrades an
  unresolvable image to its alt text and still exits 0, and a registered table whose
  caption has gone missing. `--check` now also verifies the docx by hash against
  `.render-manifest.json` (schema 2) — pandoc-free, so a machine that cannot render
  can still detect that a render is due. Figures are placed at their first prose
  citation and `references.ris` is emitted for EndNote/Zotero import.
- **Python domain-exception taxonomy (2026-08-01).** New
  `spectrafit_core.exceptions` (`SpectraFitError`, `SpecificationError` — both
  exported from the package root) and `oracles.exceptions` (`OracleError` plus
  `RegistryError`, `UnknownKeyError`, `ContractError`, `CaseSpecError`,
  `BackendError`, `BackendUnavailableError`, `AuditError`). Every subclass
  derives from both its package base and the closest builtin, so existing
  `except ValueError` / `except KeyError` callers are unaffected — this is a
  non-breaking change. 24 non-validator raise sites converted; raises inside
  Pydantic validators deliberately stay bare `ValueError` (Pydantic discards
  the type when re-raising `ValidationError`). Module loggers standardised on
  `logging.getLogger(__name__)`. Codified as house rules 5–6. Full ADR in
  `DECISIONS.md`.
- **Documentation site (2026-07-26).** A full Zensical-based docs site
  (Getting Started, Tutorials, How-to, Reference, Explanation, Contributor
  Guide) under `docs/`, hosted on both GitLab Pages and GitHub Pages. Python
  API reference via mkdocstrings; generated Rust API docs via `cargo doc`.
  The 4 example tutorials now ship runnable Python scripts with matplotlib
  plots (`docs/tutorials/gallery/`). Full ADR in `DECISIONS.md`.

### Changed
- **Manuscript: citations, neutral framing, ASCII math (2026-08-15).** The claim
  that "Python is the common substrate" and the count of 27 NIST datasets were both
  uncited; they now carry references verified through Crossref (Perez, Granger &
  Hunter 2011; Harris et al. 2020), taking the bibliography from 10 to 12. The
  abstract's speed claim is scoped to the procedure and suite that produced it, with
  an explicit sentence that it is not a general ranking of the libraries. Math
  notation is ASCII in source throughout, em-dashes cut from 69 to 35, and Figure 2's
  axis labels no longer bake a Greek glyph into the PNG — the one surface where a
  text-level check could not see it.
- **JORS manuscript: register, evidence and structure (2026-08-15).** The paper was
  switching between addressing a scientist and addressing a contributor: 136 inline
  code spans, 57 of them repo internals (lockfile names, CI job paths, runner labels).
  Measured against a published JORS paper (10.5334/jors.677, ~8-12 such spans in three
  sections), the Implementation section alone ran at 50 spans per 1000 words. It now
  runs at 1.3, with the operational layer moved to Availability and Reuse where the
  venue asks for it, and two display listings — a `compose()` example and the
  structure-routed dispatch algorithm — carrying what inline fragments used to.
  Substantively: a new *What the audit has caught* subsection giving three dated
  episodes where the project's own audit corrected a published number; a per-category
  speedup table and a NIST table with lmfit and SciPy comparison columns; the LAPACK
  dependency of the variable-projection family disclosed; the abstract's claim that
  the reference tools "are not compiled for speed" replaced with the interpreter-boundary
  framing that is actually true; the Start-1 non-convergence separated from coverage and
  named as a robustness limitation; and the contribution paragraphs lifted out of the
  comparison subsection into their own heading.
- **Manuscript build outputs regenerated (2026-08-15).** `MANUSCRIPT.md`,
  `MANUSCRIPT.docx`, `references.ris` and `.render-manifest.json` rebuilt from the
  current sources. The docx now carries all four figures embedded (881 KB of media,
  scaled to the template's text width, each with its alt text in `wp:docPr descr`),
  the captioned Table 1, the author front matter and the numbered parts — 6,095
  words against the previous 2,619, with no unresolved citation markers.
- **JORS manuscript structure (2026-08-15).** Author front matter added
  (`sections/authors.md`, `sections/author_roles.md`) — both venue-required and
  neither derivable from the repository. The venue's numbered parts are now
  rendered, with "(2) Availability" and "(3) Reuse potential" replacing their own
  headings because in this venue the part *is* the section. The NIST agreement
  table is captioned as Table 1 and registered in the state file so its number
  cannot drift from its caption. Figures renumbered 1/3/4/2 -> 1/2/3/4 to match
  order of first citation, and Figure 1's file paths in the state file corrected
  (they named `examples/fecl4/`; the architecture figure has always lived in
  `examples/figures/`).
- **Author identity metadata (2026-08-15).** ORCID `0000-0003-4543-4833` added to
  `CITATION.cff` and `codemeta.json` (as the Person's `@id` and `identifier`), and
  the scientific name "Anselm W. Hahn" now used in every machine-readable
  authorship field: `CITATION.cff` (software and `preferred-citation` authors),
  `codemeta.json` (author, maintainer), `pyproject.toml` and `Cargo.toml`. The
  LICENSE/README copyright line deliberately stays "Anselm Hahn"; the equivalence
  is declared as `alias` (CFF 1.2.0) and `alternateName` (schema.org) so a
  harvester resolves both forms to one contributor instead of two.
- **Crate encapsulation (2026-08-01).** `spectrafit-graph`, `spectrafit-solver` and
  `spectrafit-varpro` now keep their modules private, exposing only a curated
  `pub use` list; `spectrafit-models` and `spectrafit-types` keep `pub mod` as
  deliberate library-shaped exceptions. Promoted to crate roots so consumers keep
  working: `CompiledGraph` and three `executor` helpers (graph), and
  `GraphSeparableModel` (varpro). Removes three dead items that `pub mod` had
  hidden from `dead_code` analysis. Codified as house rule 26. Full ADR in
  `DECISIONS.md`.
- **Consistency open questions resolved (2026-08-01).** `unsafe` is now denied
  workspace-wide (`[workspace.lints.rust]`, all 11 crates opted in) with a single
  scoped `#[allow]` on the Accelerate `vvexp` FFI binding; `spectrafit-solver`'s
  `problem.rs` renamed to `lm_problem.rs` so `problem.rs` means only "the problem
  contract"; `from __future__ import annotations` completed across every module.
  `__all__` is now a boundary-aware rule (a package that ships declares it; the
  internal `oracles` harness need not) — no code change. Codified as house rules
  22–25. Full ADR in `DECISIONS.md`.
- **Consistency alignment Phases 1–4 (2026-08-01).** `spectrafit-levenberg-marquardt`'s
  `StepError` moved from an inline bare enum into `src/error.rs` as a `thiserror`
  enum, so it now implements `Display`/`Error` (variant shapes unchanged);
  unused `thiserror` dependencies dropped from `spectrafit-trust-region`,
  `spectrafit-core`, `spectrafit-varpro`; `spectrafit-types`' glob re-export
  replaced with an explicit 13-item list (export set verified identical via
  `cargo doc`); `from __future__ import annotations` added to
  `python/oracles/nested.py`. Codified as house rules 19–21. Full ADR in
  `DECISIONS.md`.
- **CI: benchmark HTML bundle reuses the regression-gate run instead of
  re-benchmarking (2026-07-31).** The benchmark regression gate
  (`oracles.cli run` + `gate`, `build:report_html`) still runs on every
  push/MR unchanged. HTML bundling and the Playwright UX walk now run in a
  new `build:report_html:bundle` job on the same cadence, consuming the gate
  job's already-computed `results.json`/`manifest.json` via `needs:` instead
  of re-running the ~1h+ benchmark a second time — superseding the
  2026-07-26 weekly-schedule design (`build:report_html:weekly` /
  `build:report_html:refresh`), which paid that cost twice per pipeline.
  Full ADR in `DECISIONS.md`.
- **F13 tree consolidation (2026-06-27).** `python/benchmark/` was absorbed into
  `python/oracles/` (one engine package); `benchmark/contract.py` became
  `oracles/bench_contract.py`. The CLI is now `python -m oracles.cli` — the
  `python -m benchmark.cli` mentions in the 0.1.0b1 notes below were accurate at
  release time. Full ADR in `DECISIONS.md`.
- **Amplitude-semantics correction (2026-07-24).** The "Off-domain runaway guard
  r²-escape" note below (0.1.0b1) says amplitude is an integrated area for "area-normalised
  peak models" generally — that's only true for `exp_gaussian`. `skewed_gaussian`,
  `doniach_sunjic`, and `true_voigt` keep amplitude as a peak/height-value parameter, per this
  project's normal convention. Full ADR in `DECISIONS.md`.
- **Design system re-skin (2026-07-28).** Visual identity update across the docs site and
  benchmark web dashboard: switched from teal/cyan to indigo palette, adopted Apple System
  Colors for semantic tokens, replaced Google Fonts CDN with locally-vendored IBM Plex Sans
  and JetBrains Mono, and refreshed the web component library with modernized styling
  (removed blur effects, redesigned Standing/Evidence navigation from filled pills to underline
  tabs, improved content card hierarchy).

### Fixed
- **NIST table regenerated from reproducible code; uncertainty check added (2026-08-15).**
  Three of the ten spectrafit values in the manuscript's NIST table did not reproduce —
  they came from a benchmark artifact run at commit `ccf2237` on a branch not present in
  this repository, and Misra1b was 8.03 against 10.30 today. The whole column is
  recomputed from this repo so a reader running the audit gets the printed table. The
  table also gains a column scoring fitted parameter standard errors against NIST's
  certified standard deviations, which the paper had criticised another benchmark for
  omitting: agreement is a median 8.6 significant figures and never below 6.6, except
  Lanczos1 at 0.60 against 8.75 for its values — now reported as a limitation.
- **`scripts/remote_bench.sh` could not report status at all (2026-08-15).** `rsh()`
  interpolated its payload into `bash -lc '...'`, but every payload contains single
  quotes of its own (`sed 's/^/  /'`, `tr -d ' '`), which closed the wrapper's quoting
  early — the remote shell then died on the first unquoted `(` it met, so
  `poe terra_status` never worked. The payload is now fed over stdin to `bash -s`,
  which has no quoting layer to break. The benchmark host also moves to `.env`
  (gitignored) so the machine name is not in tracked files.
- **Public-mirror exclusions for the manuscript working directories (2026-08-15).**
  `manuscript/review/*` (the reviewer panel's report carrying the author's own inline
  replies) and `manuscript/author-check/*` (the author's open questions) shipped to the
  public GitHub mirror by default from the moment they were created — the documented
  consequence of narrowing the blanket `manuscript/*` rule on 2026-08-13. Added to both
  `scripts/publish_exclusions.py` and the `pyproject.toml` mirror list, with the pinning
  test raised fourteen -> seventeen. Caught before anything was pushed.
- **Manuscript `--check` false positive (2026-08-15).** `--check` compared the
  `Repository commit:` provenance line, which records HEAD at render time and so is
  always one commit behind in a committed file — a guaranteed-failing signal. It is
  now excluded from the diff alongside the already-excluded `Generated at:` stamp.
  Both are still written; they are simply not evidence of staleness.
- **Generated architecture tree (2026-08-15).** `docs/contributor-guide/architecture.md`
  still listed `rustapi-cards.png` after a6c54259 removed the file. Regenerated by
  the `pre-merge-arch-tree` hook, which is the same check `.gitlab/20-lint.yml` runs.

## [0.1.0b1] - 2026-06-23

> Prepared, not released — see the release-status note at the top of this file.
> No `0.1.0b1` tag exists.

### Changed
- Promoted to **beta** (`Development Status :: 4 - Beta`). Intended as a
  non-public, GitLab/GWDG-only reproducible **source** release
  (clone + `uv run maturin develop`); no PyPI/wheel publish, no DOI. The
  version bump and metadata landed in-tree on this date; the tag was never
  cut.

### Fixed
- **Lean wheel (Option A packaging).** Removed the `spc-bench` `[project.scripts]`
  console script (it ImportError'd on a clean install because its deps live in
  the `[benchmark]` extra) and repointed every caller — the `poe` tasks and the
  GitLab CI jobs — to `python -m benchmark.cli` / `uv run poe benchmark`. Scoped
  maturin to `python-packages = ["spectrafit_core"]`.
- **Benchmark gate integrity.** The accuracy axis now fails on a non-finite
  `|Δr²|` (previously `NaN > threshold` silently passed and the value was coerced
  to `0.0`); the primary GitLab pipeline now enforces `python -m benchmark.cli
  gate` on push.

## [0.1.0a1] - 2026-06-13

> Prepared, not released — see the release-status note at the top of this file.
> No `0.1.0a1` tag exists.

### Added
- MIT `LICENSE` file; `CITATION.cff` (CFF 1.2.0); `CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), `SECURITY.md`.
- `LIMITATIONS.md` disclosing the benchmark's self-audit gaps (W2c κ(J),
  NIST 4-of-27 subset, χ²-floor convergence proxy, JAX-no-σ).
- `pyproject` `authors`, `[project.urls]`, and PyPI classifiers (alpha).
- Research-grade `README.md` intro with status, citation, and license sections.

### Changed
- Markdown documentation consolidated (129 → 91 tracked files); design history
  absorbed into `DECISIONS.md` and Serena project memories.
- `rrt` `repo-root-required-files` contract extended to enforce the new
  governance/legal files.

### Added — 2026-06-08 / 2026-06-09 session (Cycles 1–22)
- **`spc-bench` CLI surface gained four subcommands.** `forensics [--run ID]`
  renders matplotlib PNGs of {observed spectrum, per-backend fit, residuals}
  for every `regression_case_ids` entry of a run; `sweep --tiers 1,2,5,10`
  runs the bench at multiple `--reps` budgets and emits a budget-vs-signal
  table; `trend [--field --last N]` reads `.spectrafit_reports/index.json`
  and prints ASCII sparklines plus a table of the four gate axes across
  history; `pin-baseline` / `show-baseline` / `clear-baseline` manage
  `.spectrafit_reports/perf_baseline.json`.
- **`BenchReport.manifest: ManifestSignals | None`** (`SCHEMA_VERSION` 1.1 →
  1.2). Surfaces the four gate-axis numbers — `geomeanSpeedupVsBaseline`,
  `maxAbsDeltaR2`, `spectrafitWinRate`, `regressions` — plus optional
  `PinnedBaseline` on the typed contract so the web `GateBadge` renders real
  values instead of pointing users at the CLI. Additive minor; Pydantic
  defaults keep every 1.1 payload on disk valid.
- **IRLS robust-loss selection from Python.** `FitOptions(solver="irls:huber"
  | "irls:bisquare" | "irls:biweight" | "irls:cauchy")` reaches the underlying
  `WeightFn` variant via the colon-split parser in `dispatch.rs:108-110`. New
  `tests/test_irls_weights.py` pins each variant.
- **Trust-region power-user knobs.** Three new `Option<f64>` fields on
  `FitOptions` — `delta0`, `max_delta`, `eta` — reach `TrustRegionConfig` in
  `dispatch.rs` for the `dogleg` / `newton-cg` solvers. `None` keeps the
  library default; `Some(v)` overrides. New `tests/test_tr_knobs.py` proves
  the knobs reach the TR core (an impossible `eta=1.5` forces
  `NoImprovement`).
- **Cycle methodology codified** at `docs/methodology.md` (cycle pattern,
  fan-out playbook, verification loop, which-skill-when matrix, sprint
  cadence, anti-patterns). `CLAUDE.md` Synopsis links to it.
- **Rust binding audit** at `docs/reference/rust/binding-audit.md` enforced by a
  `scripts/audit_bindings.py` CI guard — fails the pipeline when a new
  `#[pymodule]` registration or `Solver::` variant lands without a doc entry.
- **Runnable examples** at
  `docs/examples/{fitting,shared_params,multi_dataset,3d_fitting}.md`.
- **6 new ADRs** in `DECISIONS.md` covering ManifestSignals, TR knobs sentinel
  design, methodology codification, GateBadge council redesign, Suite
  distributions data-integrity rule, informational breath signal.

### Changed — 2026-06-08 / 2026-06-09 session
- **CI redundant-loading elimination (Cycle 30, four commits).** GitLab
  base image switched from `python:3.13-slim` to the public Docker Hub
  `nikolaik/python-nodejs:python3.13-nodejs22-bookworm` (Python 3.13 +
  Node 22 + uv baked in — no own-registry maintenance per user
  constraint). `CARGO_HOME` + `RUSTUP_HOME` moved under
  `$CI_PROJECT_DIR` so rustup + cargo-llvm-cov persist via the
  project-tree cache. `cargo install cargo-llvm-cov --locked` replaced
  with the prebuilt tarball from `taiki-e/cargo-llvm-cov/releases/v0.8.7`
  (GitLab) and `taiki-e/install-action@v2` (GitHub). Apt build-deps
  install gated on a job-level `NEEDS_BUILD_DEPS=1` variable —
  cmake/gfortran/lapack/openblas now installs only in the 3 jobs that
  actually compile `netlib-src` (lint:rust, test:python, test:rust);
  the other 8 jobs skip the ~1.5 min apt cost. Cycle 27 step-summary
  refactored from four `uv run coverage report` shell-outs to one
  `coverage json` + four `jq` reads. Expected savings: GitLab ~40–55
  min/pipeline (image swap + cache + apt gating); GitHub ~2.5–3.5
  min/pipeline. See DECISIONS.md 2026-06-09 ADR for the search trail.
- **GateBadge redesign (`cupertino-council` skill).** Vertical accent edge,
  four equal-weight number cells, "All clear" / "Investigate N case(s)"
  subtitle (grepable tag survives in `data-gate-status`), informational 6 s
  breath on the status dot (pulses only when PASS AND perf ratio ≥ 95 % of
  pinned), 60×14 SVG sparkline under the geomean cell when a pin exists.
- **Suite distributions trio redesign (council + data fix).** `panels.tsx`
  `suiteSpeedRows` and `suiteAccRows` no longer use `?? 1` / `?? 0` defaults
  for missing backend metrics — the previous behaviour faked 85 jax samples
  per violin. Per-backend `n=N` annotations surface via the existing `annot`
  slot; partial-surface backends get a dimmed row label via a new `dim?:
  boolean` field on `DistRow`. Layout overridden to `1fr 1fr 2fr` so the
  scatter (the thesis) is the centrepiece.
- **scipy-ls trio** (`scipy-ls-lm` / `scipy-ls-trf` / `scipy-ls-dogbox`)
  rejoins the benchmark backend roster (3 → 6 oracle). `SOLVER_META`
  extended; `synth.py` perturb/base_ms extended; tests relaxed to subset
  assertions.

### Fixed — 2026-06-08 / 2026-06-09 session
- **Engine regression policy** (`engine.py:run_suite`) excludes oracle
  failures on `optfn` cases, mirroring the accuracy-axis policy. Without
  this, 9 of 11 regressions on `2026-06-06_run_012` were oracle
  multimodal-trap noise the accuracy axis already accepted.
- **Off-domain runaway guard r²-escape**
  (`crates/spectrafit-solver/src/postfit.rs`). CX-017 reached r² = 0.96236
  but was mislabelled `success=false` because `amplitude = 2.55e3` was
  outside the data envelope — for area-normalised peak models the amplitude
  is an integrated area, not a peak height. Guard now skips above `r² ≥
  0.5`.
- **Soft-failure r²-quality upgrade** in `apply_postfit_guards`. OF-005
  reached r² = 0.9921 but reported `no_improvement_possible`; the upgrade
  promotes `success=false → true` when termination is soft AND r² ≥ 0.9.
  Numerical errors stay failures regardless.
- **`graph.py` coverage** raised from 69.8 % to 82.6 % by exercising
  `GlobalFitGraph.fit_all_slices`; per-module CI floor lifted from 65 → 80.
- **GitLab CI hardening.** `.gitlab/00-defaults.yml` `before_script` now
  fail-fasts when build tools are missing post-apt-install — surfaces the
  cause in 20 lines instead of 200 lines of cargo trace.

### Fixed
- **CI / pre-commit governance:** repaired a long-red pre-commit suite — corrected
  validator script paths after the `.github/skills` → `.claude/skills` move, removed
  two obsolete validators (`validate-scenarios` YAML, `validate-model-stub` `ModelKernel`)
  that checked a superseded architecture, updated `pre-merge-dag.sh` allowed-deps for the
  per-method solver-crate split, dropped the uninstalled `mypy` hook (superseded by `ty`),
  and scoped the `ty` / docstring checks to project sources (not `.claude/` tooling).
- **Type checking:** cleared all `ty` errors across `python/` and `tests/` — widened
  `MeasurementData.x` to match its 1-D→2-D runtime promoter, typed `Parameter` bound
  validators and the graph eval `params` (`Mapping[str, object]`, no bare `Any`).
- **Solver:** order-safe VarPro routing (filter `amplitude` by name, not positional
  `.skip(1)` over a HashMap) and point-major n-D `x` layout in the DE/global path.
- **Graph:** reject duplicate node IDs and out-of-range `dataset_index` instead of panicking.
- **PyO3 boundary:** removed the dead `ExpressionNotImplemented` error variant, corrected
  the `_core.pyi` exception docs, and made `evaluate` reject multi-dataset / n-D input.
- **Tests:** removed a stale `xfail` masking the (landed) 2-D fit path and enabled
  `xfail_strict`; added a `ModelType` ↔ Rust parity entry for the new kernels.

### Added
- **`poe report_html` pipeline:** build the Rust extension → run the benchmark → bundle a
  single, self-contained, deployable `report.html` (JS/CSS inlined via
  `vite-plugin-singlefile`, the report inlined as `window.__BENCH__`) that opens offline with
  no server. Stored at `.spectrafit_reports/benchmark/<run>/report.html`. `data.loadReport()`
  prefers the inlined data when present, else fetches `/api/report` as before.
- **Benchmark web UI — greenfield rebuild** on the frozen JSON contract: a Vite + React
  app with 5 views — **Overview** (new default hero: all-backend head-to-head with
  co-winner ties on metric equality, suite distributions, initial→best parameter recovery
  ±σ, error-vs-runtime, and the 2-D map + time-resolved series as sections) / Dashboard /
  Report / Cockpit / Export. Category-grouped sidebar navigation. The data binding has no
  silent `?? PRIMARY` fallback and enumerates backends via `solversOf(F)` (no hardcoded
  backend ids — enforced by a source-scan test). A `vitest` suite
  (`web/src/__tests__/*`) replaces the ad-hoc `web/scripts/*.mjs` smokes; `npm run smoke`
  now runs vitest.
- **2-D fitting as a real subject:** the benchmark `_multidim()` now fits the 2-D map with
  spectrafit's native `gaussian2d` kernel (`source=spectrafit-core`), replacing the prior
  scipy oracle.
- **Time-resolved series:** a real `GlobalFitGraph` joint multi-dataset fit
  (`_time_resolved()`) — peak centers/widths shared across all time slices, per-slice
  amplitudes free (recovered kinetics).
- **Contract:** `TimeResolved` / `TimeSlice` / `PeakTrace` shapes and
  `Featured.{time_resolved, guess_params}` (initial-guess values for the recovery table).
- **Ground-truth invariants:** `tests/test_bench_invariants.py` (Tier-1 fast + Tier-2
  `slow`) — every suite category is deep-dived, the analyzed set is multiple + unique,
  per-case plots are distinct, all floats finite, and optfn carries spectrafit + lmfit but
  not jax.
- New model kernels: `tauc`, `cauchy_dispersion`, `kww` (+ catalog drift-guard test).
- Project-scoped MCP servers (`serena`, `context7`, `github`) in `.mcp.json`.
