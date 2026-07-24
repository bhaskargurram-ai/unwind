#!/usr/bin/env node
/**
 * Trivial fake upstream MCP-ish server for proxy tests.
 *
 * Reads newline-delimited JSON-RPC from stdin and replies on stdout:
 *  - method "tools/list"      -> a result with two tools (get_thing, delete_thing)
 *  - method "unknown/method"  -> echoes params back verbatim in the result
 *  - method "custom/echo"     -> echoes the whole request under result.echo
 *  - anything else            -> a generic {ok:true} result
 *
 * It preserves the request id on every response. Notifications (no id) get no
 * reply. It logs nothing to stdout except JSON-RPC.
 */

import { createInterface } from "node:readline";

const rl = createInterface({ input: process.stdin });

function send(obj) {
  process.stdout.write(JSON.stringify(obj) + "\n");
}

rl.on("line", (line) => {
  const trimmed = line.trim();
  if (trimmed.length === 0) return;
  let msg;
  try {
    msg = JSON.parse(trimmed);
  } catch {
    // Mirror a malformed input back raw so the test can assert passthrough.
    process.stdout.write(line + "\n");
    return;
  }

  const { id, method, params } = msg;
  // Notifications (no id) are not answered.
  if (id === undefined) return;

  if (method === "tools/list") {
    send({
      jsonrpc: "2.0",
      id,
      result: {
        tools: [
          {
            name: "get_thing",
            description: "Read a thing.",
            inputSchema: { type: "object", properties: {} },
          },
          {
            name: "delete_thing",
            description: "Delete a thing permanently.",
            inputSchema: { type: "object", properties: {} },
            _meta: { existing: "keep-me" },
          },
        ],
      },
    });
    return;
  }

  if (method === "unknown/method") {
    send({ jsonrpc: "2.0", id, result: { params: params ?? null } });
    return;
  }

  if (method === "custom/echo") {
    send({ jsonrpc: "2.0", id, result: { echo: msg } });
    return;
  }

  send({ jsonrpc: "2.0", id, result: { ok: true } });
});

rl.on("close", () => process.exit(0));
