export type Provenance = "measured" | "derived" | "reconstructed" | "absent";
export const PROV_ORDER: Provenance[] = ["measured", "derived", "reconstructed", "absent"];

export function provStyle(p: Provenance): { className: string; color: string; opacity: number } {
  const map: Record<Provenance, { color: string; opacity: number }> = {
    measured:      { color: "var(--prov-measured)", opacity: 1.0 },
    derived:       { color: "var(--prov-derived)", opacity: 0.92 },
    reconstructed: { color: "var(--prov-reconstructed)", opacity: 0.7 },
    absent:        { color: "var(--prov-absent)", opacity: 0.5 },
  };
  return { className: `prov-${p}`, ...map[p] };
}

export function historyMode(src: "real" | "reconstructed"): "line" | "endpoints" {
  return src === "real" ? "line" : "endpoints";
}

const FORBIDDEN_ON_SYNTHETIC = /\b(rixs|experimental|measured|observed)\b/i;
export function titleGuard(title: string, dataProvenance: "measured" | "synthetic"): string {
  if (dataProvenance === "synthetic" && FORBIDDEN_ON_SYNTHETIC.test(title)) {
    throw new Error(`synthetic data must not be titled as a real measurement: "${title}"`);
  }
  return title;
}
