export type DestId = "standing" | "evidence";

// Two destinations: Standing (facts masthead + backend table) leads; Evidence
// (all cases, side by side) is the data deep-dive. The old Audit/Methods
// destination has been removed — its verification detail is available via
// GET /api/v1/trust (the "verification ledger" link in the footer).
export const DESTINATIONS: { id: DestId; label: string; blurb: string }[] = [
  { id: "standing", label: "Standing", blurb: "what was measured — facts, no verdict" },
  { id: "evidence", label: "Evidence", blurb: "all backends, all cases, side by side" },
];

const IDS = new Set<DestId>(["standing", "evidence"]);

export function destinationFromHash(hash: string): DestId {
  // A deep-linked case (`#case=<id>`) lives inside the Evidence destination;
  // EvidencePanel reads the hash for its Overview/Case sub-view.
  if (hash.startsWith("#case=")) return "evidence";
  // #audit redirects to evidence (Audit destination removed; content via /trust ledger).
  if (hash === "#audit") return "evidence";
  const id = hash.replace(/^#/, "") as DestId;
  return IDS.has(id) ? id : "standing";
}

export function hashOf(id: DestId): string {
  return `#${id}`;
}
