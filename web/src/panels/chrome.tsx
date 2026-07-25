import { useRef } from "react";
import type { ReactNode } from "react";
import { ExportButton } from "./ExportButton";

export function PanelTitle({ children }: { children: ReactNode }) {
  return (
    <h2
      style={{
        margin: 0,
        fontFamily: "var(--font-display)",
        fontSize: "1.1rem",  /* R5: unified with audit bespoke cards (was 1.05rem) */
        fontWeight: 300,
        color: "var(--ink)",
      }}
    >
      {children}
    </h2>
  );
}

export function Caption({ children }: { children?: ReactNode }) {
  if (children === undefined || children === null || children === "") return null;
  return (
    <p
      className="panel-caption"
      style={{
        margin: "var(--s1) 0 0",
        fontSize: "0.8rem",
        color: "var(--ink-faint)",
        lineHeight: 1.5,
      }}
    >
      {children}
    </p>
  );
}

export function PanelCard({
  title,
  caption,
  children,
}: {
  title: string;
  caption?: string;
  children: ReactNode;
}) {
  const bodyRef = useRef<HTMLDivElement>(null);
  // Derive a filename-safe slug from the title (lowercase, spaces → hyphens)
  const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return (
    <section
      className="glass"
      style={{ padding: "var(--s6)", display: "flex", flexDirection: "column", gap: "var(--s3)" }}
    >
      <header style={{ display: "flex", alignItems: "flex-start", gap: "var(--s3)" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <PanelTitle>{title}</PanelTitle>
          <Caption>{caption}</Caption>
        </div>
        <ExportButton containerRef={bodyRef} filename={slug} />
      </header>
      <div ref={bodyRef}>
        {children}
      </div>
    </section>
  );
}
