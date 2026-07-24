---
title: Unwind — a reversibility layer for agentic tool use
---

# Unwind

**Unwind sits between any AI agent and any MCP server, works out which actions can be taken back, quietly takes back the ones that go wrong, and interrupts you only for the ones that truly can't be undone.**

Unwind is a *transparent* [Model Context Protocol](https://modelcontextprotocol.io) proxy. It speaks MCP to your client and MCP to each upstream server, so **no client and no server needs modification**. On the way through, it infers a reversibility class for every tool call, synthesises a concrete inverse where one exists, records the action in a durable cross-server undo log, and reserves the human confirmation prompt for the small minority of actions that genuinely cannot be undone.

!!! quote "The thesis — keep this in mind on every page"
    Human oversight of agents is failing because approval prompts are **undifferentiated**. They are undifferentiated because nothing in the stack knows which actions are **reversible**. Reversibility inference is the missing primitive — not a convenience feature, but the enabling mechanism that makes human oversight work at all.

    Unwind supplies that primitive, then exploits it twice: it **auto-allows the reversible majority** (with a real undo log behind it) and **reserves interruption for the irreversible minority** — so the approval signal stops being noise and starts meaning something.

## This is not "an undo button"

The undo button is the demo. The thesis is that reversibility is a *classification* problem, and that solving it is what makes every downstream safety decision possible. Every feature in Unwind either **sharpens that classification** or **exploits it**. Anything that does neither is out of scope — including auth, RBAC, rate limiting and secret scanning, which are the job of the [many excellent MCP gateways](integrations.md) Unwind runs alongside.

## The 20-second demo

The demo narrative is deliberately blunt and deliberately honest:

1. An agent, mid-task, **deletes a page**, **drops a table**, **sends an email**, and **force-pushes** a branch.
2. You type `unwind undo`.
3. Three of those four actions are **restored** — the page, the table, and the branch. Unwind captured pre-state before each mutation and had a validated inverse.
4. The fourth — the email — comes back marked **"couldn't be undone — here's why I should have asked first."**

That last line is the whole thesis in one screenshot, and it is honest: the email already left. Unwind does not pretend otherwise. It [grades fidelity](concepts/compensation.md), never claims a false undo, and always reports **residue** — the notifications, audit entries and version bumps an undo cannot erase.

## Install in one line

=== "pip"

    ```bash
    pip install unwind-mcp
    ```

=== "uvx (no install)"

    ```bash
    uvx unwind-mcp run -- npx -y @modelcontextprotocol/server-filesystem /work
    ```

=== "npm (stdio shim)"

    ```bash
    npm install -g unwind-mcp
    ```

=== "docker"

    ```bash
    docker run --rm -i ghcr.io/bhaskargurram-ai/unwind:latest \
      run -- npx -y @modelcontextprotocol/server-filesystem /work
    ```

Then wrap any upstream server — Unwind is the command, your existing server is the payload:

```bash
unwind run -- npx -y @modelcontextprotocol/server-filesystem /work
```

Point your client at `unwind run -- <your server>` instead of `<your server>`, and everything keeps working — Unwind is invisible until something needs undoing. Full client configs (Claude Desktop/Code, Cursor, VS Code, Cline, Windsurf, Goose, Zed, n8n) are in the [Quickstart](quickstart.md).

## Why it matters

- **Confirmation fatigue is a security bug, not a UX annoyance.** When approvals come too often, people develop an approve-approve-approve reflex, and a prompt injection that triggers an approval the user clicks through has bypassed human oversight entirely. Unwind cuts the interruption rate so the prompts that remain actually get read.
- **MCP tool schemas carry no consequence semantics.** The protocol provides no separation between `read_file` and `delete_project`, and the overwhelming majority of tool descriptions carry no consequence warning. Unwind infers the missing metadata.
- **Recovery is the one thing no gateway does.** Every serious MCP gateway is a *preventive* control — allow or block. Not one performs recovery. Unwind is the reversibility layer that runs standalone *or* [as middleware inside any of them](integrations.md).

## Where to go next

<div class="grid cards" markdown>

-   :material-school: **Understand the ideas**

    ---

    The [R0–R4 taxonomy](concepts/taxonomy.md), [compensation synthesis](concepts/compensation.md), and the [proxy architecture](concepts/architecture.md).

-   :material-rocket-launch: **Get it running**

    ---

    [Quickstart](quickstart.md) — install, wrap a server, run the demo, try `unwind history` and `unwind undo`.

-   :material-robot: **Let the agent reverse itself**

    ---

    The [agentic tool surface](agentic-tools.md): `unwind.preview`, `unwind.undo`, `unwind.explain_risk`, `unwind.history`, `unwind.checkpoint`.

-   :material-table-search: **Browse the ecosystem**

    ---

    The public [reversibility index](reversibility-index.md) — popular MCP servers rated by R-class, blast radius and half-life.

-   :material-chart-box: **See how it's measured**

    ---

    [ReversiBench](benchmark.md) — server-disjoint splits, live-sandbox fidelity, and the headline Critical Error Rate.

-   :material-file-document: **Read the research**

    ---

    The [paper](paper.md) — taxonomy, benchmark, synthesiser, and calibrated escalation.

</div>

---

*Unwind is an open-source research project. The name is the stack-unwinding metaphor — compensations execute in reverse order, exactly like unwinding a call stack. (Originally scoped as "Saga"; renamed because [SagaLLM](paper.md) already occupies that name in this conceptual space.)*
