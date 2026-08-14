/**
 * I-PROSE-CONTRACT drift guard.
 *
 * Trust-claim PROSE must not contradict the canonical wire disposition. The
 * concrete drift that motivated this guard (Cycle 1, C1.3): `LIMITATIONS.md`
 * described W2c as a "capability gap … left unaudited" while the Standing/Methods
 * panels had been flipped to render "W2c — pass". One surface drifted from the
 * other and every existing guard stayed green.
 *
 * Canonical source of truth: `python/oracles/audit/wires.py`
 * `wire_w2c_jacobian_kappa` returns pass / skipped / fail based on the SUBJECT's
 * Jacobian conditioning — it is NEVER a blanket subject-level "gap". The oracle
 * backends (lmfit/jax) not exposing κ(J) is a disclosed, non-capping per-backend
 * limitation, explicitly "not a subject capability gap".
 *
 * SCOPE — live surfaces ONLY. We scan the prose/captions that a reader takes as
 * the project's current claims: `LIMITATIONS.md` and the rendered Standing/Methods
 * panel bodies. We deliberately DO NOT scan `DECISIONS.md` ADRs or the dated
 * `docs/superpowers/{plans,specs}/*` — those are append-only history and quote the
 * pre-fix wording on purpose; scanning them would make the guard un-passable.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// web/src/__tests__ -> web/src -> web -> repo root
const REPO_ROOT = join(import.meta.dirname, "..", "..", "..");

const LIVE_SURFACES: Record<string, string> = {
  "LIMITATIONS.md": join(REPO_ROOT, "LIMITATIONS.md"),
  "standing.tsx": join(REPO_ROOT, "web", "src", "panels", "bodies", "standing.tsx"),
  "methods.tsx": join(REPO_ROOT, "web", "src", "panels", "bodies", "methods.tsx"),
  "nestedAdequacy.tsx": join(REPO_ROOT, "web", "src", "panels", "bodies", "nestedAdequacy.tsx"),
  "inferentialHeadline.tsx": join(REPO_ROOT, "web", "src", "panels", "bodies", "inferentialHeadline.tsx"),
};

const WEB_BODIES = ["standing.tsx", "methods.tsx"] as const;

/** Surfaces that carry W9 scope-disclosure prose (subset of LIVE_SURFACES). */
const W9_SURFACES = ["standing.tsx", "methods.tsx", "nestedAdequacy.tsx"] as const;

/** Surfaces that carry W10/W11 scope-disclosure prose (subset of LIVE_SURFACES). */
const W10_W11_SURFACES = ["standing.tsx", "methods.tsx", "inferentialHeadline.tsx"] as const;

// ---------------------------------------------------------------------------
// Pure checkers (exercised against injected fixtures AND the live files)
// ---------------------------------------------------------------------------

/**
 * The disposition a text asserts for W2c as the SUBJECT's status.
 *  - "pass"   : affirms (or does not contradict) W2c passing for the subject — canonical
 *  - "gap"    : asserts W2c is a gap / unaudited / failure for the subject — DRIFT
 *  - "absent" : the text does not mention W2c
 *
 * Polarity rule: within each "W2c …" clause (up to the first period or newline),
 * the FIRST disposition keyword decides. So "W2c passes … not a subject capability
 * gap" reads as PASS (first keyword "passes"), while "W2c is a capability gap, left
 * unaudited" reads as DRIFT (no pass keyword precedes the gap keyword).
 */
export function w2cDisposition(text: string): "pass" | "gap" | "absent" {
  const PASS = /\bpass(es|ed)?\b/i;
  const GAP = /\b(capability gap|left unaudited|unaudited|is a gap|gap,\s*not a pass|fails?)\b/i;
  let sawW2c = false;
  let drift = false;
  for (const m of text.matchAll(/W2c\)?([^.\n]*)/gi)) {
    sawW2c = true;
    const clause = m[1];
    const pIdx = clause.search(PASS);
    const gIdx = clause.search(GAP);
    if (gIdx >= 0 && (pIdx < 0 || gIdx < pIdx)) drift = true;
  }
  if (!sawW2c) return "absent";
  return drift ? "gap" : "pass";
}

/**
 * The disposition a text asserts for W9 (nested-model adequacy) as the current
 * claim status.
 *  - "pass"   : affirms W9 is implemented / exercised / recovers the true order — canonical
 *  - "gap"    : asserts W9 is unaudited / a bare "not exercised" gap claim — DRIFT
 *  - "absent" : the text does not mention W9
 *
 * Polarity rule:
 *  - "unaudited" or "is an unaudited gap" → always DRIFT.
 *  - "implemented … but not exercised" → NOT drift (honest scope disclosure).
 *  - "recovers … (W9, BIC)" → NOT drift (explicit pass claim).
 *  - bare "not exercised" without any qualifying implemented/pass context → DRIFT.
 *
 * Implementation: scan a window of up to 120 chars around each W9 mention,
 * looking for honest/pass qualifiers in the wider context sentence.
 */
export function w9Disposition(text: string): "pass" | "gap" | "absent" {
  const HONEST = /\b(implemented|recov(ers|ered)|pass(es|ed)?|backed by)\b/i;
  // "but not exercised" after "implemented" is a qualified honest disclosure.
  const HONEST_BUT_NOT = /implemented[^.]{0,80}not exercised/i;
  const GAP = /\b(unaudited|is\s+an?\s+unaudited\s+gap|is a gap)\b/i;
  // Bare "not exercised" WITHOUT "implemented" qualifier: a gap claim.
  const BARE_NOT_EXERCISED = /(?<!implemented[^.]{0,60})\bnot exercised\b/i;

  let sawW9 = false;
  let drift = false;

  for (const m of text.matchAll(/W9/gi)) {
    sawW9 = true;
    // Widen context: 100 chars before and 120 chars after the W9 token.
    const start = Math.max(0, m.index! - 100);
    const end = Math.min(text.length, m.index! + 120);
    const ctx = text.slice(start, end);

    if (GAP.test(ctx)) {
      drift = true;
      continue;
    }
    // "implemented … but not exercised" → honest, not drift.
    if (HONEST_BUT_NOT.test(ctx)) continue;
    // Any other honest/pass qualifier → not drift.
    if (HONEST.test(ctx)) continue;
    // Bare "not exercised" in context → drift.
    if (BARE_NOT_EXERCISED.test(ctx)) {
      drift = true;
    }
  }

  if (!sawW9) return "absent";
  return drift ? "gap" : "pass";
}

/**
 * The disposition a text asserts for W10 (σ-calibration) as the current claim status.
 *  - "pass"   : affirms W10 is implemented / exercised / backs the headline — canonical
 *  - "gap"    : asserts W10 is an unaudited gap — DRIFT
 *  - "absent" : the text does not mention W10
 *
 * Polarity rule:
 *  - "W10 is an unaudited gap" → always DRIFT.
 *  - "implemented (W10) but not exercised" → NOT drift (honest scope disclosure).
 *  - "inferential tests back the headline (W10" → NOT drift (explicit pass claim).
 *  - bare "not exercised" without qualifying context → DRIFT.
 */
export function w10Disposition(text: string): "pass" | "gap" | "absent" {
  const HONEST = /\b(implemented|back\s+the\s+headline|validated\s+where\s+tested|pass(es|ed)?)\b/i;
  const HONEST_BUT_NOT = /implemented[^.]{0,80}not exercised/i;
  const GAP = /\b(unaudited|is\s+an?\s+unaudited\s+gap|is a gap)\b/i;
  const BARE_NOT_EXERCISED = /(?<!implemented[^.]{0,60})\bnot exercised\b/i;

  let sawW10 = false;
  let drift = false;

  for (const m of text.matchAll(/W10/gi)) {
    sawW10 = true;
    const start = Math.max(0, m.index! - 100);
    const end = Math.min(text.length, m.index! + 120);
    const ctx = text.slice(start, end);

    if (GAP.test(ctx)) {
      drift = true;
      continue;
    }
    if (HONEST_BUT_NOT.test(ctx)) continue;
    if (HONEST.test(ctx)) continue;
    if (BARE_NOT_EXERCISED.test(ctx)) {
      drift = true;
    }
  }

  if (!sawW10) return "absent";
  return drift ? "gap" : "pass";
}

/**
 * The disposition a text asserts for W11 (speed significance) as the current claim status.
 *  - "pass"   : affirms W11 is implemented / exercised / backs the headline — canonical
 *  - "gap"    : asserts W11 is an unaudited gap — DRIFT
 *  - "absent" : the text does not mention W11
 *
 * Polarity rule: mirrors w10Disposition.
 */
export function w11Disposition(text: string): "pass" | "gap" | "absent" {
  const HONEST = /\b(implemented|back\s+the\s+headline|validated\s+where\s+tested|pass(es|ed)?)\b/i;
  const HONEST_BUT_NOT = /implemented[^.]{0,80}not exercised/i;
  const GAP = /\b(unaudited|is\s+an?\s+unaudited\s+gap|is a gap)\b/i;
  const BARE_NOT_EXERCISED = /(?<!implemented[^.]{0,60})\bnot exercised\b/i;

  let sawW11 = false;
  let drift = false;

  for (const m of text.matchAll(/W11/gi)) {
    sawW11 = true;
    const start = Math.max(0, m.index! - 100);
    const end = Math.min(text.length, m.index! + 120);
    const ctx = text.slice(start, end);

    if (GAP.test(ctx)) {
      drift = true;
      continue;
    }
    if (HONEST_BUT_NOT.test(ctx)) continue;
    if (HONEST.test(ctx)) continue;
    if (BARE_NOT_EXERCISED.test(ctx)) {
      drift = true;
    }
  }

  if (!sawW11) return "absent";
  return drift ? "gap" : "pass";
}

/**
 * True when the text hardcodes a credibility-rung numerator (e.g. "5/5", "4 / 5")
 * instead of deriving it from data. The live panels render `{tb.rung}/5`, where the
 * char before "/5" is "}" — never a literal digit — so a data-derived rung passes.
 */
export function hasHardcodedRung(text: string): boolean {
  return /(?<![\w}.])\d\s*\/\s*5\b/.test(text);
}

// ---------------------------------------------------------------------------
// Non-vacuity: the checkers MUST flag an injected contradiction
// ---------------------------------------------------------------------------

describe("I-PROSE-CONTRACT checkers flag injected contradictions (non-vacuity)", () => {
  it("w2cDisposition flags the pre-fix 'W2c is a capability gap, left unaudited' wording", () => {
    expect(w2cDisposition("The W2c wire is a capability gap, left unaudited for the subject.")).toBe("gap");
    expect(w2cDisposition("W2c remains a gap, not a pass.")).toBe("gap");
  });

  it("w2cDisposition does NOT flag the honest 'W2c passes … not a subject capability gap' wording", () => {
    expect(
      w2cDisposition(
        "W2c passes: κ(J) is verified for the subject; lmfit/jax do not expose it — not a subject capability gap.",
      ),
    ).toBe("pass");
    expect(w2cDisposition("Jacobian conditioning (W2c) passes for the subject; oracles are a disclosed gap.")).toBe(
      "pass",
    );
  });

  it("w2cDisposition reports 'absent' when W2c is not mentioned", () => {
    expect(w2cDisposition("This text says nothing about that wire.")).toBe("absent");
  });

  it("hasHardcodedRung flags a literal numerator but not the data-derived {tb.rung}/5", () => {
    expect(hasHardcodedRung("the render-truth credibility rung 5/5 is the hero")).toBe(true);
    expect(hasHardcodedRung("ASME V&amp;V rung {tb.rung}/5 — a verification score")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// The live surfaces must be self-consistent and canonical
// ---------------------------------------------------------------------------

describe("I-PROSE-CONTRACT: live surfaces do not contradict the canonical W2c disposition", () => {
  const dispositions = Object.fromEntries(
    Object.entries(LIVE_SURFACES).map(([name, path]) => [name, w2cDisposition(readFileSync(path, "utf-8"))]),
  );

  it.each(Object.keys(LIVE_SURFACES))(
    "%s does not describe W2c as a subject-level gap/unaudited (canon: pass-for-subject)",
    (name) => {
      expect(dispositions[name], `${name} contradicts wires.py wire_w2c_jacobian_kappa`).not.toBe("gap");
    },
  );

  it("at least one live surface actually makes the W2c claim (the claim is not silently dropped)", () => {
    expect(Object.values(dispositions)).toContain("pass");
  });
});

describe("I-PROSE-CONTRACT: the rendered rung is data-derived, never a hardcoded numerator", () => {
  it.each(WEB_BODIES)("%s does not hardcode a rung numerator (must read {tb.rung})", (name) => {
    const text = readFileSync(LIVE_SURFACES[name], "utf-8");
    expect(hasHardcodedRung(text), `${name} hardcodes a rung numerator instead of {tb.rung}/5`).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// W9 (nested-model adequacy) — non-vacuity and live-surface checks
// ---------------------------------------------------------------------------

describe("I-PROSE-CONTRACT W9 checkers flag injected contradictions (non-vacuity)", () => {
  it("w9Disposition flags 'W9 is an unaudited gap'", () => {
    expect(w9Disposition("W9 is an unaudited gap — reduced model adequacy not tested.")).toBe("gap");
  });

  it("w9Disposition flags 'W9 remains unaudited'", () => {
    expect(w9Disposition("The W9 wire remains unaudited in this run.")).toBe("gap");
  });

  it("w9Disposition does NOT flag an honest 'implemented (W9) but not exercised' disclosure", () => {
    expect(
      w9Disposition("Reduced/nested-model adequacy V&V is implemented (W9) but not exercised in this report's run."),
    ).not.toBe("gap");
  });

  it("w9Disposition does NOT flag 'recovers the true model order (W9, BIC)'", () => {
    expect(
      w9Disposition("Reduced/nested-model adequacy — V&V recovers the true model order (W9, BIC)."),
    ).not.toBe("gap");
  });

  it("w9Disposition returns 'absent' when W9 is not mentioned", () => {
    expect(w9Disposition("This text says nothing about nested models.")).toBe("absent");
  });
});

describe("I-PROSE-CONTRACT W9: live surfaces do not describe W9 as an unaudited gap", () => {
  it.each(W9_SURFACES)(
    "%s does not describe W9 as an unaudited gap (canon: implemented or honest not-exercised)",
    (name) => {
      const text = readFileSync(LIVE_SURFACES[name], "utf-8");
      expect(w9Disposition(text), `${name} describes W9 as an unaudited gap`).not.toBe("gap");
    },
  );

  it("nestedAdequacy.tsx absent-state uses the qualified honest form (w9Disposition → pass)", () => {
    const text = readFileSync(LIVE_SURFACES["nestedAdequacy.tsx"], "utf-8");
    expect(w9Disposition(text)).toBe("pass");
  });
});

// ---------------------------------------------------------------------------
// W10/W11 (inferential tests) — non-vacuity and live-surface checks
// ---------------------------------------------------------------------------

describe("I-PROSE-CONTRACT W10 checkers flag injected contradictions (non-vacuity)", () => {
  it("w10Disposition flags 'W10 is an unaudited gap'", () => {
    expect(w10Disposition("W10 is an unaudited gap — σ-calibration not tested.")).toBe("gap");
  });

  it("w10Disposition flags 'W10 remains unaudited'", () => {
    expect(w10Disposition("The W10 wire remains unaudited in this run.")).toBe("gap");
  });

  it("w10Disposition does NOT flag an honest 'implemented (W10) but not exercised' disclosure", () => {
    expect(
      w10Disposition("The σ-calibration test is implemented (W10) but not exercised in this report's run."),
    ).not.toBe("gap");
  });

  it("w10Disposition does NOT flag 'inferential tests back the headline (W10 σ-calibration, W11 speed)'", () => {
    expect(
      w10Disposition("Validated where tested — inferential tests back the headline (W10 σ-calibration, W11 speed)."),
    ).not.toBe("gap");
  });

  it("w10Disposition returns 'absent' when W10 is not mentioned", () => {
    expect(w10Disposition("This text says nothing about calibration tests.")).toBe("absent");
  });
});

describe("I-PROSE-CONTRACT W11 checkers flag injected contradictions (non-vacuity)", () => {
  it("w11Disposition flags 'W11 is an unaudited gap'", () => {
    expect(w11Disposition("W11 is an unaudited gap — speed significance not tested.")).toBe("gap");
  });

  it("w11Disposition flags 'W11 remains unaudited'", () => {
    expect(w11Disposition("The W11 wire remains unaudited in this run.")).toBe("gap");
  });

  it("w11Disposition does NOT flag an honest 'implemented (W11) but not exercised' disclosure", () => {
    expect(
      w11Disposition(
        "The speed-significance test is implemented (W11) but not exercised in this report's run.",
      ),
    ).not.toBe("gap");
  });

  it("w11Disposition does NOT flag 'inferential tests back the headline (W10 σ-calibration, W11 speed)'", () => {
    expect(
      w11Disposition("Validated where tested — inferential tests back the headline (W10 σ-calibration, W11 speed)."),
    ).not.toBe("gap");
  });

  it("w11Disposition returns 'absent' when W11 is not mentioned", () => {
    expect(w11Disposition("This text says nothing about speed significance tests.")).toBe("absent");
  });
});

describe("I-PROSE-CONTRACT W10/W11: live surfaces do not describe inferential tests as an unaudited gap", () => {
  it.each(W10_W11_SURFACES)(
    "%s does not describe W10 as an unaudited gap (canon: implemented or honest not-exercised or backed)",
    (name) => {
      const text = readFileSync(LIVE_SURFACES[name], "utf-8");
      expect(w10Disposition(text), `${name} describes W10 as an unaudited gap`).not.toBe("gap");
    },
  );

  it.each(W10_W11_SURFACES)(
    "%s does not describe W11 as an unaudited gap (canon: implemented or honest not-exercised or backed)",
    (name) => {
      const text = readFileSync(LIVE_SURFACES[name], "utf-8");
      expect(w11Disposition(text), `${name} describes W11 as an unaudited gap`).not.toBe("gap");
    },
  );

  it("inferentialHeadline.tsx absent-state uses the qualified honest form (w10Disposition → pass)", () => {
    const text = readFileSync(LIVE_SURFACES["inferentialHeadline.tsx"], "utf-8");
    expect(w10Disposition(text)).toBe("pass");
  });

  it("inferentialHeadline.tsx absent-state uses the qualified honest form (w11Disposition → pass)", () => {
    const text = readFileSync(LIVE_SURFACES["inferentialHeadline.tsx"], "utf-8");
    expect(w11Disposition(text)).toBe("pass");
  });
});
