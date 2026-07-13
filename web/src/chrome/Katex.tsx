/**
 * Katex — render a LaTeX string to real math.
 *
 * Synchronous (katex.renderToString) + isolated dangerouslySetInnerHTML, so it
 * never reaches into a React-managed subtree imperatively. throwOnError:false:
 * a malformed formula degrades to its highlighted source, never a crash.
 */
import { useMemo, type ReactElement } from "react";
import katex from "katex";

export function Katex({ tex, display = false }: { tex: string; display?: boolean }): ReactElement {
  const html = useMemo(
    () =>
      katex.renderToString(tex, {
        displayMode: display,
        throwOnError: false,
        output: "html",
      }),
    [tex, display],
  );
  return (
    <span
      dangerouslySetInnerHTML={{ __html: html }}
      style={{ fontSize: display ? "1.05rem" : "1rem", color: "var(--ink)" }}
    />
  );
}
