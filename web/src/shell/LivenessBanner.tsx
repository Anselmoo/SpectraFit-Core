/**
 * LivenessBanner — warn when the dev stack is unreachable or a newer run exists (G13).
 *
 * A dead dev-stack (Vite up, FastAPI down) leaves the SPA frozen on stale data,
 * indistinguishable from a live feed. This banner surfaces the difference.
 *
 * States:
 *   - "live"  → renders null (the happy path; no clutter).
 *   - "down"  → fetch failed; data may be frozen. Warn without auto-reload.
 *   - "stale" → a newer runTimestampUnix is served; offer a manual reload.
 *
 * Never polls when window.__BENCH__ is set (static offline bundle — no API to reach).
 */
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import type { BenchReport } from "../contract";
import { StatusStrip } from "../ui/StatusStrip";

type LivenessState = "initial" | "live" | "down" | "stale";

const POLL_INTERVAL_MS = 30_000;

export function LivenessBanner({ report }: { report: BenchReport }): ReactElement | null {
  const [liveness, setLiveness] = useState<LivenessState>("initial");
  const reportTs = report.runTimestampUnix;

  useEffect(() => {
    // Static offline bundle — no API to poll.
    if ((window as unknown as Record<string, unknown>).__BENCH__ != null) {
      return;
    }

    async function check(): Promise<void> {
      try {
        const res = await fetch("/api/report");
        if (!res.ok) {
          setLiveness("down");
          return;
        }
        const payload = (await res.json()) as { runTimestampUnix?: number | null };
        const servedTs = payload.runTimestampUnix ?? null;
        if (servedTs != null && typeof servedTs === "number" && servedTs > (reportTs ?? 0)) {
          setLiveness("stale");
        } else {
          setLiveness("live");
        }
      } catch {
        setLiveness("down");
      }
    }

    // Run one check immediately (as soon as the component mounts), then on interval.
    // Without this mount-time call the banner is blind for a full POLL_INTERVAL_MS on
    // first load — exactly the API-down/frozen-stale scenario it exists to surface.
    void check();
    const id = setInterval(() => void check(), POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [reportTs]);

  if (liveness === "initial" || liveness === "live") return null;

  if (liveness === "down") {
    return (
      <StatusStrip
        pillLabel="Dev stack unreachable"
        ariaLabel="liveness"
        style={{ maxWidth: "var(--layout-nav)" }}
      >
        Showing the last loaded run — data may be frozen. Start the FastAPI server at{" "}
        <code>:8000</code> and reload to reconnect.
      </StatusStrip>
    );
  }

  // liveness === "stale"
  return (
    <StatusStrip
      pillLabel="Newer run available"
      ariaLabel="liveness"
      style={{ maxWidth: "var(--layout-nav)" }}
      action={
        <button
          onClick={() => location.reload()}
          style={{
            padding: "2px var(--space-3)",
            fontFamily: "var(--font-mono)",
            fontSize: "0.8rem",
            cursor: "pointer",
            border: "1px solid var(--warning)",
            borderRadius: "var(--radius-md)",
            background: "transparent",
            color: "var(--text-primary)",
          }}
        >
          Reload
        </button>
      }
    >
      A newer benchmark run is available on the server.
    </StatusStrip>
  );
}
