/**
 * Public API surface for `unwind-mcp` (the TypeScript stdio shim).
 *
 * This mirrors the Python reference implementation's stdio proxy. The Python
 * package remains authoritative for classification, compensation synthesis and
 * the undo log; this shim ports only the transparent stdio proxy so the Node
 * MCP-client audience can `npm i -g unwind-mcp`.
 */
export { VERSION } from "./version.js";
export { StdioProxy } from "./proxy.js";
export type {
  StdioProxyOptions,
  Logger,
  MessageHook,
} from "./proxy.js";
export { classify, leadingVerb } from "./classify.js";
export type { RClass, Classification } from "./classify.js";
export {
  LineReader,
  tryParseFrame,
  serializeMessage,
} from "./jsonrpc.js";
export type {
  Frame,
  FrameHandler,
  JsonRpcId,
  JsonRpcMessage,
  JsonValue,
} from "./jsonrpc.js";
