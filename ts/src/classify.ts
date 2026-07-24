/**
 * Minimal lexical reversibility heuristic.
 *
 * This mirrors the *idea* of the Python reference `unwind/classify/lexical.py`:
 * map a tool-name verb prefix to an R-class on the ordinal R0..R4 scale
 * (PROJECT.md §5.1). The Python side is authoritative — it adds schema and LLM
 * ensemble signals with calibrated confidence. This TS shim ships only the
 * cheap lexical first-pass, enough to annotate `tools/list` with a useful hint.
 *
 * GOLDEN RULE #2 (fail safe, never fail open): an unrecognized verb defaults to
 * R4 (irreversible). Over-classifying a benign tool merely annoys; under-
 * classifying a destructive one is catastrophic. The asymmetric-loss design of
 * the R-scale (§5.1) demands the conservative default.
 */

export type RClass = "R0" | "R1" | "R2" | "R3" | "R4";

export interface Classification {
  /** Ordinal reversibility class R0..R4. */
  rClass: RClass;
  /** Heuristic confidence in [0, 1]. Lexical-only, so deliberately modest. */
  confidence: number;
}

/**
 * Verb prefix -> R-class table. Ordered conceptually by the R-scale:
 *   R0 nullipotent   : reads, no state change
 *   R1 self-reversible: in-place mutation, prior state recapturable
 *   R2 compensable    : creation with a plausible delete/remove inverse
 *   R3 mitigable only : external side effects (comms, publishing)
 *   R4 irreversible   : destruction, money movement, key operations
 *
 * Kept small and lexical on purpose. `# DECISION:` boundaries here match the
 * examples in PROJECT.md §5.1 so the TS hint agrees with the Python labels on
 * the common verbs.
 */
const VERB_TABLE: ReadonlyArray<readonly [readonly string[], RClass, number]> = [
  // R0 — nullipotent reads.
  [
    ["get", "list", "search", "read", "fetch", "find", "query", "describe", "show", "view", "lookup", "check", "peek", "stat"],
    "R0",
    0.9,
  ],
  // R1 — self-reversible in-place mutation (prior content recapturable).
  [
    ["update", "set", "write", "edit", "modify", "patch", "rename", "move", "replace", "configure", "toggle"],
    "R1",
    0.6,
  ],
  // R2 — compensable creation (a delete/remove inverse plausibly exists).
  [
    ["create", "add", "insert", "new", "make", "register", "upload", "clone", "copy", "duplicate", "import"],
    "R2",
    0.6,
  ],
  // R3 — mitigable only: externally observable side effects.
  [
    ["send", "post", "publish", "notify", "email", "message", "share", "broadcast", "announce", "invite", "comment", "reply", "dispatch", "submit", "trigger"],
    "R3",
    0.6,
  ],
  // R4 — irreversible destruction / money / keys / execution.
  [
    ["delete", "drop", "remove", "purge", "destroy", "wipe", "erase", "pay", "charge", "capture", "transfer", "refund", "revoke", "terminate", "kill", "execute", "run", "deploy", "release", "reset", "format"],
    "R4",
    0.7,
  ],
];

/** Extract a lowercase leading verb token from a tool name.
 * Handles `snake_case`, `kebab-case`, `dot.namespaced`, and `camelCase`. */
export function leadingVerb(name: string): string {
  const trimmed = name.trim();
  if (trimmed.length === 0) {
    return "";
  }
  // Split on the first separator among _ - . / : whitespace.
  const sepMatch = trimmed.match(/^([^_\-./:\s]+)/);
  let token = sepMatch ? sepMatch[1]! : trimmed;
  // If still camelCase (no separator hit a boundary), take the leading
  // lowercase run up to the first uppercase letter: `createPage` -> `create`.
  const camelMatch = token.match(/^([a-z]+)(?=[A-Z]|$)/);
  if (camelMatch && camelMatch[1]!.length > 0) {
    token = camelMatch[1]!;
  }
  return token.toLowerCase();
}

/**
 * Classify a tool by lexical signal alone.
 *
 * @param name        the tool name (e.g. `delete_file`, `createPage`).
 * @param _description the tool description; reserved for future keyword
 *        signals. Currently unused by the lexical-only pass but part of the
 *        stable signature so callers pass it and the Python parity holds.
 * @returns an ordinal R-class plus a modest confidence.
 */
export function classify(name: string, _description?: string): Classification {
  const verb = leadingVerb(name);
  if (verb.length === 0) {
    // No parseable verb — fail safe.
    return { rClass: "R4", confidence: 0.3 };
  }
  for (const [verbs, rClass, confidence] of VERB_TABLE) {
    if (verbs.includes(verb)) {
      return { rClass, confidence };
    }
  }
  // DECISION: unknown verb -> R4 (fail safe, never fail open). Low confidence
  // signals "this is a guess, escalate" to the downstream policy.
  return { rClass: "R4", confidence: 0.3 };
}
