/**
 * StdioProxy — a transparent MCP stdio proxy.
 *
 * The shim spawns the upstream MCP server as a child process and pumps
 * newline-delimited JSON-RPC between the *client's* stdio (this process's
 * stdin/stdout) and the *child's* stdio. The core discipline is modeled on
 * `sparfenyuk/mcp-proxy`: a transport adapter that forwards faithfully.
 *
 * GOLDEN RULES enforced here:
 *  #1 Transparency is sacred. Every line is forwarded. Messages Unwind does not
 *     understand — or cannot parse — pass through byte-identically. Ids are
 *     preserved. Order is preserved. Nothing is dropped.
 *  #2 Fail safe. A malformed line never crashes the pipe: we log to stderr and
 *     forward the raw bytes. Child crashes propagate the exit code.
 *
 * The only *observation* hooks are:
 *  - annotate `tools/list` *result* with an additive `x-unwind` reversibility
 *    hint (into each tool's `_meta`, and a non-breaking suffix on the
 *    description). Never removes or rewrites existing fields.
 *  - log observed `tools/call` requests to stderr in structured form.
 *
 * When `passthroughOnly` is set (the `--passthrough-only` panic switch), *all*
 * logic is disabled and the proxy is a pure byte pump.
 */

import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import type { Readable, Writable } from "node:stream";

import { classify, type RClass } from "./classify.js";
import {
  LineReader,
  serializeMessage,
  type Frame,
  type JsonRpcMessage,
  type JsonValue,
} from "./jsonrpc.js";

/** Namespaced key for the additive reversibility hint. */
const UNWIND_META_KEY = "x-unwind";

/** A structured stderr logger. Defaults to `process.stderr`. Never writes to
 * stdout — stdout is the client channel and must stay byte-faithful. */
export type Logger = (event: string, fields: Record<string, JsonValue>) => void;

export interface StdioProxyOptions {
  /** Upstream command to spawn (e.g. `npx`). */
  command: string;
  /** Arguments to the upstream command. */
  args?: string[];
  /** Extra environment for the child; merged over `process.env`. */
  env?: NodeJS.ProcessEnv;
  /** Working directory for the child. */
  cwd?: string;
  /** Panic switch: pure passthrough, zero annotation/observation. */
  passthroughOnly?: boolean;
  /** The client-side input stream (default `process.stdin`). */
  clientIn?: Readable;
  /** The client-side output stream (default `process.stdout`). */
  clientOut?: Writable;
  /** Structured logger (default: JSON lines to stderr). */
  logger?: Logger;
  /** Injectable hook for the child stream trio, for tests. */
  spawnFn?: typeof spawn;
}

/** Default structured logger: one JSON object per line on stderr. */
function defaultLogger(event: string, fields: Record<string, JsonValue>): void {
  const line = JSON.stringify({ ts: new Date().toISOString(), event, ...fields });
  process.stderr.write(line + "\n");
}

/**
 * A hook that may transform a message before it is forwarded. Returning the
 * same object (or `undefined`) means "forward the raw line untouched" — the
 * default identity behavior. Returning a *new* message means "re-serialize and
 * forward the modified form". Hooks must never throw; the pump guards anyway.
 */
export type MessageHook = (frame: Frame) => JsonRpcMessage | undefined;

export class StdioProxy {
  private readonly opts: Required<
    Omit<StdioProxyOptions, "args" | "env" | "cwd" | "spawnFn">
  > &
    Pick<StdioProxyOptions, "args" | "env" | "cwd" | "spawnFn">;
  private child: ChildProcessWithoutNullStreams | null = null;
  private exitResolve: ((code: number) => void) | null = null;
  private exited = false;

  constructor(options: StdioProxyOptions) {
    this.opts = {
      command: options.command,
      args: options.args ?? [],
      env: options.env,
      cwd: options.cwd,
      passthroughOnly: options.passthroughOnly ?? false,
      clientIn: options.clientIn ?? process.stdin,
      clientOut: options.clientOut ?? process.stdout,
      logger: options.logger ?? defaultLogger,
      spawnFn: options.spawnFn,
    };
  }

  /**
   * Start the proxy. Spawns the child, wires both directions, and resolves with
   * the child's exit code when it terminates.
   */
  async start(): Promise<number> {
    const spawnFn = this.opts.spawnFn ?? spawn;
    const child = spawnFn(this.opts.command, this.opts.args ?? [], {
      stdio: ["pipe", "pipe", "pipe"],
      env: this.opts.env ? { ...process.env, ...this.opts.env } : process.env,
      cwd: this.opts.cwd,
    }) as ChildProcessWithoutNullStreams;
    this.child = child;

    this.opts.logger("proxy.start", {
      command: this.opts.command,
      args: this.opts.args ?? [],
      passthroughOnly: this.opts.passthroughOnly,
    });

    const exitPromise = new Promise<number>((resolve) => {
      this.exitResolve = resolve;
    });

    // client stdin -> child stdin  (requests / notifications from the client)
    this.pump(
      this.opts.clientIn,
      child.stdin,
      (frame) => this.onClientMessage(frame),
      "client->server",
    );

    // child stdout -> client stdout  (responses / notifications from server)
    this.pump(
      child.stdout,
      this.opts.clientOut,
      (frame) => this.onServerMessage(frame),
      "server->client",
    );

    // child stderr -> our stderr, verbatim (never touches the client channel).
    child.stderr.on("data", (chunk: Buffer) => {
      process.stderr.write(chunk);
    });

    child.on("error", (err: Error) => {
      this.opts.logger("proxy.child_error", { message: err.message });
      this.finish(1);
    });

    child.on("exit", (code: number | null, signal: NodeJS.Signals | null) => {
      this.opts.logger("proxy.child_exit", {
        code: code ?? null,
        signal: signal ?? null,
      });
      // A signalled death maps to the conventional 128+signal code.
      const exitCode =
        code ?? (signal ? 128 + signalNumber(signal) : 1);
      this.finish(exitCode);
    });

    // Forward client-side termination to the child so we do not orphan it.
    const forwardSignal = (sig: NodeJS.Signals): void => {
      if (this.child && !this.exited) {
        this.child.kill(sig);
      }
    };
    process.on("SIGINT", () => forwardSignal("SIGINT"));
    process.on("SIGTERM", () => forwardSignal("SIGTERM"));

    // If the client closes its input, end the child's stdin so it can shut down
    // cleanly rather than hanging on a half-open pipe.
    this.opts.clientIn.on("end", () => {
      if (child.stdin.writable) {
        child.stdin.end();
      }
    });

    return exitPromise;
  }

  private finish(code: number): void {
    if (this.exited) {
      return;
    }
    this.exited = true;
    if (this.exitResolve) {
      this.exitResolve(code);
    }
  }

  /**
   * Wire `source` -> `dest`, applying `hook` per frame. The hook may modify a
   * message; otherwise the *raw* line is forwarded verbatim. Every forwarded
   * line is newline-terminated. Backpressure is respected implicitly: we write
   * synchronously and let Node buffer; for the modest volumes of MCP control
   * traffic this is correct and simplest. Never throws out of the data path.
   */
  private pump(
    source: Readable,
    dest: Writable,
    hook: MessageHook,
    direction: string,
  ): void {
    const reader = new LineReader((frame: Frame) => {
      let out: string = frame.raw;
      if (!this.opts.passthroughOnly) {
        try {
          const modified = hook(frame);
          if (modified !== undefined) {
            out = serializeMessage(modified);
          }
        } catch (err) {
          // GOLDEN RULE #2: a hook failure must never break the pipe. Fall back
          // to the raw line — forward faithfully, log, carry on.
          this.opts.logger("proxy.hook_error", {
            direction,
            message: err instanceof Error ? err.message : String(err),
          });
          out = frame.raw;
        }
      }
      this.write(dest, out + "\n");
    });

    source.setEncoding("utf8");
    source.on("data", (chunk: string) => {
      try {
        reader.push(chunk);
      } catch (err) {
        // Absolute last-resort guard: forward the raw chunk so nothing is lost.
        this.opts.logger("proxy.pump_error", {
          direction,
          message: err instanceof Error ? err.message : String(err),
        });
        this.write(dest, chunk);
      }
    });
    source.on("end", () => {
      reader.flush();
      if (dest !== this.opts.clientOut && dest.writable) {
        // Closing the client->child direction: end the child's stdin.
        dest.end();
      }
    });
    source.on("error", (err: Error) => {
      this.opts.logger("proxy.stream_error", { direction, message: err.message });
    });
  }

  private write(dest: Writable, data: string): void {
    if (dest.writable) {
      dest.write(data);
    }
  }

  /** Client -> server. We observe `tools/call` requests; we never modify the
   * client's outbound messages (modifying a request could break the server). */
  private onClientMessage(frame: Frame): JsonRpcMessage | undefined {
    const msg = frame.parsed;
    if (msg && msg.method === "tools/call") {
      const params = isObject(msg.params) ? msg.params : {};
      this.opts.logger("tools/call", {
        id: idField(msg.id),
        tool: stringField(params["name"]),
        // Log presence of arguments, not the arguments themselves, to avoid
        // leaking payloads to stderr by default.
        hasArguments: isObject(params["arguments"]),
      });
    }
    // Forward untouched.
    return undefined;
  }

  /** Server -> client. We annotate `tools/list` results additively. */
  private onServerMessage(frame: Frame): JsonRpcMessage | undefined {
    const msg = frame.parsed;
    if (!msg || !isObject(msg.result)) {
      return undefined;
    }
    const result = msg.result;
    const tools = result["tools"];
    if (!Array.isArray(tools)) {
      // Not a tools/list result shape — forward untouched.
      return undefined;
    }
    // This is a tools/list result. Annotate each tool additively.
    let annotated = 0;
    const newTools: JsonValue[] = tools.map((entry): JsonValue => {
      if (!isObject(entry)) {
        return entry;
      }
      const name = stringField(entry["name"]);
      if (name.length === 0) {
        return entry;
      }
      const description = stringField(entry["description"]);
      const hint = classify(name, description);
      annotated += 1;
      return this.applyHint(entry, hint.rClass, hint.confidence);
    });

    if (annotated === 0) {
      return undefined;
    }

    this.opts.logger("tools/list.annotated", {
      id: idField(msg.id),
      count: annotated,
    });

    // Build a new message so we do not mutate the parsed frame in place.
    return { ...msg, result: { ...result, tools: newTools } };
  }

  /** Additively attach the `x-unwind` hint to a single tool entry. Never
   * removes or overwrites unrelated fields; the description gets a clearly
   * namespaced, non-breaking suffix only if not already present. */
  private applyHint(
    tool: { [key: string]: JsonValue },
    rClass: RClass,
    confidence: number,
  ): JsonValue {
    const existingMeta = isObject(tool["_meta"]) ? tool["_meta"] : {};
    const meta: { [key: string]: JsonValue } = {
      ...existingMeta,
      [UNWIND_META_KEY]: {
        reversibilityClass: rClass,
        confidence,
        source: "lexical",
      },
    };

    const out: { [key: string]: JsonValue } = { ...tool, _meta: meta };

    // Non-breaking description suffix. Idempotent: skip if already annotated.
    const desc = stringField(tool["description"]);
    const marker = `[${UNWIND_META_KEY}: ${rClass}]`;
    if (!desc.includes(`[${UNWIND_META_KEY}:`)) {
      out["description"] = desc.length > 0 ? `${desc} ${marker}` : marker;
    }
    return out;
  }
}

/** Map a POSIX signal name to its number for exit-code conventions. */
function signalNumber(sig: NodeJS.Signals): number {
  const table: Record<string, number> = {
    SIGHUP: 1,
    SIGINT: 2,
    SIGQUIT: 3,
    SIGKILL: 9,
    SIGTERM: 15,
  };
  return table[sig] ?? 0;
}

function isObject(v: JsonValue | undefined): v is { [key: string]: JsonValue } {
  return v !== null && v !== undefined && typeof v === "object" && !Array.isArray(v);
}

function stringField(v: JsonValue | undefined): string {
  return typeof v === "string" ? v : "";
}

function idField(v: JsonValue | undefined): JsonValue {
  if (typeof v === "string" || typeof v === "number" || v === null) {
    return v;
  }
  return null;
}
