# rollback-mcp

**A transparent MCP stdio proxy — the reversibility layer for agentic tool use.**

`rollback-mcp` sits between an MCP client and an upstream MCP server. It pumps
newline-delimited JSON-RPC between the two, forwarding **every message
byte-faithfully**, while *observing* the traffic: it annotates `tools/list`
responses with a lexical reversibility hint (`x-unwind`) and logs observed
`tools/call` requests to stderr.

This is the **TypeScript port of the Unwind stdio shim**. The
[Python package](https://github.com/bhaskargurram-ai/unwind) is the reference
implementation and remains authoritative for full reversibility classification,
compensation synthesis, and the durable cross-server undo log. This shim mirrors
just the transparent stdio proxy so the Node MCP-client audience can build and
run it from source without the Python runtime.

## Design invariants

1. **Transparency is sacred.** Any JSON-RPC method the proxy does not understand
   — or cannot parse — is forwarded untouched. Ids and ordering are preserved. A
   malformed line never crashes the pipe; it is logged to stderr and forwarded
   raw.
2. **Fail safe.** Unknown verbs classify as `R4` (irreversible). The proxy never
   silently drops a message.
3. **`--passthrough-only` is a panic switch.** It disables all Unwind logic and
   makes the proxy a pure byte pump — the guarantee that Unwind can never break a
   client.

Annotation is strictly *additive*: the `x-unwind` hint goes into each tool's
`_meta` (namespaced, non-breaking) plus a `[x-unwind: R<n>]` suffix on the
description. Existing fields are never removed or rewritten.

## Install

**Not published to npm.** Build it from source:

```sh
git clone https://github.com/bhaskargurram-ai/unwind
cd unwind/ts
npm install
npm run build
```

Then run the built CLI directly, or `npm link` to expose the `rollback-mcp`
command on your `PATH`:

```sh
node dist/cli.js run [--passthrough-only] -- <upstream command...>
# or, after `npm link`:
rollback-mcp run [--passthrough-only] -- <upstream command...>
```

## Usage

Wrap the official filesystem server:

```sh
node dist/cli.js run -- npx -y @modelcontextprotocol/server-filesystem /path/to/dir
```

In an MCP client config (`mcp.json`), replace the upstream command with the
`rollback-mcp` wrapper:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "rollback-mcp",
      "args": ["run", "--", "npx", "-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"]
    }
  }
}
```

Logs go to **stderr** (structured JSON lines); **stdout** carries only the
byte-faithful client channel.

## Reversibility scale

| Class | Meaning | Example verbs |
|-------|---------|---------------|
| `R0`  | Nullipotent (no state change) | `get`, `list`, `search`, `read` |
| `R1`  | Self-reversible (in-place) | `update`, `set`, `write`, `edit` |
| `R2`  | Compensable (a different tool undoes it) | `create`, `add`, `insert` |
| `R3`  | Mitigable only (externally observed) | `send`, `post`, `publish` |
| `R4`  | Irreversible | `delete`, `drop`, `purge`, `pay`, `charge` |

The TS shim ships only the cheap lexical first-pass. The Python reference adds
schema-structural and LLM ensemble signals with calibrated confidence.

## Development

```sh
npm install
npm run build   # tsc -> dist/
npm test        # vitest
```

## License

Apache-2.0. See [LICENSE](./LICENSE).

Part of [Unwind](https://github.com/bhaskargurram-ai/unwind).
