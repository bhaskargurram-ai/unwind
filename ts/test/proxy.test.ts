import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { PassThrough } from "node:stream";

import { afterEach, describe, expect, it } from "vitest";

import { StdioProxy } from "../src/proxy.js";
import type { JsonRpcMessage } from "../src/jsonrpc.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const FAKE_UPSTREAM = join(HERE, "fixtures", "fake-upstream.mjs");

/**
 * A test harness that runs the real proxy over a real spawned fake-upstream
 * child, feeding requests through an in-memory client stdin and collecting the
 * client stdout as parsed frames.
 */
class Harness {
  readonly clientIn = new PassThrough();
  readonly clientOut = new PassThrough();
  private readonly outLines: string[] = [];
  private readonly proxy: StdioProxy;
  private readonly done: Promise<number>;

  constructor(passthroughOnly: boolean) {
    this.clientOut.setEncoding("utf8");
    let buffer = "";
    this.clientOut.on("data", (chunk: string) => {
      buffer += chunk;
      let idx = buffer.indexOf("\n");
      while (idx !== -1) {
        const line = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 1);
        if (line.trim().length > 0) this.outLines.push(line);
        idx = buffer.indexOf("\n");
      }
    });

    this.proxy = new StdioProxy({
      command: process.execPath, // node
      args: [FAKE_UPSTREAM],
      passthroughOnly,
      clientIn: this.clientIn,
      clientOut: this.clientOut,
      // Silence stderr logging during tests.
      logger: () => {},
    });
    this.done = this.proxy.start();
  }

  request(msg: JsonRpcMessage): void {
    this.clientIn.write(JSON.stringify(msg) + "\n");
  }

  /** Wait until at least `n` output lines have been collected, or time out. */
  async waitForLines(n: number, timeoutMs = 5000): Promise<void> {
    const start = Date.now();
    while (this.outLines.length < n) {
      if (Date.now() - start > timeoutMs) {
        throw new Error(
          `timed out waiting for ${n} lines; got ${this.outLines.length}`,
        );
      }
      await new Promise((r) => setTimeout(r, 10));
    }
  }

  get lines(): string[] {
    return this.outLines.slice();
  }

  parsedLines(): JsonRpcMessage[] {
    return this.outLines.map((l) => JSON.parse(l) as JsonRpcMessage);
  }

  async close(): Promise<number> {
    this.clientIn.end();
    return this.done;
  }
}

describe("StdioProxy transparent passthrough", () => {
  const harnesses: Harness[] = [];
  const make = (passthroughOnly = false): Harness => {
    const h = new Harness(passthroughOnly);
    harnesses.push(h);
    return h;
  };

  afterEach(async () => {
    await Promise.all(harnesses.map((h) => h.close().catch(() => 0)));
    harnesses.length = 0;
  });

  it("preserves ids on responses", async () => {
    const h = make();
    h.request({ jsonrpc: "2.0", id: 123, method: "custom/echo" });
    await h.waitForLines(1);
    const msg = h.parsedLines()[0]!;
    expect(msg.id).toBe(123);
  });

  it("forwards an unknown method result byte-faithfully", async () => {
    const h = make();
    h.request({ jsonrpc: "2.0", id: "u1", method: "unknown/method", params: { a: 1, b: [2, 3] } });
    await h.waitForLines(1);
    const line = h.lines[0]!;
    // The fake upstream echoes params under result.params; the proxy must not
    // touch a non tools/list result at all.
    const expected = JSON.stringify({
      jsonrpc: "2.0",
      id: "u1",
      result: { params: { a: 1, b: [2, 3] } },
    });
    expect(line).toBe(expected);
  });

  it("does NOT annotate tools/list in --passthrough-only mode", async () => {
    const h = make(true);
    h.request({ jsonrpc: "2.0", id: 1, method: "tools/list" });
    await h.waitForLines(1);
    const line = h.lines[0]!;
    expect(line).not.toContain("x-unwind");
    const msg = h.parsedLines()[0]!;
    const tools = (msg.result as { tools: Array<Record<string, unknown>> }).tools;
    expect(tools[0]?._meta).toBeUndefined();
    expect(tools[0]?.description).toBe("Read a thing.");
  });

  it("annotates tools/list additively and non-destructively when enabled", async () => {
    const h = make(false);
    h.request({ jsonrpc: "2.0", id: 1, method: "tools/list" });
    await h.waitForLines(1);
    const msg = h.parsedLines()[0]!;
    const tools = (msg.result as {
      tools: Array<{
        name: string;
        description: string;
        inputSchema: unknown;
        _meta?: Record<string, unknown>;
      }>;
    }).tools;

    // Original fields survive untouched.
    expect(tools[0]?.name).toBe("get_thing");
    expect(tools[0]?.inputSchema).toEqual({ type: "object", properties: {} });
    // Pre-existing _meta on delete_thing is preserved.
    expect(tools[1]?._meta?.existing).toBe("keep-me");

    // Additive x-unwind hint present with the right class.
    const getMeta = tools[0]?._meta?.["x-unwind"] as { reversibilityClass: string } | undefined;
    const delMeta = tools[1]?._meta?.["x-unwind"] as { reversibilityClass: string } | undefined;
    expect(getMeta?.reversibilityClass).toBe("R0"); // get_thing
    expect(delMeta?.reversibilityClass).toBe("R4"); // delete_thing

    // Description got a non-breaking suffix, original text retained.
    expect(tools[0]?.description).toContain("Read a thing.");
    expect(tools[0]?.description).toContain("[x-unwind: R0]");
    expect(tools[1]?.description).toContain("Delete a thing permanently.");
    expect(tools[1]?.description).toContain("[x-unwind: R4]");
  });

  it("propagates the child exit code when the client stream ends", async () => {
    const h = make();
    // No requests; just close. Fake upstream exits 0 on stdin close.
    const code = await h.close();
    expect(code).toBe(0);
    harnesses.length = 0; // already closed
  });

  it("preserves message order across a burst", async () => {
    const h = make();
    for (let i = 1; i <= 5; i++) {
      h.request({ jsonrpc: "2.0", id: i, method: "custom/echo" });
    }
    await h.waitForLines(5);
    const ids = h.parsedLines().map((m) => m.id);
    expect(ids).toEqual([1, 2, 3, 4, 5]);
  });
});
