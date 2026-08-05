/**
 * TDD: LivenessBanner — warn on dead dev-stack or newer run (G13).
 *
 * Cases:
 *   1. fetch rejects → after poll timer, a "down" banner appears.
 *   2. fetch resolves with NEWER runTimestampUnix → "stale" banner with reload control.
 *   3. fetch resolves with SAME runTimestampUnix → renders null (no banner).
 *   4. window.__BENCH__ set (static bundle) → renders null, fetch never called.
 */
import { render, cleanup, screen, act } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import React from "react";
import { LivenessBanner } from "../LivenessBanner";
import type { BenchReport } from "../../contract";

// Minimal report fixture — only runTimestampUnix matters here
const BASE_REPORT = { runTimestampUnix: 1000 } as unknown as BenchReport;

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  // Remove __BENCH__ if set
  delete (window as unknown as Record<string, unknown>).__BENCH__;
});

describe("LivenessBanner", () => {
  describe("fetch rejects → dev stack unreachable (down)", () => {
    it("renders no banner before the first poll fires", () => {
      vi.useFakeTimers();
      vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network error")));
      render(<LivenessBanner report={BASE_REPORT} />);
      expect(screen.queryByRole("status")).toBeNull();
    });

    it("shows a 'down' banner with aria-label 'liveness' after 30s", async () => {
      vi.useFakeTimers();
      vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network error")));
      render(<LivenessBanner report={BASE_REPORT} />);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(30_000);
      });

      const banner = screen.getByRole("status", { name: "liveness" });
      expect(banner).toBeTruthy();
      const text = banner.textContent ?? "";
      // Should mention unreachable / frozen / stack
      expect(text.toLowerCase()).toMatch(/unreachable|frozen|stack|dev/);
    });
  });

  describe("fetch resolves with a newer runTimestampUnix → stale", () => {
    it("shows a 'stale' banner offering a reload after 30s", async () => {
      vi.useFakeTimers();
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue({
          ok: true,
          json: () => Promise.resolve({ runTimestampUnix: 2000 }),
        }),
      );

      render(<LivenessBanner report={BASE_REPORT} />);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(30_000);
      });

      const banner = screen.getByRole("status", { name: "liveness" });
      expect(banner).toBeTruthy();
      const text = banner.textContent ?? "";
      expect(text.toLowerCase()).toMatch(/newer|available/);
      // Must offer a manual reload control
      const btn = banner.querySelector("button");
      expect(btn).toBeTruthy();
    });
  });

  describe("fetch resolves with the same runTimestampUnix → live (no banner)", () => {
    it("renders null after 30s when the run has not changed", async () => {
      vi.useFakeTimers();
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue({
          ok: true,
          json: () => Promise.resolve({ runTimestampUnix: 1000 }),
        }),
      );

      render(<LivenessBanner report={BASE_REPORT} />);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(30_000);
      });

      expect(screen.queryByRole("status", { name: "liveness" })).toBeNull();
    });
  });

  describe("window.__BENCH__ set → static bundle, never poll", () => {
    it("renders null immediately and never calls fetch", async () => {
      vi.useFakeTimers();
      const fetchMock = vi.fn();
      vi.stubGlobal("fetch", fetchMock);
      (window as unknown as Record<string, unknown>).__BENCH__ = {};

      render(<LivenessBanner report={BASE_REPORT} />);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(30_000);
      });

      expect(screen.queryByRole("status")).toBeNull();
      expect(fetchMock).not.toHaveBeenCalled();
    });
  });
});
