/**
 * Newline-delimited JSON-RPC framing for the MCP stdio transport.
 *
 * MCP's stdio transport frames each JSON-RPC message as a single line
 * terminated by `\n` (see the MCP spec, "stdio transport"). Messages MUST NOT
 * contain embedded newlines. This module provides a minimal, well-typed reader
 * and writer over that framing.
 *
 * GOLDEN RULE #1 (transparency is sacred): the reader hands each raw line back
 * verbatim so the proxy can forward bytes faithfully even when a line is not
 * valid JSON or is a method Unwind does not understand. Parsing is *observation
 * only* and never gates forwarding.
 */

/** A JSON-RPC id: string, number, or null (per JSON-RPC 2.0). */
export type JsonRpcId = string | number | null;

/** Any JSON value. Deliberately not `any` — keeps the public surface typed. */
export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

/** A parsed JSON-RPC message. We keep it permissive: MCP layers many shapes on
 * top of JSON-RPC (requests, responses, notifications, batches). We only assert
 * the object shape and let observers pick out the fields they understand. */
export interface JsonRpcMessage {
  jsonrpc?: string;
  id?: JsonRpcId;
  method?: string;
  params?: JsonValue;
  result?: JsonValue;
  error?: JsonValue;
  [key: string]: JsonValue | undefined;
}

/**
 * A single framed line coming off a stream.
 *
 * `raw` is always the exact original line content (without the trailing `\n`).
 * `parsed` is the JSON value if the line parsed as an object, else `null`.
 * Callers that must forward faithfully use `raw`; observers use `parsed`.
 */
export interface Frame {
  raw: string;
  parsed: JsonRpcMessage | null;
}

/**
 * Attempt to parse a raw line into a JSON-RPC message object.
 *
 * Returns `null` (never throws) when the line is not a JSON object — this is
 * the fail-safe path: an unparseable line is forwarded raw, never dropped.
 */
export function tryParseFrame(raw: string): JsonRpcMessage | null {
  const trimmed = raw.trim();
  if (trimmed.length === 0) {
    return null;
  }
  try {
    const value: unknown = JSON.parse(trimmed);
    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      return value as JsonRpcMessage;
    }
    // Batches (arrays) and scalars are valid JSON-RPC framing but we do not
    // model them for observation; forward raw. Return null so callers pass
    // through untouched.
    return null;
  } catch {
    return null;
  }
}

/**
 * Serialize a JSON-RPC message back to a single framed line (no trailing `\n`;
 * the writer appends it). Used only when the proxy has *chosen* to re-emit a
 * message it modified; untouched messages are written from their `raw` form.
 */
export function serializeMessage(msg: JsonRpcMessage): string {
  return JSON.stringify(msg);
}

/**
 * A callback invoked once per complete line. Return value is ignored; framing
 * is push-based.
 */
export type FrameHandler = (frame: Frame) => void;

/**
 * Incremental line reader that reassembles partial chunks into complete
 * newline-delimited frames.
 *
 * Node stream `data` events do not respect message boundaries — a single chunk
 * may contain several messages, a fraction of one, or split a multibyte UTF-8
 * character. This reader buffers until a `\n` is seen and only then emits a
 * frame. Handles `\r\n` by stripping a trailing `\r`.
 *
 * It never throws on malformed content: a line that is not valid JSON is still
 * emitted as a `Frame` with `parsed: null`, so the pump can forward it raw.
 */
export class LineReader {
  private buffer = "";
  private readonly handler: FrameHandler;

  constructor(handler: FrameHandler) {
    this.handler = handler;
  }

  /** Feed a chunk of decoded text. Emits a frame for every completed line. */
  push(chunk: string): void {
    this.buffer += chunk;
    let newlineIndex = this.buffer.indexOf("\n");
    while (newlineIndex !== -1) {
      let line = this.buffer.slice(0, newlineIndex);
      // Normalize CRLF -> LF framing.
      if (line.endsWith("\r")) {
        line = line.slice(0, -1);
      }
      this.buffer = this.buffer.slice(newlineIndex + 1);
      // Skip genuinely empty lines (keep-alive blank lines); they carry no
      // message and re-emitting them is harmless but noisy. Forwarding a blank
      // line verbatim is also acceptable, but we drop only *empty* lines here.
      if (line.length > 0) {
        this.emit(line);
      }
      newlineIndex = this.buffer.indexOf("\n");
    }
  }

  /**
   * Flush any trailing content that arrived without a terminating newline
   * (e.g. the peer closed the stream mid-line). Emitted as a best-effort frame
   * so nothing is silently lost.
   */
  flush(): void {
    if (this.buffer.length > 0) {
      let line = this.buffer;
      if (line.endsWith("\r")) {
        line = line.slice(0, -1);
      }
      this.buffer = "";
      if (line.length > 0) {
        this.emit(line);
      }
    }
  }

  private emit(line: string): void {
    this.handler({ raw: line, parsed: tryParseFrame(line) });
  }
}
