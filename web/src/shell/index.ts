/**
 * Shell module — top-level app shell with neutral narrative chain routing.
 *
 * Three destinations in evidence order: Standing → Audit → Evidence.
 * Subject-blind: no backend is crowned.
 * Hash permalink: #standing | #audit | #evidence.
 */
export { Shell } from "./Shell";
export { DESTINATIONS, destinationFromHash, hashOf } from "./nav";
export type { DestId } from "./nav";

// Legacy stub preserved for any existing consumers
export const SHELL_VERSION = "gen-3";
