import type { ReactElement } from "react";

export interface SuiteRow {
  id: string; name?: string; category: string; difficulty?: number;
  m: Record<string, { r2: number; speedup: number; redChi2?: number; success?: boolean }>;
  winner: string; regression: boolean;
}

export function toCsv(suite: SuiteRow[], solverIds: string[]): string {
  const head = ["id", "category", ...solverIds.flatMap((b) => [`${b}_r2`, `${b}_speedup`, `${b}_redChi2`, `${b}_success`]), "winner", "regression"];
  const lines = suite.map((c) =>
    [c.id, c.category, ...solverIds.flatMap((b) => [
      c.m[b]?.r2 ?? "",
      c.m[b]?.speedup ?? "",
      c.m[b]?.redChi2 ?? "",
      c.m[b]?.success != null ? (c.m[b].success ? "1" : "0") : "",
    ]), c.winner, c.regression ? "1" : "0"].join(","),
  );
  return [head.join(","), ...lines].join("\n");
}

export function SuiteTable({ suite, solverIds, onSelect }: { suite: SuiteRow[]; solverIds: string[]; onSelect?: (id: string) => void }): ReactElement {
  return (
    <table className="suite-table" style={{ fontFamily: "var(--font-mono)", fontSize: "11px", borderCollapse: "collapse", width: "100%" }}>
      <thead>
        <tr style={{ color: "var(--ink-faint)", textAlign: "right" }}>
          <th style={{ textAlign: "left" }}>case</th>
          <th style={{ textAlign: "left" }}>category</th>
          {solverIds.map((b) => <th key={`${b}-r2`}>{b} r²</th>)}
          {solverIds.map((b) => <th key={`${b}-chi2`}>{b} χ²_red</th>)}
          {solverIds.map((b) => <th key={`${b}-ok`}>{b} ok</th>)}
          <th>winner</th>
        </tr>
      </thead>
      <tbody>
        {suite.map((c) => (
          <tr key={c.id} data-case-id={c.id} data-regression={c.regression ? "1" : "0"}
              className={onSelect ? "suite-row--clickable" : undefined}
              style={{ color: c.regression ? "var(--warn)" : "var(--ink-dim)", textAlign: "right", ...(onSelect ? { cursor: "pointer" } : {}) }}
              onClick={() => onSelect?.(c.id)}
              tabIndex={onSelect ? 0 : undefined}
              aria-label={onSelect ? `Open case ${c.id}` : undefined}
              title={onSelect ? `Open case ${c.id}` : undefined}
              onKeyDown={(e) => {
                if (onSelect && (e.key === "Enter" || e.key === " ")) {
                  e.preventDefault();
                  onSelect(c.id);
                }
              }}>
            {/* Case id reads as a link (accent) when the row is clickable — the
                affordance signal, on top of the hover highlight + cursor. */}
            <td style={{ textAlign: "left", ...(onSelect ? { color: "var(--accent)" } : {}) }}>{c.id}</td>
            <td style={{ textAlign: "left" }}>{c.category}</td>
            {solverIds.map((b) => <td key={`${b}-r2`}>{c.m[b] ? c.m[b].r2.toFixed(4) : "—"}</td>)}
            {solverIds.map((b) => <td key={`${b}-chi2`}>{c.m[b]?.redChi2 != null ? c.m[b].redChi2!.toFixed(3) : "—"}</td>)}
            {solverIds.map((b) => <td key={`${b}-ok`} title={c.m[b]?.success != null ? (c.m[b].success ? "converged" : "failed") : "—"}>{c.m[b]?.success != null ? (c.m[b].success ? "✓" : "✗") : "—"}</td>)}
            <td>{c.winner}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
