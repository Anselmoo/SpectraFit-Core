# Fe L<sub>2,3</sub>-edge case study — [FeCl<sub>4</sub>]<sup>−</sup> vs [FeCl<sub>4</sub>]<sup>2−</sup>

A worked, real-data example: fitting measured Fe L<sub>2,3</sub>-edge X-ray
absorption spectra of two tetrachloroferrate anions that differ only in the iron
oxidation state — Fe(III) d<sup>5</sup> and Fe(II) d<sup>6</sup>. This is the
case study reproduced as Figure 2 of the software metapaper.

## Provenance and licence of the data

The two `.txt` spectra are **third-party measured data**, previously published in:

> Wasinger EC, de Groot FMF, Hedman B, Hodgson KO, Solomon EI. *L-edge X-ray
> absorption spectroscopy of non-heme iron sites: experimental determination of
> differential orbital covalency.* J Am Chem Soc. 2003;125(42):12894-906.
> [doi:10.1021/ja034634s](https://doi.org/10.1021/ja034634s)

They are reproduced and redistributed here **with the authors' permission**.
They are **not** covered by this repository's MIT licence — that licence applies
to the code. If you reuse the spectra, cite the paper above.

The scripts in this directory are MIT, like the rest of the repository.

## Contents

| File | What it is |
|---|---|
| `FeCl4_d5.txt` | Measured spectrum, [FeCl<sub>4</sub>]<sup>−</sup> (Fe<sup>3+</sup>, d<sup>5</sup>) |
| `FeCl4_d6.txt` | Measured spectrum, [FeCl<sub>4</sub>]<sup>2−</sup> (Fe<sup>2+</sup>, d<sup>6</sup>) |
| `fig_fecl4_case_study.py` | Fits both spectra, selects the model by BIC, renders the figure |
| `fig_architecture.py` | Renders the architecture diagram (Figure 1); no data input |
| `fecl4_fit_results.json` | Fitted parameters, uncertainties, and the full model-selection comparison |

Both `.txt` files are two columns — incident photon energy in eV, then
normalised absorption — spanning 660–830 eV on a **non-uniform** grid (roughly
0.11 eV across the white lines, coarser in the background). They use classic-Mac
carriage-return line endings, so read them by splitting on `[\r\n]+`;
`readlines()` returns a single 691-record line.

## Reproducing

```bash
uv sync --group manuscript
uv run --with maturin maturin develop --release
uv run --group manuscript python manuscript/examples/fecl4/fig_fecl4_case_study.py
```

Expected output:

```
d5: 9 peaks  R2=0.999061  chi2_red=0.0071393  iters=41
d6: 10 peaks R2=0.999247  chi2_red=0.0043575  iters=37
ablation dBIC: d5 pre-shoulder +572.0 | d6 pre-shoulder +361.7 | d6 post-shoulder +30.4
L3 separation d5-d6 = 1.933 +/- 0.029 eV
```

## What the example demonstrates

**Expression edges as constraints.** The two `arctan` step amplitudes are not
fitted independently; they are tied in a fixed 2:1 ratio by one expression edge:

```python
compose(nodes).bind("step_l3.amplitude / 2", to="step_l2.amplitude")
```

That removes one free parameter and holds the ratio at exactly 2.000. This is
the capability the example exists to show, and it is the same mechanism the
JAX/optimistix backend in the benchmark cannot express.

Read the `arctan` pair as an empirical baseline, not as the physical 2p to
continuum edge jump. These published spectra are continuum-normalised: measured
directly on the shipped files, the difference between the pre-edge (698-703 eV)
and far post-edge (780-830 eV) regions is -0.005 for d5 and -0.025 for d6, both
zero within the noise of those regions. There is no edge step left in the data.
The 2:1 tie is a conventional and well-behaved constraint on a two-arctan
baseline, and a good demonstration of the feature; it is not evidence about the
L3/L2 branching ratio.

**Components specified from spectroscopy; BIC used as an ablation check.** The
component list is not chosen by a fit statistic. d5 carries a pre-shoulder near
706 eV; d6 carries a pre-shoulder near 705 eV and a post-shoulder near 708 eV.
Each is modelled because it is assigned. The Bayesian information criterion is
then reported per component as a check: each named shoulder is refitted away and
the resulting dBIC recorded (+572.0, +361.7, +30.4 — all favouring the
component). Every ablation is written to `fecl4_fit_results.json`, along with
each fit's condition number, so the evidence is auditable.

The order of those two steps matters. Letting BIC choose instead, with the d5
shoulder seeded at 706.3 eV from inspection of the residuals rather than at
706.0 eV from the spectroscopic assignment, has BIC *reject* the component by
+16.8 — the opposite verdict, from the same criterion on the same data. An
information criterion scores the optimum a solver actually reached, so on a
multi-modal surface it is partly scoring the initial guess.

## Limits of this example

It is a phenomenological decomposition, and it is here to exercise the fitting
machinery rather than to advance a spectroscopic analysis. Three limits are
worth stating plainly:

- The original publication did not peak-fit these spectra. It used a
  charge-transfer multiplet treatment and reported integrated intensities and
  metal-character percentages, so this decomposition is not a reproduction of
  it and the components are not comparable one-to-one with anything published.
- Individual component areas, widths and mixing parameters carry no orbital
  assignment. For weak-field high-spin halides the L3 region is dominated by
  2p core-hole multiplet effects, so the components are bookkeeping for a
  multiplet manifold, not resolvable states.
- The d5 fit is numerically ill-conditioned (condition number 1.5e20; several
  bounded `fraction` parameters return standard errors far exceeding their own
  bounds). The +/- 0.029 eV on the separation is a formal propagated value, not
  a defensible measurement uncertainty. Treat the result as "cleanly separated
  by about 1.9 eV" and check it against the published literature for these
  complexes before citing it.
