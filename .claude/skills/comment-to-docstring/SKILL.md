---
name: comment-to-docstring
description: >-
  Convert Python comment blocks into real module, function, and class docstrings
  without confusing arbitrary inline comments with documentation. Use this skill
  whenever the user asks to turn greyed-out # comments into docstrings, promote
  comments to documentation, clean up Python comments, or make a file such as
  runner.py self-documenting. Inspect the syntax position first, produce a dry-run
  diff, preserve meaningful text and indentation, and report comments that cannot
  safely become docstrings. For JavaScript or TypeScript, explain that JSDoc is a
  separate format and do not apply Python triple quotes.
license: MIT
compatibility: Python 3.13+
---

# Comment to docstring

Turn comments into documentation only when Python will actually treat the result
as a docstring. A triple-quoted string after executable code is merely an unused
expression, so never pretend that it documents a function or class.

## Workflow

1. Read the complete target file and identify the comment block's syntax owner.
2. Classify each block:
   - **Module-leading**: before the first real statement at file scope.
   - **Declaration-leading**: immediately before `def`, `async def`, or `class`,
     at the declaration's indentation.
   - **Body-leading**: immediately after a declaration, before its first statement.
   - **Inline/non-leading**: after executable code or inside a control-flow branch.
3. Convert only the first three categories into a real docstring.
4. If a declaration already has a docstring, replace it only when the user asked
   for replacement; otherwise leave it unchanged and report the conflict.
5. Preserve indentation, line order, and comment text after removing the comment
   marker and one conventional separator space.
6. Run `--dry-run` first and show a unified diff. Apply changes only after review.
7. Parse the transformed file with `ast.parse`; abort rather than writing invalid
   Python.

## Reference implementation

Use `scripts/convert_py.py` for deterministic conversion. It supports:

- `--dry-run` (default): print a unified diff and write nothing.
- `--apply`: write the transformed file after syntax validation.
- `--replace-existing`: replace an existing declaration docstring.
- `--check`: exit 1 when safe convertible blocks exist.
- `--json-report`: emit converted/skipped block metadata.

Example:

```text
python .claude/skills/comment-to-docstring/scripts/convert_py.py \
  --dry-run python/oracles/audit/runner.py
```

## Important behavior for `runner.py`

The module header is already a real module docstring. The docstrings for
`_sanitize`, `_compute_rung`, `_assert_audited_claims_resolve`, and the other
functions are already real docstrings. Comments such as `# any genuine failure`
after executable code are inline comments, not docstrings, and must remain
comments. The converter should therefore produce no unsafe rewrite for those
lines and report them as skipped when requested.

## JavaScript and TypeScript

Do not insert Python triple quotes into JS/TS. If JS/TS support is requested,
use a parser-aware JSDoc transformation (`/** ... */`) and preserve whether the
comment documents a declaration or is an inline implementation note. That
implementation is intentionally separate from the Python converter because the
languages have different documentation semantics.

## Output contract

Report:

- converted blocks and their owner (`module`, `function`, or `class`);
- skipped blocks and why they are not docstrings;
- whether an existing docstring was replaced;
- the validation result and the diff path/content.

Never claim that every `#` comment became a docstring when some blocks were
skipped. This distinction is the core correctness guarantee.
