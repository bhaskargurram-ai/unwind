#!/usr/bin/env node
/**
 * `unwind-mcp` CLI — the transparent MCP stdio shim.
 *
 * Usage:
 *   unwind-mcp run [--passthrough-only] -- <upstream command...>
 *
 * Example (wrap the official filesystem server):
 *   unwind-mcp run -- npx -y @modelcontextprotocol/server-filesystem /path
 *
 * All logging goes to *stderr*; stdout is reserved for the byte-faithful client
 * channel (GOLDEN RULE #1). The child's exit code is propagated as ours.
 */

import { Command } from "commander";

import { StdioProxy } from "./proxy.js";
import { VERSION } from "./version.js";

function log(event: string, fields: Record<string, unknown>): void {
  process.stderr.write(
    JSON.stringify({ ts: new Date().toISOString(), event, ...fields }) + "\n",
  );
}

export function buildProgram(): Command {
  const program = new Command();
  program
    .name("unwind-mcp")
    .description(
      "Transparent MCP stdio proxy — a reversibility layer for agentic tool use.",
    )
    .version(VERSION, "-v, --version", "print the version and exit");

  program
    .command("run")
    .description("Spawn an upstream MCP server and proxy its stdio transparently.")
    .option(
      "--passthrough-only",
      "PANIC SWITCH: disable all Unwind logic; pure byte-faithful passthrough.",
      false,
    )
    .argument(
      "<command...>",
      "upstream command and args (put after `--`), e.g. -- npx -y @modelcontextprotocol/server-filesystem /path",
    )
    .action(async (command: string[], options: { passthroughOnly: boolean }) => {
      if (command.length === 0) {
        log("cli.error", { message: "no upstream command given" });
        process.exit(2);
      }
      const [cmd, ...args] = command as [string, ...string[]];
      const proxy = new StdioProxy({
        command: cmd,
        args,
        passthroughOnly: options.passthroughOnly,
      });
      try {
        const code = await proxy.start();
        process.exit(code);
      } catch (err) {
        log("cli.fatal", {
          message: err instanceof Error ? err.message : String(err),
        });
        // Fail safe: a proxy that cannot start must not silently succeed.
        process.exit(1);
      }
    });

  return program;
}

// Only run when invoked directly (not when imported by tests).
const isMain =
  process.argv[1] !== undefined &&
  import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  buildProgram().parseAsync(process.argv).catch((err: unknown) => {
    log("cli.fatal", { message: err instanceof Error ? err.message : String(err) });
    process.exit(1);
  });
}
