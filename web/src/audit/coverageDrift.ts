/**
 * Discovery instrument (NOT a CI guard): given the contractCoverage manifest and
 * the concatenated panel/binding source, report every leaf classified `ignored:`
 * whose terminal field name nonetheless appears in the source — a candidate that
 * the manifest has drifted from reality (rendered-but-marked-ignored). Heuristic:
 * emits candidates for human/subagent confirmation, never verdicts.
 */
export interface DriftFinding {
  leaf: string;
  classification: string;
}

export function findCoverageDrift(
  manifest: Record<string, string>,
  source: string,
): DriftFinding[] {
  const out: DriftFinding[] = [];
  for (const [leaf, classification] of Object.entries(manifest)) {
    if (!classification.startsWith("ignored")) continue;
    // terminal field: last dotted segment, stripped of `[]`.
    const field = leaf.split(".").pop()!.replace(/\[\]/g, "");
    if (field.length >= 3 && source.includes(field)) {
      out.push({ leaf, classification });
    }
  }
  return out;
}
