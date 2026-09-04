/**
 * Table — fit-result / benchmark data table, mono type throughout since it's
 * overwhelmingly numeric. Ported from the DesignSync handbook's
 * components/data/Table.jsx, adapted onto this repo's tokens.css names.
 *
 * Token mapping notes (handbook name -> tokens.css name):
 *   --text-xs -> no named type-scale token exists in tokens.css; sized
 *                directly in kind with the other hardcoded rem sizes there
 *                (e.g. .wire-evidence at 0.78rem).
 * All other tokens (--border-strong, --border-subtle, --text-tertiary,
 * --text-primary, --font-mono) already exist under the same names.
 */
import type { ReactNode } from "react";

export interface TableColumn {
  key: string;
  label: string;
  align?: "left" | "right" | "center";
}

export interface TableProps {
  columns: TableColumn[];
  rows: Record<string, ReactNode>[];
  /** Tighter row padding for dense dashboards. @default false */
  dense?: boolean;
}

export function Table({ columns = [], rows = [], dense = false }: TableProps) {
  const cellPad = dense ? "6px 10px" : "9px 12px";
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--font-mono)", fontSize: "0.78rem" }}>
      <thead>
        <tr>
          {columns.map((c) => (
            <th
              key={c.key}
              style={{
                textAlign: c.align ?? "left",
                padding: cellPad,
                borderBottom: "1px solid var(--border-strong)",
                color: "var(--text-tertiary)",
                fontWeight: 600,
                textTransform: "uppercase",
                letterSpacing: "0.04em",
                fontSize: "10.5px",
              }}
            >
              {c.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          // eslint-disable-next-line react/no-array-index-key -- rows have no stable id in the contract
          <tr key={i} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
            {columns.map((c) => (
              <td key={c.key} style={{ textAlign: c.align ?? "left", padding: cellPad, color: "var(--text-primary)" }}>
                {r[c.key]}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
