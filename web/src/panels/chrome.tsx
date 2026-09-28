import { useRef } from "react";
import type { ReactNode } from "react";
import { ExportButton } from "./ExportButton";
import { Card } from "../ui/Card";

export function PanelTitle({ children }: { children: ReactNode }) {
  return (
    <h2
      style={{
        margin: 0,
        fontFamily: "var(--font-display)",
        fontSize: "1.1rem",  /* R5: unified with audit bespoke cards (was 1.05rem) */
        fontWeight: 300,
        color: "var(--text-primary)",
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
        margin: "var(--space-1) 0 0",
        fontSize: "0.8rem",
        color: "var(--text-secondary)",
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
  // Composes the shared Card (flat --surface-card + --shadow-sm) instead of a
  // hand-rolled `<section className="glass">`: the handbook restricts
  // backdrop-filter blur/vibrancy chrome material to NAVIGATION surfaces
  // (sticky topbars/sidebars) and forbids it on content cards. Panel cards
  // are content, so they no longer carry "glass" at all.
  //
  // Card's own header slot only accepts a string title/subtitle, not an
  // action node, so ExportButton — previously rendered beside the title in
  // a hand-rolled header row — now renders as a right-aligned row at the
  // top of the body instead. It stays functionally in the same place
  // (top of the card, immediately below the title) via the ref Card
  // forwards to its body wrapper, which is exactly the container
  // ExportButton's `querySelector("svg")` needs to search.
  return (
    <Card ref={bodyRef} title={title} subtitle={caption} padding="lg">
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "var(--space-2)" }}>
        <ExportButton containerRef={bodyRef} filename={slug} />
      </div>
      {children}
    </Card>
  );
}
