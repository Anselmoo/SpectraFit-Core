#!/bin/bash

################################################################################
# PyO3 Boundary Validator
#
# Purpose: Ensure every #[pyfunction] in Rust code returns a JSON string
#          (String / Result<String, PyErr> / PyResult<String>), with a single
#          named, commented exemption for the zero-copy numpy path.
#
# Exit codes:
#   0 = All pyfunctions valid (correct return types)
#   1 = Violations found (invalid return types)
#
# Invocation status (verified 2026-09-08): AUTO-WIRED. `.pre-commit-config.yaml`
# registers this script as the `pre-merge-pyO3` hook with
# `stages: [pre-commit, pre-push]`, so it blocks commits and pushes wherever
# pre-commit's git hooks are installed. It is also runnable by hand, directly or
# via .claude/hooks/run-hook.sh. (The pre-2026-09-08 header claimed MANUAL-ONLY;
# that was true when audit F11 was written on 2026-06-26 and stopped being true
# when the pre-commit entry was added.)
#
# Scope note: the check is a signature-level static check. It joins a
# #[pyfunction]-annotated signature across however many lines it spans — up to
# the `{` that opens the body — before testing the return type, so a multi-line
# signature whose `->` sits on a later line is checked like any other. (Before
# 2026-09-08 only the `fn` line itself was inspected, which silently skipped
# both `fit_arrays` and `fit_arrays_numpy` — the two entrypoints Python
# actually calls.)
#
# Fail-closed note (2026-09-08): the scan between a `#[pyfunction]` marker and
# its `fn` line used to bail out to the seek state on any line it did not
# recognise, which silently DROPPED — never checked at all — a pyfunction whose
# marker was followed by a `///` doc comment, by a `#[pyo3(...)]` attribute
# spanning more than one line, or by a `pub(crate)`/`async`/`unsafe`/`const` fn
# (only `fn` and `pub fn` were matched). The scan now recognises those, and
# anything it still does not recognise is reported as
#   VIOLATION: #[pyfunction] at FILE:LINE has no recognisable signature
# rather than skipped. The recognised set between marker and `fn` is exactly:
# further attributes (including their continuation lines while the `[...]` is
# unclosed) and `//` / `///` comment lines. A blank line there is deliberately
# NOT recognised — legal Rust, but never written here, and treating it as a
# violation is what keeps "unrecognised" from becoming a silent skip again.
#
################################################################################

REPO_ROOT=$(git rev-parse --show-toplevel)
VIOLATIONS_FOUND=0

# ------------------------------------------------------------------------------
# Allowlist: #[pyfunction] names exempt from the JSON-string return rule.
#
#   fit_arrays_numpy — returns `PyResult<(String, Bound<PyArray1<f64>>)>` by
#     design. It is the zero-copy path: the compact result stays a JSON string
#     and the fitted curve is handed back as a NumPy array so the large
#     per-point buffer never round-trips through JSON (~2 ms/call). Handing it
#     back as JSON would delete the reason the entrypoint exists.
#
# Anything not listed here must return a JSON string. Adding a name to this list
# is a deliberate boundary change: document it in CLAUDE.md §4 (Rust) alongside
# the rule it exempts.
# ------------------------------------------------------------------------------
ALLOWLIST="fit_arrays_numpy"

# Find all Rust files with #[pyfunction] decorators. The bracket class
# `[](]` matches a literal `]` (a bare `#[pyfunction]`) or `(` (the start of
# `#[pyfunction(signature = ...)]`) right after the marker name — `]` must
# be the class's first character to be taken literally rather than closing
# it (POSIX bracket-expression rule). Before this, `#\[pyfunction\]` only
# matched the bare, argument-less marker and silently skipped any file whose
# sole pyfunction used `#[pyfunction(...)]`.
PYFUNCTION_FILES=$(find "$REPO_ROOT/crates" -name "*.rs" -type f -exec grep -l "#\[pyfunction[](]" {} + 2>/dev/null)

if [ -z "$PYFUNCTION_FILES" ]; then
    echo "[PyO3 Validator] No pyfunctions found. PASS."
    exit 0
fi

echo "[PyO3 Validator] Checking $(echo "$PYFUNCTION_FILES" | wc -l) files with #[pyfunction] decorators..."

while IFS= read -r FILE; do
    awk -v allowlist="$ALLOWLIST" '
    BEGIN {
        state = "seek"
        n_allow = split(allowlist, allow_parts, /[ ,]+/)
        for (i = 1; i <= n_allow; i++) allowed[allow_parts[i]] = 1
    }

    # Net `[` minus `]` on a line, so a `#[pyo3(...)]` attribute that spans
    # several lines can be consumed to its close instead of ending the scan.
    function bracket_delta(s,   i, ch, d) {
        d = 0
        for (i = 1; i <= length(s); i++) {
            ch = substr(s, i, 1)
            if (ch == "[") d++
            else if (ch == "]") d--
        }
        return d
    }

    function check_signature(sig, decl_line,   head, brace, arrow, ret, name) {
        brace = index(sig, "{")
        head = (brace > 0) ? substr(sig, 1, brace - 1) : sig

        # Function name: the identifier right after `fn`.
        name = head
        sub(/^.*[^a-zA-Z0-9_]fn[ \t]+/, "", name)
        sub(/^fn[ \t]+/, "", name)
        sub(/[^a-zA-Z0-9_].*$/, "", name)

        arrow = index(head, "->")
        if (arrow == 0) {
            print "VIOLATION: #[pyfunction] \"" name "\" has no return type in " \
                  FILENAME ":" decl_line " (must return a JSON string)"
            return 1
        }
        ret = substr(head, arrow + 2)
        gsub(/[ \t\r\n]+/, " ", ret)
        gsub(/^ +| +$/, "", ret)

        if (name in allowed) {
            print "[PyO3 Validator] allowlisted exemption: " name " -> " ret \
                  " (" FILENAME ":" decl_line ")"
            return 0
        }
        if (ret !~ /^(String|Result<String, PyErr>|PyResult<String>)$/) {
            print "VIOLATION: Invalid return type \"" ret "\" for #[pyfunction] \"" \
                  name "\" in " FILENAME ":" decl_line
            return 1
        }
        return 0
    }

    {
        if (state == "seek") {
            # Matches a bare `#[pyfunction]` or an argument-taking
            # `#[pyfunction(signature = ...)]` marker — before this, the
            # marker regex required the immediate `]` and silently skipped
            # every file whose sole pyfunction took arguments.
            if ($0 ~ /^[ \t]*#\[pyfunction(\]|\()/) {
                state = "attr"; decl_line = NR; attr_depth = bracket_delta($0)
            }
            next
        }
        if (state == "attr") {
            # Continuation lines of an attribute whose `[...]` is still open,
            # e.g. a #[pyo3(\n signature = (a)\n)] block.
            if (attr_depth > 0) { attr_depth += bracket_delta($0); next }
            # Further attributes (e.g. #[pyo3(signature = ...)]) and doc / line
            # comments sit between the #[pyfunction] marker and the signature.
            if ($0 ~ /^[ \t]*#\[/) { attr_depth = bracket_delta($0); next }
            if ($0 ~ /^[ \t]*\/\//) next
            # Visibility, async, unsafe, const and extern qualifiers all precede
            # `fn`; matching only `fn` / `pub fn` silently dropped the rest.
            if ($0 ~ /^[ \t]*((pub([ \t]*\([^)]*\))?|async|unsafe|const|extern[^ ]*)[ \t]+)*fn[ \t]/) {
                sig = $0; state = "sig"
            } else {
                # Fail closed: an unrecognised line between the marker and the
                # signature is reported, never skipped.
                print "VIOLATION: #[pyfunction] at " FILENAME ":" decl_line \
                      " has no recognisable signature"
                violations += 1
                state = "seek"
                next
            }
        } else if (state == "sig") {
            sig = sig " " $0
        }
        # Accumulate until the `{` that opens the body, then test the whole thing.
        if (state == "sig" && index(sig, "{") > 0) {
            violations += check_signature(sig, decl_line)
            state = "seek"
            sig = ""
        }
    }

    END { if (violations > 0) exit 1 }
    ' "$FILE" || VIOLATIONS_FOUND=$((VIOLATIONS_FOUND + 1))
done <<< "$PYFUNCTION_FILES"

if [ "$VIOLATIONS_FOUND" -gt 0 ]; then
    echo "[PyO3 Validator] FAIL: $VIOLATIONS_FOUND file(s) contain pyfunction return-type violations."
    exit 1
else
    echo "[PyO3 Validator] PASS: All pyfunctions return JSON strings (or are allowlisted)."
    exit 0
fi
