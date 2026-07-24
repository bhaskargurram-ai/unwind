---
title: Quickstart
---

# Quickstart

Get Unwind wrapping a real MCP server, run the demo, and take an action back — in a few minutes. Unwind is a **transparent proxy**: you replace `<your server command>` with `unwind run -- <your server command>` everywhere it appears, and nothing else changes.

!!! tip "The one-line mental model"
    ```
    unwind run -- <the exact command your client already runs for the upstream server>
    ```
    Everything after `--` is forwarded byte-faithfully. Unwind only interposes on the MCP methods it understands; anything else passes straight through.

## 1. Install

=== "pip"

    ```bash
    pip install unwind-mcp
    unwind --version
    ```

=== "uvx (zero install)"

    ```bash
    # Runs the latest release in an ephemeral environment.
    uvx unwind-mcp --version
    ```

=== "npm (Node stdio shim)"

    ```bash
    npm install -g unwind-mcp
    unwind --version
    ```

=== "docker"

    ```bash
    docker pull ghcr.io/bhaskargurram-ai/unwind:latest
    docker run --rm ghcr.io/bhaskargurram-ai/unwind:latest --version
    ```

!!! note "Requirements"
    Python 3.11+ and `mcp==1.28.1` (installed automatically). The Node shim targets active LTS releases. Docker images are published to GHCR on every tagged release.

## 2. Wrap an existing MCP server

Take any server you already run. Prefix its command with `unwind run --`:

=== "filesystem"

    ```bash
    unwind run -- npx -y @modelcontextprotocol/server-filesystem /work
    ```

=== "git"

    ```bash
    unwind run -- uvx mcp-server-git --repository /work/repo
    ```

=== "sqlite"

    ```bash
    unwind run -- uvx mcp-server-sqlite --db-path /work/app.db
    ```

On startup Unwind calls `tools/list` on the upstream server once, classifies every tool into the [R0–R4 scale](concepts/taxonomy.md), synthesises [compensation plans](concepts/compensation.md), and caches the result. This is the only place classification happens — **R0 reads never pay for it on the hot path**.

!!! danger "The panic switch"
    If you ever suspect Unwind is interfering with a client, run it in pure pass-through mode. Every method is forwarded untouched; no classification, no undo log, no elicitation:

    ```bash
    unwind run --passthrough-only -- <your server command>
    ```

    This must always work. Transparency is a golden rule — a proxy that breaks a client is worthless.

## 3. Configure your MCP client

Every config below wraps the filesystem server as the example. Swap in your own server command. The pattern is identical across clients: **`unwind` is the command, and the real server is its arguments.**

=== "Claude Desktop / Claude Code"

    `claude_desktop_config.json` (Desktop) or `.mcp.json` (Claude Code):

    ```json
    {
      "mcpServers": {
        "filesystem": {
          "command": "unwind",
          "args": [
            "run", "--",
            "npx", "-y", "@modelcontextprotocol/server-filesystem", "/work"
          ]
        }
      }
    }
    ```

=== "Cursor"

    `~/.cursor/mcp.json` (or project `.cursor/mcp.json`):

    ```json
    {
      "mcpServers": {
        "filesystem": {
          "command": "unwind",
          "args": ["run", "--", "npx", "-y", "@modelcontextprotocol/server-filesystem", "/work"]
        }
      }
    }
    ```

=== "VS Code"

    `.vscode/mcp.json`:

    ```json
    {
      "servers": {
        "filesystem": {
          "type": "stdio",
          "command": "unwind",
          "args": ["run", "--", "npx", "-y", "@modelcontextprotocol/server-filesystem", "/work"]
        }
      }
    }
    ```

=== "Cline"

    `cline_mcp_settings.json`:

    ```json
    {
      "mcpServers": {
        "filesystem": {
          "command": "unwind",
          "args": ["run", "--", "npx", "-y", "@modelcontextprotocol/server-filesystem", "/work"]
        }
      }
    }
    ```

=== "Windsurf"

    `~/.codeium/windsurf/mcp_config.json`:

    ```json
    {
      "mcpServers": {
        "filesystem": {
          "command": "unwind",
          "args": ["run", "--", "npx", "-y", "@modelcontextprotocol/server-filesystem", "/work"]
        }
      }
    }
    ```

=== "Goose"

    `~/.config/goose/config.yaml`:

    ```yaml
    extensions:
      filesystem:
        type: stdio
        cmd: unwind
        args:
          - run
          - "--"
          - npx
          - "-y"
          - "@modelcontextprotocol/server-filesystem"
          - /work
    ```

=== "Zed"

    `settings.json` → `context_servers`:

    ```json
    {
      "context_servers": {
        "filesystem": {
          "command": {
            "path": "unwind",
            "args": ["run", "--", "npx", "-y", "@modelcontextprotocol/server-filesystem", "/work"]
          }
        }
      }
    }
    ```

=== "n8n"

    In the **MCP Client** node, set the command to `unwind` and the arguments to
    `run -- npx -y @modelcontextprotocol/server-filesystem /work`. For remote
    deployments use the [HTTP proxy mode](concepts/architecture.md) and point the
    node's URL at Unwind's Streamable HTTP endpoint.

!!! info "Confirmations use native MCP elicitation"
    When Unwind needs to interrupt you, it does **not** pop a bespoke UI. It uses the protocol's native [elicitation](concepts/architecture.md) channel (MRTR / SEP-2322), so the confirmation appears in whatever your client already renders for input requests. That is what makes it work everywhere without per-client code.

## 4. Run the demo

The bundled demo scripts an agent through four consequential actions and then reverses them:

```bash
unwind demo
```

You'll see the agent:

1. delete a page,
2. drop a table,
3. send an email,
4. force-push a branch,

and then a single `unwind undo` restore the three reversible actions while honestly flagging the email as unrecoverable. See the [demo narrative](index.md#the-20-second-demo) for the full story.

## 5. Inspect and reverse actions

Everything an agent did through Unwind is in the durable undo log. Two commands do the work:

```bash
# What happened, and what's still reversible?
unwind history
```

```text
#  when       server      tool            class  status   fidelity              expires
7  16:04:11   notion      create_page     R2     active   semantic              —
6  16:04:12   sqlite      drop_table      R1     active   exact                 —
5  16:04:14   gmail       send_email      R3     active   acceptable-approx.    in 24s
4  16:04:15   git         push --force    R2     active   semantic              —
```

```bash
# Reverse the last N actions across every connected server, in reverse order.
unwind undo            # undo the most recent action
unwind undo --last 4   # undo the last four
unwind undo --id 6     # undo a specific log entry
```

Each reversed action reports its outcome as `restored`, `approximately_restored`, or `could_not_undo` with a reason and any [residue](concepts/compensation.md) that undo could not remove.

!!! warning "Reversibility has a half-life"
    Notice the `expires` column. Many actions are only reversible for a window — an email recall lasts seconds, trash retention lasts days, a payment can be voided only before settlement. Unwind models this [reversibility half-life](concepts/taxonomy.md#reversibility-half-life-a-novel-dimension) and expires undo-log entries accordingly. `unwind undo` on an expired entry returns `could_not_undo`, never a false success.

## 6. Talk to Unwind from the agent

Unwind is itself an MCP server. The agent can reason about and reverse its *own* actions through five tools — `unwind.preview`, `unwind.undo`, `unwind.explain_risk`, `unwind.history`, `unwind.checkpoint`. See [Agentic tools](agentic-tools.md).

## Next steps

- Understand *why* a tool got its class → [Reversibility taxonomy](concepts/taxonomy.md)
- Understand *how* inverses are found → [Compensation synthesis](concepts/compensation.md)
- Embed Unwind in a gateway or wire more clients → [Integrations](integrations.md)
- Something not working? → [FAQ](faq.md)
