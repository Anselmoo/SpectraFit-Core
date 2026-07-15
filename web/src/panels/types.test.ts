import { expect, test } from "vitest";
import { scopeMatches } from "./types";

test("static panels show in any view", () => {
  expect(scopeMatches("static", "overview")).toBe(true);
  expect(scopeMatches("static", "case")).toBe(true);
});
test("overview panels only in overview view", () => {
  expect(scopeMatches("overview", "overview")).toBe(true);
  expect(scopeMatches("overview", "case")).toBe(false);
});
test("case panels only in case view", () => {
  expect(scopeMatches("case", "case")).toBe(true);
  expect(scopeMatches("case", "overview")).toBe(false);
});
