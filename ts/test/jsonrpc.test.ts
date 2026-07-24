import { describe, expect, it } from "vitest";

import {
  LineReader,
  serializeMessage,
  tryParseFrame,
  type Frame,
} from "../src/jsonrpc.js";

function collect(): { reader: LineReader; frames: Frame[] } {
  const frames: Frame[] = [];
  const reader = new LineReader((f) => frames.push(f));
  return { reader, frames };
}

describe("tryParseFrame", () => {
  it("parses a JSON-RPC object", () => {
    const msg = tryParseFrame('{"jsonrpc":"2.0","id":1,"method":"ping"}');
    expect(msg).not.toBeNull();
    expect(msg?.method).toBe("ping");
    expect(msg?.id).toBe(1);
  });

  it("returns null (never throws) for malformed JSON", () => {
    expect(tryParseFrame("{not json")).toBeNull();
    expect(tryParseFrame("")).toBeNull();
    expect(tryParseFrame("   ")).toBeNull();
  });

  it("returns null for JSON scalars and arrays (not observed shapes)", () => {
    expect(tryParseFrame("42")).toBeNull();
    expect(tryParseFrame('"hi"')).toBeNull();
    expect(tryParseFrame("[1,2,3]")).toBeNull();
  });
});

describe("serializeMessage round-trip", () => {
  it("round-trips a message through serialize + parse", () => {
    const original = { jsonrpc: "2.0", id: "abc", result: { ok: true } };
    const line = serializeMessage(original);
    const parsed = tryParseFrame(line);
    expect(parsed).toEqual(original);
  });
});

describe("LineReader framing", () => {
  it("emits one frame per newline-terminated line", () => {
    const { reader, frames } = collect();
    reader.push('{"id":1}\n{"id":2}\n');
    expect(frames).toHaveLength(2);
    expect(frames[0]?.parsed?.id).toBe(1);
    expect(frames[1]?.parsed?.id).toBe(2);
  });

  it("reassembles a message split across chunks (partial line)", () => {
    const { reader, frames } = collect();
    reader.push('{"jsonrpc":"2.0",');
    expect(frames).toHaveLength(0);
    reader.push('"id":7,"method":"x"}');
    expect(frames).toHaveLength(0); // no newline yet
    reader.push("\n");
    expect(frames).toHaveLength(1);
    expect(frames[0]?.parsed?.id).toBe(7);
    expect(frames[0]?.parsed?.method).toBe("x");
  });

  it("splits multiple messages arriving in a single chunk", () => {
    const { reader, frames } = collect();
    reader.push('{"id":1}\n{"id":2}\n{"id":3}\n');
    expect(frames.map((f) => f.parsed?.id)).toEqual([1, 2, 3]);
  });

  it("preserves the exact raw line for faithful forwarding", () => {
    const { reader, frames } = collect();
    const raw = '{"id":1,"weird":"  spaced  "}';
    reader.push(raw + "\n");
    expect(frames[0]?.raw).toBe(raw);
  });

  it("normalizes CRLF framing", () => {
    const { reader, frames } = collect();
    reader.push('{"id":1}\r\n');
    expect(frames).toHaveLength(1);
    expect(frames[0]?.raw).toBe('{"id":1}');
    expect(frames[0]?.parsed?.id).toBe(1);
  });

  it("handles a malformed line without throwing and still emits it raw", () => {
    const { reader, frames } = collect();
    expect(() => reader.push("this is not json\n")).not.toThrow();
    expect(frames).toHaveLength(1);
    expect(frames[0]?.raw).toBe("this is not json");
    expect(frames[0]?.parsed).toBeNull();
  });

  it("skips empty lines between messages", () => {
    const { reader, frames } = collect();
    reader.push('{"id":1}\n\n{"id":2}\n');
    expect(frames).toHaveLength(2);
  });

  it("flush() emits a trailing unterminated line", () => {
    const { reader, frames } = collect();
    reader.push('{"id":9}');
    expect(frames).toHaveLength(0);
    reader.flush();
    expect(frames).toHaveLength(1);
    expect(frames[0]?.parsed?.id).toBe(9);
  });
});
