---
title: Show HN (draft)
---

# Show HN (draft)

!!! warning "Launch-day draft — not published yet"
    This is a **draft** for launch day. No hype, no fabricated numbers. Fill any bracketed placeholder only with a real, reproducible figure from `make results`; otherwise leave it as TBD or cut it. Lead with the thesis and the demo.

---

**Title:** Show HN: Unwind – a transparent MCP proxy that infers which agent actions can be undone

**URL:** https://github.com/bhaskargurram-ai/unwind

**Text:**

Hi HN. I've been building Unwind, a reversibility layer for agentic tool use.

The problem I kept hitting: human oversight of AI agents is failing because approval prompts are undifferentiated. Your client asks "allow this tool call?" the same way whether the agent is about to read a file or delete a production table. When approvals come that often, everyone develops an approve-approve-approve reflex — which is a documented *security* problem, not just an annoyance, because a prompt injection that triggers an approval you click through has bypassed oversight entirely.

The reason the prompts are undifferentiated is that nothing in the stack knows which actions are reversible. MCP tool schemas carry no consequence semantics — there's no protocol-level difference between `read_file` and `delete_project`. So Unwind tries to supply the missing primitive: it infers a reversibility class for every tool call (R0 nullipotent … R4 irreversible), synthesises a concrete inverse operation where one exists, keeps a durable cross-server undo log, and only interrupts you for the actions that genuinely can't be taken back.

It's a transparent proxy — one line in your `mcp.json`, wraps any existing server, no client or server changes. Anything it doesn't understand is forwarded untouched, and there's a `--passthrough-only` panic switch.

The demo, honestly: an agent deletes a page, drops a table, sends an email, and force-pushes. You type `unwind undo`. Three come back. The email comes back marked *"couldn't be undone — here's why I should have asked first."* That last line is the whole point — Unwind grades rollback fidelity (exact / semantic / approximation / failed), reports residue an undo can't erase, and never claims a false undo. A false undo guarantee would just manufacture the auto-approve reflex I'm trying to cure.

A few design choices I'd love feedback on:

- Reversibility is a function of *(tool, environment)*, not the tool alone. `write_file` is reversible on a git-backed tree and irreversible on a versionless one, so classes are re-derived per environment.
- Reversibility has a *half-life*: email recall ~30s, trash retention ~30 days, payment void-before-settlement. The undo log expires accordingly, so it can't hand you a stale, false undo.
- Confirmations ride MCP's native elicitation channel, so they work in any compliant client with no custom UI.

What Unwind is **not**: a gateway. Auth, RBAC, rate limiting, secret scanning, container isolation — that space is saturated (Docker MCP Gateway, ToolHive, agentgateway, ContextForge, …) and permanently out of scope. Unwind embeds *inside* those as middleware. They prevent; Unwind recovers.

There's also a benchmark (ReversiBench) with server-disjoint splits and a live sandbox that actually runs forward+inverse and diffs state, so fidelity is measured rather than asserted. Numbers are still landing — I'd rather show TBD than fake a table.

Repo, docs and the 20-second demo GIF are in the README. Happy to answer anything, especially where the classification or compensation approach is likely to break.
