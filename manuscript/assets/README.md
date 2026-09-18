# Venue assets

## `jors-template.docx`

The official JORS (Journal of Open Research Software, Ubiquity Press) software
metapaper template, downloaded unmodified from

    https://account.openresearchsoftware.metajnl.com/index.php/up-j-jors/libraryFiles/downloadPublic/4

sha256 `e7d18e25a580011a4b06fb42675dec01154d1101759e7fdddeffec392205d0f8`, verified on every `--docx` render.

It is committed unmodified on purpose. `render_manuscript.py --docx` derives a
pandoc-compatible reference document from it at render time rather than editing
it in place, because pandoc and this template disagree about style *names*:

| pandoc emits | template ships |
| --- | --- |
| `Heading1`, `Heading2` | `UPPaperTitle`, `UPSectionHeading` |
| `BodyText`, `FirstParagraph`, `Compact` | (absent) |

Word resolves an unknown style id to Normal **silently**, so passing this file
to `--reference-doc` directly produces a document that opens cleanly with every
heading rendered as plain body text. The derived reference doc adds the missing
ids as `basedOn` aliases of the UP styles, so the formatting is inherited from
the official template rather than copied — if JORS revises the template, the
headings follow instead of drifting.
