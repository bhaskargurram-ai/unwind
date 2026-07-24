---
title: Reddit (draft)
---

# Reddit (draft)

!!! warning "Launch-day draft — not published yet"
    This is a **draft**. Honest tone, no fabricated numbers, lead with the thesis and the demo. Suitable for r/LocalLLaMA, r/mcp, r/ArtificialIntelligence, r/programming. Trim per subreddit norms; drop the demo GIF inline.

---

**Title:** I built Unwind: a transparent MCP proxy that figures out which agent actions can be undone (and only interrupts you for the ones that can't)

**Body:**

I kept running into the same thing wiring agents up to MCP servers: the approval prompt is the same whether the agent wants to read a file or delete everything. When you get that prompt constantly you stop reading it — you just click "allow." That reflex is the actual failure mode of human oversight, and it's why a prompt injection that triggers one approval you rubber-stamp is game over.

The root cause is that MCP tool schemas have no idea which actions are reversible. There's no protocol-level distinction between a harmless read and a permanent delete.

So **Unwind** tries to fix the missing piece: it sits transparently between your client and any MCP server, classifies each tool call on a reversibility scale (R0 nullipotent → R4 irreversible), works out a concrete "inverse" call where one exists, keeps a durable undo log across servers, and only interrupts you for the genuinely irreversible stuff.

**The honest demo:** agent deletes a page, drops a table, sends an email, force-pushes → you type `unwind undo` → three come back, and the email comes back flagged *"couldn't be undone — here's why I should have asked first."* Unwind never fakes an undo. It grades how faithfully something was restored (exact / semantic / approximation / failed) and lists the residue it couldn't erase (notifications that fired, audit entries, version bumps).

**Setup is one line** — wrap your existing server with `unwind run -- <server>` and point your client at it. Nothing in the client or server changes, unknown methods pass straight through, and there's a `--passthrough-only` panic switch if you ever suspect it's interfering.

A couple of ideas I think are the interesting bits:

- Reversibility depends on the *environment*, not just the tool. `write_file` is reversible on a git-backed folder and irreversible on a plain one — so the class is recomputed per environment.
- Reversibility has a **half-life**. Email recall is ~30 seconds, trash is ~30 days, a payment can be voided only before it settles. The undo log expires so it can't lie to you later.

**What it's deliberately NOT:** a gateway. Auth/RBAC/rate-limiting/secret-scanning is a crowded space (Docker MCP Gateway, ToolHive, agentgateway, ContextForge…) and I'm staying out of it — Unwind embeds *inside* those as middleware. They prevent; Unwind recovers.

It's open source (Apache-2.0), Python with a Node shim, and there's a benchmark that runs real forward+inverse pairs in a sandbox and diffs state so fidelity is measured, not claimed. Results are still coming — I'd rather post TBD than a fake table.

Repo + docs + demo GIF in the comments. Would genuinely love to hear where you think the classification or the auto-generated inverses will fall over — that's the risky part.
