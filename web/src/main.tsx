import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style/tokens.css";
import "katex/dist/katex.min.css";
import { loadReport, assertSupported, type BenchReport } from "./contract";
import { Shell } from "./shell";

type AppState =
  | { status: "loading" }
  | { status: "ok"; report: BenchReport }
  | { status: "error"; message: string };

function App() {
  const [state, setState] = useState<AppState>({ status: "loading" });

  useEffect(() => {
    // Prefer window.__BENCH__ (offline bundle inlined by vite.config.ts).
    // Fall back to the API fetch for the live / dev mode.
    const inlined = (window as unknown as Record<string, unknown>).__BENCH__;
    if (inlined != null && typeof inlined === "object") {
      try {
        const report = inlined as BenchReport;
        assertSupported(report);
        setState({ status: "ok", report });
      } catch (err: unknown) {
        setState({
          status: "error",
          message: err instanceof Error ? err.message : String(err),
        });
      }
      return;
    }

    loadReport()
      .then((report) => setState({ status: "ok", report }))
      .catch((err: unknown) =>
        setState({
          status: "error",
          message: err instanceof Error ? err.message : String(err),
        }),
      );
  }, []);

  if (state.status === "loading") {
    return (
      <div
        role="status"
        aria-live="polite"
        aria-busy="true"
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "var(--s5)",
        }}
      >
        <div className="glass" style={{ padding: "var(--s6)", color: "var(--ink-dim)" }}>
          Loading report…
        </div>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div
        role="alert"
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "var(--s5)",
        }}
      >
        <div
          className="glass"
          style={{
            padding: "var(--s6)",
            borderColor: "var(--fail)",
            maxWidth: 480,
          }}
        >
          <h2
            style={{
              margin: "0 0 var(--s3)",
              fontFamily: "var(--font-display)",
              color: "var(--fail)",
              fontSize: "1.25rem",
            }}
          >
            Report load failed
          </h2>
          <p
            style={{
              margin: 0,
              fontFamily: "var(--font-mono)",
              fontSize: "0.85rem",
              color: "var(--ink-dim)",
              wordBreak: "break-all",
            }}
          >
            {state.message}
          </p>
          <p style={{ margin: "var(--s3) 0 0", fontSize: "0.8rem", color: "var(--ink-faint)" }}>
            Is the FastAPI server running at{" "}
            <code style={{ fontFamily: "var(--font-mono)" }}>http://localhost:8000</code>?
          </p>
        </div>
      </div>
    );
  }

  return <Shell report={state.report} />;
}

const root = document.getElementById("root");
if (!root) throw new Error("No #root element found in index.html");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
