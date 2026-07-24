import { describe, expect, it } from "vitest";

import { classify, leadingVerb, type RClass } from "../src/classify.js";

describe("leadingVerb", () => {
  it.each([
    ["get_file", "get"],
    ["list-items", "list"],
    ["notion.create_page", "notion"], // dotted: leading token before first sep
    ["createPage", "create"], // camelCase
    ["deleteRecord", "delete"],
    ["DELETE_ALL", "delete"], // case-insensitive
    ["send", "send"],
    ["", ""],
  ])("leadingVerb(%s) -> %s", (name, expected) => {
    expect(leadingVerb(name)).toBe(expected);
  });
});

describe("classify verb -> R-class mapping", () => {
  const cases: Array<[string, RClass]> = [
    // R0 — reads
    ["get_user", "R0"],
    ["list_files", "R0"],
    ["search_docs", "R0"],
    ["read_file", "R0"],
    ["fetch_url", "R0"],
    // R1 — self-reversible mutation
    ["update_record", "R1"],
    ["set_status", "R1"],
    ["write_file", "R1"],
    ["edit_page", "R1"],
    // R2 — compensable creation
    ["create_page", "R2"],
    ["add_member", "R2"],
    ["insert_row", "R2"],
    // R3 — mitigable-only external effects
    ["send_email", "R3"],
    ["post_message", "R3"],
    ["publish_article", "R3"],
    // R4 — irreversible destruction / money / keys
    ["delete_page", "R4"],
    ["drop_table", "R4"],
    ["remove_user", "R4"],
    ["purge_cache", "R4"],
    ["pay_invoice", "R4"],
    ["charge_card", "R4"],
  ];

  it.each(cases)("classify(%s) -> %s", (name, expected) => {
    expect(classify(name).rClass).toBe(expected);
  });

  it("defaults unknown verbs to R4 (fail safe, never fail open)", () => {
    const result = classify("frobnicate_the_widget");
    expect(result.rClass).toBe("R4");
    // Low confidence signals a guess to the escalation policy.
    expect(result.confidence).toBeLessThan(0.5);
  });

  it("defaults an empty / unparseable name to R4", () => {
    expect(classify("").rClass).toBe("R4");
    expect(classify("___").rClass).toBe("R4");
  });

  it("returns a confidence in [0, 1]", () => {
    for (const [name] of cases) {
      const c = classify(name);
      expect(c.confidence).toBeGreaterThanOrEqual(0);
      expect(c.confidence).toBeLessThanOrEqual(1);
    }
  });

  it("handles camelCase tool names", () => {
    expect(classify("deleteRecord").rClass).toBe("R4");
    expect(classify("createPage").rClass).toBe("R2");
    expect(classify("getUser").rClass).toBe("R0");
  });
});
