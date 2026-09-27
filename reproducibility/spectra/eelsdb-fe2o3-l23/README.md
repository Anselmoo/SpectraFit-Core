# Fe₂O₃ Fe L₂,₃ core-loss spectrum (EELS Database)

> **This directory is licensed ODbL, not MIT.** The rest of this repository is
> MIT-licensed; that licence covers the *code*. The spectrum below is third-party
> data redistributed under the Open Data Commons Open Database License, which is
> share-alike for derivative databases. Do not let the repository's MIT notice be
> read as applying to this file.

## The file

`DspecTi3wqG.msa` — the upstream filename, kept unchanged because it is the
provenance handle that ties this copy to its source record.

| | |
| :--- | :--- |
| Format | EMSA/MAS Spectral Data File v1.0, `#DATATYPE XY` (comma-separated `x, y` rows) |
| Title | `Fe2O3_Fe_L3_Qiang_Xu_141` |
| Points | 1024 |
| Range | 695.00 – 746.15 eV |
| Dispersion | 0.05 eV/channel (`#XPERCHAN`), offset 695.0 eV (`#OFFSET`) |
| Signal | `ELS`, core loss; Fe L₂,₃ edge of Fe₂O₃ (L3 white line at 710.75 eV) |
| Resolution | 0.3 eV |
| Instrument | Tecnai F20 monochromator, 200 kV, parallel GIF Tridiem detector |
| Acquisition | 15 s integration, 50 nm² probe, parallel illumination |
| Bytes / sha256 | 30096 / `28e88f85350c353f524c828740c533312dc897505410ac940cd544060df963d4` |

The digest is also recorded in `reproducibility/assets.toml` and verified by
`uv run poe fair asset verify`.

## Provenance

- **Source page:** <https://eelsdb.eu/spectra/iron-oxide-2/>
- **Download:** <https://eelsdb.eu/wp-content/uploads/2015/09/DspecTi3wqG.msa>
- **Retrieved:** 2026-09-22
- **Contributor:** Qiang Xu, submitted 2007-12-10
- **Original publication:** none. The source record states *"No reference found
  for this data."* — so the database citation below is the citation, not a
  fallback.
- **Per-spectrum DOI:** none issued.

## Licence and required attribution

Spectroscopic data in the EELS Database is published under the
[Open Data Commons Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/):
you are free to copy, distribute, transmit and adapt the data as long as you
credit the EELS Data Base and its contributors, and distribute any adapted
*database* under the same licence. A figure rendered from this spectrum is a
Produced Work: it may carry any licence, but must carry the attribution notice.

**Cite when using this data:**

> Ewels P, Sikora T, Serin V, Ewels CP, Lajaunie L. A Complete Overhaul of the
> Electron Energy-Loss Spectroscopy and X-Ray Absorption Spectroscopy Database:
> eelsdb.eu. *Microscopy and Microanalysis.* 2016;22(3):717–724.
> doi:[10.1017/S1431927616000179](https://doi.org/10.1017/S1431927616000179)

Credit is due to the EELS Database and to the contributor named above.

## What uses it

`docs/tutorials/gallery/misspecified_model.py` fits the 704–716 eV L3 window
with a ladder of three increasingly elaborate models, to show r² and AIC both
improving while a runs test on the residuals rejects every rung. An Fe L-edge
carries multiplet structure that no small number of independent symmetric
components reproduces — which is precisely why it makes the point.
