import { readFileSync } from "node:fs";

import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// Two build modes:
//   * default — a normal deployable static app that fetches the report at runtime from
//     the FastAPI app (`/api/report`); `/api` is proxied to uvicorn in dev.
//   * BUILD_HTML=1 — a SELF-CONTAINED single `report.html` (JS + CSS inlined via
//     vite-plugin-singlefile) with the report inlined as `window.__BENCH__` from the
//     `BENCH_JSON` file, so it opens offline / deploys as one file (poe report_html).
const buildHtml = process.env.BUILD_HTML === "1";
const benchJson = process.env.BENCH_JSON;

/** Inject the benchmark results.json as `window.__BENCH__` into <head>. */
function inlineBench(jsonPath: string): Plugin {
  return {
    name: "inline-bench-report",
    transformIndexHtml(html) {
      // Read the file as text and escape `<` so a stray `</script>` in the
      // data can never close the tag.  We deliberately skip JSON.parse →
      // JSON.stringify: that round-trip (a) doubles peak heap on a ~44 MB
      // file and (b) crashes on non-RFC-8259 tokens like `Infinity` / `NaN`
      // that Python's json module can emit for float("inf") values.  The raw
      // file is already compact-enough JSON for the browser; no minification
      // is required here.
      const json = readFileSync(jsonPath, "utf-8").replace(/</g, "\\u003c");
      return html.replace(
        "</head>",
        `<script>window.__BENCH__=${json}</script>\n</head>`,
      );
    },
  };
}

export default defineConfig({
  plugins: [
    react(),
    ...(buildHtml ? [viteSingleFile()] : []),
    ...(buildHtml && benchJson ? [inlineBench(benchJson)] : []),
  ],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  build: {
    target: "es2022",
    chunkSizeWarningLimit: 100_000,
    ...(buildHtml ? { outDir: "dist-html" } : {}),
  },
});
