---
title: Architecture
---

# Architecture

Unwind is a **transparent MCP intermediary**. It speaks MCP to the client and MCP to each upstream server, so no client and no server needs modification. Everything it does — classification, compensation synthesis, the undo log, escalation — happens *inside the proxy*, and anything it does not understand is forwarded byte-faithfully.

## The proxy

```text
MCP Client (Claude Desktop / Code / Cursor / Goose / VS Code / n8n / any)
        │  stdio or Streamable HTTP — unmodified
        ▼
┌──────────────────────────────────────────────────────────────┐
│                        UNWIND PROXY                          │
│                                                              │
│  Catalog Analyzer   ── on tools/list: classify every tool,   │
│      │                 synthesize compensation plans, cache  │
│      ▼                                                       │
│  Call Interceptor   ── on tools/call:                        │
│      ├─ Reversibility Classifier  (R0–R4 + confidence)       │
│      ├─ Blast-Radius Estimator    (dry-run / read-probe)     │
│      ├─ Pre-State Capturer        (snapshot before mutate)   │
│      ├─ Escalation Policy         (auto | elicit | block)    │
│      │      └─ confirmation via native MCP elicitation       │
│      └─ Undo Log (durable, cross-server, expiry-aware)       │
│                                                              │
│  Unwind Tools (exposed to the agent as a real MCP server):   │
│      unwind.preview · unwind.undo · unwind.explain_risk ·    │
│      unwind.history · unwind.checkpoint                      │
└──────────────────────────────────────────────────────────────┘
        │  fan-out, unmodified MCP
        ▼
Upstream MCP servers: filesystem · git · sqlite/postgres · Notion ·
Slack · Gmail · Stripe · Jira · CRM · cloud · calendar · …
```

### Catalog Analyzer — runs once, at `tools/list`

When a client lists tools, Unwind classifies every upstream tool into the [R0–R4 scale](taxonomy.md), synthesises [compensation plans](compensation.md), and **caches** the results keyed by `(tool, environment)`. This is the *only* place classification runs, which is what keeps R0 reads free on the hot path (golden rule #7).

### Call Interceptor — runs on every `tools/call`

For a mutating call, the interceptor:

1. looks up the cached **classification** (R-class + calibrated confidence);
2. estimates **blast radius**, optionally via a nullipotent read-probe;
3. **captures pre-state** (the snapshot that makes R1 reachable and pushes the commit point later);
4. asks the **escalation policy** for a decision (`auto_allow` / `auto_allow_logged` / `elicit_confirmation` / `block`);
5. writes a durable **undo-log** entry with the compensation plan and its expiry.

For an R0 read, it does effectively none of this — the call passes straight through.

### Escalation and elicitation

When the policy returns `elicit_confirmation`, Unwind asks the human through the protocol's **native elicitation channel** (MRTR / SEP-2322), never a bespoke UI. The MCP spec's own example is literally an input request like `{"type": "elicitation", "message": "Delete 3 files?", "schema": {"type": "boolean"}}`. Riding this channel is what lets Unwind's confirmations render correctly in every compliant client without per-client integration code.

## Deployment modes

=== "Standalone stdio shim (default)"

    One line in `mcp.json`, zero infrastructure. The client spawns Unwind as a subprocess; Unwind spawns the upstream server as *its* subprocess and relays newline-delimited JSON-RPC in both directions. This is the mode that wins stars and the one every [Quickstart](../quickstart.md) config uses.

    ```bash
    unwind run -- <upstream server command>
    ```

=== "HTTP proxy (teams)"

    Unwind runs as a long-lived Streamable HTTP service in front of remote servers, for shared team deployments. Streamable HTTP now carries `Mcp-Method` and `Mcp-Name` headers (SEP-2243) *specifically so gateways can route on the operation without inspecting the body* — the proxy pattern is blessed by the spec.

=== "Middleware library (embed in a gateway)"

    Unwind ships as an embeddable library so it can run **inside** an existing gateway — Docker MCP Gateway, ToolHive, agentgateway, ContextForge, MCPJungle — adding recovery to their prevention. See [Integrations](../integrations.md).

## Design invariants

These are enforced, not aspirational. Each maps to a [golden rule](../faq.md) and is gated by CI.

!!! abstract "Transparency is sacred"
    The proxy must be **invisible when idle**. Any MCP method Unwind does not understand is forwarded byte-faithfully. Protocol-conformance tests gate every change, and the `--passthrough-only` panic switch must always work — a proxy that breaks a client is worthless.

!!! abstract "Fail safe, never fail open"
    Unknown tool, failed classification, timeout, crashed classifier → **escalate to the human**. Never auto-allow on uncertainty. The default `ReversibilityClass` in code is **R4**.

!!! abstract "R0 stays ~free"
    Classification happens once at `tools/list` time and is cached. Reads never pay a latency tax. The [benchmark](../benchmark.md) reports R0 latency separately and holds it to a near-zero budget.

!!! abstract "The undo log is durable"
    The 2026-07-28 spec RC removed protocol-level sessions, so Unwind **cannot** lean on transport state. The undo log is its own SQLite store: it survives process restart, it is cross-server, and it is expiry-aware so a lapsed [half-life](taxonomy.md#reversibility-half-life-a-novel-dimension) can never yield a false undo.

## Where this maps in the code

| Concept | Module |
|---|---|
| Core typed protocol objects | `unwind/types.py` — see the [API reference](../reference.md) |
| stdio shim / HTTP / passthrough / elicitation | `unwind/proxy/` |
| Classification (lexical, schema, LLM, environment, ensemble) | `unwind/classify/` |
| Compensation synthesis | `unwind/synthesize/` |
| Blast-radius estimation | `unwind/blast.py` |
| Durable undo log | `unwind/undolog/` |
| Escalation policy / damage-rate solver | `unwind/policy/` |
| The agent-facing tool surface | `unwind/tools.py` |
| Calibration on risk scores | `unwind/calibration/` |
