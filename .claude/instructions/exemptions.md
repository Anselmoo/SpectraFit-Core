> Applies to: **/*.{py,rs}

# Exemptions & experimental code policy

When generated code, large prototypes, or vendor snapshots cannot meet coverage or linting rules immediately, follow this process to request a timeboxed exemption.

## Rules

- Exemption request must be added to the PR body in an `Exemption:` section and link to a tracking issue describing:
  - Reason for exemption
  - Scope (files/modules affected)
  - Remediation plan with ETA (date or milestone)

- Exemptions are timeboxed (default 30 days). PRs that request longer exemptions must include an approver and a clear migration plan.

- Exempted files should be located under a clearly named path (e.g., `experimental/` or contain a header comment) and listed in the tracking issue.

## Coverage and exemptions

- Exemptions do not change repository-level thresholds permanently. Use `# pragma: no cover` sparingly and only when tracked in the exemption issue.

## Do not

- Do not request blanket long-term exemptions without an approved architecture-level decision and a linked issue.
